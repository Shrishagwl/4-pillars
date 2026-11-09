# eval (Python, offline)

Runs the digital twin over many seeded scenarios, feeds the events to the engine and to the
baselines, and measures how well each one finds the real cause. Uses `engine` and `twin` as
local libraries (no network), so a full batch is quick and repeatable. Results and charts go
in the submission.

Baselines: B0 fixed 15-minute-gap dispatch, B1 per-meter Outage API check.
Metrics: macro F1, affected-meter Jaccard, time to verdict, false dispatches, dollars saved,
API calls, calibration (Brier).

Plan: batch runner (#27) → baselines (#34) → metrics (#38) → ablations + API what-ifs (#42)
→ sensitivity (#45).

    uv sync && uv run pytest
    uv run pillars-eval run --seeds 50 --out results/
