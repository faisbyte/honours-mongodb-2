"""Per-cell comparison of the 7.0.45 re-collect against the 8.3.7 reference.

Usage, from the repo root:
    .venv/bin/python compare/compare_cells.py \
        measurements/merged/<stamp>__recollect_figures

Reads cells.csv from both figure folders (both made by harness.analyse --plan)
and writes compare/cells_7.0.45_vs_8.3.7.csv: one row per cell, the two
versions side by side, then the ratio 7.0.45 / 8.3.7 for each metric.

A metric is flagged when the two versions differ by more than 20%, with the
same rule val_report.py uses for round agreement: larger / smaller - 1 > 0.20.
Both zero is no difference; one zero and the other not is flagged (ratio inf
or 0), so check the stale counts before reading much into a stale-rate flag.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness.analyse import CONFIG_ORDER, TARGET_ORDER, WC_LABEL  # noqa: E402

REF = (Path.home() / "Documents/honours-mongodb/measurements/merged"
       / "20261019T030223Z__recollect_figures")
NEW, OLD = "7.0.45", "8.3.7"
METRICS = ["stale_rate", "read_p50_ms", "read_p90_ms", "read_p99_ms",
           "ack_p50_ms", "ack_p99_ms"]
THRESHOLD = 0.20
OUT = ROOT / "compare" / f"cells_{NEW}_vs_{OLD}.csv"


def rel_diff(a: float, b: float) -> float:
    lo, hi = sorted((a, b))
    if hi == 0:
        return 0.0
    return float("inf") if lo == 0 else hi / lo - 1


def ratio(a: float, b: float) -> float:
    if b == 0:
        return 1.0 if a == 0 else float("inf")
    return a / b


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("new_figures", type=Path,
                    help=f"figures folder of the {NEW} plan")
    ap.add_argument("--ref-figures", type=Path, default=REF,
                    help=f"figures folder of the {OLD} plan")
    args = ap.parse_args()

    key = ["config", "target"]
    new = pd.read_csv(args.new_figures / "cells.csv")
    old = pd.read_csv(args.ref_figures / "cells.csv")
    m = new.merge(old, on=key, how="outer", suffixes=(f"_{NEW}", f"_{OLD}"),
                  indicator=True)
    missing = m[m["_merge"] != "both"]
    if len(missing):
        sys.exit(f"cells present in only one version:\n{missing[key]}")

    rows = []
    for _, r in m.iterrows():
        row = {"config": r["config"], "write_concern": WC_LABEL[r["config"]],
               "target": r["target"]}
        for v in (NEW, OLD):
            row[f"runs_{v}"] = r[f"runs_{v}"]
        for v in (NEW, OLD):
            row[f"stale_{v}"] = r[f"stale_{v}"]
            row[f"stale_of_{v}"] = r[f"stale_of_{v}"]
        flags = []
        for k in METRICS:
            a, b = r[f"{k}_{NEW}"], r[f"{k}_{OLD}"]
            row[f"{k}_{NEW}"], row[f"{k}_{OLD}"] = a, b
            row[f"{k}_ratio"] = ratio(a, b)
            if rel_diff(a, b) > THRESHOLD:
                flags.append(k)
        row["n_flagged"] = len(flags)
        row["flagged"] = " ".join(flags)
        rows.append(row)

    out = pd.DataFrame(rows)
    out["_c"] = out["config"].map(CONFIG_ORDER.index)
    out["_t"] = out["target"].map(TARGET_ORDER.index)
    out = out.sort_values(["_c", "_t"]).drop(columns=["_c", "_t"])
    out.to_csv(OUT, index=False)

    show = ["write_concern", "target"] + [f"{k}_ratio" for k in METRICS] + ["flagged"]
    with pd.option_context("display.width", 200, "display.max_columns", None,
                           "display.float_format", "{:.2f}".format):
        print(out[show].to_string(index=False))
    print(f"\n{(out['n_flagged'] > 0).sum()} of {len(out)} cells have at least one "
          f"metric differing by more than {THRESHOLD:.0%}")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
