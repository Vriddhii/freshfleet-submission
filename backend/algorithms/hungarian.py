"""
Hungarian Algorithm — "Global Batch Optimizer"

Strategy:
1. Build a cost matrix where cost[i][j] = operational cost minus
   delivered value for assigning truck i to order j.
2. Set cost to infinity (999999) for invalid pairings
   (hard constraint violations).
3. Run scipy's linear_sum_assignment to find the one-to-one
   matching that minimizes total cost across the entire fleet.
4. Filter out any pairing where cost was infinity (leave those
   orders unassigned).

The key insight: the cost matrix uses (operational_cost - delivered_value)
so that high-value orders actively attract trucks. Without this,
Hungarian would just minimize distance and ignore the fact that
a $1500 P1 salmon order is worth far more than a $150 P4 canned
goods order.

Strengths: Mathematically optimal for batch one-to-one assignment.
Weakness: Needs all orders upfront, can't handle streaming.
Quality depends on how well the cost matrix captures the real
tradeoffs (especially nonlinear P1 decay).
"""

import time
import numpy as np
from scipy.optimize import linear_sum_assignment
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


# Cost for invalid assignments — effectively "impossible"
INVALID_COST = 999999.0


def _build_cost_matrix(
    trucks: list[Truck],
    orders: list[Order],
    current_time,
) -> np.ndarray:
    """
    Build the cost matrix for the Hungarian algorithm.

    cost[i][j] = how "bad" it is to assign truck i to order j.
    Lower is better. Invalid pairings get INVALID_COST.

    The cost is: negative delivered value + operational cost.
    This means the algorithm tries to MAXIMIZE total delivered
    value while MINIMIZING operational cost. A high-value P1
    order gets a very negative (attractive) cost, pulling trucks
    toward it even if the distance is longer.

    Without the negative value term, Hungarian would just minimize
    distance and ignore the fact that P1 seafood orders are worth
    $1500 while P4 canned goods are worth $150.
    """
    num_trucks = len(trucks)
    num_orders = len(orders)

    cost_matrix = np.full((num_trucks, num_orders), INVALID_COST)

    for i, truck in enumerate(trucks):
        for j, order in enumerate(orders):
            # Calculate timing
            dist_to_pickup = calculate_distance(
                truck.location, order.pickup_location
            )
            time_to_pickup = calculate_travel_time(
                dist_to_pickup, truck.speed_kmh
            )

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

            # Check hard constraints
            valid, reason = is_valid_assignment(
                truck, order, current_time,
                est_pickup, est_delivery, transit_min,
            )

            if not valid:
                continue  # leave as INVALID_COST

            # Calculate the cost components
            operational_cost = calculate_cost(total_dist)
            delivered_value = calculate_delivered_value(
                order.base_value,
                order.perishability_tier,
                transit_min,
                order.max_transit_minutes,
            )

            # Cost = operational cost - delivered value
            # Negative delivered value makes high-value orders attractive
            # Hungarian minimizes total cost, so it will prefer assignments
            # that maximize value and minimize distance
            cost_matrix[i][j] = operational_cost - delivered_value

    return cost_matrix


def run_hungarian(scenario: Scenario) -> AlgorithmResult:
    """
    Run the Hungarian (Kuhn-Munkres) allocation algorithm.

    Returns an AlgorithmResult with assignments, unassigned orders,
    and performance metrics.
    """
    start_time = time.time()

    orders = scenario.orders
    trucks = scenario.trucks

    current_time = min(o.order_time for o in orders)

    # Build the cost matrix
    cost_matrix = _build_cost_matrix(trucks, orders, current_time)

    # Run the Hungarian algorithm
    # It returns (row_indices, col_indices) — the optimal pairing
    row_indices, col_indices = linear_sum_assignment(cost_matrix)

    assignments = []
    assigned_order_ids = set()

    for row, col in zip(row_indices, col_indices):
        # Skip invalid pairings (cost was set to INVALID_COST)
        if cost_matrix[row][col] >= INVALID_COST:
            continue

        truck = trucks[row]
        order = orders[col]

        # Recalculate timing for the assignment
        dist_to_pickup = calculate_distance(
            truck.location, order.pickup_location
        )
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

        delivered_value = calculate_delivered_value(
            order.base_value,
            order.perishability_tier,
            transit_min,
            order.max_transit_minutes,
        )
        cost = calculate_cost(total_dist)

        explanation = (
            f"Globally optimal assignment. {truck.id} to {order.id} "
            f"({order.perishability_tier}, {order.cargo_description}). "
            f"Cost matrix value: {cost_matrix[row][col]:.1f} "
            f"(distance cost: ${cost:.0f}, "
            f"delivered value: ${delivered_value:.0f}). "
            f"Transit: {transit_min:.0f}min."
        )

        assignment = Assignment(
            truck_id=truck.id,
            order_id=order.id,
            estimated_pickup_time=est_pickup,
            estimated_delivery_time=est_delivery,
            transit_minutes=round(transit_min, 1),
            delivered_value=round(delivered_value, 2),
            cost=round(cost, 2),
            explanation=explanation,
        )
        assignments.append(assignment)
        assigned_order_ids.add(order.id)

    # Find unassigned orders
    all_order_ids = {o.id for o in orders}
    unassigned_order_ids = sorted(all_order_ids - assigned_order_ids)

    # Calculate metrics
    computation_ms = round((time.time() - start_time) * 1000, 2)
    metrics = calculate_fleet_score(assignments, orders)
    metrics["computation_time_ms"] = computation_ms

    return AlgorithmResult(
        algorithm="hungarian",
        assignments=assignments,
        unassigned_order_ids=unassigned_order_ids,
        metrics=metrics,
    )