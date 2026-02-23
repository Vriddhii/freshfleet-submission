"""
FreshFleet Data Models

Defines the core entities: Trucks, Orders, Assignments, and Metrics.
Uses Pydantic for validation and automatic JSON serialization in the API.
"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# Perishability Tier Configuration

TIER_CONFIG = {
    "P1": {
        "label": "Ultra-perishable",
        "examples": "Raw seafood, fresh dairy, sushi-grade fish",
        "max_transit_minutes": 45,
        "tier_weight": 4,       # used in urgency scoring
    },
    "P2": {
        "label": "Highly perishable",
        "examples": "Cut flowers, fresh meat, prepared foods",
        "max_transit_minutes": 120,
        "tier_weight": 3,
    },
    "P3": {
        "label": "Moderately perishable",
        "examples": "Fresh produce, baked goods, eggs",
        "max_transit_minutes": 240,
        "tier_weight": 2,
    },
    "P4": {
        "label": "Low perishability",
        "examples": "Canned goods, dry goods, packaged snacks",
        "max_transit_minutes": 480,
        "tier_weight": 1,
    },
}


# Core Models

class Location(BaseModel):
    """A point on our 20km x 20km city grid."""
    x: float  # km from origin (0-20)
    y: float  # km from origin (0-20)


class Truck(BaseModel):
    """A delivery truck in the fleet."""
    id: str                          # e.g. "TRK-01"
    location: Location               # current position on the grid
    capacity_kg: float               # max cargo weight
    current_load_kg: float = 0.0     # weight already on truck
    speed_kmh: float = 40.0          # average urban speed
    availability_start: datetime     # shift start
    availability_end: datetime       # shift end
    status: str = "available"        # "available" or "busy"


class Order(BaseModel):
    """A delivery request for perishable goods."""
    id: str                          # e.g. "ORD-01"
    pickup_location: Location        # supplier location
    dropoff_location: Location       # customer location
    cargo_description: str           # e.g. "Fresh Atlantic Salmon, 24 fillets"
    perishability_tier: str          # "P1", "P2", "P3", or "P4"
    weight_kg: float                 # cargo weight
    base_value: float                # dollar value if delivered fresh
    order_time: datetime             # when the order was placed
    delivery_window_start: datetime  # earliest acceptable delivery
    delivery_window_end: datetime    # latest acceptable delivery
    max_transit_minutes: float       # max time from pickup to dropoff (from tier)


class Assignment(BaseModel):
    """The output: a truck assigned to an order."""
    truck_id: str
    order_id: str
    estimated_pickup_time: datetime
    estimated_delivery_time: datetime
    transit_minutes: float
    delivered_value: float           # base_value after decay
    cost: float                      # operational cost
    explanation: str                 # human-readable reasoning


class AlgorithmResult(BaseModel):
    """Full output from running one algorithm."""
    algorithm: str
    assignments: list[Assignment]
    unassigned_order_ids: list[str]
    metrics: dict                    # fleet score, distances, etc.


class Scenario(BaseModel):
    """A complete problem instance: trucks + orders."""
    trucks: list[Truck]
    orders: list[Order]
    generated_at: datetime