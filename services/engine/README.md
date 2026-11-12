# engine (Python, FastAPI) · port 8084

Takes silent-meter events, groups them into incidents, scores the likely cause
(power / network / meter fault / tamper), picks the cheapest action by expected cost, and
explains why. Calls Telstra only through telstra-gateway.

Plan: clustering (#11) → clues (#15) → v1 rules (#19) → v2 naive Bayes (#33) → expected-cost
action (#37) → evidence (#39) → re-scoring (#40). Cloud Run service: #24.

    uv sync && uv run pytest && uv run ruff check .
    uv run uvicorn engine.main:app --reload --port 8084
