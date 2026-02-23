"""
FreshFleet API

Exposes the scenario data and algorithm results to the frontend.
Run with: uvicorn main:app --reload
Docs at: http://localhost:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from data_generator import generate_scenario, generate_multiple_scenarios
from algorithms.greedy import run_greedy
from algorithms.hungarian import run_hungarian
from algorithms.auction import run_auction


app = FastAPI(
    title="FreshFleet API",
    description="Perishable goods delivery allocation engine",
)

# Allow the React frontend (localhost:3000) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Endpoints

@app.get("/api/health")
def health():
    """Simple health check."""
    return {"status": "ok"}


@app.get("/api/scenario")
def get_scenario(seed: int = 42):
    """
    Generate and return a scenario (trucks + orders).
    Pass ?seed=77 to get a different scenario.
    """
    scenario = generate_scenario(seed=seed)
    return scenario.model_dump(mode="json")


@app.get("/api/allocate/greedy")
def allocate_greedy(seed: int = 42):
    """Run the greedy algorithm on a scenario."""
    scenario = generate_scenario(seed=seed)
    result = run_greedy(scenario)
    return result.model_dump(mode="json")


@app.get("/api/allocate/hungarian")
def allocate_hungarian(seed: int = 42):
    """Run the Hungarian algorithm on a scenario."""
    scenario = generate_scenario(seed=seed)
    result = run_hungarian(scenario)
    return result.model_dump(mode="json")


@app.get("/api/allocate/auction")
def allocate_auction(seed: int = 42):
    """Run the auction algorithm on a scenario."""
    scenario = generate_scenario(seed=seed)
    result = run_auction(scenario)
    return result.model_dump(mode="json")


@app.get("/api/compare")
def compare_algorithms(seed: int = 42):
    """
    Run all 3 algorithms on the same scenario and return
    side-by-side results. This is the main endpoint the
    frontend uses.
    """
    scenario = generate_scenario(seed=seed)

    greedy = run_greedy(scenario)
    hungarian = run_hungarian(scenario)
    auction = run_auction(scenario)

    return {
        "scenario": scenario.model_dump(mode="json"),
        "results": {
            "greedy": greedy.model_dump(mode="json"),
            "hungarian": hungarian.model_dump(mode="json"),
            "auction": auction.model_dump(mode="json"),
        },
    }


@app.get("/api/compare/multi")
def compare_multi_seed(seeds: str = "42,77,123,256,999"):
    """
    Run all 3 algorithms across multiple seeds.
    Returns per-seed results and averages.
    Pass ?seeds=42,77,123 to customize.
    """
    seed_list = [int(s.strip()) for s in seeds.split(",")]

    all_results = []
    avg_metrics = {
        "greedy": {},
        "hungarian": {},
        "auction": {},
    }

    for seed in seed_list:
        scenario = generate_scenario(seed=seed)
        g = run_greedy(scenario)
        h = run_hungarian(scenario)
        a = run_auction(scenario)

        all_results.append({
            "seed": seed,
            "greedy": g.metrics,
            "hungarian": h.metrics,
            "auction": a.metrics,
        })

        # Accumulate for averages
        for key in g.metrics:
            if isinstance(g.metrics[key], (int, float)):
                avg_metrics["greedy"][key] = avg_metrics["greedy"].get(key, 0) + g.metrics[key]
                avg_metrics["hungarian"][key] = avg_metrics["hungarian"].get(key, 0) + h.metrics[key]
                avg_metrics["auction"][key] = avg_metrics["auction"].get(key, 0) + a.metrics[key]

    # Calculate averages
    n = len(seed_list)
    for algo in avg_metrics:
        for key in avg_metrics[algo]:
            avg_metrics[algo][key] = round(avg_metrics[algo][key] / n, 2)

    return {
        "seeds": seed_list,
        "per_seed": all_results,
        "averages": avg_metrics,
    }