"""Overlay charts, 7.0.45 against the 8.3.7 reference, in the harness's style.

Usage, from the repo root:
    .venv/bin/python compare/overlay_charts.py \
        measurements/merged/<stamp>__recollect_figures

Colour carries what it carries in harness.analyse (write concern on the ack
CDF, read path on the freshness curves); line style carries the version:
solid = 7.0.45, dashed = 8.3.7.

  ack_cdf_overlay.png              write ack latency CDF per write concern,
                                   rs-primary-local cells, from the raw
                                   writes of the runs in each sources.csv
  freshness_from_ack_overlay.png   P(fresh) for rs-secondary-majority,
  freshness_from_start_overlay.png rs-secondary-local and
                                   rs-secondary-causal-majority, w:1 and
                                   w:"majority", from curve_{ack,start}.csv

The ack CDF uses the same selection as harness.analyse (non-warmup writes with
no error, both rounds pooled), and checks that its quantiles reproduce each
version's ack_by_write_concern.csv before drawing.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness.analyse import (AXIS, CONFIG_ORDER, HIGHLIGHT, INK, INK2, MUTED,  # noqa: E402
                             SLOTS, WC_LABEL, _log_ticks, _plt, _read_jsonl,
                             _style)

REF = (Path.home() / "Documents/honours-mongodb/measurements/merged"
       / "20261019T030223Z__recollect_figures")
NEW, OLD = "7.0.45", "8.3.7"
STYLE = {NEW: "-", OLD: (0, (4, 2))}
OUT = ROOT / "compare"


def ack_latencies(figures: Path) -> dict[str, np.ndarray]:
    """Ack latency (ms) per config, rs-primary-local runs of one plan."""
    measurements = figures.parent.parent
    src = pd.read_csv(figures / "sources.csv")
    out = {}
    for cfg in CONFIG_ORDER:
        ids = src[(src["config"] == cfg) & (src["target"] == "rs-primary-local")]["run_id"]
        xs = []
        for rid in ids:
            w = _read_jsonl(measurements / rid, "writes.jsonl")
            xs.append(w[w["error"].isna() & ~w["warmup"]]["latency_ns"].to_numpy())
        if xs:
            out[cfg] = np.sort(np.concatenate(xs)) / 1e6
    return out


def check_against_table(lat: dict, figures: Path, version: str) -> None:
    t = pd.read_csv(figures / "ack_by_write_concern.csv").set_index("config")
    for cfg, a in lat.items():
        got = [len(a)] + [np.quantile(a, q) for q in (.01, .5, .9, .99)] + [a[-1]]
        want = t.loc[cfg, ["n", "p01_ms", "p50_ms", "p90_ms", "p99_ms", "max_ms"]].tolist()
        if not np.allclose(got, want, rtol=1e-9, atol=1e-9):
            sys.exit(f"{version} {cfg}: raw writes give {got}, table says {want}")


def fig_ack_cdf(lat: dict[str, dict], out: Path) -> Path:
    plt = _plt()
    from matplotlib.lines import Line2D
    fig, ax = plt.subplots(figsize=(10.0, 4.2))
    handles = []
    for slot, cfg in enumerate(CONFIG_ORDER):
        for v in (NEW, OLD):
            a = lat[v][cfg]
            y = np.arange(1, len(a) + 1) / len(a)
            ax.plot(a, y, color=SLOTS[slot], lw=2, ls=STYLE[v],
                    solid_capstyle="round", dash_capstyle="round")
            handles.append(Line2D([], [], color=SLOTS[slot], lw=2, ls=STYLE[v], label=(
                f"{WC_LABEL[cfg]} {v}   median {np.quantile(a, .5):.2f} ms, "
                f"p99 {np.quantile(a, .99):.2f} ms")))
    ax.set_xscale("log")
    _log_ticks(ax, *ax.get_xlim())
    ax.set_ylim(0, 1.01)
    ax.set_xlabel("Write acknowledgement latency (ms, log scale)")
    ax.set_ylabel("Share of writes acknowledged")
    ax.set_title(f"Write acknowledgement by write concern, {NEW} vs {OLD}",
                 loc="left", color=INK, fontweight="semibold")
    ax.legend(handles=handles, loc="center left", bbox_to_anchor=(1.01, 0.5),
              fontsize=7.5, labelcolor=INK2)
    _style(ax, "both")
    fig.text(0.01, 0.005, f"Solid = {NEW}, dashed = {OLD}. rs-primary-local cells only, "
             "both rounds pooled, warmup and errors excluded. Writes every 100 ms.",
             color=MUTED, fontsize=7)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    path = out / "ack_cdf_overlay.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def fig_freshness(curves: dict[str, pd.DataFrame], anchor: str, bucket_us: int,
                  xmax_ms: float, out: Path) -> Path:
    plt = _plt()
    from matplotlib.lines import Line2D
    configs = ["threaded-w1", "threaded-wmaj"]
    fig, axes = plt.subplots(1, 2, figsize=(10.0, 3.9), sharey=True)
    grid = range(0, int(xmax_ms * 1000), bucket_us)
    for ax, cfg in zip(axes, configs):
        for tgt, _, color in HIGHLIGHT:
            for v in (OLD, NEW):
                g = curves[v]
                s = g[(g["config"] == cfg) & (g["target"] == tgt)]
                # Same rule as harness.analyse: break the line at buckets that
                # are missing or under the minimum sample.
                s = s.set_index("bucket_us").reindex(grid)
                bad = ~s["adequate"].fillna(False).astype(bool)
                s.loc[bad, ["p_fresh", "ci_low", "ci_high"]] = float("nan")
                if s["p_fresh"].isna().all():
                    continue
                x = (s.index + bucket_us / 2) / 1000
                ax.fill_between(x, s["ci_low"], s["ci_high"], color=color,
                                alpha=0.10, lw=0, zorder=2)
                ax.plot(x, s["p_fresh"], color=color, lw=2, ls=STYLE[v],
                        zorder=3 if v == NEW else 4, solid_capstyle="round",
                        dash_capstyle="round", solid_joinstyle="round")
        ax.set_title(WC_LABEL[cfg], loc="left", color=INK, fontweight="semibold")
        ax.set_xlim(0, xmax_ms)
        ax.set_ylim(-0.02, 1.02)
        _style(ax, "both")
        ax.set_xlabel("Time since the write was "
                      + ("sent" if anchor == "start" else "acknowledged") + " (ms)")
    axes[0].set_ylabel("Share of reads returning the newest write")
    handles = [Line2D([], [], color=c, lw=2, label=lab) for _, lab, c in HIGHLIGHT]
    handles += [Line2D([], [], color=AXIS, lw=2, ls=STYLE[v], label=v) for v in (NEW, OLD)]
    fig.legend(handles=handles, loc="upper left", ncol=5, fontsize=8,
               bbox_to_anchor=(0.01, 1.0), labelcolor=INK2)
    note = ("Newest write = the one most recently sent; reads during the write window count."
            if anchor == "start" else
            "Newest write = the one most recently acknowledged; reads while a write was in flight are excluded.")
    fig.text(0.01, 0.005, f"Solid = {NEW}, dashed = {OLD}. {note} Shaded: 95% Wilson "
             f"interval. {bucket_us} us buckets; gaps are buckets under the minimum sample. "
             "Lines at 1.0 overlap.",
             color=MUTED, fontsize=7)
    fig.tight_layout(rect=(0, 0.04, 1, 0.92))
    path = out / f"freshness_from_{anchor}_overlay.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("new_figures", type=Path, help=f"figures folder of the {NEW} plan")
    ap.add_argument("--ref-figures", type=Path, default=REF,
                    help=f"figures folder of the {OLD} plan")
    ap.add_argument("--xmax-ms", type=float, default=20.0)
    ap.add_argument("--bucket-us", type=int, default=500)
    args = ap.parse_args()
    figs = {NEW: args.new_figures, OLD: args.ref_figures}

    lat = {}
    for v, f in figs.items():
        lat[v] = ack_latencies(f)
        check_against_table(lat[v], f, v)
        print(f"[compare] {v}: ack latencies match {f.name}/ack_by_write_concern.csv")
    written = [fig_ack_cdf(lat, OUT)]
    for anchor in ("ack", "start"):
        curves = {v: pd.read_csv(f / f"curve_{anchor}.csv") for v, f in figs.items()}
        written.append(fig_freshness(curves, anchor, args.bucket_us, args.xmax_ms, OUT))
    for p in written:
        print(f"  {p.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
