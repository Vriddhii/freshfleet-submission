# FreshFleet — Algorithm Analysis

## 1. Problem Framing

FreshFleet solves a constrained resource allocation problem: given 15 delivery trucks and 25 perishable goods orders, assign trucks to orders to maximize total delivered value while minimizing operational costs.

The challenge is that perishable goods decay at different rates. A P1 order (sushi-grade tuna, $1,500) loses 50% of its value every 15 minutes past deadline — exponential decay. A P4 order (canned goods, $170) barely loses value at all. This creates a tension: do you prioritize the high-value P1 orders even if they require sending trucks on longer routes, or do you optimize for overall fleet efficiency?

### Scenario Design

Each scenario places 25 orders across 5 zones with a deliberate scarcity challenge:

- **Fish Wharf**: 5 P1 orders (critical seafood) but only 2 nearby trucks
- **Downtown**: 4 trucks, mixed P2/P3 orders
- **Suburbs North/South**: 7 trucks total, P2-P4 orders
- **Industrial**: 2 trucks, P3-P4 orders

The Fish Wharf bottleneck forces algorithms to make hard tradeoffs. The 2 wharf trucks can only serve 2 of the 5 P1 orders, so the other 3 must be served by downtown trucks 8-9km away — if those trucks haven't already been assigned to closer, cheaper orders.

### Constraints

Every assignment must satisfy five hard constraints:
1. Truck capacity ≥ order weight
2. Delivery within driver's shift window
3. Arrival before delivery window closes
4. Truck can physically reach destination in time
5. Cargo retains >10% of value on arrival

With 15 trucks and 25 orders, only 15 orders can be served (one truck per order). The 10 unassigned orders represent the allocation tradeoff — which orders are worth skipping?

## 2. Algorithm Design

### Greedy — "Nearest Available Truck"

**Strategy:** Sort all orders by urgency (P1 first, then P2, P3, P4; ties broken by deadline). For each order, find the nearest available truck that satisfies all constraints. Assign and move on.

**Why it works for P1:** By processing P1 orders first, Greedy guarantees they get first pick of trucks before any truck is consumed by a lower-priority order. The 2 wharf trucks are naturally closest to P1 orders, so they're assigned immediately.

**Why it's limited:** Greedy doesn't look ahead. It might assign a downtown truck to a nearby P2 order, not realizing that truck was the only one that could reach a P1 order at Fish Wharf. Each decision is locally optimal but globally unaware.

**Complexity:** O(orders × trucks) — one pass through orders, scanning trucks for each.

### Hungarian — "Global Cost Minimizer"

**Strategy:** Build a cost matrix where `cost[i][j] = operational_cost - delivered_value` for assigning truck i to order j. Invalid pairings get cost 999,999. Use scipy's `linear_sum_assignment` to find the one-to-one matching that minimizes total cost across the entire fleet.

**Why it maximizes profit:** By subtracting delivered value from cost, the matrix makes high-value orders attractive (large negative costs). Hungarian finds the assignment that maximizes `total_delivered_value - total_cost` across all 15 pairings simultaneously.

**Why it drops P1 orders:** The algorithm optimizes globally. Sometimes the global optimum says "skip a $325 P1 dairy order at Fish Wharf (requires a downtown truck driving 9km) and instead assign that truck to a $700 P2 smoked salmon order 2km away." The global profit is higher, but the P1 order is abandoned. The cost matrix doesn't capture the real-world consequence of losing a critical seafood client.

**Complexity:** O(n³) via the Hungarian algorithm on an n×n matrix.

### Auction — "Smart Urgency with Opportunity Cost"

**Strategy:** 
1. Score every order by urgency = `base_value × tier_weight × (1 / minutes_until_deadline)`
2. Process orders highest urgency first
3. For each order, every eligible truck "bids" with: `proximity_score + value_preservation_score - opportunity_cost`
4. Opportunity cost checks: "If I assign this truck here, is it the only truck that can serve another critical P1/P2 order?"
5. Best bid wins

**Why it protects P1:** The opportunity cost mechanism is the key innovation. When a downtown truck bids for a nearby P2 order, the algorithm checks "can any other truck serve the remaining P1 orders at Fish Wharf?" If this truck is the sole option for a critical order, its bid gets a heavy penalty. The truck is effectively "reserved" for the more important delivery.

**Why it's the best balance:** Auction combines urgency-first processing (like Greedy) with value awareness and resource protection. It doesn't have Hungarian's global optimality, but it avoids Hungarian's critical flaw of abandoning P1 orders.

**Complexity:** O(orders × trucks × urgent_orders) due to the opportunity cost calculation.

## 3. Results

### Averaged Across 5 Scenarios

| Metric | Greedy | Hungarian | Auction |
|--------|--------|-----------|---------|
| **Fleet Score** | 0.76 | **0.80** | 0.79 |
| **P1 Fulfilled** | **100%** | 80% | **100%** |
| **Value Delivered** | $12,419 | **$13,076** | $12,898 |
| **Value Lost** | $3,443 | **$2,786** | $2,964 |
| **Operational Cost** | $362 | **$321** | $372 |
| **Total Distance** | 241 km | **214 km** | 248 km |
| **Avg Transit** | 13.7 min | **13.6 min** | 14.0 min |
| **Compute Time** | **0.4 ms** | 2.3 ms | 21.2 ms |

### Per-Seed Consistency

| Seed | Greedy | Hungarian | Auction |
|------|--------|-----------|---------|
| 42 | 0.76 | 0.80 | 0.78 |
| 77 | 0.77 | 0.80 | 0.79 |
| 123 | 0.77 | 0.83 | 0.81 |
| 256 | 0.79 | 0.81 | 0.81 |
| 999 | 0.70 | 0.78 | 0.76 |

Hungarian leads on Fleet Score in every seed. Auction is second in every seed. Greedy is last in every seed. The ranking is consistent — this is not a fluke of one scenario.

### P1 Fulfillment Per Seed

| Seed | Greedy | Hungarian | Auction |
|------|--------|-----------|---------|
| 42 | 100% | 60% | 100% |
| 77 | 100% | 100% | 100% |
| 123 | 100% | 60% | 100% |
| 256 | 100% | 100% | 100% |
| 999 | 100% | 80% | 100% |

Hungarian drops P1 orders in 3 of 5 seeds. On seed 42 and 123, it only serves 60% of P1 orders (3 out of 5). Greedy and Auction never drop a single P1 order.

## 4. Key Findings

### Finding 1: The "Optimal" Algorithm Isn't Always Best

Hungarian is mathematically optimal — it finds the assignment that maximizes `delivered_value - cost` across the entire fleet. Yet it produces the worst P1 fulfillment. This is because:

- The cost matrix treats all value equally. A $325 P1 dairy order and a $325 P3 bread order look identical.
- Skipping a far-away P1 order often saves $30-40 in fuel, which improves the global score.
- The algorithm doesn't model the nonlinear consequence of P1 failure — losing a seafood client's trust costs far more than one delivery.

This is a core lesson: **global optimality depends on what you optimize for**. Hungarian optimizes for fleet economics. In perishable goods delivery, you also need to optimize for cargo protection.

### Finding 2: Domain Knowledge Beats Generic Algorithms

Auction's opportunity cost mechanism is a simple heuristic (one-step lookahead for P1/P2 scarcity), but it outperforms the mathematically optimal Hungarian on the metric that matters most for perishable goods. The insight is that domain-specific heuristics — "don't waste the only truck that can reach critical cargo" — can be more valuable than mathematical optimality guarantees.

### Finding 3: Speed Has Real Value

Greedy runs in 0.4ms — 54× faster than Auction. In a real-time system where orders stream in continuously (not batched), Greedy's speed matters. Hungarian requires all orders upfront (batch processing), while Greedy and Auction can process orders as they arrive. For a production system, Greedy could serve as the real-time allocator with Auction running periodically to rebalance.

### Finding 4: The Gap Between Algorithms Is Consistent

Across all 5 seeds, the ranking never changes: Hungarian > Auction > Greedy on Fleet Score, and Auction = Greedy > Hungarian on P1 fulfillment. This consistency means the results reflect genuine algorithmic differences, not scenario-specific artifacts.

## 5. Tradeoff Summary

| Priority | Best Algorithm | Why |
|----------|---------------|-----|
| Maximum profit | Hungarian | Global optimization finds highest value-to-cost ratio |
| Never lose critical cargo | Auction (or Greedy) | Both achieve 100% P1; Auction does it with higher profit |
| Real-time speed | Greedy | 54× faster than Auction, processes orders incrementally |
| Best overall balance | **Auction** | Only algorithm with both high profit AND 100% P1 protection |
| Minimum fuel usage | Hungarian | 11% less driving than Greedy, global routing optimization |

## 6. Design Decisions

### Why Euclidean Distance?
We use straight-line distance rather than road networks to keep the focus on the allocation problem. Real deployments would plug in a routing API (Google Maps, OSRM), but the algorithmic comparison holds regardless of distance calculation method.

### Why Fixed Scenarios?
Deterministic seeding (`random.seed(42)` + fixed base_time) ensures reproducibility. Anyone running the same seed gets identical results. This is critical for comparing algorithms fairly — they must run on exactly the same data.

### Why One Truck Per Order?
Simplifying to one-to-one assignment makes the problem tractable for Hungarian (which requires a bipartite matching structure) and keeps comparison fair. A production system would handle multi-stop routes, but that's a vehicle routing problem (VRP), not a resource allocation problem.

### Why Not Penalize Hungarian's Cost Matrix for P1?
We intentionally kept Hungarian "pure" — it optimizes what cost matrices naturally optimize (minimize cost, maximize value). Adding artificial P1 penalties would make it behave like Auction, defeating the purpose of comparing different approaches. The finding that pure optimization drops critical orders is itself valuable.

## 7. Limitations and Future Improvements

### Current Limitations
- **Single assignment per truck**: Real fleets handle multi-stop routes
- **Static scenario**: Orders arrive all at once, no dynamic re-routing
- **Euclidean distance**: No road network, traffic, or real travel times
- **No vehicle heterogeneity beyond capacity/speed**: Real trucks have refrigeration tiers, loading constraints
- **Auction's opportunity cost is O(n²)**: Scales poorly beyond ~100 orders; a precomputed feasibility matrix would fix this

### Potential Improvements
- **Hybrid approach**: Use Greedy for real-time allocation, periodically run Auction to rebalance
- **Multi-objective Hungarian**: Add P1 penalty terms to the cost matrix, tunable by the dispatcher
- **Dynamic re-allocation**: When new orders arrive, reassign trucks that haven't reached pickup yet
- **Reinforcement learning**: Train an RL agent on historical scenarios to learn allocation policies
- **Capacity pooling**: Allow trucks to carry multiple small orders on one route

## 8. Testing

73 pytest tests validate the entire pipeline:

| Category | Tests | What They Verify |
|----------|-------|-----------------|
| Models | 4 | Data structures create correctly |
| Scoring | 14 | Distance, travel time, all 4 decay tiers, cost, fleet score |
| Constraints | 10 | Capacity, availability, time windows, spoilage |
| Algorithms | 18 | Each returns results, no duplicates, explanations, metrics consistency |
| Integration | 7 | No constraint violations, determinism, multi-seed, algorithms differ |
| Data Generator | 5 | Correct counts, tier distribution, determinism |
| API | 7 | All endpoints return correct responses |

All tests pass in under 1 second.
