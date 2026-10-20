"""Sensitivity check: is the w:"majority" ack-latency gap a warm-up artefact?

Usage, from the repo root:
    .venv/bin/python compare/wmaj_ack_sensitivity.py \
        measurements/merged/<stamp>__recollect_figures

In the 7.0.45 re-collect the first threaded-wmaj runs after rs.initiate were
faster to acknowledge than later ones (NOTES.md). This compares write ack
latency of every threaded-wmaj cell between 7.0.45 and 8.3.7 twice: both rounds
pooled (as in cells.csv) and round 2 only, where every 7.0.45 threaded-wmaj
run started at least 44 minutes after the initiate. "all non-linearizable" pools the five
cells whose writer is not competing with linearizable reads.

Same selection as harness.analyse: non-warmup writes with no error; numpy
linear quantiles. Writes compare/wmaj_ack_sensitivity.csv.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness.analyse import TARGET_ORDER, _read_jsonl  # noqa: E402

REF = (Path.home() / "Documents/honours-mongodb/measurements/merged"
       / "20261019T030223Z__recollect_figures")
NEW, OLD = "7.0.45", "8.3.7"
CONFIG = "threaded-wmaj"
OUT = ROOT / "compare" / "wmaj_ack_sensitivity.csv"


def acks(figures: Path) -> pd.DataFrame:
    """One row per run: target, round, ack latencies (ms)."""
    measurements = figures.parent.parent
    src = pd.read_csv(figures / "sources.csv")
    rows = []
    for _, s in src[src["config"] == CONFIG].iterrows():
        w = _read_jsonl(measurements / s["run_id"], "writes.jsonl")
        a = w[w["error"].isna() & ~w["warmup"]]["latency_ns"].to_numpy() / 1e6
        rows.append({"target": s["target"], "round": int(s["round"]), "ack_ms": a})
    return pd.DataFrame(rows)


def stats(runs: pd.DataFrame) -> dict:
    a = np.concatenate(runs["ack_ms"].to_list())
    return {"runs": len(runs), "n": len(a), "p50": np.quantile(a, .5),
            "p90": np.quantile(a, .9), "p99": np.quantile(a, .99)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("new_figures", type=Path, help=f"figures folder of the {NEW} plan")
    ap.add_argument("--ref-figures", type=Path, default=REF,
                    help=f"figures folder of the {OLD} plan")
    args = ap.parse_args()
    data = {NEW: acks(args.new_figures), OLD: acks(args.ref_figures)}

    groups = [(t, [t]) for t in TARGET_ORDER if t in set(data[NEW]["target"])]
    groups.append(("all non-linearizable",
                   [t for t, _ in groups if t != "rs-primary-linearizable"]))
    rows = []
    for name, targets in groups:
        for sel, rounds in (("pooled", (1, 2)), ("round 2", (2,))):
            row = {"cell": name, "rounds": sel}
            for v, d in data.items():
                s = stats(d[d["target"].isin(targets) & d["round"].isin(rounds)])
                for k, x in s.items():
                    row[f"{k}_{v}"] = x
            for q in ("p50", "p90", "p99"):
                row[f"{q}_ratio"] = row[f"{q}_{NEW}"] / row[f"{q}_{OLD}"]
            rows.append(row)
    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)

    show = ["cell", "rounds", f"runs_{NEW}", f"p50_{NEW}", f"p50_{OLD}", "p50_ratio",
            f"p99_{NEW}", f"p99_{OLD}", "p99_ratio"]
    with pd.option_context("display.width", 200, "display.float_format", "{:.3f}".format):
        print(out[show].to_string(index=False))
    print(f"\nwrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
