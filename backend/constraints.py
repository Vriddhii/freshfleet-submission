"""
FreshFleet Constraint Checker

All hard constraints that must NEVER be violated.
If any check returns False, the assignment is invalid.
"""

from datetime import datetime
from models import Truck, Order, Location
from scoring import calculate_distance, calculate_travel_time


def check_capacity(truck: Truck, order: Order) -> bool:
    """Truck must have enough remaining capacity for the order's cargo."""
    remaining = truck.capacity_kg - truck.current_load_kg
    return remaining >= order.weight_kg


def check_availability(
    truck: Truck,
    estimated_start: datetime,
    estimated_end: datetime,
) -> bool:
    """
    The entire delivery (pickup to dropoff) must fall within
    the truck driver's shift window.
    """
    return (
        estimated_start >= truck.availability_start
        and estimated_end <= truck.availability_end
    )


def check_time_window(
    estimated_delivery_time: datetime,
    order: Order,
) -> bool:
    """
    Delivery must arrive before the window closes.
    Arriving early is fine — the truck just waits or the customer
    accepts it. Arriving LATE is the problem.
    """
    return estimated_delivery_time <= order.delivery_window_end


def check_location_feasibility(
    truck: Truck,
    order: Order,
    current_time: datetime,
) -> bool:
    """
    Can the truck physically reach the pickup location and then
    the dropoff location before the delivery window closes?
    """
    # Time to drive from truck's current location to pickup
    dist_to_pickup = calculate_distance(truck.location, order.pickup_location)
    time_to_pickup = calculate_travel_time(dist_to_pickup, truck.speed_kmh)

    # Time to drive from pickup to dropoff
    dist_pickup_to_dropoff = calculate_distance(
        order.pickup_location, order.dropoff_location
    )
    time_pickup_to_dropoff = calculate_travel_time(
        dist_pickup_to_dropoff, truck.speed_kmh
    )

    # Total minutes from now until delivery
    total_minutes = time_to_pickup + time_pickup_to_dropoff

    # Estimated delivery time
    from datetime import timedelta
    earliest_departure = max(current_time, order.order_time)
    estimated_delivery = earliest_departure + timedelta(minutes=total_minutes)

    return estimated_delivery <= order.delivery_window_end


def check_spoilage_cutoff(
    transit_minutes: float,
    order: Order,
) -> bool:
    """
    If the cargo would lose 90%+ of its value by the time it's delivered,
    the assignment is forbidden. Don't deliver rotten fish.
    """
    from scoring import calculate_delivered_value

    delivered = calculate_delivered_value(
        order.base_value,
        order.perishability_tier,
        transit_minutes,
        order.max_transit_minutes,
    )
    # Must retain more than 10% of value
    return delivered > (order.base_value * 0.10)


def is_valid_assignment(
    truck: Truck,
    order: Order,
    current_time: datetime,
    estimated_pickup_time: datetime,
    estimated_delivery_time: datetime,
    transit_minutes: float,
) -> tuple[bool, str]:
    """
    Run ALL hard constraint checks.
    Returns (is_valid, reason) — reason explains why it failed if invalid.
    """
    if not check_capacity(truck, order):
        return False, f"Capacity: truck has {truck.capacity_kg - truck.current_load_kg:.1f}kg free, order needs {order.weight_kg:.1f}kg"

    if not check_availability(truck, estimated_pickup_time, estimated_delivery_time):
        return False, f"Availability: delivery falls outside truck shift ({truck.availability_start.strftime('%H:%M')}-{truck.availability_end.strftime('%H:%M')})"

    if not check_time_window(estimated_delivery_time, order):
        return False, f"Time window: delivery at {estimated_delivery_time.strftime('%H:%M')} outside window ({order.delivery_window_start.strftime('%H:%M')}-{order.delivery_window_end.strftime('%H:%M')})"

    if not check_location_feasibility(truck, order, current_time):
        return False, "Location: truck cannot reach destination before window closes"

    if not check_spoilage_cutoff(transit_minutes, order):
        return False, f"Spoilage: {order.perishability_tier} cargo would lose >90% value ({transit_minutes:.0f}min transit, max {order.max_transit_minutes:.0f}min)"

    return True, "All constraints satisfied"