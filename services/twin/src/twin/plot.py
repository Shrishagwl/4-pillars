"""Draw the twin (#6): meters coloured by transformer, and the same meters coloured by suburb.

    uv run python -m twin.plot --seed 42 --out twin_seed42.png

Put the two panels side by side and the key idea is visible: transformer clusters (left) cut
across the suburb borders (right). matplotlib is a dev-only dependency, so the service image
doesn't carry it.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .grid import Twin, build_twin


def plot_twin(twin: Twin, out: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")  # draw to a file, no window needed
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    fig, (by_tf, by_sub) = plt.subplots(1, 2, figsize=(14, 7), sharex=True, sharey=True)
    lons = [m.lon for m in twin.meters]
    lats = [m.lat for m in twin.meters]

    tf_index = {t.id: i for i, t in enumerate(twin.transformers)}
    by_tf.scatter(
        lons, lats, s=4, c=[tf_index[m.transformer_id] for m in twin.meters], cmap="tab20"
    )
    by_tf.scatter(
        [t.lon for t in twin.transformers],
        [t.lat for t in twin.transformers],
        marker="^",
        s=60,
        c="black",
        label="transformer",
    )
    by_tf.set_title(f"Coloured by transformer ({len(twin.transformers)})")
    by_tf.legend(loc="upper right")

    sub_index = {s.name: i for i, s in enumerate(twin.suburbs)}
    by_sub.scatter(lons, lats, s=4, c=[sub_index[m.suburb] for m in twin.meters], cmap="Set2")
    by_sub.set_title(f"Coloured by suburb ({len(twin.suburbs)})")

    for ax in (by_tf, by_sub):
        for s in twin.suburbs:
            ax.add_patch(
                Rectangle(
                    (s.west, s.south),
                    s.east - s.west,
                    s.north - s.south,
                    fill=False,
                    linewidth=1,
                    linestyle="--",
                    edgecolor="grey",
                )
            )
            ax.text(
                (s.west + s.east) / 2,
                s.north - 0.001,
                f"{s.name} {s.postcode}",
                ha="center",
                va="top",
                fontsize=8,
                color="dimgrey",
            )
        ax.ticklabel_format(useOffset=False)  # show 144.95, not 0.05 + 1.449e2
        ax.set_xlabel("longitude")
        ax.set_aspect(1 / 0.79)  # 1 / cos(37.75 deg), so a km looks the same both ways
    by_tf.set_ylabel("latitude")

    fig.suptitle(f"Grid twin, seed {twin.seed}: {len(twin.meters)} meters")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    out = args.out or Path(f"twin_seed{args.seed}.png")
    print(plot_twin(build_twin(args.seed), out))


if __name__ == "__main__":
    main()
