# FreshFleet Backend Issues

## Critical

### 1. Non-deterministic scenarios despite seeding
**File:** `backend/data_generator.py:111, 119`

`random.seed(seed)` only controls positions/weights/cargo. The DATE anchoring every timestamp comes from `datetime.now()`, so the scenario changes across calendar days. On Jan 1 seed=42 produces different absolute datetimes than on Jan 2 seed=42. For a demo comparing algorithms this is mostly harmless (relative timing is consistent), but the API is not truly reproducible.

```python
# Current — date changes every day
base_time = datetime.now().replace(hour=6, minute=0, second=0, microsecond=0)

# Fix — use a fixed reference date
base_time = datetime(2024, 1, 1, 6, 0, 0)
```

---

### 2. `check_location_feasibility` uses wrong departure time
**File:** `backend/constraints.py:56-74`

This function assumes the truck departs at `current_time`, but `_estimate_times` in every algorithm correctly uses `max(current_time, order.order_time)`. For orders with `order_time > current_time`, `check_location_feasibility` is overly optimistic — it can say "feasible" when the actual delivery would miss the window. It won't cause invalid assignments (because `check_time_window` runs with the real calculated time afterward), but it makes the feasibility check unreliable and redundant.

```python
# Current — departs at current_time (too optimistic for future orders)
estimated_delivery = current_time + timedelta(minutes=total_minutes)

# Fix — match the departure logic used in _estimate_times
earliest_departure = max(current_time, order.order_time)
estimated_delivery = earliest_departure + timedelta(minutes=total_minutes)
```

---

## Significant Bugs

### 3. `available_truck_ids` in auction is dead code
**File:** `backend/algorithms/auction.py:174, 288`

`available_truck_ids` is built and maintained throughout `run_auction` but never read. All iteration uses `available_trucks` (the list). Harmless but misleading.

```python
available_truck_ids = {t.id for t in trucks}   # built...
available_truck_ids.remove(best_truck.id)       # maintained...
# ...never used anywhere
```

---

### 4. Non-deterministic `unassigned_order_ids` in Hungarian
**File:** `backend/algorithms/hungarian.py:203-204`

Set subtraction produces non-deterministic ordering. Greedy and auction preserve insertion order; Hungarian doesn't. The API response for `unassigned_order_ids` will vary between runs with the same seed.

```python
# Current — non-deterministic
unassigned_order_ids = list(all_order_ids - assigned_order_ids)

# Fix
unassigned_order_ids = sorted(all_order_ids - assigned_order_ids)
```

---

### 5. Mutable default argument
**File:** `backend/data_generator.py:259`

Classic Python gotcha — the same list object is shared across all calls. Safe here since `seeds` is never mutated, but it's a latent trap.

```python
# Current
def generate_multiple_scenarios(seeds: list[int] = [42, 77, 123, 256, 999], ...)

# Fix
def generate_multiple_scenarios(seeds: list[int] | None = None, ...):
    if seeds is None:
        seeds = [42, 77, 123, 256, 999]
```

---

### 6. Hungarian timing computed twice
**File:** `backend/algorithms/hungarian.py:154-170`

After `linear_sum_assignment`, every distance/time calculation already done in `_build_cost_matrix` is repeated verbatim for each valid assignment. A `(i, j) → timing` dict could be populated during matrix construction and reused here.

---

### 7. `delivery_window_start` is generated but never enforced
**File:** `backend/constraints.py:34-43`

`Order.delivery_window_start` is populated in the data generator but `check_time_window` only checks the end:

```python
return estimated_delivery_time <= order.delivery_window_end  # start silently ignored
```

For the current generator this doesn't matter (`window_start = order_time`, and no truck departs before `order_time`), but the field is misleading since it's silently ignored.

---

## Algorithm / Design Issues

### 8. `dist_to_pickup` computed twice per truck-order pair in greedy
**File:** `backend/algorithms/greedy.py:142-145`

`_estimate_times` already computes `dist_to_pickup` and returns `total_dist`, but the selection loop calls `calculate_distance` again to pick the nearest truck.

---

### 9. Fleet score clamps negative values to 0
**File:** `backend/scoring.py:128`

```python
fleet_score = max(0.0, net_value / total_possible_value)
```

If an algorithm's operational costs exceed its delivered value (possible with distant trucks on cheap orders), the score floors at 0 regardless of how bad it was. This loses the ability to distinguish "mediocre" from "catastrophic."

---

### 10. `total_value_lost` excludes operational costs
**File:** `backend/scoring.py:113`

```python
total_value_lost = total_possible_value - total_delivered_value
```

This measures value lost to decay and non-delivery only. An algorithm that delivers everything fresh but drives very long routes will show `total_value_lost = 0` despite poor economics. The `fleet_score` correctly captures net value (`delivered − cost`), but the standalone `total_value_lost` metric can be misleading.

---

### 11. Auction's `_calculate_opportunity_cost` is O(n²) per order
**File:** `backend/algorithms/auction.py:91-146`

For each order, for each available truck, for each remaining urgent order, `_can_truck_serve` is called (which includes full constraint checking). At 15 trucks and 25 orders this is fine, but complexity scales as O(orders × trucks × urgent_orders) and `_can_truck_serve` is not cheap.

---

### 12. Zone center exclusion — points never placed near zone centers
**File:** `backend/data_generator.py:85`

```python
r = radius * random.uniform(0.1, 1.0) ** 0.5
```

The minimum of `0.1` means `r_min = radius × √0.1 ≈ 0.316 × radius`. Points are never generated within the innermost ~31% of any zone's radius. The intended `fish_wharf` scarcity scenario relies on trucks and orders being near each other at `(2, 16)`, but both are always offset by at least 31% of the zone radius. Likely unintentional.

```python
# Fix — allow full range including center
r = radius * random.uniform(0.0, 1.0) ** 0.5
```

---

## Summary

| # | Severity | Issue | File |
|---|----------|-------|------|
| 1 | Critical | `datetime.now()` makes scenarios vary by calendar day | `data_generator.py:111` |
| 2 | Critical | `check_location_feasibility` uses wrong departure time | `constraints.py:56` |
| 3 | Bug | `available_truck_ids` in auction is dead code | `auction.py:174` |
| 4 | Bug | `unassigned_order_ids` is non-deterministic in Hungarian | `hungarian.py:203` |
| 5 | Bug | Mutable default argument in `generate_multiple_scenarios` | `data_generator.py:259` |
| 6 | Bug | Hungarian timing recalculated after solve | `hungarian.py:154` |
| 7 | Bug | `delivery_window_start` field generated but never enforced | `constraints.py:34` |
| 8 | Design | `dist_to_pickup` computed twice in greedy | `greedy.py:142` |
| 9 | Design | Fleet score loses negative signal (clamped to 0) | `scoring.py:128` |
| 10 | Design | `total_value_lost` excludes operational costs | `scoring.py:113` |
| 11 | Design | Opportunity cost check is O(n²) per order | `auction.py:91` |
| 12 | Design | Zone center exclusion radius (~31%) likely unintentional | `data_generator.py:85` |
