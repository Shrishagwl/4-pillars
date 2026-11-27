"""Make training examples for the v2 model from simulated runs, and train it.

One example = the clues of the real fault's cluster at one moment + the real cause.
We take several moments per run (early, middle, late) because the engine has to score a
cluster while it is still growing, not only once everything has arrived.

The model is trained on seeds 1000+ and scored on seeds 0-49, so it is never tested on a run
it has already seen. That gap is what makes "beats v1 on held-out runs" a fair claim.
"""

from collections.abc import Collection, Iterable, Sequence
from datetime import timedelta
from functools import lru_cache

from engine.bayes import NaiveBayes
from engine.clues import Clues, compute_clues
from engine.clustering import cluster_silent_meters
from engine.contracts import Cause

from .runner import cached_run
from .sim import KINDS, SimSettings
from .systems import EngineSystem

TRAIN_SEEDS = range(1000, 1100)
# Seconds after the fault at which we take an example.
SNAPSHOTS_S = (60, 180, 300, 480, 780, 1200, 1800)


@lru_cache(maxsize=32)
def training_examples(
    settings: SimSettings = SimSettings(),  # noqa: B008  (frozen, safe as a default)
    seeds: Iterable[int] = TRAIN_SEEDS,
    kinds: Sequence[str] = KINDS,
    outage_shapes: bool = False,
    restore_events: bool = False,
) -> tuple[tuple[Clues, Cause], ...]:
    # Borrow the engine system's view of the world so training sees what scoring will see.
    view = EngineSystem(outage_shapes=outage_shapes, restore_events=restore_events)
    examples = []
    for kind in kinds:
        for seed in seeds:
            run = cached_run(kind, seed, settings)
            topology = run.grid.topology
            for seconds in SNAPSHOTS_S:
                now = min(run.fault_at + timedelta(seconds=seconds), run.end)
                signals = view.signals(run, now)
                clusters = cluster_silent_meters(
                    run.events_until(now), topology, now, restored=signals.restored
                )

                def overlap(cluster, truth=run.truth_meter_ids) -> int:
                    return sum(1 for m in cluster.members if m.meter.meter_id in truth)

                main = max(clusters, key=overlap, default=None)
                if main is None or overlap(main) == 0:
                    continue  # nothing of the fault has shown up yet
                clues = compute_clues(
                    main,
                    topology,
                    signals.outage_suburbs,
                    outage_msisdns=signals.outage_msisdns,
                    moved_msisdns=signals.moved_msisdns,
                )
                examples.append((clues, run.truth))
    return tuple(examples)


def train_v2(
    settings: SimSettings | None = None,
    drop: Collection[str] = (),
    outage_shapes: bool = False,
    restore_events: bool = False,
) -> NaiveBayes:
    examples = training_examples(
        settings or SimSettings(), outage_shapes=outage_shapes, restore_events=restore_events
    )
    return NaiveBayes.fit(examples, drop=drop)


def v2_system(
    model: NaiveBayes,
    name: str = "engine-v2",
    outage_shapes: bool = False,
    restore_events: bool = False,
) -> EngineSystem:
    return EngineSystem(
        name=name, scorer=model.score, outage_shapes=outage_shapes, restore_events=restore_events
    )
