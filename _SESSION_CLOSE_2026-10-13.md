# Session close — 2026-10-13 (night)

**Offline suite right now: `Professor suite: 90 passed, 0 failed, 0 env-blocked, of 90`** (`_suite_final.out`). Nothing is half-edited: every file below compiles and the whole suite was re-run after the last change.

## Fixed and PROVEN this session

| Thing | The actual reason (measured, not guessed) | The fix | Proof |
|---|---|---|---|
| Word's "control not found in the live tree" (5 of 8 tasks dead) | Word's saved catalog contained **81–103 controls belonging to a Chrome window** — paths like `MsoDockLeft > "…Google Chrome - Dhruv"`, `trust: measured`, `sources: ["uia"]`. The foreign `'Address and search bar'` (#166) **outran Word's own `'Microsoft search'` box (#211)** in the search-to-reveal pick, so the search "typed into nothing". Two generic defects made it: (a) a UIA window subtree legitimately contains nodes of OTHER processes; (b) `_all_nodes()` concatenated several window snapshots into one list without translating indices, so every parent-walk crossed windows | `P_PID` read per node in `fast_uia`; foreign-pid nodes **blanked** (slots kept so index paths still work) in `harvest.harvest_tree` + a `foreign-window\|<title>` ledger note; `fast_uia.rebased()` at all three merge points in `executor._all_nodes`; search-to-reveal requires a box whose live node is the window's own process; a load-time scrub (`HOJAIGA_CATALOG_SCRUB`, default on) | Word's catalog cleaned **4885 → 4812 verbs (73 foreign removed)**; probe on live windows showed foreign pids really appear inside one window's tree; 0 broken links after `rebased()` |
| PR40 turned the suite 90 → 89 | `registrable("127.0.0.1")` answered **`0.1`**, so `docs_host_sources` invented `https://help.0.1/`, `https://docs.0.1/` … and fetched them; plus `help.github.com`-style probes off a wiki URL. A sandboxed test watched the run reach outside it | `registrable()` returns an IP literal unchanged; `docs_host_sources` skips IP hosts and code-hosting platforms (the wiki tier already covers those) | PR40 **PASS** alone, and the full suite **90/90, 0 failed** |

## Done earlier (still standing, from this MVP push)

- Search-to-reveal built (Settings' collapsed-expander bug found and fixed): Settings **6/6 in 198 s**.
- Content seeding for state deadlock (`--hours`, page numbers, selected text): fired live in Word.
- Exploration cached/capped per build: Settings reached the guide phase in **144 s** (was ~500 s).
- In-step modal guard + step cap wired into `Executor._run_inner`; guidebook **history** consulted mid-run (`_book()` / `_book_prefer()`); `perms.practise` wired into the `practice` phase; triggers capped (`MAX_PER_APP=8`, `MAX_NEW_PER_RUN=3`).
- Vision as the eye at init: Blender **4/6** with the start-up popup read before any action.

## What is NOT yet proven (tomorrow's order)

1. **Zero-doc guidebooks (7 of 91: acad, tableau, matlab, vlc, sharex, skype, taskmgr).** Actual reason: the docs host root is an **unfollowable portal** — the crawler fetched only `https://help.autodesk.com/` (7 227 B) and `https://help.tableau.com/` (2 812 B) of navigation, while `help.tableau.com/current/pro/desktop/en-us/default.htm` answers 200 with **30 640 B** of real manual. The `site:<docs host> "<product>" manual` fallback is written into `guide_finder.discover`, **but the verification run never executed it** (`discover` was called with `search=None` and no `HOJAIGA_GUIDE_SEARCH_URL`, and the guard requires one). → **run it with the env var set** and look for a `host search (<host>)` tier, then top up the corpus.
2. **Live Word run** (8 tasks, `--phases guide,practice`) proving: the pick is now `'Microsoft search'`, `eye` non-null, mirror reads fall from 7 996, `book_prefer_hits > 0`, `perms` route/pair counts.
3. **Full-book run** `--all --hours` so every recorded procedure has a result, not just 8.
4. **Blender** live popup-vision re-confirmation; **Discord / OBS** with mirror + guard.

## Commands for tomorrow

```powershell
cd "d:\new_automation\All codes"
$env:PYTHONIOENCODING="utf-8"
$PY = "C:\Users\dhruv\AppData\Local\Programs\Python\Python313\python.exe"

# 1. suite stays green
& $PY -u -m core_organs.si_tests_professor

# 2. prove the host-scoped search on the two apps we diagnosed
$env:HOJAIGA_GUIDE_SEARCH_URL = "<your SearXNG / CSE template with {q}>"
& $PY -u d:\new_automation\scratch\discover_stage_probe.py "AutoCAD" "Tableau Desktop"

# 3. live runs (never steals the mouse: virtual pointer, owned windows)
& $PY -u -m core_organs.professor.apprun winword --tasks 8 --phases guide,practice
& $PY -u -m core_organs.professor.apprun blender --tasks 6 --phases guide,practice
& $PY -u -m core_organs.professor.apprun excel --all --hours --phases guide,practice
```

Env knobs: `HOJAIGA_STEP_CAP`, `HOJAIGA_SEARCH_WAIT`, `HOJAIGA_REUSE_DAYS`, `HOJAIGA_CATALOG_SCRUB` (set `0` to disable the load-time scrub), `HOJAIGA_GUIDE_SEARCH_URL`.

Where the guidebook history lives (consulted mid-run, and the folder the corpus downloads into):
- `D:\new_automation\data\professor\guides\*.json` — 4 681 documents / 56 759 chunks, 84 of 91 apps covered (`corpus_report.json`)
- `D:\new_automation\data\professor\workflows\<app>.json` + `.md` + `INDEX.md` — every procedure with its recorded runs
- `data/professor/catalogs/<app>.json`, `data/professor/triggers/<app>.json`, `data/professor/logs/guide_fetch.log`
