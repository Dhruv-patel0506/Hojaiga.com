# Overnight App-Knowledge Report

Run `20261008_015929`  started 2026-10-08 01:59:29  finished 2026-10-08 02:08:44

Every claim below is measured causality (open-then-cancel probes on the
live app). `unverified` revert means a control changed state in a way we
could not safely auto-undo; `no-effect`/`no-change` are honest negatives.

| App | Status | Found window | Probed | Exhausted | Dialogs | Reverted | Unverified | Failed | Evidence |
|-----|--------|--------------|--------|-----------|---------|----------|------------|----------|----------|
| calculator | ok | already-running | 39 | True | 0 | 25 | 14 | 0 | 14 |
| fileexplorer | ok | already-running | 112 | False | 8 | 105 | 7 | 0 | 15 |
| blender | ok | already-running | 78 | True | 0 | 78 | 0 | 0 | 0 |

Per-app `report.json`, `trace.jsonl` and evidence PNGs live under:
```
D:\new_automation\overnight_results\probe_calculator_20261008_015929
D:\new_automation\overnight_results\probe_fileexplorer_20261008_015929
D:\new_automation\overnight_results\probe_blender_20261008_015929
```
