# 🚛 FreshFleet — Perishable Goods Delivery Allocation Engine

A full-stack resource allocation system that optimally assigns delivery trucks to perishable goods orders, comparing three different algorithms to find the best tradeoffs between profit, speed, and cargo protection.

## Problem

Perishable goods lose value every minute they're in transit. A $1,500 sushi-grade tuna order loses 50% of its value every 15 minutes past its deadline, while canned goods barely decay at all. How should a fleet dispatcher assign limited trucks to maximize delivered value while minimizing costs?

This is a constrained optimization problem with competing objectives:
- **Maximize** total cargo value delivered
- **Minimize** operational costs (fuel, distance)
- **Protect** critical P1 orders (ultra-perishable seafood, dairy)
- **Respect** hard constraints (truck capacity, driver shifts, delivery windows)

## Solution

FreshFleet implements three allocation algorithms, each with a different strategy:

| Algorithm | Strategy | Strength | Weakness |
|-----------|----------|----------|----------|
| **Greedy** | Process most urgent orders first, assign nearest truck | Fastest (0.4ms), 100% P1 fulfillment | Short-sighted, lowest profit |
| **Hungarian** | Build cost matrix, find globally optimal matching | Highest profit, most fuel efficient | Drops P1 orders (80% avg) |
| **Auction** | Urgency-weighted bidding with opportunity cost | Best balance: high profit + 100% P1 | Slowest (21ms), heuristic |

## Architecture

```
freshfleet/
├── backend/                    # Python + FastAPI
│   ├── models.py               # Pydantic data models (Truck, Order, Assignment)
│   ├── scoring.py              # Distance, decay, cost, Fleet Score
│   ├── constraints.py          # Hard constraint validation (5 checks)
│   ├── data_generator.py       # Deterministic scenario generation
│   ├── algorithms/
│   │   ├── greedy.py           # Nearest-truck heuristic
│   │   ├── hungarian.py        # scipy linear_sum_assignment
│   │   └── auction.py          # Custom domain-aware auction
│   ├── main.py                 # FastAPI endpoints
│   └── test_freshfleet.py      # 73 pytest tests
├── frontend/                   # React dashboard
│   └── src/
│       ├── App.js              # SVG map, metrics, charts
│       └── App.css             # Dark theme styling
└── ANALYSIS.md                 # Detailed algorithm comparison
```

## Key Features

### 4-Tier Perishability Model
| Tier | Example | Max Transit | Decay Pattern |
|------|---------|-------------|---------------|
| P1 | Sushi-grade tuna, raw oysters | 45 min | Exponential — halves every 15 min late |
| P2 | Smoked salmon, cut flowers | 2 hours | Linear — loses 10% per 15 min late |
| P3 | Sourdough bread, farm eggs | 4 hours | Slow linear — loses 5% per 30 min late |
| P4 | Canned goods, rice crackers | 8 hours | Negligible — loses 2% per 60 min late |

### 5 Hard Constraints
Every assignment must pass all five checks:
1. **Capacity** — truck has enough remaining kg
2. **Availability** — delivery falls within driver's shift
3. **Time Window** — arrives before delivery window closes
4. **Location Feasibility** — truck can physically reach destination in time
5. **Spoilage Cutoff** — cargo retains >10% of value on arrival

### Deliberate Scarcity Scenario
The data generator creates a challenging situation: 5 P1 orders clustered at Fish Wharf with only 2 nearby trucks. The nearest non-wharf truck is 8-9km away. This forces algorithms to make hard choices about which orders to prioritize.

### Fleet Score
```
Fleet Score = (total_delivered_value - total_cost) / total_possible_value
```
Ranges from 0 to 1. A perfect 1.0 would mean all orders delivered fresh at zero cost (impossible). Real scores range 0.70–0.83.

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install fastapi uvicorn pydantic scipy numpy
```

### Frontend
```bash
cd frontend
npm install
```

## Running

Start both servers in separate terminals:

**Terminal 1 — Backend (port 8000):**
```bash
cd backend
uvicorn main:app --reload
```

**Terminal 2 — Frontend (port 3000):**
```bash
cd frontend
npm start
```

Open `http://localhost:3000` to view the dashboard.

### API Documentation
With the backend running, visit `http://localhost:8000/docs` for interactive Swagger UI.

### Key Endpoints
| Endpoint | Description |
|----------|-------------|
| `GET /api/scenario?seed=42` | Generate a scenario |
| `GET /api/allocate/greedy?seed=42` | Run greedy algorithm |
| `GET /api/allocate/hungarian?seed=42` | Run Hungarian algorithm |
| `GET /api/allocate/auction?seed=42` | Run auction algorithm |
| `GET /api/compare?seed=42` | Run all 3, side-by-side |
| `GET /api/compare/multi` | Run all 3 across 5 seeds |

## Testing

```bash
cd backend
pytest test_freshfleet.py -v
```

73 tests covering models, scoring, constraints, all three algorithms, integration, data generation, and API endpoints. All pass in under 1 second.

## Results Summary

Averaged across 5 scenarios (seeds 42, 77, 123, 256, 999):

| Metric | Greedy | Hungarian | Auction |
|--------|--------|-----------|---------|
| Fleet Score | 0.76 | **0.80** | 0.79 |
| P1 Fulfilled | **100%** | 80% | **100%** |
| Value Delivered | $12,419 | **$13,076** | $12,898 |
| Total Distance | 241 km | **214 km** | 248 km |
| Compute Time | **0.4 ms** | 2.3 ms | 21.2 ms |

**Key finding:** No single algorithm wins everything. Hungarian maximizes profit but drops critical seafood orders. Greedy is fastest but least profitable. Auction is the only algorithm that achieves both high profit AND 100% P1 protection — making it the best choice for perishable goods delivery.

See [ANALYSIS.md](ANALYSIS.md) for the full comparison and discussion.
