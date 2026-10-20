# Notes

## 2026-10-20: round-agreement flag in the 7.0.45 re-collect

Plan `runs/plans/20261020T103929Z__recollect.json` (seed 1999558622, 36 runs, all `ok`).
`scripts/val_report.py --plan` flags 1 of 18 cells on round agreement
(`runs/plans/20261020T103929Z__recollect_report.txt`, last section):

| cell | metric | r1 | r2 | rel. diff | threshold |
|---|---|---|---|---|---|
| threaded-wmaj / rs-secondary-causal-majority | median ack latency | 10.581 ms | 13.022 ms | **23.1%** | 20% |

Its median read latency agrees (0.166 / 0.162 ms, 2.3%), and so does its stale rate (0 in both
rounds). Every other check passed: no expect refusals or fatals, wire log as spec 7.5,
operationTime check PASS on all 8 causal runs, `harness.runs check` 0 problems, every run
7.0.45 / FCV 7.0. The 8.3.7 reference flagged 0 of 18 cells. The data is kept as collected.

**The flagged r1 run was the first cell after a fresh `rs.initiate`.** The set in
`~/mongo-rs-7.0.45` was bootstrapped (spec 11 step 3); `replSetInitiate` was received at
10:38:35 UTC (`n0/mongod.log`, id 21356). Run 1
(`20261020T103929Z__threaded-wmaj__rs-secondary-causal-majority__r1`) started at 10:39:29 UTC,
54 s later, on a set that had taken no writes beyond the initiate itself.

**The other early w:"majority" runs were also lower.** Median ack latency of every
threaded-wmaj run, in execution order (linearizable is higher in both rounds, as on 8.3.7):

| run | round, position | target | ack p50 (ms) |
|---|---|---|---|
| 1 | r1, 1 | rs-secondary-causal-majority | **10.581** |
| 3 | r1, 3 | rs-secondary-local | **11.070** |
| 6 | r1, 6 | rs-primary-local | 12.576 |
| 10 | r1, 10 | rs-primary-linearizable | 16.539 |
| 13 | r1, 13 | rs-secondary-causal-local | 12.776 |
| 17 | r1, 17 | rs-secondary-majority | 12.673 |
| 22 | r2, 4 | rs-primary-linearizable | 16.931 |
| 25 | r2, 7 | rs-primary-local | 13.023 |
| 26 | r2, 8 | rs-secondary-causal-local | 13.029 |
| 28 | r2, 10 | rs-secondary-causal-majority | 13.022 |
| 34 | r2, 16 | rs-secondary-majority | 12.736 |
| 35 | r2, 17 | rs-secondary-local | 12.675 |

Only runs 1 and 3 fall below 12.5 ms. rs-secondary-local, run 3, differs by 14.5% between
rounds (11.070 / 12.675), under the threshold but in the same direction. From run 6 on, every
non-linearizable w:"majority" run lies between 12.5 and 13.1 ms.

**Interpretation: a suspected warm-up effect of the newly initiated set, not proven.** The
pattern fits a cold set (first ~10 minutes after `rs.initiate`) acknowledging majority writes
faster, but nothing here tests that. Testing it would need, for example, a second plan on the
already-warm set, or a fresh initiate followed by repeated runs of one cell. Neither was run.
`compare/` reports the w:"majority" version gap both pooled and from round 2 only, so the
comparison with 8.3.7 does not rest on the early runs.
