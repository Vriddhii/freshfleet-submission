"""
FreshFleet Scoring Engine

Handles all the math:
- Distance and travel time between locations
- Perishability decay (how much value cargo loses over time)
- Fleet Score (composite metric to compare algorithms)
- Operational cost calculation
"""

import math
from models import Location, Assignment, Order, TIER_CONFIG


# ──────────────────────────────────────────────
# Distance & Travel Time
# ──────────────────────────────────────────────

def calculate_distance(loc1: Location, loc2: Location) -> float:
    """Euclidean distance in km between two grid points."""
    return math.sqrt((loc1.x - loc2.x) ** 2 + (loc1.y - loc2.y) ** 2)


def calculate_travel_time(distance_km: float, speed_kmh: float) -> float:
    """Travel time in minutes."""
    if speed_kmh <= 0:
        return float("inf")
    return (distance_km / speed_kmh) * 60


# ──────────────────────────────────────────────
# Perishability Decay
# ──────────────────────────────────────────────

def calculate_delivered_value(
    base_value: float,
    tier: str,
    transit_minutes: float,
    max_transit_minutes: float,
) -> float:
    """
    Calculate how much the cargo is worth after transit.

    If delivered within the max transit time → full value.
    If delivered late → value decays based on tier:
        P1: exponential (halves every 15 min overtime)
        P2: linear (loses 10% per 15 min overtime)
        P3: slow linear (loses 5% per 30 min overtime)
        P4: negligible (loses 2% per 60 min overtime)
    """
    if transit_minutes <= max_transit_minutes:
        return base_value

    overtime = transit_minutes - max_transit_minutes

    if tier == "P1":
        # Exponential decay: halves every 15 minutes past deadline
        return base_value * (0.5 ** (overtime / 15))

    elif tier == "P2":
        # Linear: loses 10% of value per 15 min overtime
        factor = max(0.0, 1.0 - 0.10 * (overtime / 15))
        return base_value * factor

    elif tier == "P3":
        # Slow linear: loses 5% per 30 min overtime
        factor = max(0.0, 1.0 - 0.05 * (overtime / 30))
        return base_value * factor

    elif tier == "P4":
        # Negligible: loses 2% per 60 min overtime
        factor = max(0.0, 1.0 - 0.02 * (overtime / 60))
        return base_value * factor

    return base_value  # fallback


# ──────────────────────────────────────────────
# Operational Cost
# ──────────────────────────────────────────────

COST_PER_KM = 1.50  # fuel + wear, dollars per km

def calculate_cost(distance_km: float) -> float:
    """Operational cost for a delivery based on total distance driven."""
    return distance_km * COST_PER_KM


# ──────────────────────────────────────────────
# Fleet Score (composite metric)
# ──────────────────────────────────────────────

def calculate_fleet_score(
    assignments: list[Assignment],
    all_orders: list[Order],
) -> dict:
    """
    Compute the Fleet Score and all comparison metrics.

    Fleet Score = sum(delivered_value - cost) / total_possible_value

    A perfect 1.0 means all orders delivered fresh at zero cost (impossible).
    Real scores range from ~0.3 to ~0.7.
    """
    total_possible_value = sum(o.base_value for o in all_orders)

    if total_possible_value == 0:
        return _empty_metrics(all_orders)

    # Aggregate metrics from assignments
    total_delivered_value = sum(a.delivered_value for a in assignments)
    total_cost = sum(a.cost for a in assignments)
    total_value_lost = total_possible_value - total_delivered_value
    transit_times = [a.transit_minutes for a in assignments]

    # Calculate total distance from cost (reverse the cost formula)
    total_distance_km = total_cost / COST_PER_KM if COST_PER_KM > 0 else 0

    # P1 fulfillment
    all_p1_ids = {o.id for o in all_orders if o.perishability_tier == "P1"}
    fulfilled_p1_ids = {a.order_id for a in assignments if a.order_id in all_p1_ids}
    p1_fulfilled_pct = (
        (len(fulfilled_p1_ids) / len(all_p1_ids) * 100) if all_p1_ids else 100.0
    )

    # Fleet score
    net_value = total_delivered_value - total_cost
    fleet_score = max(0.0, net_value / total_possible_value)

    # Worst-case decay percentage
    worst_decay_pct = 0.0
    for a in assignments:
        order = next((o for o in all_orders if o.id == a.order_id), None)
        if order and order.base_value > 0:
            decay_pct = (1 - a.delivered_value / order.base_value) * 100
            worst_decay_pct = max(worst_decay_pct, decay_pct)

    return {
        "fleet_score": round(fleet_score, 4),
        "total_delivered_value": round(total_delivered_value, 2),
        "total_value_lost": round(total_value_lost, 2),
        "total_cost": round(total_cost, 2),
        "orders_fulfilled": len(assignments),
        "total_orders": len(all_orders),
        "p1_fulfilled_pct": round(p1_fulfilled_pct, 1),
        "avg_transit_minutes": round(
            sum(transit_times) / len(transit_times), 1
        ) if transit_times else 0.0,
        "total_distance_km": round(total_distance_km, 1),
        "worst_decay_pct": round(worst_decay_pct, 1),
    }


def _empty_metrics(all_orders: list[Order]) -> dict:
    """Return zeroed metrics when there's nothing to score."""
    return {
        "fleet_score": 0.0,
        "total_delivered_value": 0.0,
        "total_value_lost": 0.0,
        "total_cost": 0.0,
        "orders_fulfilled": 0,
        "total_orders": len(all_orders),
        "p1_fulfilled_pct": 0.0,
        "avg_transit_minutes": 0.0,
        "total_distance_km": 0.0,
        "worst_decay_pct": 0.0,
    }