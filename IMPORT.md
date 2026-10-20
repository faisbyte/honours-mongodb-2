# Import record

Source: `harness-export-a157159.tgz` (export of `honours-mongodb` at commit
a157159f11431e9b2649b9fbc5eee748448e7cef; see `EXPORT.txt`).

| Item | Value |
|---|---|
| Tarball sha256 | `68d4e6a35c1a582b151f53f9193229859e898e084fcf9487b36177ca35de1d76` |
| Imported | 2026-10-20 |
| Unpacked with | `tar -xzf harness-export-a157159.tgz --strip-components=1` (drops the top-level `harness-export-a157159/` folder) |
| `README.md` | replaced the one GitHub created (`# honours-mongodb-2`) with the exported one |
| `HARNESS_SPEC.md` | the exported copy is byte-identical to the one already in the repo |

## Checks

- Every file listed in `EXPORT.txt` (55 files) matches its sha256 (`shasum -a 256 -c`).
- `runs/VALID.csv` exists with the header row only; `measurements/.gitkeep` exists.
- Config sha256 against `HARNESS_SPEC.md` 6.1:

| config | sha256 | spec 6.1 |
|---|---|---|
| threaded-w1 | daf15a2270bb92ea3fe307a008f79c8a00f74c5ea7fed89a66de33ce270eb2b1 | match |
| threaded-w2 | a9d9e7f87561e55ad1b1336494f52068d03386a074505c089867e2495dabcdc1 | match |
| threaded-w3 | 3e1384b00f77dee0fe3c30461358d5137bfde72b51c80a95e2dae1a45696bb9a | match |
| threaded-wmaj | e7e613f5185ec21988d28a98c4cfecae8ad89c7a08b8ea2594b50953c6c0f316 | match |

The `__pycache__/` folders in the tarball are ignored by the exported `.gitignore` and not
committed.
