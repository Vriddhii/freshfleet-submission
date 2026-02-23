"""
FreshFleet Data Generator

Generates realistic scenarios with trucks and orders
spread across a 20km x 20km city grid.

The scenario is designed with deliberate "scarcity zones" —
areas where multiple high-urgency P1 orders cluster but only
1-2 trucks are nearby. This forces algorithms to make hard
tradeoffs about which critical orders to prioritize.
"""

import math
import random
from datetime import datetime, timedelta
from models import Truck, Order, Location, Scenario, TIER_CONFIG

# Cargo templates by tier

CARGO_TEMPLATES = {
    "P1": [
        ("Fresh Atlantic Salmon, 24 fillets", 15.0, 1200.0),
        ("Sushi-grade Tuna, 10kg block", 10.0, 1800.0),
        ("Raw Oysters, 5 dozen", 8.0, 900.0),
        ("Fresh Dairy Milk, 40L", 42.0, 350.0),
        ("Live Lobsters, 12 count", 14.0, 1500.0),
    ],
    "P2": [
        ("Cut Flower Bouquets, 30 arrangements", 25.0, 750.0),
        ("Fresh Ground Beef, 50kg case", 50.0, 600.0),
        ("Prepared Sushi Platters, 20 trays", 18.0, 1100.0),
        ("Fresh Chicken Breasts, 40kg case", 40.0, 480.0),
        ("Marinated Lamb Shanks, 24 pieces", 30.0, 850.0),
        ("Fresh Pasta, 15kg artisan batch", 15.0, 420.0),
        ("Smoked Salmon Sides, 20 pieces", 12.0, 950.0),
    ],
    "P3": [
        ("Organic Strawberries, 40 punnets", 20.0, 320.0),
        ("Artisan Sourdough Loaves, 60 units", 35.0, 280.0),
        ("Farm Fresh Eggs, 50 dozen", 45.0, 400.0),
        ("Heirloom Tomatoes, 30kg crate", 30.0, 250.0),
        ("Fresh Herb Bundles, 100 packets", 10.0, 350.0),
        ("Seasonal Stone Fruit, 25kg box", 25.0, 200.0),
        ("Baked Croissants, 80 units", 16.0, 380.0),
        ("Mixed Salad Greens, 20kg", 20.0, 290.0),
        ("Wholesale Fruit Crate Pallet, 6 crates", 180.0, 650.0),
        ("Farmers Market Produce Bundle, bulk", 150.0, 500.0),
    ],
    "P4": [
        ("Canned Tomato Sauce, 100 tins", 60.0, 180.0),
        ("Dry Pasta Variety Pack, 80kg", 80.0, 150.0),
        ("Packaged Rice Crackers, 200 bags", 40.0, 220.0),
        ("Bottled Olive Oil, 48 bottles", 55.0, 400.0),
        ("Granola Bar Cases, 30 boxes", 35.0, 160.0),
        ("Bulk Canned Goods Pallet, 200 tins", 220.0, 350.0),
        ("Restaurant Dry Stock Resupply", 180.0, 280.0),
        ("Wholesale Rice Sacks, 10x25kg", 250.0, 420.0),
    ],
}


# City Zones
# We define zones to create realistic clustering.
# Each zone is a (center_x, center_y, radius) tuple.
# Points are generated within the radius of the center.

ZONES = {
    "downtown":      (10.0, 10.0, 3.0),   # city center, lots of restaurants
    "fish_wharf":    (2.0, 16.0, 2.0),     # near the docks, seafood pickups
    "industrial":    (17.0, 4.0, 2.5),     # warehouses, bulk goods
    "suburbs_north": (14.0, 17.0, 3.0),    # residential deliveries
    "suburbs_south": (6.0, 3.0, 3.0),      # residential deliveries
}


def _random_point_in_zone(zone_name: str) -> Location:
    """Generate a random point within a named zone."""
    cx, cy, radius = ZONES[zone_name]
    angle = random.uniform(0, 2 * math.pi)
    r = radius * random.uniform(0.0, 1.0) ** 0.5
    x = max(0.5, min(19.5, round(cx + r * math.cos(angle), 2)))
    y = max(0.5, min(19.5, round(cy + r * math.sin(angle), 2)))
    return Location(x=x, y=y)


def generate_scenario(
    num_trucks: int = 15,
    num_orders: int = 25,
    seed: int = 42,
) -> Scenario:
    """
    Generate a complete scenario with trucks and orders.

    The scenario has deliberate scarcity zones:
    - 5 P1 orders with pickups near fish_wharf (but only 2 trucks there)
    - Most trucks are in downtown and suburbs (far from the wharf)
    - This forces algorithms to decide: send a distant truck to save
      expensive seafood, or serve cheaper nearby orders instead?

    Truck count: 15 (default)
    Order count: 25 (default)
    Tier mix: 5 P1, 7 P2, 8 P3, 5 P4
    """
    random.seed(seed)

    base_time = datetime(2026, 2, 21, 6, 0, 0)
    trucks = _generate_trucks(num_trucks, base_time)
    orders = _generate_orders(num_orders, base_time)

    return Scenario(
        trucks=trucks,
        orders=orders,
        generated_at=datetime.now(),
    )


def _generate_trucks(num_trucks: int, base_time: datetime) -> list[Truck]:
    """
    Generate trucks with deliberate spatial distribution:
    - 2 trucks near fish_wharf (the P1 scarcity zone)
    - 4 trucks downtown
    - 4 trucks suburbs_north
    - 3 trucks suburbs_south
    - 2 trucks industrial
    
    This means 5 P1 orders compete for 2 nearby trucks.
    The other 3 P1 orders must be served by trucks driving
    from downtown or suburbs — if the algorithm is smart enough.
    """
    truck_zones = (
        ["fish_wharf"] * 2
        + ["downtown"] * 4
        + ["suburbs_north"] * 4
        + ["suburbs_south"] * 3
        + ["industrial"] * 2
    )

    # Adjust if num_trucks differs from 15
    truck_zones = truck_zones[:num_trucks]
    while len(truck_zones) < num_trucks:
        truck_zones.append(random.choice(list(ZONES.keys())))

    trucks = []
    for i, zone in enumerate(truck_zones):
        shift_offset = random.randint(0, 90)
        shift_start = base_time - timedelta(minutes=30) + timedelta(minutes=shift_offset)
        shift_length = random.uniform(8, 10)
        shift_end = shift_start + timedelta(hours=shift_length)

        truck = Truck(
            id=f"TRK-{i+1:02d}",
            location=_random_point_in_zone(zone),
            capacity_kg=random.choice([80, 100, 120, 150, 200, 250, 300]),
            current_load_kg=0.0,
            speed_kmh=round(random.uniform(30, 50), 1),
            availability_start=shift_start,
            availability_end=shift_end,
            status="available",
        )
        trucks.append(truck)

    return trucks


def _generate_orders(num_orders: int, base_time: datetime) -> list[Order]:
    """
    Generate orders with deliberate scarcity tension.

    Each order has a defined (tier, pickup_zone, dropoff_zone):
    - 5 P1 orders: all pickup from fish_wharf (5 orders, 2 trucks = scarcity)
    - 7 P2 orders: 2 compete at wharf, rest spread out
    - 8 P3 orders: spread across the city
    - 5 P4 orders: mostly industrial, low urgency
    """
    order_configs = [
        # ── P1: all pickup from wharf (scarcity zone) ──
        ("P1", "fish_wharf", "downtown"),
        ("P1", "fish_wharf", "suburbs_north"),
        ("P1", "fish_wharf", "downtown"),
        ("P1", "fish_wharf", "fish_wharf"),
        ("P1", "fish_wharf", "suburbs_south"),
        # ── P2: some near wharf (competing), rest spread ──
        ("P2", "fish_wharf", "downtown"),
        ("P2", "fish_wharf", "suburbs_north"),
        ("P2", "downtown", "suburbs_north"),
        ("P2", "downtown", "suburbs_south"),
        ("P2", "downtown", "downtown"),
        ("P2", "suburbs_north", "downtown"),
        ("P2", "suburbs_south", "downtown"),
        # ── P3: spread across city ──
        ("P3", "downtown", "suburbs_north"),
        ("P3", "downtown", "suburbs_south"),
        ("P3", "suburbs_north", "downtown"),
        ("P3", "suburbs_south", "industrial"),
        ("P3", "industrial", "downtown"),
        ("P3", "suburbs_north", "suburbs_south"),
        ("P3", "industrial", "suburbs_north"),
        ("P3", "downtown", "industrial"),
        # ── P4: mostly industrial, low urgency ──
        ("P4", "industrial", "downtown"),
        ("P4", "industrial", "suburbs_south"),
        ("P4", "industrial", "suburbs_north"),
        ("P4", "suburbs_south", "industrial"),
        ("P4", "downtown", "industrial"),
    ]

    # Adjust if num_orders differs from 25
    order_configs = order_configs[:num_orders]
    while len(order_configs) < num_orders:
        tier = random.choices(
            ["P1", "P2", "P3", "P4"], weights=[0.2, 0.3, 0.3, 0.2]
        )[0]
        zones = list(ZONES.keys())
        order_configs.append((tier, random.choice(zones), random.choice(zones)))

    orders = []
    for i, (tier, pickup_zone, dropoff_zone) in enumerate(order_configs):
        cargo_name, weight, value = random.choice(CARGO_TEMPLATES[tier])

        # Add randomness to weight and value
        weight = round(weight * random.uniform(0.8, 1.2), 1)
        value = round(value * random.uniform(0.7, 1.3), 2)

        # Order placed between 6:00 and 8:00 AM
        order_offset = random.randint(0, 120)
        order_time = base_time + timedelta(minutes=order_offset)

        max_transit = TIER_CONFIG[tier]["max_transit_minutes"]

        # Delivery window: starts at order_time, ends based on tier + 30min buffer
        window_start = order_time
        window_end = order_time + timedelta(minutes=max_transit + 30)

        order = Order(
            id=f"ORD-{i+1:02d}",
            pickup_location=_random_point_in_zone(pickup_zone),
            dropoff_location=_random_point_in_zone(dropoff_zone),
            cargo_description=cargo_name,
            perishability_tier=tier,
            weight_kg=weight,
            base_value=value,
            order_time=order_time,
            delivery_window_start=window_start,
            delivery_window_end=window_end,
            max_transit_minutes=max_transit,
        )
        orders.append(order)

    return orders


def generate_multiple_scenarios(
    seeds: list[int] | None = None,
    num_trucks: int = 15,
    num_orders: int = 25,
) -> list[Scenario]:
    """
    Generate multiple scenarios with different random seeds.

    Same zone layout and order structure each time, but different
    exact positions, cargo selections, and timing. This lets you
    compare algorithms across varied conditions to see if patterns
    hold or if one scenario was a fluke.

    Default seeds produce 5 scenarios with different characteristics:
      - Seed 42:  baseline scenario
      - Seed 77:  different truck/order positions
      - Seed 123: different cargo mix and values
      - Seed 256: different timing windows
      - Seed 999: different capacity distribution
    """
    if seeds is None:
        seeds = [42, 77, 123, 256, 999]
    return [
        generate_scenario(num_trucks=num_trucks, num_orders=num_orders, seed=s)
        for s in seeds
    ]