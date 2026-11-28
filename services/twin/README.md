# twin (Python, FastAPI) · port 8085

A digital twin of a small piece of Melbourne: about 2,000 smart meters, the 20 street
transformers that power them, and the suburbs Telstra reports network outages by. We break
things in it on purpose (a transformer, the mobile network, one meter, a stolen meter) and it
produces the same Loss of Connectivity reports Telstra would send. Because we caused each
fault, every run comes with an answer key, which is what the eval scores the engine against.

    uv sync
    uv run pytest -q && uv run ruff check . && uv run ruff format --check .

## Try it

    # run every scenario 10 times (seeds 0-9) and write the results to runs/
    uv run python -m twin run scenarios/*.yaml --seeds 10

    # draw the map: meters coloured by transformer and by suburb
    uv run python -m twin.plot --seed 42

    # or from Python
    from twin.scenario import load_scenario
    from twin.run import run_scenario
    result = run_scenario(load_scenario("scenarios/power-outage.yaml"), seed=1)

`runs/` and the plot images are ignored by git: they can be made again from the seeds at any time.

## How it fits together

| File | What it does | Issue |
|---|---|---|
| `grid.py` | `build_twin(seed)`: suburbs, transformers, meters. Same seed, same map. | #6 |
| `clock.py` | `TwinClock`: moves time one minute at a time; each meter has three switches (`powered`, `connected`, `healthy`) and sends a heartbeat every 15 minutes while all three are on. | #12 |
| `scenario.py` | Reads and checks scenario files (YAML). Typos and impossible numbers fail on load. | #9 |
| `faults.py` | What each fault does to the meters, and the LoC reports it causes. | #18, #21, #28, #31 |
| `run.py` | `run_scenario(scenario, seed)`: plays a scenario and returns what happened. | #18, #32 |
| `export.py`, `__main__.py` | Writes runs to files; the `python -m twin run` command. | #32 |
| `plot.py` | The map picture. | #6 |

The map is four real neighbouring Melbourne suburbs: Coburg (3058), Brunswick (3056),
Brunswick West (3055) and Pascoe Vale South (3044), using the ABS SAL 2021 boundaries in
`src/twin/data/suburbs.geojson` (simplified to ~10 m). Meters cluster around their
transformer, so transformers near a border feed meters in two suburbs. That overlap matters:
a power outage follows a transformer, a network outage follows a suburb, and if the two
matched exactly the engine could never tell them apart.

## The faults

| Kind | Answer | What happens | LoC codes |
|---|---|---|---|
| `power` | POWER | Every meter on one transformer drops within 10 s. | ~70% a last gasp (code 0 on 4G, 6 on 5G) at once, the rest a timeout (2 or 7) two to four minutes later |
| `network` | NETWORK | 60-90% of one suburb loses signal over ~3 minutes, across many transformers. Telstra lists the outage 10-30 minutes in. | all detection timeouts, code 2 (4G) or 7 (5G): the meters still have power, so no last gasp |
| `meter` | METER_FAULT | One meter dies on its own; a technician replaces it later. | one timeout (2 or 7) |
| `tamper` | TAMPER | One meter is unplugged and taken away; 5-30 minutes later its SIM comes back online 2-10 km away. | one last gasp or timeout; then Location Verification would answer FALSE for its address |
| `noise` (not a fault) | none | A normal day: now and then a meter loses signal for 1-15 minutes and comes back by itself. | a timeout only if it outlasts the detection timer |

The default numbers match the engine's own test fixtures. They still need checking against
real-world research (#23).

## Scenario files

    name: power-outage
    description: One transformer fails around 02:00 and power is back 1 to 2 hours later.
    twin_seed: 42                  # which map; the same for every run of this scenario
    duration_min: 300
    faults:
      - kind: power
        at_min: [100, 140]         # a window: each run picks a minute inside it
        transformer: random        # or a real id like T-07
        restore_after_min: [60, 120]

- Any target can be `random`, and any time can be a fixed minute (`120`) or a window
  (`[100, 140]`). The run's seed picks both, so seeds vary where and when.
- Every setting in the table above can be overridden per fault, for example
  `last_gasp_share: 0.5` for a harder power case. See the classes in `scenario.py` for the full
  list and defaults.
- Add `noise:` at the top level for background dropouts (see `normal-day.yaml`).
- To add a scenario, copy a file in `scenarios/` and change it. A test loads every file in
  that folder, so a broken one fails `pytest`.

## What a run gives you

`run_scenario(scenario, seed)` returns a `RunResult`:

| Field | What it is | Who may look |
|---|---|---|
| `loc_reports` | LoC reports in time order (`to_telstra()` gives Telstra's JSON) | the engine |
| `outages` | network outages and the time Telstra lists each one (`listed_at`) | the engine, from `listed_at` on |
| `moved_msisdns(at)` | SIMs online away from their meter's address at time `at` (Location Verification) | the engine |
| `heartbeats` | every heartbeat | ingest / dashboard |
| `answer_key` | the truth: cause, target, start, repair, the meters actually silenced | the eval only |
| `background` | the truth about normal-day dropouts (not incidents) | the eval only |

`python -m twin run` writes the same things to `runs/<scenario>/seed-NNN/`, with the answer
key and background always in their own files, apart from the events.

For the eval (#27), skip the files: build the engine's `Topology` from
`build_twin(scenario.twin_seed).meters` (the first four `Meter` fields match the engine's), turn
each `LocReport` into a `MeterSilentEvent`, and score the verdicts against `answer_key`.

## Not done yet

- **#35 Cloud Run service.** `main.py` is still the template. The plan is endpoints to start a
  scenario and stream its events to telstra-fake and ingest-api.

## Attribution

Suburb boundaries: Australian Bureau of Statistics, Australian Statistical Geography Standard
(ASGS) Edition 3, Suburbs and Localities (SAL) 2021, licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Queried from the ABS ASGS 2021 SAL map
service and simplified.
