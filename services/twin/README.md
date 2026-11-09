# twin (Python, FastAPI) · port 8085

Digital twin of the grid and the mobile network: ~20 transformers, ~2,000 meters on real
Melbourne suburbs, a minute-by-minute clock, and YAML scenarios that inject faults (power,
network, meter failure, tamper). Every run is seeded and saves the true cause separately, so
the eval can score the engine.

Plan: graph (#6) → scenario format (#9) → clock + state (#12) → fault models (#18, #21, #28, #31)
→ calibration (#23) → real suburbs (#26) → seeds + ground truth (#32) → Cloud Run service (#35).

    uv sync && uv run pytest && uv run ruff check .
    uv run uvicorn twin.main:app --reload --port 8085
