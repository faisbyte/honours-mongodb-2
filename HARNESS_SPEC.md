# Harness specification: client-side freshness measurement, MongoDB replica set

Reference implementation: `honours-mongodb` at commit **a157159f11431e9b2649b9fbc5eee748448e7cef**.
Reference dataset: plan `runs/plans/20261019T030223Z__recollect.json`, collected at commit
**7ef826be13c3c289c26fb66e39c0feb7a80d1d97** (clean tree). Between those two commits only
`harness/analyse.py`, `harness/runs.py` (adds `plan_run_ids`) and `scripts/val_report.py`
(uses it) changed. `harness/collect.py`, `harness/wire.py`, `harness/provenance.py`,
`scripts/recollect.py`, `scripts/start.sh`, `scripts/stop.sh` and every file in `config/` are
byte-identical, so the exported code collects exactly what the reference dataset collected.

A replica is identical when everything below matches except the `mongod` binary (and the
values that necessarily follow from it: version strings, FCV, git hash, data paths). Section 12
lists every place the server version enters.

---

## 1. Versions

### Client

| Item | Reference value |
|---|---|
| Python | 3.12.7, Anaconda build: `3.12.7 \| packaged by Anaconda, Inc. \| (main, Oct  4 2024, 08:22:19) [Clang 14.0.6 ]` |
| Virtualenv | `.venv` created from that interpreter, pip 24.2 |
| pymongo | 4.18.0 (pulls in dnspython 2.8.0) |
| Full `pip freeze` | in `requirements-lock.txt` in the export, reproduced here |

```
contourpy==1.3.3
cycler==0.12.1
dnspython==2.8.0
fonttools==4.64.0
kiwisolver==1.5.1
matplotlib==3.11.1
numpy==2.5.3
packaging==26.3
pandas==3.0.5
pillow==12.3.0
pyarrow==25.0.1
pymongo==4.18.0
pyparsing==3.3.2
python-dateutil==2.9.0.post0
PyYAML==6.0.3
six==1.17.0
```

`requirements.txt` (unpinned lower bounds: `pymongo>=4.9`, `PyYAML>=6.0`, `pandas>=2.2`,
`pyarrow>=16.0`, `matplotlib>=3.8`) is kept for history; install from `requirements-lock.txt`.

### Server and tools

| Item | Reference value |
|---|---|
| mongod | **8.3.7**, gitVersion `34eee04f34989abb7a3d91447976f033f4f74af2`, allocator `system`, OpenSSL `Apple Secure Transport`, modules `[]`, 64-bit, not debug, target_arch `arm64` |
| mongod install | Homebrew `mongodb-community` 8.3.7: `/opt/homebrew/bin/mongod` -> `/opt/homebrew/Cellar/mongodb-community/8.3.7/bin/mongod` |
| mongosh | 2.9.2 (Homebrew, `/opt/homebrew/bin/mongosh`); used by `scripts/start.sh` and `scripts/stop.sh` only |
| Storage engine | WiredTiger, default cache: 16,642,998,272 bytes (15.5 GiB) per node, no explicit limit |

### Host

| Item | Reference value |
|---|---|
| Machine | MacBook Pro, model `Mac14,10`, Apple M2 Pro, 12 cores (12 physical), 32 GB, arm64, page size 16 KB |
| OS | macOS 27.0.1 (build 26A434); Python reports `macOS-27.0.1-arm64-arm-64bit` |
| Clients and servers | all on the same machine, loopback (127.0.0.1) only |
| Power during the reference dataset | **battery** for all 36 runs, before and after each (recorded, not enforced; see 7.4) |

---

## 2. Replica set

### Members and settings

Four data-bearing voting members, replica set `rs0`, protocolVersion 1. From `replSetGetConfig`
recorded in every run (`provenance/repl_before.json`):

| _id | host | priority | votes | hidden | secondaryDelaySecs | arbiterOnly | buildIndexes | tags |
|---|---|---|---|---|---|---|---|---|
| 0 | 127.0.0.1:27017 | 10 | 1 | false | 0 | false | true | {} |
| 1 | 127.0.0.1:27018 | 1 | 1 | false | 0 | false | true | {} |
| 2 | 127.0.0.1:27019 | 1 | 1 | false | 0 | false | true | {} |
| 3 | 127.0.0.1:27020 | 1 | 1 | false | 0 | false | true | {} |

Majority of voting members: 3 of 4.

| Setting | Value |
|---|---|
| `writeConcernMajorityJournalDefault` | true |
| `settings.chainingAllowed` | **false** |
| `settings.heartbeatIntervalMillis` | 2000 |
| `settings.heartbeatTimeoutSecs` | 10 |
| `settings.electionTimeoutMillis` | 10000 |
| `settings.catchUpTimeoutMillis` | -1 |
| `settings.catchUpTakeoverDelayMillis` | 30000 |
| `settings.getLastErrorModes` | {} |
| `settings.getLastErrorDefaults` | `{w: 1, wtimeout: 0}` |
| Config version / term at collection | 25 / 13786 (history, not a requirement) |

Cluster-wide read/write defaults (`getDefaultRWConcern`): `defaultReadConcern {level: "local"}`,
`defaultWriteConcern {w: "majority", wtimeout: 0}`, both `implicit` (never set). The harness
sends an explicit write concern on every measured write and an explicit read concern on every
measured read; the implicit default applies only to the probe reset in 4.2.

featureCompatibilityVersion: **8.3** on all four nodes.

### mongod processes

Started by `scripts/start.sh` (or the original `~/mongo-rs/start.sh`, same flags). Recorded
`getCmdLineOpts.argv` for node i (port 27017+i):

```
mongod --replSet rs0 --port <27017+i> --dbpath <RS_DIR>/n<i> --bind_ip 127.0.0.1 --logpath <RS_DIR>/n<i>/mongod.log
```

`RS_DIR` = `$MONGO_RS_DIR`, default `~/mongo-rs`. Parsed options: `net.bindIp`, `net.port`,
`replication.replSet`, `storage.dbPath`, `systemLog.destination=file`, `systemLog.path`.
Nothing else: no config file, no `--setParameter`, no `--wiredTigerCacheSizeGB`, no
`--logappend` (each start truncates the log), no auth, no TLS. **Every server parameter is
at its default for the binary.** Stdout/stderr go to /dev/null; processes run under `nohup`.

### Star topology: how it is enforced

1. `chainingAllowed: false`, set by `scripts/start.sh unchained` (reads
   `rs.conf().settings.chainingAllowed`, reconfigs only if different, re-reads and fails if it
   did not take). With chaining disallowed, secondaries sync from the primary.
2. Before every run, `harness/collect.py` reads `replSetGetStatus` and builds a topology label
   (`provenance.topology_label`): `"star"` when every non-primary member's `syncSourceHost`
   is the primary, otherwise the explicit map, e.g. `"27018<27020 27019<27020 27020<27017"`
   (a member with no sync source shows as `<-`). The config's `expect.topology: star` must
   match or the run refuses to start (7.1).
3. `scripts/recollect.py` preflight waits up to 180 s (polling every 5 s) for label `star` and
   journal default true before the first cell.
4. After each run the label is read again (`topology_after.json`); a change prints a warning
   only.

### Startup and shutdown

- `scripts/start.sh chained|unchained`: for each port, if `mongosh --port P --eval
  'db.adminCommand({ping:1}).ok'` succeeds the node is left alone, otherwise mongod is started
  as above. Waits up to 60 s for `db.hello().isWritablePrimary` on 27017, then sets
  `chainingAllowed`. **Does not run `rs.initiate()`**: the set must already be initiated.
- `scripts/stop.sh`: `{shutdown: 1}` on every running secondary, then `{shutdown: 1, force:
  true}` on the primary, then waits up to 30 s for all ports to stop answering.

---

## 3. Workload

| Item | Value |
|---|---|
| Database / collection | `freshness` / `probe` |
| Document | single document, `_id: "probe-1"` |
| Document shape | `{_id: "probe-1", seq: <int>, wall_ns: <int>, pad: "xxxxxxxxxxxxxx"}`; `pad` is `payload_bytes` = 14 `x` characters |
| Indexes | only the default `_id` index; the harness creates none. The collection is created by the first upsert |
| Write interval | `write_interval_ms: 100` in all four configs |
| Write concern | `{w: <1 \| 2 \| 3 \| "majority">, wtimeout: 5000}`; `j` is omitted because the configs set `j: null` |
| Duration per run | `duration_s: 120` (includes warmup) |

### Write loop (`harness/collect.py`, `_writer_body`)

- Client: `MongoClient("mongodb://127.0.0.1:27017,127.0.0.1:27018,127.0.0.1:27019,127.0.0.1:27020/?replicaSet=rs0", appname="freshness-writer", serverSelectionTimeoutMS=5000, event_listeners=[WireListener("writer")])`, default pool size.
- One session, `start_session(causal_consistency=True)`, used only by the writer thread.
- Slots: the first slot is `perf_counter_ns() + interval`. Each iteration: if `now > next_at`,
  `missed = (now - next_at) // interval + 1` and `next_at += missed * interval` (the passed
  slots are skipped and counted, never made up); `t_sched = next_at`; wait until `t_sched`;
  `next_at += interval`.
- Waiting (`_spin_until`): `time.sleep(deadline - now - 1.5 ms)` if positive, then busy-spin on
  `perf_counter_ns()` until the deadline.
- Command, sent with `Database.command(cmd, session=session)`:
  ```
  {update: "probe",
   updates: [{q: {_id: "probe-1"},
              u: {$set: {seq: <seq>, wall_ns: time.time_ns(), pad: <14 x>}},
              upsert: true}],
   writeConcern: {w: ..., wtimeout: 5000}}
  ```
  `wall_ns` is taken when the command document is built, just before `t0`.
- Timing: `t0 = perf_counter_ns()` immediately before `db.command`, `t1` immediately after it
  returns or raises. The acknowledgement is the command's return, i.e. the write concern is
  satisfied. `latency_ns = t1 - t0`.
- After a reply carrying `operationTime`, the writer publishes `(operationTime, $clusterTime,
  seq)` to a lock-protected `WriteClock` for causal readers.
- `seq` starts at 0 and increments by one per write attempted; errors are recorded, never
  retried. If the writer thread dies, the run stops (`writer_fatal`).

---

## 4. Reads

### The ten read paths (`config/threaded-w1.yaml`, `targets`)

Common client options for every target: `read_preference=<as below>`,
`appname="freshness-<id>"`, `serverSelectionTimeoutMS=5000`, `maxPoolSize=1`, `minPoolSize=1`,
`event_listeners=[WireListener("target:<id>")]`.

| id | Connection string | readPreference | readConcern | Session | Other |
|---|---|---|---|---|---|
| direct-27017 | `mongodb://127.0.0.1:27017/?directConnection=true` | secondaryPreferred | local | none | the primary, addressed directly |
| direct-27018 | `mongodb://127.0.0.1:27018/?directConnection=true` | secondaryPreferred | local | none | |
| direct-27019 | `mongodb://127.0.0.1:27019/?directConnection=true` | secondaryPreferred | local | none | |
| direct-27020 | `mongodb://127.0.0.1:27020/?directConnection=true` | secondaryPreferred | local | none | |
| rs-primary-local | `mongodb://127.0.0.1:27017,127.0.0.1:27018,127.0.0.1:27019,127.0.0.1:27020/?replicaSet=rs0` | primary | local | none | |
| rs-secondary-local | same replica-set URI | secondary | local | none | |
| rs-secondary-majority | same | secondary | majority | none | |
| rs-secondary-causal-majority | same | secondary | majority | `start_session(causal_consistency=True)` | session advanced from the writer before each read |
| rs-secondary-causal-local | same | secondary | local | `start_session(causal_consistency=True)` | same |
| rs-primary-linearizable | same | primary | linearizable | none | `max_time_ms=5000` |

The cell plan uses all ten under `threaded-w1`, the six `rs-*` paths (no `direct-*`) under
`threaded-wmaj`, and `rs-primary-local` alone under `threaded-w2` and `threaded-w3` (6.2).

### The driver call

Every read, and every calibration read, is:

```python
coll = client["freshness"]["probe"].with_options(
    read_preference=<Primary() | Secondary() | SecondaryPreferred() ...>,
    read_concern=ReadConcern(<level or None>))
doc = coll.find_one({"_id": "probe-1"}, session=<causal session or None>, max_time_ms=<5000 or None>)
```

No read goes through `Database.command`. In PyMongo 4.18 `Database.command` never passes a read
concern to the command runner, so a causal session's `afterClusterTime` is never applied there;
`find_one` builds the find itself and `ClientSession._update_read_concern` adds it.

### Causal reads

Before each causal read the reader copies `(operationTime, $clusterTime, seq)` from the
`WriteClock` and calls `session.advance_cluster_time(...)` then
`session.advance_operation_time(...)` on its own session, on its own thread.
`causal_waited_for_seq` records that `seq`. From the moment the session holds an operation
time, the driver must send `readConcern.afterClusterTime`; the abort rule in 7.3 enforces it.

### Read loop and rate (`reader_loop`)

- One reader thread, one target, per process (`workload.mode: isolated`).
- Slot grid with `read_interval_us: 500` (2,000 slots per second); the same skip-and-count rule
  as the writer, first slot at start + 500 us.
- Per read: `t_start_ns` immediately before `find_one`, `t_end_ns` immediately after.
- Observed throughput in the reference dataset: about 198.5 reads per write (200 slots per
  100 ms write interval, minus missed slots), except linearizable (about 8.5 reads per write)
  and w:1 causal majority (about 181.5).

### Calibration (before the run proper)

500 sequential reads per target through the same collection object and session, with the
writer not yet running. Results go to `provenance/calibration.json`: `n`, `errors`,
`min_ns`, `p50_ns` (`lat[n // 2]`), `p95_ns` (`lat[int(n * 0.95)]`), `p99_ns`
(`lat[int(n * 0.99)]`), `max_ns`, `mean_ns`. The causal abort rule applies here too. The
recollect runner always passes `--calibrate`.

---

## 5. Measurement

| Item | Definition |
|---|---|
| Clock | `time.perf_counter_ns()` in the single collector process; writer and reader threads share it, so no skew |
| Wall anchor | `clock_anchor = {wall_ns: time.time_ns(), perf_ns: perf_counter_ns()}` taken after calibration, just before the threads start; wall = `anchor.wall_ns + (t - anchor.perf_ns)` |
| Warmup | a write or read is `warmup: true` when `t_start_ns - anchor.perf_ns < warmup_s * 1e9`, `warmup_s: 5`. Warmup records are written to disk and excluded from statistics |
| Duration | threads start, then the main thread waits `duration_s` (120 s) on `time.monotonic()`, sets stop and joins each thread (10 s timeout) |
| Probe reset | before calibration: `update_one({_id: "probe-1"}, {$set: {seq: -1, wall_ns: 0, pad: <14 x>}}, upsert=True)` with the client's default write concern (implicit majority) |
| Missed slots | per record, `missed_slots` = slots skipped immediately before it (formula in 3). `r_missed` = sum over all reads of a run, warmup included; `w_missed` = the same over writes |
| Stale | see below |

### Stale (as computed by `scripts/val_report.py` and `harness/analyse.py --plan`)

For each read with no error and `warmup == false`: find the latest write whose `t_ack_ns <=`
the read's `t_start_ns` (`pandas.merge_asof`, direction backward, on writes sorted by
`t_ack_ns`). Reads with no earlier acknowledged write are dropped. The read is **stale** when
`observed_seq < seq of that write` (a null `observed_seq` counts as -1). `stale_of` is the
number of reads that had such a write. A read that misses a write still in flight is not
stale.

Minor difference: `val_report.py` builds the acknowledged-write list from writes with no error;
`analyse.py` uses all writes. They agree whenever no write errored (none did in the reference
dataset).

### Freshness curves (`harness/analyse.py`, function `curve`)

Reads with no error and not warmup. Each read is joined to the latest acknowledged write
(`acked_seq`, by `t_ack_ns`) and the latest submitted write (`submitted_seq`, by `t_start_ns`).

- From write start: `elapsed = read.t_start_ns - submitted write's t_start_ns`; fresh when
  `observed_seq == submitted_seq`.
- From acknowledgement: reads with `submitted_seq != acked_seq` (a write in flight) are
  excluded; `elapsed = read.t_start_ns - acked write's t_ack_ns`; fresh when
  `observed_seq == acked_seq`.
- Bucket = `floor(elapsed / bucket_us) * bucket_us`, `bucket_us = 500`, elapsed >= 0 only.
  `p_fresh = n_fresh / n`; 95% Wilson interval (z = 1.96); a bucket is plotted only when
  `n >= 30` (`min_samples_per_bucket`).

---

## 6. Runs, plan and rounds

### 6.1 Configs

`config/threaded-w1.yaml`, `threaded-w2.yaml`, `threaded-w3.yaml`, `threaded-wmaj.yaml`. They
are identical except the header comment, `experiment.name` and `write_concern.w`. SHA-256 of the
files as collected (also stored in the plan file):

| config | w | sha256 |
|---|---|---|
| threaded-w1 | 1 | daf15a2270bb92ea3fe307a008f79c8a00f74c5ea7fed89a66de33ce270eb2b1 |
| threaded-w2 | 2 | a9d9e7f87561e55ad1b1336494f52068d03386a074505c089867e2495dabcdc1 |
| threaded-w3 | 3 | 3e1384b00f77dee0fe3c30461358d5137bfde72b51c80a95e2dae1a45696bb9a |
| threaded-wmaj | "majority" | e7e613f5185ec21988d28a98c4cfecae8ad89c7a08b8ea2594b50953c6c0f316 |

Shared values: `replica_set` rs0 with the four seed hosts; `expect: {topology: star,
journal_default: true}`; `workload: {database: freshness, collection: probe, doc_key:
"probe-1", payload_bytes: 14, mode: isolated, duration_s: 120, warmup_s: 5,
write_interval_ms: 100, read_interval_us: 500, write_concern: {w, j: null, wtimeout_ms:
5000}}`; the ten targets of 4; `capture: {compress_output: true}`; `analysis: {bucket_us: 500,
min_samples_per_bucket: 30}`.

### 6.2 The 18 cells (`scripts/recollect.py`, `cell_plan`)

Index order (used by the shuffle):

| index | config | target |
|---|---|---|
| 0-9 | threaded-w1 | the ten targets in config order: direct-27017, direct-27018, direct-27019, direct-27020, rs-primary-local, rs-secondary-local, rs-secondary-majority, rs-secondary-causal-majority, rs-secondary-causal-local, rs-primary-linearizable |
| 10-15 | threaded-wmaj | rs-primary-local, rs-primary-linearizable, rs-secondary-local, rs-secondary-majority, rs-secondary-causal-majority, rs-secondary-causal-local |
| 16 | threaded-w2 | rs-primary-local |
| 17 | threaded-w3 | rs-primary-local |

### 6.3 Rounds, shuffle and seed

- 2 rounds (`--rounds 2`). Every round runs all 18 cells.
- `seed = --seed` if given, else `secrets.randbelow(2**32)`; printed and stored.
- `rng = random.Random(seed)`; for round r = 1, 2 in order: `order = list(range(18));
  rng.shuffle(order)`. The seed alone reproduces both rounds' orders (same Python random
  implementation).
- **Reference seed: 1999558622.** To reproduce the reference cell order exactly, pass
  `--seed 1999558622`.

### 6.4 Runner behaviour

1. Preflight: `scripts/start.sh unchained`; wait (<= 180 s) for topology `star` and
   journal default true; drop `freshness.nudge` if it exists; record power.
2. Write the plan file (6.6) before the first cell.
3. For each round, each position: run
   `<python> -m harness.collect --config config/<config>.yaml --target <target> --calibrate --round-index <r>`
   as a child process. The new run folder is found by diffing `measurements/` before and after.
4. Append one line per attempted cell to the progress log.
5. **Stop at the first cell that exits non-zero or is interrupted.** Ctrl-C gives the child up
   to 30 s to finish writing, then terminates it.
6. In all cases, add every completed run to `runs/VALID.csv` with `include=yes`.

Approximate wall time: 36 x (120 s + about 20 s overhead) = about 84 min.

### 6.5 Run id

`<UTC %Y%m%dT%H%M%SZ>__<experiment.name>__<target>__r<round>`, for example
`20261019T030223Z__threaded-wmaj__rs-secondary-causal-majority__r1`.

### 6.6 Plan file and progress log

`runs/plans/<UTC stamp>__recollect.json`:

| key | content |
|---|---|
| `created_utc` | ISO timestamp |
| `seed` | int |
| `rounds` | int |
| `shuffle` | text description of the shuffle |
| `cells` | `[{index, config, target}]`, 18 entries |
| `order` | `{"1": [{position, cell, config, target}], "2": [...]}` |
| `preflight` | `{topology, journal_default, chaining_allowed, nudge_dropped, power}` |
| `git` | `{commit, dirty, dirty_files, branch}` at plan time |
| `configs` | `{<name>: {sha256, duration_s, write_interval_ms, write_concern}}` |

`runs/plans/<UTC stamp>__recollect.progress.jsonl`, one line per attempted cell: `round`,
`position`, `cell`, `config`, `target`, `started_utc`, `finished_utc`, `rc`, `interrupted`,
`run_id`, `status` (`ok` or `failed`).

---

## 7. Validity checks

### 7.1 Before any connection or folder

| Check | Rule | On failure |
|---|---|---|
| Workload keys | `database, collection, doc_key, payload_bytes, duration_s, write_interval_ms, write_concern` present | exit, no folder |
| Mode | `isolated` or `concurrent`; isolated needs `--target` that exists | exit, no folder |
| Linearizable targets (`check_targets`) | `read_preference: primary`, `kind: replicaset`, not causal, `max_time_ms` set | exit, no folder |
| `expect` schema | `expect.topology` string, `expect.journal_default` bool, optional `expect.chaining_allowed` bool | exit, no folder |

### 7.2 Against the live set, before the folder exists (`check_expect`)

| Check | Rule |
|---|---|
| Topology | live label (2) `==` `expect.topology` (`star`) |
| Journal default | live `writeConcernMajorityJournalDefault is expect.journal_default` (true) |
| Chaining | only if `expect.chaining_allowed` is present (not in the four re-collect configs) |
| Readability | `replSetGetStatus` and `replSetGetConfig` must both succeed |

Any failure: exit status 1, message `[expect] refusing to start, no run folder created: ...`.
The server version and FCV are **not** checked.

### 7.3 During the run

| Check | Rule | On failure |
|---|---|---|
| Causal wire rule (`wire.causal_problem`) | for a causal target, if the session held an operationTime before the read, the `find` seen by the command listener must carry `readConcern.afterClusterTime`; if no `find` was seen and the read did not raise, that also fails | reader appends to `reader_fatal`, stops the run, exit status 1 after data is written. During calibration: exit before collection |
| Writer death | any exception escaping the writer thread | `writer_fatal`, run stops, exit 1 |
| Topology after | label re-read after the run | warning only |

### 7.4 Power

`pmset -g batt` before and after each run, parsed to `AC`, `battery` or `unknown`. **Recorded,
never checked**; the recollect preflight prints a note when not on AC. The reference dataset is
all `battery`.

### 7.5 After the run (`scripts/val_report.py`)

| Check | Rule (threshold) |
|---|---|
| Wire log | per run: the set of `read_concern_sent` values; `afterClusterTime present` = reads with non-null `after_cluster_time_sent` / non-warmup error-free reads. Expected: causal targets n/n, all others 0/n; level equals the configured read concern |
| Listener summary | the manifest's per-client counts `find level=<level> afterClusterTime=<yes\|no>`. Expected for causal targets: exactly 1 `no` (the first calibration read, before the session has an operation time) |
| operationTime check | causal targets only: every error-free read (warmup included) has a `request_id`; that id appears in the listener's reply log (`find_replies.jsonl`); the recorded `operationTime` equals the logged reply's; reply ids unique. **PASS only if all hold for every read**; `not recorded` for runs without `find_replies.jsonl` |
| Round agreement | per cell: median read latency and median ack latency per round (rounds pooled separately); `rel_diff = larger / smaller - 1`; **flag `DIFFERS` if either > 0.20** |
| VALID.csv consistency | `python -m harness.runs check`: every row's config, topology, journal default and power equal what its provenance says; every run folder is listed |

Reference results: operationTime check PASS on all 8 causal runs; 0 of 18 cells differ by
more than 20%.

---

## 8. Outputs

### 8.1 Run folder (`measurements/<run_id>/`)

| File | Content |
|---|---|
| `config.yaml` | verbatim copy of the config file used |
| `manifest.json` | see 8.2 |
| `writes.jsonl.gz` | one record per write, 8.3 |
| `reads.jsonl.gz` | one record per read, 8.4 |
| `find_replies.jsonl.gz` | the command listener's own log of every `find` reply, including calibration reads: `target`, `request_id`, `operationTime {t, i}` |
| `checksums.txt` | `<sha256>  <relative path>` for every file in the folder |
| `provenance/client_env.json` | `python`, `python_executable`, `pymongo`, `platform`, `machine`, `processor`, `cpu_count`, `hostname`, `tz`, `cwd`, `sysctl_cpu` (`sysctl -n machdep.cpu.brand_string`), `power` (parsed), `power_source` (raw `pmset -g batt`), `clock_sync` (`sntp -d time.apple.com`) |
| `provenance/git.json` | `commit`, `dirty`, `dirty_files`, `branch`, taken before the run folder exists |
| `provenance/nodes.json` | per seed host (direct connection): `host`, `buildInfo`, `hostInfo`, `getCmdLineOpts`, `featureCompatibilityVersion` (getParameter), `writeConcernDefaults` (getDefaultRWConcern), `writeConcernMajorityJournalDefault` (from replSetGetConfig) |
| `provenance/topology_before.json`, `topology_after.json` | `captured_ns`, `members [{name, stateStr, syncSourceHost}]`, `label`, `chainingAllowed`, `writeConcernMajorityJournalDefault`, `errors` |
| `provenance/repl_before.json`, `repl_after.json` | `captured_ns`, `replSetGetStatus`, `replSetGetConfig`, `hello` |
| `provenance/server_status_before.json`, `_after.json` | serverStatus trimmed to `host, version, process, uptimeMillis, localTime, opcounters, opcountersRepl, repl, connections, network, metrics` (only `repl, operation, ttl, commands`), `wiredTiger` (only `log, cache, transaction`), `electionMetrics` |
| `provenance/calibration.json` | per target, 4 |

Every provenance call is best-effort: a failing command records `{"__error__": ...}` instead
of aborting.

### 8.2 `manifest.json`

`run_id`, `harness_version` (3), `read_path`, `mode`, `target`, `round_index`, `writer_fatal`,
`reader_fatal`, `wire` (per client: `client`, `commands`, `read_concerns`), `started_utc`,
`finished_utc`, `clock_anchor`, `expect`, `topology {before, after}`, `chaining_allowed`,
`journal_default`, `power {before, after}`, `clock_note`, `threading_note`,
`totals {writes, reads {<target>: n}}`, `config` (the parsed config).

Wire clients: `writer`, `target:<id>`, `node:<host>` for each of the four seed hosts.

### 8.3 `writes.jsonl`

`seq`, `t_sched_ns`, `missed_slots`, `t_start_ns`, `t_ack_ns`, `latency_ns`, `ok`, `n`,
`nModified`, `operationTime {t, i}`, `writeConcernError`, `error`, `write_concern` (document
sent), `warmup`.

### 8.4 `reads.jsonl`

`target`, `t_sched_ns`, `missed_slots`, `t_start_ns`, `t_end_ns`, `latency_ns`,
`observed_seq`, `observed_wall_ns`, `operationTime {t, i}` (this read's own reply, via the
listener), `causal_waited_for_seq`, `request_id`, `read_concern_sent`,
`after_cluster_time_sent {t, i}`, `error`, `warmup`.

### 8.5 `runs/VALID.csv`

Columns: `run_id` (folder name under `measurements/`, may contain a subfolder such as
`scratch/...`), `config` (`experiment.name`), `topology` (label from
`topology_before.json`, else from `repl_before.json`), `journal_default` (`true`/`false`),
`power` (`AC`/`battery`/`unknown`), `include` (`yes`/`no`). Every analysis script selects
runs only from this file. `python -m harness.runs build` appends rows for unlisted run
folders with `include=yes`; `check` validates; `list` prints a selection.

**Both `runs/VALID.csv` and `measurements/` must exist before `scripts/recollect.py` runs**: it
lists `measurements/` before each cell and reloads `VALID.csv` after the last completed one.
The export ships `runs/VALID.csv` with the header row only and `measurements/.gitkeep`.

---

## 9. Analysis

### 9.1 `scripts/val_report.py --plan <plan.json>`

Selects the runs with `status: ok` in the plan's progress log. Sections, in order:

1. **Every run**: `run`, `config`, `target`, `w`, `topo` (before->after), `jd`, `power`
   (before/after), `fatal` (len(reader_fatal) + len(writer_fatal)), `writes` (all),
   `w_missed`, `reads` (all), `r_missed`, `reads/write` = reads / writes (all records),
   `w_err`, `r_err`.
2. **Wire log, per target**: as 7.5.
3. **Causal opTime vs writer**: for causal targets, share of non-warmup error-free reads with
   `causal_waited_for_seq` set whose `operationTime` differs from the writer's `operationTime`
   for that `seq`.
4. **operationTime check**: as 7.5.
5. **Stale reads and median read latency**: per run `stale`, `stale_of` (5), `read_p50_ms` =
   median of `latency_ns` over non-warmup error-free reads / 1e6.
6. **Write ack latency, primary-local runs**: `n` (non-warmup error-free writes), `ack_p50_ms`,
   `ack_p99_ms` (pandas quantile, linear interpolation), `interval_ms`.
7. **Per cell, pooled across rounds** (shown when a cell has more than one run): `runs`,
   `stale` (sum), `stale_rate` = sum(stale) / sum(stale_of), `read_p50/p90/p99` and
   `ack_p50/p99` = `numpy.quantile` (linear) over the concatenated latencies of the cell's
   runs (non-warmup, error-free), `r_missed`, `w_missed` (sums).
8. **Round agreement**: as 7.5, with per-round stale rates shown (not flagged), and a count of
   flagged cells.

### 9.2 `python -m harness.analyse --plan <plan.json> [--out DIR] [--xmax-ms 20]`

Default output: `measurements/merged/<plan stamp>__recollect_figures/`. Every run is joined on
its own clock, config is part of every key, then results are pooled per cell. Colours: the
reference categorical palette slots 1-4 (`#2a78d6` blue, `#eb6834` orange, `#1baf7a` aqua,
`#eda100` yellow), grey `#c3c2b7` for context, surface `#fcfcfb`, 200 dpi PNG.

| File | What it draws |
|---|---|
| `freshness_from_start.png` | two panels, w:1 and w:"majority". x: time since the write was sent, bucket centres, 0-20 ms. y: P(fresh) (5, from write start). Coloured with Wilson band: rs-secondary-majority (blue), rs-secondary-local (orange), rs-secondary-causal-majority (aqua). Every other path: thin grey. Lines break at buckets with n < 30 |
| `freshness_from_ack.png` | the same with the acknowledgement anchor (in-flight reads excluded) |
| `stale_rate_by_cell.png` | horizontal bars, one per cell (w:1, w:2, w:3, w:"majority"; targets in a fixed order), stale rate in %, each labelled with rate and `stale of stale_of` |
| `latency_by_cell.png` | two panels sharing rows: read latency and write ack latency per cell; dot = median, tick = p90, line to p99; log x with plain millisecond ticks |
| `ack_cdf_by_write_concern.png` | empirical CDF of write ack latency for the rs-primary-local cells of w:1, w:2, w:3, w:"majority" (blue, orange, aqua, yellow), log x; legend shows median and p99 |

Tables in the same folder: `cells.csv` (per-cell figures of 9.1 section 7 plus `ack_p90_ms`;
`stale_rate` there is a fraction, not a percentage),
`curve_start.csv`, `curve_ack.csv` (`config, target, bucket_us, n_fresh, n, p_fresh, ci_low,
ci_high, adequate`), `ack_by_write_concern.csv` (`write_concern, config, n, p01_ms, p50_ms,
p90_ms, p99_ms, max_ms`),
`sources.csv` (run id, config, target, round).

### 9.3 Other analysis and plotting scripts (not used for the 18-cell report)

| Script | Output |
|---|---|
| `python -m harness.analyse --config/--run-id ...` (non-plan mode) | per selection: `curve_ack.csv`, `curve_start.csv`, `headline_*.csv` (overall P(fresh), first bucket with p >= 0.99, last bucket with p < 1), `errors.csv`, `read_latency.csv`, `monotonic_reads.csv` (consecutive reads whose `observed_seq` decreases, per run and target), `lag_writes.csv`, `reads_joined.parquet`, and `freshness_curve_{ack,start}.png` (one line per target, Wilson bands). Groups by target only, so select one config at a time |
| `harness.event_timings` | per write and path, visibility interval (last stale read start, first fresh read end); `visibility_cdf.png`: one panel per condition (w, j, journal default, topology), CDF of the upper bound (ms after write start, log x) per target; `TIMINGS.md`, CSVs |
| `harness.ack_latency` | `ack_latency.png`: CDF (log x) and histogram (log-log) of ack latency per condition (w, j, journal default, topology); summary CSV |
| `harness.visibility_chart` | horizontal bar chart: median and p90 of per-write visibility time (end of first read seeing the write minus write start) for rs-primary-local, rs-secondary-local, rs-secondary-majority; default selection `threaded-w1`, journal default true; PNG and SVG |
| `harness.ryw_figure` | **collects its own data** (writes and immediate secondary reads, three arms: no session, causal session through `db.command`, causal session through `find_one`); bar chart of read-your-writes rate and read latency CDF |
| `harness.ryw_test` | the same test, text output only |
| `harness.describe_setup` | `SETUP.md` from run provenance; flags runs that differ in MongoDB version, hostname, replica set member count or primary |

`tests/dryrun.py` runs 121 offline checks against fake PyMongo objects; it opens no network
connection.

---

## 10. Commands, in order (reference procedure as run on 8.3.7)

```bash
cd ~/Documents/honours-mongodb
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-lock.txt   # once (lock file is in the export)
.venv/bin/python tests/dryrun.py                                              # offline, expect 0 failure(s)

scripts/start.sh unchained          # start nodes if down; chainingAllowed false; prints sync sources
caffeinate -i .venv/bin/python scripts/recollect.py 2>&1 | tee ~/recollect.log
#   reference run: no --seed given, drawn seed 1999558622

.venv/bin/python -m harness.runs check
.venv/bin/python scripts/val_report.py --plan runs/plans/<stamp>__recollect.json 2>&1 | tee ~/recollect_report.txt
.venv/bin/python -m harness.analyse --plan runs/plans/<stamp>__recollect.json
open measurements/merged/<stamp>__recollect_figures/*.png

scripts/stop.sh                     # when finished
```

---

## 11. Replicating on MongoDB 7.0.45

Binaries: `~/mongodb-bins/mongodb-macos-aarch64-7.0.45/bin` contains `mongod` (7.0.45,
gitVersion `a52313e13ab55c9bddf7c3ff91dab286fa381796`, allocator `system`, target_arch
`aarch64`), `mongos` and `install_compass`. **It has no `mongosh`**; keep using mongosh 2.9.2,
which supports 7.0.

### Steps

```bash
# 0. Stop the 8.3.7 set: both sets need ports 27017-27020.
cd ~/Documents/honours-mongodb && scripts/stop.sh

# 1. In the replica repo, every shell used below needs these two exports.
cd <replica repo>
export PATH="$HOME/mongodb-bins/mongodb-macos-aarch64-7.0.45/bin:$PATH"   # mongod -> 7.0.45
export MONGO_RS_DIR="$HOME/mongo-rs-7.0.45"                                 # fresh data
which mongod && mongod --version | head -1      # must print db version v7.0.45
which mongosh                                   # still /opt/homebrew/bin/mongosh

# 2. Python environment, identical to the reference.
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-lock.txt
.venv/bin/python tests/dryrun.py                # 0 failure(s)

# 3. Bootstrap the set once (start.sh does not initiate). Same flags as start.sh.
for i in 0 1 2 3; do
  mkdir -p "$MONGO_RS_DIR/n$i"
  nohup mongod --replSet rs0 --port $((27017+i)) --dbpath "$MONGO_RS_DIR/n$i" \
    --bind_ip 127.0.0.1 --logpath "$MONGO_RS_DIR/n$i/mongod.log" > /dev/null 2>&1 &
done
sleep 5      # if rs.initiate reports a member unreachable, wait a few seconds and rerun it
mongosh --port 27017 --quiet --eval 'rs.initiate({_id: "rs0", members: [
  {_id: 0, host: "127.0.0.1:27017", priority: 10},
  {_id: 1, host: "127.0.0.1:27018", priority: 1},
  {_id: 2, host: "127.0.0.1:27019", priority: 1},
  {_id: 3, host: "127.0.0.1:27020", priority: 1}],
  settings: {chainingAllowed: false}})'

# 4. From here on, the reference procedure.
scripts/start.sh unchained
mongosh --port 27017 --quiet --eval 'const c = rs.conf(); printjson({members: c.members, settings: c.settings, wcmjd: c.writeConcernMajorityJournalDefault})'
#   compare with section 2: priorities, votes, hidden, delays, every settings value
caffeinate -i .venv/bin/python scripts/recollect.py --seed 1999558622 2>&1 | tee ~/recollect-7.0.45.log
.venv/bin/python -m harness.runs check
.venv/bin/python scripts/val_report.py --plan runs/plans/<stamp>__recollect.json 2>&1 | tee ~/recollect-7.0.45_report.txt
.venv/bin/python -m harness.analyse --plan runs/plans/<stamp>__recollect.json

# 5. Verify the server actually used (nothing in the harness checks it):
.venv/bin/python - <<'EOF'
import json, glob
for d in sorted(glob.glob("measurements/2*")):
    n = json.load(open(d + "/provenance/nodes.json"))
    v = {x["buildInfo"].get("version") for x in n}
    f = {str(x["featureCompatibilityVersion"].get("featureCompatibilityVersion")) for x in n}
    print(d.split("/")[-1], v, f)
EOF
#   every line must show {'7.0.45'} and FCV 7.0
```

`--seed 1999558622` reproduces the reference cell order in both rounds; omit it to draw a new
seed (recorded either way). The `recollect.py` preflight calls `scripts/start.sh`, so the two
exports must be set in the shell that runs it.

### Server parameters

The reference passes no `--setParameter`, so every parameter is at the 8.3.7 default. Use none
on 7.0.45 either. To document any default that differs between the two binaries, capture both
with the same command and diff them:

```bash
mongosh --port 27017 --quiet --eval 'printjson(db.adminCommand({getParameter: "*"}))' > params-<version>.json
```

### What will differ by construction

`buildInfo` (version, gitVersion, `target_arch` `aarch64` against `arm64`), FCV (7.0 against
8.3), `getCmdLineOpts` paths (`--dbpath`, `--logpath` under `$MONGO_RS_DIR`), replica set
config version, term and `replicaSetId`, hostname, timestamps, git commit of the replica repo.
Nothing else should.

---

## 12. Every place the server version is assumed or hardcoded

| Location | What it assumes | Change for 7.0.45 |
|---|---|---|
| `scripts/start.sh` | runs `mongod` from `PATH`; Homebrew puts 8.3.7 first | prepend the 7.0.45 `bin` to `PATH` (11, step 1). No code change |
| `scripts/start.sh` | `RS_DIR=${MONGO_RS_DIR:-$HOME/mongo-rs}`; `~/mongo-rs` holds data at FCV 8.3, which a 7.0 binary cannot open | set `MONGO_RS_DIR` to a fresh directory. No code change |
| `scripts/start.sh` | the set is already initiated with the section-2 config | bootstrap once with `rs.initiate` (11, step 3) |
| `scripts/start.sh`, `scripts/stop.sh` | `mongosh` on `PATH`; uses `db.hello().isWritablePrimary`, `rs.conf()`, `rs.reconfig()`, `rs.status().members[].syncSourceHost`, `{shutdown: 1, force: true}` | all available on 7.0 with mongosh 2.9.2. No change |
| `harness/provenance.py` | `replSetGetStatus` (`syncSourceHost`), `replSetGetConfig`, `hello`, `getDefaultRWConcern`, `getParameter featureCompatibilityVersion`, `buildInfo`, `hostInfo`, `getCmdLineOpts`, `serverStatus` | all exist on 7.0. No change. The trimmed serverStatus keys may hold different sub-fields; they are recorded, not used |
| `harness/collect.py` | `update` with `writeConcern`, `find` with `readConcern` `local`/`majority`/`linearizable`, `afterClusterTime` on causal sessions, `operationTime` and `$clusterTime` in replies | standard on 7.0. The causal wire rule and the operationTime check verify it on every run |
| `harness/collect.py` (probe reset) | implicit default write concern `{w: "majority"}` | the same on 7.0 for this topology (no arbiters) |
| `harness/collect.py` `check_expect` | checks topology and journal default, **not** version or FCV | verify version and FCV from `nodes.json` (11, step 5) |
| 8.3 sync-source selection | 8.3 logs "prefer to select primary as sync source" when pings are within a threshold (log id 9649500), and drops a `replSetSyncFrom` target that is not strictly ahead | irrelevant to the 18-cell plan (chaining disallowed, star). Matters only for `scripts/a1_alternate.sh` |
| `tests/dryrun.py` | its fake server reports `buildInfo.version` `"8.3.7"` | cosmetic, never asserted. No change needed |
| `README.md` | says every run so far reports 8.3.7, FCV 8.3 | documentation only |
| PyMongo 4.18.0 | supports the server version in use | 7.0 is within PyMongo 4.18's supported range; confirm against the PyMongo compatibility table if in doubt |
| Power | reference runs were on battery | not version-related, but run the replica on battery too, or record that it was not, since power is not enforced |
