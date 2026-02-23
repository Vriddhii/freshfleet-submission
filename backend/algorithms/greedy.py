"""
Greedy Algorithm — "Most Urgent First, Nearest Truck"

Strategy:
1. Sort all orders by urgency (P1 first, then P2, P3, P4).
   Within the same tier, earlier deadlines go first.
2. For each order, find all available trucks that pass
   every hard constraint.
3. From those, pick the nearest truck to the pickup location.
4. Assign it and remove the truck from the available pool.
5. If no valid truck exists, the order goes unassigned.

Strengths: Fast, simple, handles streaming naturally.
Weakness: Locally optimal but globally blind — might waste
a nearby truck on a cheap order when it was needed for an
expensive one later.
"""

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
import time


# Tier urgency order: P1 is most urgent (sorted first)
TIER_URGENCY = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}


def _sort_orders_by_urgency(orders: list[Order]) -> list[Order]:
    """
    Sort orders so the most urgent come first.
    Primary sort: tier (P1 before P2 before P3 before P4)
    Secondary sort: earliest deadline first (tighter window = more urgent)
    """
    return sorted(
        orders,
        key=lambda o: (TIER_URGENCY[o.perishability_tier], o.delivery_window_end),
    )


def _estimate_times(truck: Truck, order: Order, current_time):
    """
    Calculate the key timestamps for a truck-order pairing:
    - When the truck arrives at pickup
    - When the truck arrives at dropoff
    - Total transit time (pickup to dropoff)
    - Total distance driven
    """
    # Distance from truck's location to the pickup
    dist_to_pickup = calculate_distance(truck.location, order.pickup_location)
    time_to_pickup = calculate_travel_time(dist_to_pickup, truck.speed_kmh)

    # Distance from pickup to dropoff
    dist_pickup_to_dropoff = calculate_distance(
        order.pickup_location, order.dropoff_location
    )
    time_pickup_to_dropoff = calculate_travel_time(
        dist_pickup_to_dropoff, truck.speed_kmh
    )

    # Truck can't depart before the order is placed
    earliest_departure = max(current_time, order.order_time)

    # Timestamps
    estimated_pickup_time = earliest_departure + timedelta(minutes=time_to_pickup)
    estimated_delivery_time = estimated_pickup_time + timedelta(
        minutes=time_pickup_to_dropoff
    )

    # Transit = just the pickup-to-dropoff leg (this is what decay cares about)
    transit_minutes = time_pickup_to_dropoff

    # Total distance = both legs
    total_distance = dist_to_pickup + dist_pickup_to_dropoff

    return (
        estimated_pickup_time,
        estimated_delivery_time,
        transit_minutes,
        total_distance,
    )


def run_greedy(scenario: Scenario) -> AlgorithmResult:
    """
    Run the greedy allocation algorithm.

    Returns an AlgorithmResult with assignments, unassigned orders,
    and performance metrics.
    """
    start_time = time.time()

    orders = scenario.orders
    trucks = scenario.trucks

    # Use the earliest order time as "now" for scheduling
    current_time = min(o.order_time for o in orders)

    # Sort orders by urgency
    sorted_orders = _sort_orders_by_urgency(orders)

    # Track which trucks are still available
    available_truck_ids = {t.id for t in trucks}
    truck_lookup = {t.id: t for t in trucks}

    assignments = []
    unassigned_order_ids = []

    for order in sorted_orders:
        best_truck = None
        best_distance = float("inf")
        best_times = None

        # Try every available truck
        for truck_id in available_truck_ids:
            truck = truck_lookup[truck_id]

            # Calculate timing for this pairing
            (
                est_pickup,
                est_delivery,
                transit_min,
                total_dist,
            ) = _estimate_times(truck, order, current_time)

            # Check all hard constraints
            valid, reason = is_valid_assignment(
                truck, order, current_time, est_pickup, est_delivery, transit_min
            )

            if not valid:
                continue

            # Among valid trucks, pick the nearest one
            dist_to_pickup = calculate_distance(
                truck.location, order.pickup_location
            )
            if dist_to_pickup < best_distance:
                best_distance = dist_to_pickup
                best_truck = truck
                best_times = (est_pickup, est_delivery, transit_min, total_dist)

        if best_truck is not None:
            est_pickup, est_delivery, transit_min, total_dist = best_times

            # Calculate delivered value after decay
            delivered_value = calculate_delivered_value(
                order.base_value,
                order.perishability_tier,
                transit_min,
                order.max_transit_minutes,
            )

            # Calculate operational cost
            cost = calculate_cost(total_dist)

            # Generate explanation
            explanation = (
                f"Assigned {best_truck.id} (nearest valid truck, "
                f"{best_distance:.1f}km to pickup) to {order.id} "
                f"({order.perishability_tier}, {order.cargo_description}). "
                f"Transit: {transit_min:.0f}min, "
                f"Delivered value: ${delivered_value:.0f}/${order.base_value:.0f}."
            )

            assignment = Assignment(
                truck_id=best_truck.id,
                order_id=order.id,
                estimated_pickup_time=est_pickup,
                estimated_delivery_time=est_delivery,
                transit_minutes=round(transit_min, 1),
                delivered_value=round(delivered_value, 2),
                cost=round(cost, 2),
                explanation=explanation,
            )
            assignments.append(assignment)

            # Remove truck from available pool
            available_truck_ids.remove(best_truck.id)
        else:
            unassigned_order_ids.append(order.id)

    # Calculate metrics
    computation_ms = round((time.time() - start_time) * 1000, 2)
    metrics = calculate_fleet_score(assignments, orders)
    metrics["computation_time_ms"] = computation_ms

    return AlgorithmResult(
        algorithm="greedy",
        assignments=assignments,
        unassigned_order_ids=unassigned_order_ids,
        metrics=metrics,
    )