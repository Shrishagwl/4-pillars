# eval (Python, offline)

Runs many seeded fault scenarios through the digital twin, feeds the events to the engine and
to two baselines, and measures how well each one finds the real cause. Everything runs in one
Python process with `twin` and `engine` imported as libraries (no services, no network), so
200 runs take seconds and give the same numbers every time.

    uv sync && uv run pytest
    uv run pillars-eval run          --seeds 50 --out results/
    uv run pillars-eval ablations    --seeds 50 --out results/
    uv run pillars-eval sensitivity  --seeds 20 --out results/

| File | What it does |
|---|---|
| `sim.py` | Builds a one-fault twin scenario, runs the twin and turns it into a `Run` |
| `systems.py` | What we compare: the engine (v1 rules or v2 model), B0 and B1 |
| `runner.py` | Batch runner (#27): every system on the same seeds, results to disk |
| `metrics.py` | Metrics and the results table (#38) |
| `training.py` | Training examples for the v2 model, from separate seeds (#33) |
| `experiments.py` | Ablations, API-improvement tests (#42) and sensitivity tests (#45) |

## Systems

- **engine-v1**: the hand-written rules. **engine-v2**: the naive Bayes model.
- **B0**: send a technician to any meter silent for 15 minutes, one job per transformer.
- **B1**: the same, but first ask the Outage API about each silent meter's suburb and wait if
  an outage is listed (#34).

## Metrics

Accuracy, macro F1, affected-meter Jaccard, time to a correct verdict, false dispatches,
avoidable cost and dollars saved against B0, Telstra API calls, and Brier score (calibration).

## Results (50 seeds per fault type, `results/`)

| System | Accuracy | False dispatches / run | Cost / run | Brier |
|---|---|---|---|---|
| engine-v1 | 81% | 0.00 | $89 | 0.357 |
| engine-v2 | 94% | 1.71 | $1,119 | 0.114 |
| B0 | 25% | 3.76 | $3,101 | 1.500 |
| B1 | 28% | 2.86 | $2,557 | 1.440 |

- Both engine versions beat both baselines on every metric. v2 beats v1 on accuracy and
  calibration (#33), mostly on meter faults (72% to 100%) and tampers (58% to 84%).
- **v1 is still cheaper.** v2's extra cost is background dropouts: a meter that loses signal
  for 5 to 15 minutes looks exactly like a dead meter when its code 7 arrives, and v2 is sure
  enough to send a technician. v1 sends those to manual review. Waiting a few minutes before
  dispatching to a single silent meter is the obvious next fix.
- **Ablations:** the last-gasp clue matters most (94% to 73% without it), then Location
  Verification (to 88%). The other clues barely move the score on their own.
- **Proposed API changes:** exact outage areas take v1 from 81% to 88%, and both changes
  together to 90%. A restore event cuts B0's wasted jobs by a quarter.
- **Sensitivity:** v1 falls apart when few meters send a last gasp (51% at 0 to 25%). v2 holds
  up until there are none at all (72%). Heavy background noise (60 dropouts an hour) hurts
  everything.

## Read the numbers with these limits in mind

- **The twin's settings are not all researched.** See `docs/twin-settings.md`: the last-gasp
  rate, the Outage API delay and the network outage size are still guesses, and the code 7
  delay is an open question. The sensitivity tests show how much each one matters.
- **The stale outage listing is added by the eval, not the twin.** A quarter of non-network
  runs get an older outage still listed for the same suburb, to test the "check the Outage
  API" rule. Set `stale_outage_rate=0` to switch it off.
- **The v2 model is trained and tested on the same twin** (different seeds). Its score shows it
  learned the twin, not that it will do as well on real data.
- **Dollar values** come from `docs/decision-costs.md` (#8).
