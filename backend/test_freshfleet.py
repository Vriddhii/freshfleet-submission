"""
FreshFleet Test Suite

Tests cover:
1. Models — data structures create correctly
2. Scoring — distance, travel time, decay, cost, fleet score
3. Constraints — capacity, availability, time windows, spoilage
4. Algorithms — greedy, hungarian, auction produce valid results
5. Integration — algorithms don't violate constraints, metrics are consistent
6. API — FastAPI endpoints return correct responses
"""

import pytest
import math
from datetime import datetime, timedelta

from models import Location, Truck, Order, Assignment, Scenario, TIER_CONFIG
from scoring import (
    calculate_distance,
    calculate_travel_time,
    calculate_delivered_value,
    calculate_cost,
    calculate_fleet_score,
    COST_PER_KM,
)
from constraints import (
    check_capacity,
    check_availability,
    check_time_window,
    check_location_feasibility,
    check_spoilage_cutoff,
    is_valid_assignment,
)
from data_generator import generate_scenario
from algorithms.greedy import run_greedy
from algorithms.hungarian import run_hungarian
from algorithms.auction import run_auction


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def base_time():
    return datetime(2026, 2, 21, 7, 0, 0)


@pytest.fixture
def sample_truck(base_time):
    return Truck(
        id="TRK-TEST",
        location=Location(x=5.0, y=5.0),
        capacity_kg=200,
        current_load_kg=0,
        speed_kmh=40,
        availability_start=base_time - timedelta(hours=1),
        availability_end=base_time + timedelta(hours=8),
        status="available",
    )


@pytest.fixture
def sample_order(base_time):
    return Order(
        id="ORD-TEST",
        pickup_location=Location(x=8.0, y=5.0),
        dropoff_location=Location(x=12.0, y=5.0),
        cargo_description="Fresh Salmon, 10 fillets",
        perishability_tier="P1",
        weight_kg=15.0,
        base_value=1000.0,
        order_time=base_time,
        delivery_window_start=base_time,
        delivery_window_end=base_time + timedelta(hours=1),
        max_transit_minutes=45,
    )


@pytest.fixture
def scenario_seed42():
    return generate_scenario(seed=42)


# ──────────────────────────────────────────────
# 1. Model Tests
# ──────────────────────────────────────────────

class TestModels:
    def test_location_creation(self):
        loc = Location(x=3.5, y=7.2)
        assert loc.x == 3.5
        assert loc.y == 7.2

    def test_truck_creation(self, sample_truck):
        assert sample_truck.id == "TRK-TEST"
        assert sample_truck.capacity_kg == 200
        assert sample_truck.status == "available"

    def test_order_creation(self, sample_order):
        assert sample_order.id == "ORD-TEST"
        assert sample_order.perishability_tier == "P1"
        assert sample_order.base_value == 1000.0

    def test_tier_config_exists(self):
        assert "P1" in TIER_CONFIG
        assert "P2" in TIER_CONFIG
        assert "P3" in TIER_CONFIG
        assert "P4" in TIER_CONFIG
        for tier in TIER_CONFIG.values():
            assert "tier_weight" in tier
            assert "max_transit_minutes" in tier


# ──────────────────────────────────────────────
# 2. Scoring Tests
# ──────────────────────────────────────────────

class TestDistance:
    def test_same_point(self):
        loc = Location(x=5.0, y=5.0)
        assert calculate_distance(loc, loc) == 0.0

    def test_horizontal(self):
        a = Location(x=0.0, y=0.0)
        b = Location(x=3.0, y=0.0)
        assert calculate_distance(a, b) == 3.0

    def test_vertical(self):
        a = Location(x=0.0, y=0.0)
        b = Location(x=0.0, y=4.0)
        assert calculate_distance(a, b) == 4.0

    def test_diagonal(self):
        a = Location(x=0.0, y=0.0)
        b = Location(x=3.0, y=4.0)
        assert calculate_distance(a, b) == 5.0

    def test_symmetry(self):
        a = Location(x=1.0, y=2.0)
        b = Location(x=4.0, y=6.0)
        assert calculate_distance(a, b) == calculate_distance(b, a)


class TestTravelTime:
    def test_basic(self):
        # 40km at 40km/h = 60 minutes
        assert calculate_travel_time(40, 40) == 60.0

    def test_short_distance(self):
        # 5km at 30km/h = 10 minutes
        assert calculate_travel_time(5, 30) == 10.0

    def test_zero_distance(self):
        assert calculate_travel_time(0, 40) == 0.0

    def test_zero_speed(self):
        assert calculate_travel_time(10, 0) == float("inf")


class TestDeliveredValue:
    def test_on_time_full_value(self):
        """Delivered within max transit → full value, any tier."""
        for tier in ["P1", "P2", "P3", "P4"]:
            val = calculate_delivered_value(1000, tier, 30, 45)
            assert val == 1000.0

    def test_p1_exponential_decay(self):
        """P1 halves every 15 min past deadline."""
        val = calculate_delivered_value(1000, "P1", 60, 45)
        # 15 min overtime → half
        assert abs(val - 500.0) < 1.0

    def test_p1_severe_decay(self):
        """P1: 30 min overtime → quarter value."""
        val = calculate_delivered_value(1000, "P1", 75, 45)
        assert abs(val - 250.0) < 1.0

    def test_p2_linear_decay(self):
        """P2 loses 10% per 15 min overtime."""
        val = calculate_delivered_value(1000, "P2", 135, 120)
        # 15 min overtime → 90%
        assert abs(val - 900.0) < 1.0

    def test_p3_slow_decay(self):
        """P3 loses 5% per 30 min overtime."""
        val = calculate_delivered_value(1000, "P3", 270, 240)
        # 30 min overtime → 95%
        assert abs(val - 950.0) < 1.0

    def test_p4_negligible_decay(self):
        """P4 loses 2% per 60 min overtime."""
        val = calculate_delivered_value(1000, "P4", 540, 480)
        # 60 min overtime → 98%
        assert abs(val - 980.0) < 1.0

    def test_value_never_negative(self):
        """Even with extreme overtime, value floors at 0."""
        val = calculate_delivered_value(1000, "P2", 500, 120)
        assert val >= 0.0


class TestCost:
    def test_basic_cost(self):
        assert calculate_cost(10) == 15.0  # 10km * $1.50

    def test_zero_distance(self):
        assert calculate_cost(0) == 0.0

    def test_cost_rate(self):
        assert COST_PER_KM == 1.50


class TestFleetScore:
    def test_perfect_scenario(self, base_time):
        """High-value deliveries with low cost → high fleet score."""
        orders = [
            Order(id="O1", pickup_location=Location(x=0, y=0), dropoff_location=Location(x=1, y=0),
                  cargo_description="Test", perishability_tier="P1", weight_kg=10,
                  base_value=1000, order_time=base_time,
                  delivery_window_start=base_time, delivery_window_end=base_time + timedelta(hours=2),
                  max_transit_minutes=45)
        ]
        assignments = [
            Assignment(truck_id="T1", order_id="O1",
                       estimated_pickup_time=base_time, estimated_delivery_time=base_time + timedelta(minutes=10),
                       transit_minutes=10, delivered_value=1000, cost=5, explanation="test")
        ]
        metrics = calculate_fleet_score(assignments, orders)
        assert metrics["fleet_score"] > 0.9
        assert metrics["orders_fulfilled"] == 1
        assert metrics["p1_fulfilled_pct"] == 100.0

    def test_no_assignments(self, base_time):
        """No assignments → score of 0."""
        orders = [
            Order(id="O1", pickup_location=Location(x=0, y=0), dropoff_location=Location(x=1, y=0),
                  cargo_description="Test", perishability_tier="P1", weight_kg=10,
                  base_value=1000, order_time=base_time,
                  delivery_window_start=base_time, delivery_window_end=base_time + timedelta(hours=2),
                  max_transit_minutes=45)
        ]
        metrics = calculate_fleet_score([], orders)
        assert metrics["fleet_score"] == 0.0
        assert metrics["orders_fulfilled"] == 0


# ──────────────────────────────────────────────
# 3. Constraint Tests
# ──────────────────────────────────────────────

class TestCapacity:
    def test_within_capacity(self, sample_truck, sample_order):
        assert check_capacity(sample_truck, sample_order) is True

    def test_exceeds_capacity(self, sample_truck, sample_order):
        sample_order.weight_kg = 250  # truck only has 200kg
        assert check_capacity(sample_truck, sample_order) is False

    def test_exact_capacity(self, sample_truck, sample_order):
        sample_order.weight_kg = 200
        assert check_capacity(sample_truck, sample_order) is True

    def test_partial_load(self, sample_truck, sample_order):
        sample_truck.current_load_kg = 190
        sample_order.weight_kg = 15
        assert check_capacity(sample_truck, sample_order) is False


class TestAvailability:
    def test_within_shift(self, sample_truck, base_time):
        start = base_time
        end = base_time + timedelta(hours=1)
        assert check_availability(sample_truck, start, end) is True

    def test_before_shift(self, sample_truck, base_time):
        start = base_time - timedelta(hours=3)
        end = base_time - timedelta(hours=2)
        assert check_availability(sample_truck, start, end) is False

    def test_after_shift(self, sample_truck, base_time):
        start = base_time + timedelta(hours=10)
        end = base_time + timedelta(hours=11)
        assert check_availability(sample_truck, start, end) is False


class TestTimeWindow:
    def test_on_time(self, sample_order, base_time):
        delivery = base_time + timedelta(minutes=30)
        assert check_time_window(delivery, sample_order) is True

    def test_late(self, sample_order, base_time):
        delivery = base_time + timedelta(hours=2)
        assert check_time_window(delivery, sample_order) is False

    def test_early_is_ok(self, sample_order, base_time):
        delivery = base_time - timedelta(minutes=10)
        assert check_time_window(delivery, sample_order) is True


class TestSpoilageCutoff:
    def test_fresh_delivery(self, sample_order):
        assert check_spoilage_cutoff(20, sample_order) is True

    def test_rotten_delivery(self, sample_order):
        """P1 with extreme overtime → >90% loss → rejected."""
        assert check_spoilage_cutoff(200, sample_order) is False


# ──────────────────────────────────────────────
# 4. Algorithm Tests
# ──────────────────────────────────────────────

class TestGreedy:
    def test_returns_result(self, scenario_seed42):
        result = run_greedy(scenario_seed42)
        assert result.algorithm == "greedy"
        assert len(result.assignments) > 0

    def test_no_duplicate_trucks(self, scenario_seed42):
        result = run_greedy(scenario_seed42)
        truck_ids = [a.truck_id for a in result.assignments]
        assert len(truck_ids) == len(set(truck_ids))

    def test_no_duplicate_orders(self, scenario_seed42):
        result = run_greedy(scenario_seed42)
        order_ids = [a.order_id for a in result.assignments]
        assert len(order_ids) == len(set(order_ids))

    def test_p1_all_fulfilled(self, scenario_seed42):
        result = run_greedy(scenario_seed42)
        assert result.metrics["p1_fulfilled_pct"] == 100.0

    def test_has_explanations(self, scenario_seed42):
        result = run_greedy(scenario_seed42)
        for a in result.assignments:
            assert len(a.explanation) > 0

    def test_metrics_consistent(self, scenario_seed42):
        result = run_greedy(scenario_seed42)
        assert result.metrics["orders_fulfilled"] == len(result.assignments)
        assert result.metrics["orders_fulfilled"] + len(result.unassigned_order_ids) == result.metrics["total_orders"]


class TestHungarian:
    def test_returns_result(self, scenario_seed42):
        result = run_hungarian(scenario_seed42)
        assert result.algorithm == "hungarian"
        assert len(result.assignments) > 0

    def test_no_duplicate_trucks(self, scenario_seed42):
        result = run_hungarian(scenario_seed42)
        truck_ids = [a.truck_id for a in result.assignments]
        assert len(truck_ids) == len(set(truck_ids))

    def test_no_duplicate_orders(self, scenario_seed42):
        result = run_hungarian(scenario_seed42)
        order_ids = [a.order_id for a in result.assignments]
        assert len(order_ids) == len(set(order_ids))

    def test_has_explanations(self, scenario_seed42):
        result = run_hungarian(scenario_seed42)
        for a in result.assignments:
            assert len(a.explanation) > 0

    def test_metrics_consistent(self, scenario_seed42):
        result = run_hungarian(scenario_seed42)
        assert result.metrics["orders_fulfilled"] == len(result.assignments)
        assert result.metrics["orders_fulfilled"] + len(result.unassigned_order_ids) == result.metrics["total_orders"]


class TestAuction:
    def test_returns_result(self, scenario_seed42):
        result = run_auction(scenario_seed42)
        assert result.algorithm == "auction"
        assert len(result.assignments) > 0

    def test_no_duplicate_trucks(self, scenario_seed42):
        result = run_auction(scenario_seed42)
        truck_ids = [a.truck_id for a in result.assignments]
        assert len(truck_ids) == len(set(truck_ids))

    def test_no_duplicate_orders(self, scenario_seed42):
        result = run_auction(scenario_seed42)
        order_ids = [a.order_id for a in result.assignments]
        assert len(order_ids) == len(set(order_ids))

    def test_p1_all_fulfilled(self, scenario_seed42):
        result = run_auction(scenario_seed42)
        assert result.metrics["p1_fulfilled_pct"] == 100.0

    def test_has_explanations(self, scenario_seed42):
        result = run_auction(scenario_seed42)
        for a in result.assignments:
            assert len(a.explanation) > 0

    def test_metrics_consistent(self, scenario_seed42):
        result = run_auction(scenario_seed42)
        assert result.metrics["orders_fulfilled"] == len(result.assignments)
        assert result.metrics["orders_fulfilled"] + len(result.unassigned_order_ids) == result.metrics["total_orders"]


# ──────────────────────────────────────────────
# 5. Integration Tests
# ──────────────────────────────────────────────

class TestIntegration:
    """Cross-cutting tests that verify the whole pipeline."""

    def test_all_algorithms_same_scenario(self, scenario_seed42):
        """All 3 algorithms should work on the same scenario."""
        g = run_greedy(scenario_seed42)
        h = run_hungarian(scenario_seed42)
        a = run_auction(scenario_seed42)
        assert g.metrics["total_orders"] == h.metrics["total_orders"] == a.metrics["total_orders"]

    def test_no_constraint_violations(self, scenario_seed42):
        """Every assignment must pass all hard constraints."""
        for algo_fn in [run_greedy, run_hungarian, run_auction]:
            result = algo_fn(scenario_seed42)
            current_time = min(o.order_time for o in scenario_seed42.orders)

            for a in result.assignments:
                truck = next(t for t in scenario_seed42.trucks if t.id == a.truck_id)
                order = next(o for o in scenario_seed42.orders if o.id == a.order_id)

                # Capacity
                assert check_capacity(truck, order), f"{algo_fn.__name__}: capacity violation {a.truck_id}->{a.order_id}"

                # Time window
                assert check_time_window(a.estimated_delivery_time, order), \
                    f"{algo_fn.__name__}: time window violation {a.truck_id}->{a.order_id}"

                # Spoilage
                assert check_spoilage_cutoff(a.transit_minutes, order), \
                    f"{algo_fn.__name__}: spoilage violation {a.truck_id}->{a.order_id}"

    def test_delivered_value_not_exceeds_base(self, scenario_seed42):
        """Delivered value can never exceed base value."""
        for algo_fn in [run_greedy, run_hungarian, run_auction]:
            result = algo_fn(scenario_seed42)
            for a in result.assignments:
                order = next(o for o in scenario_seed42.orders if o.id == a.order_id)
                assert a.delivered_value <= order.base_value + 0.01, \
                    f"{algo_fn.__name__}: delivered value ${a.delivered_value} > base ${order.base_value}"

    def test_fleet_score_between_0_and_1(self, scenario_seed42):
        """Fleet score must be in [0, 1]."""
        for algo_fn in [run_greedy, run_hungarian, run_auction]:
            result = algo_fn(scenario_seed42)
            assert 0.0 <= result.metrics["fleet_score"] <= 1.0

    def test_deterministic_results(self, scenario_seed42):
        """Same seed → same results every time."""
        g1 = run_greedy(scenario_seed42)
        g2 = run_greedy(scenario_seed42)
        assert g1.metrics["fleet_score"] == g2.metrics["fleet_score"]
        assert len(g1.assignments) == len(g2.assignments)

    def test_multiple_seeds_work(self):
        """All 5 default seeds should produce valid results."""
        for seed in [42, 77, 123, 256, 999]:
            scenario = generate_scenario(seed=seed)
            for algo_fn in [run_greedy, run_hungarian, run_auction]:
                result = algo_fn(scenario)
                assert result.metrics["orders_fulfilled"] > 0
                assert result.metrics["fleet_score"] > 0

    def test_algorithms_differ(self, scenario_seed42):
        """Algorithms should produce different results (not identical)."""
        g = run_greedy(scenario_seed42)
        h = run_hungarian(scenario_seed42)
        a = run_auction(scenario_seed42)
        scores = {g.metrics["fleet_score"], h.metrics["fleet_score"], a.metrics["fleet_score"]}
        assert len(scores) > 1, "All algorithms produced identical fleet scores"


# ──────────────────────────────────────────────
# 6. Data Generator Tests
# ──────────────────────────────────────────────

class TestDataGenerator:
    def test_correct_counts(self, scenario_seed42):
        assert len(scenario_seed42.trucks) == 15
        assert len(scenario_seed42.orders) == 25

    def test_p1_count(self, scenario_seed42):
        p1_orders = [o for o in scenario_seed42.orders if o.perishability_tier == "P1"]
        assert len(p1_orders) == 5

    def test_tier_distribution(self, scenario_seed42):
        tiers = [o.perishability_tier for o in scenario_seed42.orders]
        assert tiers.count("P1") == 5
        assert tiers.count("P2") == 7
        assert tiers.count("P3") == 8
        assert tiers.count("P4") == 5

    def test_deterministic(self):
        s1 = generate_scenario(seed=42)
        s2 = generate_scenario(seed=42)
        assert s1.trucks[0].location.x == s2.trucks[0].location.x
        assert s1.orders[0].base_value == s2.orders[0].base_value

    def test_different_seeds_differ(self):
        s1 = generate_scenario(seed=42)
        s2 = generate_scenario(seed=77)
        assert s1.orders[0].base_value != s2.orders[0].base_value


# ──────────────────────────────────────────────
# 7. API Tests
# ──────────────────────────────────────────────

class TestAPI:
    @pytest.fixture(autouse=True)
    def setup_client(self):
        from fastapi.testclient import TestClient
        from main import app
        self.client = TestClient(app)

    def test_health(self):
        r = self.client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_scenario(self):
        r = self.client.get("/api/scenario?seed=42")
        assert r.status_code == 200
        data = r.json()
        assert len(data["trucks"]) == 15
        assert len(data["orders"]) == 25

    def test_allocate_greedy(self):
        r = self.client.get("/api/allocate/greedy?seed=42")
        assert r.status_code == 200
        data = r.json()
        assert data["algorithm"] == "greedy"
        assert len(data["assignments"]) > 0
        assert "fleet_score" in data["metrics"]

    def test_allocate_hungarian(self):
        r = self.client.get("/api/allocate/hungarian?seed=42")
        assert r.status_code == 200
        assert r.json()["algorithm"] == "hungarian"

    def test_allocate_auction(self):
        r = self.client.get("/api/allocate/auction?seed=42")
        assert r.status_code == 200
        assert r.json()["algorithm"] == "auction"

    def test_compare(self):
        r = self.client.get("/api/compare?seed=42")
        assert r.status_code == 200
        data = r.json()
        assert "scenario" in data
        assert "results" in data
        assert "greedy" in data["results"]
        assert "hungarian" in data["results"]
        assert "auction" in data["results"]

    def test_compare_multi(self):
        r = self.client.get("/api/compare/multi")
        assert r.status_code == 200
        data = r.json()
        assert "averages" in data
        assert "per_seed" in data
        assert len(data["per_seed"]) == 5