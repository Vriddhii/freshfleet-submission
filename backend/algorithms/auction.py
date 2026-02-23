"""
Decay-Aware Priority Auction — "Smart Urgency with Opportunity Cost"

Strategy:
1. Score every order by urgency = base_value × tier_weight × (1 / minutes_until_deadline).
   Orders that are valuable AND decaying fast AND running out of time rank highest.
2. Sort orders by urgency (highest first).
3. For each order, every eligible truck "bids" with a score that combines:
   - Proximity (closer = better bid)
   - Opportunity cost penalty (if this truck is the only one that can
     reach another high-urgency order, penalize using it here)
4. Best bid wins. Assign and remove truck from pool.

Strengths: Domain-aware, handles perishability tradeoffs that generic
algorithms miss. Produces good explanations. Protects scarce resources
for critical orders.
Weakness: Heuristic — no mathematical optimality guarantee. The
opportunity cost estimation is approximate (one step lookahead).
"""

import time
from datetime import timedelta
from models import Order, Truck, Assignment, AlgorithmResult, Scenario, TIER_CONFIG
from scoring import (
    calculate_distance,
    calculate_travel_time,
    calculate_delivered_value,
    calculate_cost,
    calculate_fleet_score,
)
from constraints import is_valid_assignment


def _calculate_urgency(order: Order, current_time) -> float:
    """
    Compute how urgently this order needs to be assigned.

    urgency = base_value × tier_weight × (1 / minutes_until_deadline)

    High value + high perishability + tight deadline = very urgent.
    Low value + P4 + hours of slack = not urgent at all.
    """
    tier_weight = TIER_CONFIG[order.perishability_tier]["tier_weight"]

    # Minutes until the delivery window closes
    minutes_until_deadline = max(
        1.0,  # avoid division by zero
        (order.delivery_window_end - current_time).total_seconds() / 60,
    )

    return order.base_value * tier_weight * (1.0 / minutes_until_deadline)


def _can_truck_serve(truck: Truck, order: Order, current_time) -> tuple[bool, dict]:
    """
    Check if a truck can validly serve an order.
    Returns (is_valid, timing_info) where timing_info has all the
    calculated values we need for bidding and assignment.
    """
    dist_to_pickup = calculate_distance(truck.location, order.pickup_location)
    time_to_pickup = calculate_travel_time(dist_to_pickup, truck.speed_kmh)

    dist_pickup_to_dropoff = calculate_distance(
        order.pickup_location, order.dropoff_location
    )
    time_pickup_to_dropoff = calculate_travel_time(
        dist_pickup_to_dropoff, truck.speed_kmh
    )

    earliest_departure = max(current_time, order.order_time)
    est_pickup = earliest_departure + timedelta(minutes=time_to_pickup)
    est_delivery = est_pickup + timedelta(minutes=time_pickup_to_dropoff)
    transit_min = time_pickup_to_dropoff
    total_dist = dist_to_pickup + dist_pickup_to_dropoff

    valid, reason = is_valid_assignment(
        truck, order, current_time, est_pickup, est_delivery, transit_min,
    )

    timing = {
        "dist_to_pickup": dist_to_pickup,
        "total_dist": total_dist,
        "transit_min": transit_min,
        "est_pickup": est_pickup,
        "est_delivery": est_delivery,
    }

    return valid, timing


def _calculate_opportunity_cost(
    truck: Truck,
    current_order: Order,
    remaining_orders: list[Order],
    available_trucks: list[Truck],
    current_time,
) -> float:
    """
    Estimate how much we'd lose by using this truck here.

    For each OTHER high-urgency order (P1 or P2) in the remaining list:
    - Count how many available trucks (besides this one) can serve it.
    - If this truck is the ONLY one that can serve it, the opportunity
      cost is high — we'd strand that order.
    - If many trucks can serve it, opportunity cost is low.

    Returns a penalty value (higher = worse to use this truck here).
    """
    penalty = 0.0
    other_trucks = [t for t in available_trucks if t.id != truck.id]

    # Only check high-urgency orders (P1 and P2) for opportunity cost
    # Checking all orders would be too slow and P3/P4 aren't worth protecting
    urgent_remaining = [
        o for o in remaining_orders
        if o.id != current_order.id
        and o.perishability_tier in ("P1", "P2")
    ]

    for other_order in urgent_remaining:
        # Can THIS truck serve the other order?
        can_this, _ = _can_truck_serve(truck, other_order, current_time)
        if not can_this:
            continue  # this truck can't serve it anyway, no loss

        # How many OTHER trucks can also serve it?
        other_capable_count = 0
        for other_truck in other_trucks:
            can_other, _ = _can_truck_serve(other_truck, other_order, current_time)
            if can_other:
                other_capable_count += 1

        # If this truck is the only option for that order, big penalty
        if other_capable_count == 0:
            # This truck is the SOLE option for a critical order
            urgency = _calculate_urgency(other_order, current_time)
            penalty += urgency * 2.0  # heavy penalty

        elif other_capable_count == 1:
            # Only one other truck can do it — risky to use this one
            urgency = _calculate_urgency(other_order, current_time)
            penalty += urgency * 0.5  # moderate penalty

        # If 2+ other trucks can serve it, no penalty — plenty of options

    return penalty


def run_auction(scenario: Scenario) -> AlgorithmResult:
    """
    Run the decay-aware priority auction algorithm.

    Returns an AlgorithmResult with assignments, unassigned orders,
    and performance metrics.
    """
    start_time = time.time()

    orders = scenario.orders
    trucks = scenario.trucks

    current_time = min(o.order_time for o in orders)

    # Calculate urgency for each order
    order_urgencies = [
        (order, _calculate_urgency(order, current_time))
        for order in orders
    ]

    # Sort by urgency (highest first)
    order_urgencies.sort(key=lambda x: x[1], reverse=True)

    # Track available trucks
    available_trucks = list(trucks)

    assignments = []
    unassigned_order_ids = []

    # Remaining orders (for opportunity cost calculation)
    remaining_orders = [o for o, _ in order_urgencies]

    for order, urgency in order_urgencies:
        # Remove this order from remaining list
        remaining_orders = [o for o in remaining_orders if o.id != order.id]

        if not available_trucks:
            unassigned_order_ids.append(order.id)
            continue

        # Each available truck "bids" for this order
        best_truck = None
        best_bid = float("-inf")
        best_timing = None
        best_explanation_parts = {}

        for truck in available_trucks:
            # Check if truck can serve this order
            valid, timing = _can_truck_serve(truck, order, current_time)
            if not valid:
                continue

            # Bid combines three factors:
            # 1. Proximity (closer = better)
            # 2. Value preservation (how much value this truck delivers)
            # 3. Opportunity cost (penalty if truck is needed elsewhere)

            dist_to_pickup = timing["dist_to_pickup"]

            # Proximity score: closer = higher bid
            proximity_score = 10.0 / max(0.5, dist_to_pickup)

            # Value score: how much of the cargo value does this truck preserve?
            # A faster truck delivering P1 preserves more value than a slow one
            delivered_val = calculate_delivered_value(
                order.base_value,
                order.perishability_tier,
                timing["transit_min"],
                order.max_transit_minutes,
            )
            # Normalize to 0-10 range based on preservation percentage
            value_score = (delivered_val / max(1, order.base_value)) * 10.0

            # Opportunity cost: penalty for using this truck here
            opp_cost = _calculate_opportunity_cost(
                truck, order, remaining_orders, available_trucks, current_time
            )

            bid = proximity_score + value_score - opp_cost

            if bid > best_bid:
                best_bid = bid
                best_truck = truck
                best_timing = timing
                best_explanation_parts = {
                    "proximity": round(proximity_score, 2),
                    "value_score": round(value_score, 2),
                    "opp_cost": round(opp_cost, 2),
                    "bid": round(bid, 2),
                    "dist": round(dist_to_pickup, 1),
                }

        if best_truck is not None:
            timing = best_timing

            delivered_value = calculate_delivered_value(
                order.base_value,
                order.perishability_tier,
                timing["transit_min"],
                order.max_transit_minutes,
            )
            cost = calculate_cost(timing["total_dist"])

            # Build detailed explanation
            parts = best_explanation_parts
            opp_note = ""
            if parts["opp_cost"] > 0:
                opp_note = (
                    f" Opportunity cost penalty: {parts['opp_cost']} "
                    f"(this truck is needed for other critical orders)."
                )

            explanation = (
                f"Auction winner: {best_truck.id} for {order.id} "
                f"({order.perishability_tier}, {order.cargo_description}). "
                f"Urgency score: {urgency:.1f}. "
                f"Bid: {parts['bid']} "
                f"(proximity: {parts['proximity']}, "
                f"value: {parts['value_score']}, "
                f"distance: {parts['dist']}km).{opp_note} "
                f"Transit: {timing['transit_min']:.0f}min, "
                f"Delivered value: ${delivered_value:.0f}/${order.base_value:.0f}."
            )

            assignment = Assignment(
                truck_id=best_truck.id,
                order_id=order.id,
                estimated_pickup_time=timing["est_pickup"],
                estimated_delivery_time=timing["est_delivery"],
                transit_minutes=round(timing["transit_min"], 1),
                delivered_value=round(delivered_value, 2),
                cost=round(cost, 2),
                explanation=explanation,
            )
            assignments.append(assignment)

            # Remove truck from available pool
            available_trucks = [t for t in available_trucks if t.id != best_truck.id]
        else:
            unassigned_order_ids.append(order.id)

    # Calculate metrics
    computation_ms = round((time.time() - start_time) * 1000, 2)
    metrics = calculate_fleet_score(assignments, orders)
    metrics["computation_time_ms"] = computation_ms

    return AlgorithmResult(
        algorithm="auction",
        assignments=assignments,
        unassigned_order_ids=unassigned_order_ids,
        metrics=metrics,
    )