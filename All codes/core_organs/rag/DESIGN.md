# HoJaiga Federated Multi-RAG — Design Spec (Checkpoint 2)

Status: design, approved for implementation. Author: Opus (architecture pass). Implementer: Sonnet.
Source brief: `final hojaiga tutor/src/hojaiga-vision app -subpart.md` (Parts 6–8).
Package: `All codes/core_organs/rag/`.

This spec is written so the implementation does not need structural changes later. The things that usually force
a rewrite (state identity, embedding model swaps, schema growth, a moved SSD, cross-app contamination, graph/DB drift)
are each settled here with an explicit mechanism. Where this spec deviates from the brief, it says so and why.

---

## 0. Ground truth this design builds on (measured in the repo, 2026-10-16)

| Fact | Consequence |
|---|---|
| `lancedb 0.30.0`, `pyarrow 24`, `networkx 3.6.1` installed | No new installs for the core. |
| LanceDB native FTS works without tantivy; `where(..., prefilter=True)` works on FTS, vector and hybrid; nullable vector column works; `add_columns` works (scratch test) | One store gives keyword + vector + hybrid search with an app-scoped prefilter. Schema can grow. |
| No `sentence-transformers`, `open_clip`, `fastembed`, `imagehash`. Existing convention: Ollama `nomic-embed-text` on CPU, `num_gpu: 0` (`professor/knowledge/manual_rag.py`) | Text embedder = nomic-embed-text 768-d on CPU. GPU stays with Qwen3-VL. No CLIP in v1 (see §5.1). |
| `professor/icon_memory.py`: 256-bit theme-invariant fingerprint, measured same-icon ≈12 bits, different ≥39 | Sub-RAG 1 reuses it as the matcher. 64-bit dHash is added only as an O(1) exact-hit prefilter. |
| `command_registry.py`: one unified command map per app, `canon(label)`, trust `learned > catalog > archetype > distilled` | The canonical command is the join key across all five sub-RAGs (§3). |
| `knowledge_store` (`app_behavior.db`): `bm_commands`, states, transitions, dialogs | Sub-RAG 2 and 4 ingest from it through adapters, never by copying code. |
| `professor/history.py` (transitions, apps registry), `skills.py` (verified macro library), `workflows.py` (guide procedures), `popup_policy.py` (popup decisions, pathway cache, `fingerprint()`), `manual_rag.py` (BM25+embedding manual search) | Each becomes a source or a facade over a sub-RAG. Nothing is thrown away. |
| `safety_guard.py` (Checkpoint 0) | Every executable candidate the router returns carries a safety verdict from it. |
| E: drive not mounted today | Storage root must resolve and fall back explicitly (§2). |

---

## 1. Principles (the rules every module obeys)

1. **Partition by app first, always.** Every row has `app_key`. Every query prefilters on it. Cross-app knowledge is
   only ever *borrowed* through the archetype fallback, tagged, discounted, and never executed unverified. This
   kills the brief's main failure mode ("extrude in AutoCAD returns Blender chunks").
2. **Federate by evidence shape, not by topic.** Each sub-RAG owns one kind of evidence and the index that suits it:
   exact hashes, a graph, ranked text, executable payloads, failure signatures.
3. **One join key across modalities: the command.** Icons, transcript steps, hotkeys, graph edges and error fixes all
   resolve to `command_id`. Cross-modal retrieval is a join, not an embedding-space alignment (§3, §6).
4. **Identity is assigned, recognition is fuzzy.** State IDs are stable UUIDs minted once. Hashes and similarity are
   only used to *find* the ID. UI drift therefore never fragments the graph (§5.2).
5. **One source of truth per fact.** SQLite and LanceDB hold the data. NetworkX is a derived, disposable in-memory
   view rebuilt from SQLite. There is never a pickled graph to fall out of sync.
6. **Deterministic hot path.** Routing and retrieval use no LLM. One capped, cached LLM query rewrite is allowed only on
   weak recall (the `manual_rag` pattern).
7. **Trust is data.** Every row carries `source` and `trust`. Execution outcomes move confidence up or down. Nothing
   guessed (LLM-synthesised hotkeys, scraped tables) executes without verification.
8. **Append observations, derive aggregates.** Execution results are appended. Counters and weights are recomputed from
   them, which makes merges between machines (Nucleus/Edge, two storage roots) safe.
9. **Forward-compatible schemas.** Every table has `schema_v` and `extra_json`. Migrations are numbered. Embedder
   identity is stored per row.
10. **Honest output.** Every result carries `gaps`: what was not found and why. An empty answer is a valid answer.

---

## 2. Storage root and layout

### 2.1 Resolution (`rag/storage.py`)
Order:
1. env `AI_STORAGE_ROOT`
2. `D:/new_automation/data/rag_root.txt` (one line, a path)
3. default `D:/new_automation/data/ai_root`

Rules:
- The resolved root gets `rag/meta.json` with a `root_uuid` on first use.
- If the configured root (1 or 2) is missing (SSD unplugged), fall back to (3), log it once at WARNING, and set
  `RagStatus.degraded = "storage_root_missing:<path>"` so callers and tests can see it. Never fall back silently.
- **All stored file paths are root-relative.** A drive-letter change never breaks a row.
- A later `rag.tools.merge_roots(src, dst)` merges two roots. This is safe because IDs are content hashes or UUIDs
  and observations are append-only (§1.8).

### 2.2 Layout
```
<root>/rag/
  meta.json                 schema_version, root_uuid, embedder registry, created_at
  lancedb/                  knowledge_chunks, procedures, fast_paths, error_playbooks, ui_states
  graph.db                  SQLite WAL: nodes, edges, observations, aliases, landmark_df
  icons.db                  Sub-RAG 1 (IconMemory file, relocated here; see §5.1)
  lexicon.db                SQLite: per-app alias -> command_id (the join spine, §3)
  cache.db                  SQLite: query-embedding cache, router result cache, LLM rewrite cache
  blobs/screens/<app_key>/<sha1[:2]>/<sha1>.webp     content-addressed screenshots
  blobs/icons/<sha1[:2]>/<sha1>.png                  optional crops for audit
  exports/packs/<app_key>-<ts>.hjpack               Nucleus/Edge packs (§10)
<root>/telemetry.db          SQLite: router calls, latencies, outcomes (SSMS sink optional, §11)
```

---

## 3. Identity model (the part everything else depends on)

| ID | Definition | Owner |
|---|---|---|
| `app_key` | The existing canonical key (`history.register_app` / `command_registry`). Never re-derived inside `rag/`. | existing |
| `app_version` | Normalised version string (major.minor). Matching via `knowledge/version_fit.py`. | existing |
| `command_id` | `f"{app_key}:{command_registry.canon(label)}"`. One per unified command. | Lexicon |
| `state_id` | UUID4, minted when a new state is first recognised (§5.2). | Sub-RAG 2 |
| `control_ref` | `f"{state_id}/{role}/{automation_id or canon(name)}"`, the address of one control in one state. | Sub-RAG 2 |
| `chunk_id` | `sha1(source_ref + span + text_norm)`, idempotent re-ingest. | Sub-RAG 3 |
| `procedure_id` | Existing `workflows.workflow_id(app, goal, cite, steps)` for guides; the same formula for transcripts. | Sub-RAG 3 |
| `fast_id` | `sha1(app_key + kind + payload_norm + context)` | Sub-RAG 4 |
| `sig_id` | `sha1(app_key or "*" + popup_policy.fingerprint(...))` | Sub-RAG 5 |

### 3.1 The Lexicon (`rag/lexicon.py`, `lexicon.db`)
This is the cross-modal spine. Per app it maps every **surface form** to a `command_id`:
```
aliases(app_key, surface_norm, command_id, kind, source, trust, n_seen, PRIMARY KEY(app_key, surface_norm, command_id))
   kind ∈ label | menu_path | tooltip | icon_label | keymap_action | doc_term | transcript_term | synonym
```
Fed by: `command_registry.build()` (labels, menu paths, help text), keymaps (`atlas/keymaps.py` action names),
Sub-RAG 1 (icon labels), Sub-RAG 3 ingest (terms that grounded), and `bm_commands` synonyms.

`resolve(app_key, text) -> [(command_id, score, kind)]`:
1. exact `surface_norm` match
2. menu-path suffix match ("Insert > Picture" → "picture")
3. token-set containment with IDF weighting over that app's aliases
4. a fuzzy ratio ≥ 0.88 (stdlib `difflib`, no new dependency)

When several commands tie, choose by trust, then by `n_seen`. Unresolved forms are returned as `gaps`, never
silently dropped.

---

## 4. The common result envelope (`rag/types.py`)

Every sub-RAG returns `Evidence`; the router returns a `Retrieval`. Pure dataclasses, JSON round-trippable.

```python
@dataclass
class Evidence:
    sub_rag: str            # icon | graph | procedure | fast | recovery
    app_key: str
    kind: str               # e.g. "path", "hotkey", "script", "chunk", "procedure", "icon_label", "playbook"
    text: str               # human-readable summary / quoted passage
    command_ids: list[str]  # what it is about (join key)
    payload: dict           # kind-specific (steps, keys, template+params, path edges, resolution)
    trust: str              # verified | learned | catalog | official_doc | seed | transcript | web | llm | borrowed
    confidence: float       # 0..1 calibrated (§7.3)
    cost_ms: float          # expected execution cost (for plans), 0 for pure text
    safety: str             # allow | destructive | financial | commit | unnamed   (safety_guard verdict)
    citation: str           # source_ref: video_id@t0-t1, url#heading, "uia:<state_id>", "observed:<run_id>"
    borrowed_from: str = "" # app_key it was borrowed from (archetype fallback), else ""
    score: float = 0.0      # retrieval score inside its sub-RAG (not comparable across sub-RAGs)

@dataclass
class PlanStep:
    command_id: str
    route: str              # script | wm_command | hotkey | uia_invoke | menu_path | control_click | posted_click | type
    args: dict
    expect_state: str|None  # state_id expected after the step (verification target)
    expect_note: str        # e.g. "dialog 'Export' opens"
    reliability: float
    safety: str
    evidence: list[int]     # indexes into Retrieval.evidence

@dataclass
class Plan:
    steps: list[PlanStep]
    p_success: float
    cost_ms: float
    grounded_ratio: float   # steps resolved to live/known controls / total
    needs_human: bool       # any step safety != allow, or any elevation/payment
    origin: str             # skill | fast_path | graph | procedure+graph | script | borrowed

@dataclass
class Retrieval:
    query: Query
    intent: str
    tier: int
    state_id: str|None
    plans: list[Plan]       # ranked, best first; empty for EXPLAIN/IDENTIFY
    evidence: list[Evidence]
    gaps: list[str]
    trace: list[dict]       # each routing hop: sub_rag, ms, hits, why stopped
    degraded: list[str]     # storage_root_missing, embedder_down, store_unavailable:<x>
```

---

## 5. The five sub-RAGs

Each sub-RAG is one module with the same shape:
```python
class SubRag(Protocol):
    name: str
    def upsert(self, records: Iterable[dict]) -> UpsertReport: ...   # idempotent by id
    def query(self, q: SubQuery) -> list[Evidence]: ...              # app-prefiltered, budgeted
    def observe(self, outcome: Outcome) -> None: ...                  # learning hook (§8)
    def forget_app(self, app_key: str) -> int: ...
    def stats(self, app_key: str = "") -> dict: ...
```

### 5.1 Sub-RAG 1: Visual & Icon Vault (`rag/icons.py`)
- **Purpose:** crop → label → `command_id` in under 1 ms, so Qwen3-VL never sees a known icon twice.
- **Store:** the existing `IconMemory` SQLite (moved to `<root>/rag/icons.db` with a one-time copy; the
  `icon_memory.memory()` factory reads the root from `rag.storage`). Add two columns: `dhash64 INTEGER` and
  `app_key TEXT` (votes already carry app).
- **Lookup ladder:**
  1. `dhash64` exact hit in an in-RAM dict for the app, then globally → O(1). Accept only if the 256-bit distance
     to the stored fingerprint is ≤ 12 (guards dHash collisions).
  2. Vectorised 256-bit Hamming ≤ 30 (existing `nearest`), app-scoped first, then global.
     100k icons × 32 B = 3.2 MB; about 2 ms on CPU.
  3. Miss → return `gaps=["icon_unknown:<fp>"]`. The caller batches misses into a contact sheet
     (`labeler.make_sheet`) and writes the answers back with `source=vlm`.
- **To command:** label → `lexicon.resolve(app_key, label)`. The icon label is also written into the Lexicon as
  `kind=icon_label`.
- **Trust:** `uia (3) > ocr (2) = knowledge (2) > vlm (1)`, unchanged. A UIA-named control sitting on the pixels
  overrides a VLM label and retro-corrects it (`symbol_eval` scores disagreements).
- **Deviation from the brief:** no CLIP/SigLIP `vector[512]` in v1. The fingerprint is measured, theme-invariant and
  free. CLIP is not installed and would compete for VRAM or slow the CPU. `ui_states.visual_vec` is reserved as a
  nullable column so a visual embedder can be added later without a schema change (§9).

### 5.2 Sub-RAG 2: UI Topology & State-Action Graph (`rag/graph.py`, `rag/statekey.py`)

**Purpose:** where the app is now, and the cheapest reliable path from here to a state where a command can run.

**State recognition (`statekey.py`), the anti-fragmentation core.**
From a snapshot (fast_uia nodes or a universal_scan SoM map), compute:
- `window_kind` = `toolkit + ":" + normalised top-level class + ":" + role` (role ∈ main | dialog | flyout | menu |
  backstage). Use the UIA `pid` to keep only nodes of the app's own processes (the fast_uia `P_PID` fix).
- `modal_stack` = ordered `window_kind`s of open owned popups/dialogs.
- `landmarks` = a set of `(ctrl_type, canon(name) or automation_id)` for **structural** controls only: menu-bar items,
  tab items, toolbar/ribbon buttons, group headers, dialog title, pane names.
  - **Excluded** (volatile): Edit/Document contents, list/tree items, title-bar text, any name > 40 chars, any name
    containing a path, URL or e-mail.
  - **Normalised:** digits → `#`.
- **Blind-tree fallback (Tier 3, fewer than 5 named landmarks):** use OCR'd header/tab text, Sub-RAG 1 labels of
  toolbar icons, and an 8×8 layout grid code (edge density quantised to 2 bits per cell) as landmarks, with weight 0.5.

**Matching** (`localize(app_key, snapshot) -> (state_id, similarity, created: bool)`):
- Candidates are nodes with the same `app_key`, `window_kind` and `modal_stack` length.
- Score = **IDF-weighted Jaccard** over landmarks. IDF comes from `landmark_df(app_key, landmark, df)`, so landmarks
  present in every state (e.g. "File") weigh almost nothing.

| Score | Result |
|---|---|
| ≥ 0.75 | Same state. Merge the landmark stats and bump `visits`. |
| 0.50–0.75 | Variant of that state, recorded in the node's `variants_json`. Matching is never re-run on variants. |
| < 0.50 | New node with a new UUID. |

- Exact fast path: `sha1(window_kind + modal_stack + sorted(landmarks))` is indexed. A hit skips scoring.
- Deterministic and order-independent. The thresholds live in `rag/config.py` and are calibrated by the RG2 test (§12).
- **Node merge:** if two nodes later prove identical (score ≥ 0.9 after both accumulate landmarks), write
  `aliases(old → canonical)`. Readers resolve aliases. Nothing is ever renumbered.
- **Deviation from the brief:** the brief's `state_id = SHA256(app+class+control signature)` changes whenever one
  label or one control changes, which fragments the graph and orphans its edges. Here a hash only *finds* the ID.

**Graph store (`graph.db`, source of truth):**
```sql
nodes(state_id PK, app_key, app_version, window_kind, modal_stack_json, landmarks_json, variants_json,
      exact_sig, tier, visits, first_seen, last_seen, screenshot_ref, schema_v, extra_json)
edges(edge_id PK, app_key, src, dst, command_id, action_type, route, args_json,
      n_ok, n_fail, n_noeffect, ewma_latency_ms, last_ok_ts, last_seen_ts, source, trust, safety, schema_v, extra_json,
      UNIQUE(app_key, src, command_id, route, dst))
observations(obs_id PK AUTOINCREMENT, ts, run_id, app_key, src, command_id, route, args_json,
      expected_dst, observed_dst, ok, effect, latency_ms, verify_note, source)
aliases(state_id PK, canonical_id)
landmark_df(app_key, landmark, df, PRIMARY KEY(app_key, landmark))
generation(app_key PK, gen)       -- bumped on every write; readers rebuild views when it moves
```
- Self-edges (`src == dst`) record commands that act without changing structure (Bold, Zoom). That is how
  "command X is available in state S" is known.
- `edges` counters are a materialised aggregate of `observations` (`rag.tools.rebuild_edges()` recomputes them).
  Observations are never updated in place.
- **In-memory view:** a `networkx.MultiDiGraph` per app, built lazily from SQLite and kept in an LRU cache (max 8 apps).
  It is rebuilt when `generation[app_key]` differs from the cached one. One writer per process; cross-process safety
  comes from SQLite WAL plus the generation check. No pickles.

**Edge weight for planning:**
```
p̂      = (n_ok + a) / (n_ok + n_fail + n_noeffect + a + b)    # Beta prior by trust: verified a=4,b=1 · learned 3,1 · catalog 2,1 · transcript 1,1 · llm 1,2
p̂_t    = p̂ ^ (1 + age_days/90)                                 # stale edges lose confidence (erosion)
w      = ROUTE_COST_MS[route] / 1000  +  λ · (-ln p̂_t)          # λ = 2.0
w      = inf if safety != allow and not query.allow_categories ⊇ {safety}
```
`ROUTE_COST_MS`: script 50, wm_command 20, hotkey 15, uia_invoke 60, menu_path 400, control_click 250,
posted_click 300, type 40/char. This matches the existing route order "command > shortcut > control > posted click".

**Planning** (`path_to(app_key, from_state, target)`):
- target is a `command_id` (most common) or a `state_id`.
- A command with a **global route** (a verified hotkey or `wm_command` valid for the `window_kind`, from Sub-RAG 4)
  needs a zero-length path: one step.
- Otherwise run Dijkstra (non-negative weights, so it cannot loop) to the cheapest state with a self-edge or outgoing
  edge for `command_id`, then that edge. Max depth 12, max 3 alternatives (Yen's k-shortest, k=3), all exposed as
  separate `Plan`s.

**Execution sync** (called by the executor after every step):
`observe(Outcome(src, step, observed_snapshot))` → `localize(observed)`:
- `observed == expected` → ok observation.
- A different known state → observation with the actual `dst`. Edges keep a dst histogram, so a stochastic edge (Save
  opens a dialog only the first time) learns both outcomes. Then **replan from the actual state**.
- An unknown state → mint a node, record the edge, replan.
- A popup or error on screen → hand to Sub-RAG 5.

Runtime loop guards: a per-run `visited(state_id, command_id)` set (a repeat means the step is blocked), max 3
replans, a monotonic wall-clock budget, and max steps = plan length + 4.

**Natural-language state search:** LanceDB `ui_states` (one row per node): `state_id, app_key, description`
(`window_kind` + dialog title + top landmarks), `vector` (nomic 768), nullable `visual_vec`, `screenshot_ref`.
It answers "where is the export dialog?" (LOCATE).

**Feeds:** `knowledge_store` states/transitions (adapter), `history.transitions`, `triggers.py` + delta-box crawls
(Checkpoint 1), and `atlas/uimap.py` maps (surface → tab → group → control becomes nodes + edges).

### 5.3 Sub-RAG 3: Procedural Workflow RAG (`rag/procedures.py`)
**Purpose:** how-to knowledge in words (lakhs of transcripts, manuals, guides, self-generated crawl docs), grounded
to commands.

Two LanceDB tables:
- `knowledge_chunks` is the retrieval unit:
  `chunk_id, app_key, app_version, source_kind (video_transcript | manual | guide | web_doc | self_doc), source_ref
  (video_id@t0-t1 | url#heading | crawl:<run_id>), heading_path, text, steps_json, mentions (list<string> command_ids),
  unresolved (list<string>), division, lang, trust, quality (0..1), vector (768, nullable), embedder_id,
  procedure_id, ingested_at, schema_v, extra_json`
- `procedures` is the execution unit:
  `procedure_id, app_key, app_version, goal, goal_norm, steps_json [{text, command_id|null, route_hint, args}],
  sources (list<string>), grounded_ratio, n_runs, n_ok, last_run_ts, trust, vector (goal embedding, nullable),
  embedder_id, schema_v, extra_json`

**Ingest pipeline (shared by every source):**
1. Normalise and chunk:
   - Transcripts: merge caption lines into ~25–45 s windows split at pauses or discourse markers ("next", "now",
     "then"). Keep `t0/t1`.
   - Documents: the existing `manual_rag.chunk_markdown` (≈150 words, heading path kept).
2. Extract imperative steps (rule-based: verb lexicon + UI nouns + quoted labels + chord regex
   `command_registry.chord_in_name`). The LLM is not used at ingest by default. `--llm-steps` is an opt-in batch
   mode run offline on the Nucleus.
3. Ground the steps with `lexicon.resolve`, filling `mentions` and `unresolved`. Unresolved terms that recur across
   ≥ 3 sources for the app are queued as **exploration targets** for the crawler (Sub-RAG 2 frontier).
4. Quality:
   - auto-captions 0.5, manual captions 0.7, official docs 0.9, self_doc 0.8
   - × `min(1, grounded_ratio + 0.3)`
   - Near-duplicate chunks (same `steps_json` after normalisation) keep one row and record the extra `source_ref`s in
     `extra_json.dupes`.
5. Embed `f"search_document: {heading_path} :: {text}"` with nomic. If Ollama is down, write `vector=NULL`,
   `embedder_id=""`. The background `reembed` job fills these later; FTS still finds them immediately.
6. Procedures: a guide workflow (`workflows.py`) or a transcript segment with ≥ 2 grounded steps becomes a
   `procedures` row.

**Query:**
- Hybrid search: FTS on `text` plus vector on the query embedding (`search_query:` prefix), both with
  `where app_key = ? [AND app_version compatible]` as a prefilter. Fuse with RRF (k=60).
- Re-rank with `score × quality × trust_w × (1 + 0.5·grounding_bonus)`, where `grounding_bonus` is the fraction of the
  chunk's `mentions` available in the current state (self-edge or one hop in Sub-RAG 2).
- Then fetch the chunk's `procedure_id`, so a hit returns runnable steps, not just a paragraph.

**Scale:** 2M chunks × 768 × float32 ≈ 6 GB of vectors on the SSD.
- Create an `IVF_PQ` index when a table passes 100k rows (`num_partitions ≈ sqrt(n)`, `num_sub_vectors = 96`).
- Keep a scalar BITMAP index on `app_key` and a BTREE index on `procedure_id`.
- An app-scoped prefilter keeps the searched set small.

**Facades:** `manual_rag.ManualIndex.search/retrieve` keeps its API and delegates to Sub-RAG 3 when the store is
available. A one-time importer moves `manuals.db` chunks in.

### 5.4 Sub-RAG 4: Superhuman Macro & Hotkey Vault (`rag/fastpaths.py`)
**Purpose:** the fastest correct route: hotkeys, chord sequences, `wm_command` IDs, CLI flags, scripts (bpy,
AutoCAD `.scr`/AutoLISP, Office COM/VBA, PowerShell).

LanceDB `fast_paths`:
```
fast_id, app_key, app_version_min, app_version_max, kind (hotkey | chord_seq | wm_command | menu_accel | cli | script | com),
command_id (nullable for multi-command scripts), task_pattern, payload (keys | command line | template text),
params_schema_json (JSON Schema of template slots), preconditions_json ({window_kind, mode, editor, selection}),
context, source (keymap_file | registry | probe | seed | web_table | tldr | llm), trust, verified (bool),
n_ok, n_fail, last_ok_ts, safety, sandbox (none | scripting_route), vector (task_pattern embedding, nullable),
embedder_id, schema_v, extra_json
```

**Query:**
- By `command_id`: exact, the fastest route for one command whose preconditions hold in the current state.
- By goal: hybrid search on `task_pattern`, for scripts and multi-step tasks.
- Templates fill their `params_schema` from the goal by deterministic slot extraction (numbers + units + quoted names).
  When required slots stay empty, return the candidate with `gaps=["needs_param:<slot>"]` rather than guessing.

**Execution gate (unchanged project law):** only rows with `verified=True` or `trust ∈ {verified, learned}` are
returned as direct-execution steps.
- Anything else is returned as a `probe` step (`route="hotkey", args.probe=True`). The executor tries it with
  before/after verification and reports the outcome back.
- Scripts never run outside the existing scripting route's sandbox.
- `safety` is computed with `safety_guard.check(task_pattern + command label)`.

**Feeds:** `command_registry` (shortcuts, menu IDs) on every `refresh_profile`, `atlas/keymaps.py` (shipped keymap
files: highest-trust static source), the Checkpoint-3 harvesters (web tables, tldr, seeds), and `skills.py`
compiled skills (exported as `kind=chord_seq`, `trust=verified`).

### 5.5 Sub-RAG 5: Error & Recovery Playbooks (`rag/recovery.py`)
**Purpose:** recognise a failure and return a fix, or an honest escalation.

LanceDB `error_playbooks`:
```
sig_id, app_key ("*" = global), toolkit, signature (popup_policy.fingerprint),
failure_code (popup:<class> | no_effect | uia_blocked | capture_blank | state_mismatch | timeout | crash | script_error),
message_template (numbers, paths, names masked), resolution_json [ordered {action, target_role, args}],
class (elevation | destructive | payment | file_locked | unsaved_changes | missing_dependency | permission |
       automation_blocked | network | crash | app_specific),
needs_human (bool), n_ok, n_fail, source (popup_policy | observed | doc | seed), trust,
vector (message embedding, nullable), embedder_id, schema_v, extra_json
```
- **Popup recovery:** `popup_policy` stays the decision engine. Sub-RAG 5 is its knowledge store. The pathway cache
  is imported, and every popup resolution `popup_policy` performs is written back through `observe`.
- **Hard rule:** `class ∈ {elevation, destructive, payment}` forces `needs_human=True` regardless of history (the
  `hojaiga-popup-defense` law).
- **Non-popup failures** map to strategy playbooks keyed by `(failure_code, toolkit)`. Seed set:
  - `uia_blocked` → visual SoM + posted input
  - `capture_blank` → restore-capture ladder
  - `no_effect` → next route in route order
  - `state_mismatch` → re-localise and replan

  Note the brief's "switch to Phantom Alpha" entry is **not** seeded, by decision of 2026-10-16.
- **Query:** exact `sig_id`, then `(app_key, failure_code)`, then FTS + vector on the message (global rows included,
  `app_key` rows first).

---

## 6. Cross-modal retrieval: how pixels, trees, words and keys meet

```
 icon crop ──fingerprint──► Sub-RAG 1 label ──┐
 UIA node  ──canon(name)────────────────────┤
 transcript step "click Extrude" ──terms────┼──► Lexicon.resolve ──► command_id ──┬──► Sub-RAG 4 fastest verified route
 keymap action "mesh.extrude_region" ───────┤                                     ├──► Sub-RAG 2 path from current state
 popup button "Don't Save" ── role ─────────┘                                     └──► Sub-RAG 5 known failure on this command
```
- Everything converges on `command_id` through the Lexicon, so no shared embedding space across modalities is needed.
  This is cheaper and more exact, and testable offline.
- **Conflicts:**
  - Two sources map one surface form to different commands: keep both rows; `resolve` ranks by trust then `n_seen`.
    The live state breaks the tie (the command present in the current state wins).
  - A VLM icon label contradicts a UIA name on the same pixels: UIA wins, the VLM vote is demoted, and the
    disagreement is logged for `symbol_eval`.
- Embeddings are used **within** a modality only: text↔text for chunks, task patterns, state descriptions and error
  messages.

---

## 7. The Master Router (`rag/router.py`)

### 7.1 Inputs
```python
@dataclass
class Query:
    text: str
    app_key: str = ""                 # resolved by caller when known
    snapshot: Any = None              # fast_uia nodes or SoM map of the live window
    region: tuple|None = None         # a pointed-at box (tutor mode)
    popup: Any = None                 # popup_policy DialogInfo if one is blocking
    failure: dict|None = None         # executor failure being recovered
    mode: str = "tutor"               # tutor | auto | explain
    allow_categories: frozenset = frozenset()   # human-approved safety lifts (never 'financial')
    budget_ms: int = 150              # hot-path budget without LLM
    allow_llm_rewrite: bool = True
```

### 7.2 Stage A: context (no I/O beyond local stores, ~5 ms)
1. `app_key`: from the query, or from the owned window (caller), or by text alias through the launcher's app catalog.
   Still unknown: the intent can only be EXPLAIN and the router searches procedures globally, tagged as borrowed.
2. `tier` comes from `history.apps.tier`. If unknown, infer it from the snapshot:

   | Snapshot | Tier |
   |---|---|
   | named ratio ≥ 0.8 and nodes < 400 | 0 |
   | Chromium/Electron classes | 1 |
   | ribbon/tab strips or ≥ 400 nodes | 2 |
   | named ratio < 0.3 with a large unnamed pane | 3 |

   Store the inferred tier back.
3. `state_id` = `graph.localize(app_key, snapshot)` when a snapshot is given.
4. Preemption: `popup` or `failure` present → intent = RECOVER, regardless of the text.

### 7.3 Stage B: intent (deterministic, ~1 ms)
Rules are checked in order:

| Intent | Trigger |
|---|---|
| RECOVER | popup/failure present (preemptive) |
| IDENTIFY | `region` given, or "what is this / what does this (icon\|button) do" |
| LOCATE | "where is / find / show me / which button" |
| EXPLAIN | "why / what does X mean / explain / difference between / what is <feature>" |
| CURRICULUM | "teach me / learn / from basics / course / practice" |
| DO | imperative verb, or "how do I / how to" in auto mode, or the text resolves to ≥ 1 command in the Lexicon |
| EXPLAIN | fallback |

"How do I …" in **tutor** mode is DO with `mode=tutor`: the plan is computed and *shown*, not executed. When rule
confidence < 0.6 (two rules fire), run DO and EXPLAIN together. Both are cheap.

### 7.4 Stage C: routing table (order = cheapest reliable signal first; stop at the first sufficient answer)

| Intent | Probe order | Stop when |
|---|---|---|
| RECOVER | S5 exact sig → S5 (app, code) → S2 replan from localised state → S5 fuzzy | a playbook with `p̂ ≥ 0.6`, or `needs_human` |
| IDENTIFY | S1 (crop in region) → Lexicon → S2 control in state → S3 chunks mentioning that command (meaning) | label + command + one explanation |
| LOCATE | Lexicon → S2 path from current state (where it lives) → `ui_states` NL search → S1 labels | a path or a known control_ref |
| EXPLAIN | S3 hybrid → S4 (`task_pattern` matches add "shortcut: …") → S2 (where it is) | k=4 chunks with quality ≥ 0.5 |
| DO | `skills.find` (verified macro) → S4 by command (single-command goals) → **Tier 3 and creation verbs: S4 scripts** → S3 procedures → ground steps → for each step S4 global route or S2 path → S1 for unresolved icon terms | a plan with `grounded_ratio = 1` and `p_success ≥ 0.7`; else best 3 plans + gaps |
| CURRICULUM | S3 procedures ordered by division + difficulty (`steps` count, prerequisite commands) → S2 coverage of the app | an ordered list (the Professor's pedagogy layer owns presentation) |

**Tier biases:**
| Tier | Bias |
|---|---|
| 0 | S2 dominant, S3 rarely needed |
| 1 | S1 + S2, posted/visual routes |
| 2 | S4 hotkeys first, S2 for ribbon paths |
| 3 | S4 scripts/hotkeys first, S3 for method, S1 for toolbars; the graph is expected sparse |

Encode the biases as route-cost multipliers per tier, not as separate code paths.

**Per-probe budgets:** each probe gets `budget_ms × share`, with shares from `config.ROUTE_SHARES[intent]`. A probe
over budget returns what it has and records `trace.why="budget"`.

### 7.5 Stage D: fusion
- **Plans (DO / LOCATE / RECOVER):** candidate plans come from each origin (skill, fast_path, graph,
  procedure+graph, script, borrowed). Score:
  ```
  p_success = Π step.reliability            (from §5.2 edge p̂_t or fast-path Beta posterior)
  utility   = p_success − α · cost_s − β · (1 − grounded_ratio) − γ · [needs_human]      α=0.05, β=0.6, γ=0.1
  ```
  Rank by utility. Ties go to higher trust, then fewer steps. In tutor mode `needs_human` is not penalised: the human
  does every step anyway.
- **Evidence (EXPLAIN / IDENTIFY):** RRF across sub-RAGs with weight `trust_w × quality`. No raw-score mixing.
  Scores are not comparable across sub-RAGs, which is why fusion is rank-based.
- **Calibration:** `confidence` for each Evidence is the Beta posterior mean for executable items and
  `quality × normalised_rank` for text. RG7 checks that a reliability bucket's predicted `p_success` falls within ±0.15
  of its observed success rate on the offline fixture history.

### 7.6 Stage E: weak-recall rewrite (at most one LLM call)
Triggered only when the best plan's `grounded_ratio < 0.6` **or** S3's top fused score falls below the weak threshold
**and** `allow_llm_rewrite` is set.
- One CPU text-model call through the existing brain/gatekeeper, timeout 4 s: "rewrite into 2 manual-style queries".
- Cached in `cache.db` by `(app_key, goal_norm)`. Rerun stages C–D once.
- Still weak → return the best plans + `gaps` + `explore_targets` (unresolved terms, unexplored frontier nodes near
  the current state).

### 7.7 Contamination and version guards
- Every store call carries `app_key`. The only cross-app path is `borrow(archetype)`, used when the app has fewer than
  20 commands in the Lexicon or S3 has < 3 chunks for it.
- Borrowed evidence has `trust="borrowed"`, confidence × 0.5 and `borrowed_from` set, and is never a direct-execution
  step (always `probe`).
- **Version:** prefer the same major version. Other versions are allowed with confidence × 0.8 via `version_fit`.

### 7.8 Caching
- The router result cache key is `(app_key, state_id, goal_norm, intent, mode, gens)`. `gens` is the tuple of the
  per-app generation counters of S2/S4 plus table versions of S3/S5, so any write invalidates it automatically. TTL 1 h.
- Query embeddings are cached in `cache.db` (LRU 50k).

### 7.9 Public API (`rag/__init__.py`)
```python
retrieve(query: Query) -> Retrieval                                   # the router
retrieve_workflow(app_key, user_goal, current_som_map=None, mode="auto") -> Retrieval   # brief's name, thin wrapper
localize(app_key, snapshot) -> tuple[str, float, bool]
observe(outcome: Outcome) -> None                                      # executor reports every step result
ingest(sub_rag: str, records: Iterable[dict]) -> UpsertReport
status() -> RagStatus                                                  # root, degraded, table counts, embedder health
```

---

## 8. Learning loop (how the RAG gets better without code changes)

`Outcome(run_id, app_key, step: PlanStep, src_state, observed_snapshot, ok, effect, latency_ms, failure_code, popup)`
fans out:

| Sub-RAG | What it records |
|---|---|
| S2 | observation → edge counters → generation bump; new nodes/edges for unknown states |
| S4 | `n_ok`/`n_fail`; a probe that succeeds 2× in different runs → `verified=True`; 3 consecutive failures → `trust` drops one level (the organ_47 erosion mechanics) |
| S3 | `procedures.n_runs/n_ok`; grounded steps that executed write their surface form → command into the Lexicon (`kind=transcript_term`) |
| S5 | a failure whose resolution worked → new or strengthened playbook; a failed resolution → `n_fail` |
| S1 | a UIA name observed on a clicked control → icon vote `source=uia` |
| skills | a fully verified plan → `skills.compile()` (existing): the next identical goal is one hop |

Self-documentation (brief Part 4): after a crawl run, `rag.tools.self_doc(app_key, run_id)` writes `source_kind=self_doc`
chunks ("To open X: File → New Project, which opens dialog Y") generated **from graph paths, not from an LLM**. Unseen
apps therefore become explainable immediately.

---

## 9. Embedders and evolution (no-rewrite guarantees)

- `rag/embed.py` registry: `Embedder(id, dim, kind, embed(texts, mode))`.
  - Default text embedder: `nomic-embed-text@ollama-cpu`, 768-d, `search_document:` / `search_query:` prefixes.
- Each table records `embedder_id` per row; `meta.json` records `active_text_embedder`.
  - Swapping the model = add an embedder, set it active, run `rag.tools.reembed(table)`.
  - Until done, vector search only covers rows with the active `embedder_id`; FTS covers everything. No mixed-space
    search, ever.
- Embedder down → rows written with `vector=NULL`; `status().degraded` includes `embedder_down`; the reembed job heals.
- A visual embedder (SigLIP/CLIP via onnxruntime 1.27, already installed) can later fill `ui_states.visual_vec` and an
  `icon_vec` column, with no schema change. That is its only slot.
- **Migrations:** `rag/migrations/NNNN_*.py`, applied in order by `storage.open()`; `meta.json.schema_version` tracks
  them. New fields go to `extra_json` first and are promoted to columns by migration only when queried.

---

## 10. Nucleus ⇄ Edge packs (brief Part 5)

- `rag.tools.export_pack(app_key, include={graph, lexicon, fast_paths(verified), playbooks, icons(labels+fp)})`
  → `.hjpack` (zip of JSONL + meta). Screenshots and transcripts are excluded by default.
- PII: every text field passes `professor/privacy.py` scrubbing. Landmark names are already structural (§5.2); dialog
  titles get paths and names masked.
- `import_pack` merges by ID. Observations are appended with `source=pack:<origin_uuid>`; counters are rebuilt. Trust
  from a pack is capped at `learned` until verified locally.

## 11. Telemetry
`telemetry.db`: `router_calls(ts, app_key, intent, tier, ms_total, ms_by_probe_json, n_plans, best_p, grounded_ratio,
llm_used, degraded)` and `outcomes` mirrored from observations. An `SsmsSink` adapter (pyodbc) is optional and off
by default. It is not part of Checkpoint 2.

## 12. Performance budgets (asserted by tests)
| Operation | Budget (warm, local SSD) |
|---|---|
| Stage A+B (context + intent) | ≤ 10 ms |
| `localize` (≤ 2k nodes/app) | ≤ 15 ms |
| S1 lookup | ≤ 1 ms exact, ≤ 5 ms Hamming at 100k |
| S3 hybrid (≤ 200k chunks/app, prefiltered) | ≤ 60 ms p95 |
| S2 path (≤ 5k nodes) | ≤ 20 ms |
| `retrieve()` without LLM | ≤ 150 ms p95 |
| LLM rewrite | ≤ 4 s, at most 1 per query, cached |

---

## 13. Module layout
```
rag/
  __init__.py        public API (§7.9)
  config.py          thresholds, route costs, shares, priors (one place; all tunables)
  storage.py         root resolution, meta.json, migrations, connections (LanceDB, SQLite), degraded status
  types.py           Evidence, PlanStep, Plan, Query, Retrieval, Outcome, UpsertReport, RagStatus
  embed.py           embedder registry, ollama-cpu nomic, cache
  lexicon.py         alias spine + resolve
  statekey.py        landmarks, window_kind, IDF-Jaccard, exact_sig
  icons.py           Sub-RAG 1 (IconMemory adapter + dhash64)
  graph.py           Sub-RAG 2 (graph.db, NX view, localize, path_to, observe)
  procedures.py      Sub-RAG 3 (chunks, procedures, hybrid, grounding)
  fastpaths.py       Sub-RAG 4
  recovery.py        Sub-RAG 5
  router.py          Stages A–E, fusion, caches
  adapters/          command_registry, knowledge_store, history, workflows, manual_rag, popup_policy, atlas_uimap, keymaps, skills
  tools.py           reembed, rebuild_edges, merge_roots, export_pack, import_pack, self_doc, import_manuals
  migrations/0001_initial.py
```

## 14. Tests (all offline; no live scans)
File `si_tests_rag.py`, registered into the Professor suite like `si_tests_safety.py`. Each test builds a temporary
root (`AI_STORAGE_ROOT` = a tmp dir) and fixture data.

| ID | Proves |
|---|---|
| RG1 | Storage: env root used; a missing root falls back and reports `degraded`; paths are stored root-relative; migrations idempotent |
| RG2 | State key: the same window with changed document title / list contents / one renamed button → same `state_id`; a different dialog → new id; ID never changes after an alias merge |
| RG3 | Graph: observations rebuild identical edge counters; Dijkstra picks the hotkey over a 3-click menu path; an unsafe edge is never on a path unless allowed; a replan after state mismatch reaches the goal on a fixture graph with a stochastic edge |
| RG4 | Lexicon: icon label, transcript term, keymap action and UIA name for one command all resolve to the same `command_id`; a tie is broken by the live state |
| RG5 | Contamination: Blender and AutoCAD fixtures both contain "extrude"; an AutoCAD query never returns a Blender row except via `borrow`, which is tagged and probe-only |
| RG6 | Execution gate: an unverified/LLM hotkey comes back as `probe`, never a direct step; 2 successful probes promote it; 3 failures demote it |
| RG7 | Fusion: utility ranking on fixtures; calibration within ±0.15 per reliability bucket |
| RG8 | Embedder swap: rows from embedder A are not vector-searched under B; FTS still returns them; `reembed` heals |
| RG9 | Recovery: elevation/destructive/payment playbooks always `needs_human` even with 100 % success history |
| RG10 | Budgets: `retrieve()` p95 ≤ 150 ms on a 50k-chunk, 2k-node synthetic app (skipped as ENV-BLOCKED if lancedb is missing) |
| RG11 | Round trip: `export_pack` → `import_pack` into a fresh root gives identical answers for 20 fixture queries; PII strings absent from the pack |

The embedder in tests is a deterministic hashing embedder (`embed.HashEmbedder`, 64-d) so tests need no Ollama.

## 15. Implementation order for Sonnet (each step committed and tested before the next)
1. `config`, `types`, `storage` (+ migration 0001), `embed` (Ollama + Hash) → RG1, RG8 (part)
2. `lexicon` + adapter from `command_registry` → RG4
3. `statekey` + `graph` (+ adapters knowledge_store, history, atlas_uimap) → RG2, RG3
4. `fastpaths` (+ adapters command_registry, keymaps, skills) → RG6
5. `procedures` (+ adapters workflows, manual_rag importer) → part of RG5
6. `recovery` (+ adapter popup_policy) → RG9
7. `icons` (IconMemory relocation + dhash64)
8. `router` → RG5, RG7, RG10
9. `tools` (reembed, rebuild_edges, export/import pack, self_doc) → RG8, RG11
10. Wire-in (separate commits): `manual_rag` facade, the executor calling `rag.observe`, the professor teacher calling
    `rag.retrieve`. Each wire-in keeps the old path as fallback when `rag.status().ok` is false.

## 16. Decisions recorded
- Phantom alpha=1 capture: **left out** (user decision 2026-10-16). Not seeded in Sub-RAG 5.
- No CLIP/SigLIP in v1; reserved columns only (§5.1, §9).
- `state_id` is an assigned UUID, not a content hash (§5.2).
- NetworkX is a view; SQLite is truth (§5.2).
- Text embedder: nomic-embed-text on CPU via Ollama, as the project already does.
- SSMS: optional sink only, not in Checkpoint 2.

---

## 17. As built (Checkpoint 2 implementation, Sonnet, 2026-10-16) -- where the code differs from sections 1-16, and why

Everything below was found by measuring on this machine (lancedb 0.30, sqlite 3.50, RTX 3050 box, no GPU use). Sections 1-16 remain the intent; this section is the truth where they disagree.

| # | Design said | Built | Why (measured) |
|---|---|---|---|
| 1 | Lexical leg = LanceDB FTS | **SQLite FTS5** (`text.db`, `rag/textindex.py`): contentless `tf_<table>` + `ti_<table>` payload, app as an indexed token (`app : <id> AND text : (...)`), porter stemming, AND-first then rarest-terms OR cascade | lancedb 0.30 FTS ignores rows written after the index was built for any term the index already knows (a fresh row was invisible to a query that contained a known word), and costs 45-80 ms at 5k rows. FTS5 is transactional with the write. `textindex.ensure_consistent` heals from Lance if the two ever disagree. |
| 2 | Counters (`n_ok`, `n_fail`, `consecutive_fail`, `ok_runs`, promotion/demotion) in the Lance rows | **`learn.db`** (`fast_stats`, `proc_stats`, `playbook_stats`), overlaid on read; Lance rows are immutable after ingest | Rewriting a row on every observation is slow and (see 1) made it invisible to text search. This is also what section 1.8 (append observations, derive aggregates) required. The Lance `n_ok`/`n_fail` columns are the ingest-time seed, added to the learned counts. |
| 3 | Generation counters in `graph.db` | **`cache.db:gens`**, scopes `graph:<app>`, `fast:<app>`, `proc:<app>`, `recovery:<app>`, `lexicon:<app>` | one place for every invalidation |
| 4 | BITMAP scalar index on `app_key` | **none** | with `merge_insert`, a BITMAP index made filtered reads return empty ~1 run in 3. The app filter is a column scan; cost scales with the app's rows, which is the quantity that matters. |
| 5 | k alternatives by Yen's algorithm | k **distinct goal edges**, each with its cheapest approach (Dijkstra) | alternatives that differ only in an intermediate hop add no information to a tutor or an executor |
| 6 | IVF_PQ built inline at 100k rows | **explicit `tools.build_ann` / `tools.maintain`**, threshold **20k** rows per table; `status().degraded` carries `ann_recommended:<table>` until built | flat vector scan = ~3.3 us/row (164 ms/query at 50k x 768-d, one app); IVF_PQ build = 112 s for 50k rows, so it cannot run in an interactive ingest. With the index: ~35 ms/query. |
| 7 | Budgets: hybrid S3 <= 60 ms at <=200k chunks/app | **Per app**: flat <= ~15k chunks (typical 40 ms at 5k), ANN beyond; test ceiling 80 ms (design 60) because OS noise flakes 60 ms 1 run in 3; retrieve() typical ~52 ms, ceiling 150 | measured (RG10, best of 3 rounds, every query distinct) |
| 8 | Probe budgets | **soft**: optional probes (rewrite, supporting passages) are skipped once the budget is spent; essential probes (procedures, borrow) always run | a cold first query overran 150 ms and skipped the borrow fallback |
| 9 | Router cache key = (app, state, goal tokens, ...) | key = **the whole normalised text** | the first version dropped single-digit tokens: "cube of size 3" and "size 4" shared a cached answer (RG13 now pins this) |
| 10 | Script candidates only for tier 3 | scripts compete whenever the goal is a **creation, carries a number/quoted value, or the app is tier 3** | "create a cube of size 3" resolved to the UI command "Add Cube" and never considered the parametrised template |
| 11 | `export_pack` ships verified fast paths | ships every **non-LLM hotkey / chord / wm_command / menu_accel** (trust capped at `learned` on import, `verified` reset) | otherwise an edge node loses the catalog hotkeys its own registry would also give it, and answers differ (RG11) |
| 12 | State description includes the dialog title | `describe_landmarks`: window kind + **sorted structural landmark names**, no titles | a main window's title is the document name (content); makes the description reproducible from a pack |
| 13 | Recovery plan steps are executable routes | non-click playbook actions (`perceive`, `localize`, `replan`, `wait`, `retry_once`, ...) are steps with `route="meta"` and the action in `args` | they are instructions to the executor, not input events |
| 14 | `Rag` single embedder | `Storage(embedder=...)`; vectors zero-padded to `config.VEC_DIM=768`; an embedder wider than that is refused by `reembed` (`dimension_too_large`) | a fixed-size Lance vector column; widening needs a migration |

### Tests added beyond section 14
RG12 (icon vault: dHash path, collision guard, UIA-over-VLM, misses as gaps), RG13 (intents, tiers, cache + invalidation, numbers in the key, degraded embedder), RG14 (30 rounds of interleaved writes/reads: guards index staleness), RG15 (self_doc, explore targets, adapters). RG1-RG11 as specified. All offline; temp roots; `HashEmbedder`.

### Not done (deliberately), in priority order
1. **Wire-ins (section 15 step 10).** The executor must call `rag.observe(Outcome(...))` after every step; the teacher/Professor must call `rag.retrieve(Query(...))`; `manual_rag.ManualIndex.search/retrieve` should delegate to Sub-RAG 3 (`tools.import_manuals` already moves its chunks in). These files carry other sessions' uncommitted changes, so editing them here would have mixed two changes; each wire-in must keep the old path as a fallback when `rag.status().ok` is false.
2. **The default LLM rewriter** (`rag/adapters/llm_rewrite.py`) is written but not attached: `Rag(rewriter=...)` is opt-in until the brain/gatekeeper API is confirmed.
3. **Live data.** Nothing here has seen a live window, a real transcript corpus, or the SSD. The E: drive was not mounted; the storage root falls back (and says so). Checkpoint 3 (harvesters) will be the first real ingest.
4. **Open numbers**: the 200k-chunks/app point is extrapolated, not measured (50k measured).

### 17b. What the first REAL harvested store changed (Checkpoint 3, 2026-10-16)
The offline suite passed while the first run against real data (6 YouTube transcripts, 64 scraped/seeded hotkeys, 5 macro templates) showed 3-7 s queries and mis-ranked answers. Measured causes and the fixes (all pinned by RG18):

| # | Found | Fix |
|---|---|---|
| 15 | The LLM rewriter fired on almost every query. "Weak recall" was a score taken AFTER multiplying by quality and trust, which on real auto-captions is always tiny. | Weak = **no passage found by both retrieval legs** (raw RRF < `WEAK_RECALL_SCORE` 0.025), no exact chord hit, no command resolved. For DO: nothing resolved and no strong passage/procedure (not "no plan is grounded": without a scanned UI every plan is a probe). |
| 16 | The "4 s" LLM cap was a read-timeout; one call took 6.2 s. | The rewriter runs in a worker; the router stops waiting at `LLM_REWRITE_TIMEOUT_S` (wall clock) and answers without it (`trace.why = "timeout"`). |
| 17 | A cold Ollama embedding model costs ~1 s and the query-embed timeout was 30 s. | `keep_alive: 30m`; query embeddings get a 2 s cap (vector leg skipped for that query, lexical still answers); a timeout backs off 5 s, a connection failure 30 s. |
| 18 | "what is the shortcut for clearing memory" ranked the exact `Ctrl+L / Clear memory` row 5th. "what does ctrl plus h do" had no chord understanding. | Questions about keys (`shortcut / hotkey / keyboard / chord`) weight the hotkey rows x2.5 in fusion; spoken or typed chords ("ctrl plus h", "Control + Shift + Esc") are normalised and looked up by exact payload FIRST (`FastPaths.by_chord`). |
| 19 | LOCATE with no scanned UI state returned nothing. | Falls back to hotkey rows + passages and says so (`answered_from_text_not_from_a_ui_map`). |
| 20 | A router-cache entry computed by older routing logic was served for an hour after a code change. | `config.ROUTER_VERSION` is part of every cache key. **Bump it whenever routing, fusion or planning logic changes.** |

Measured on the real store after the fixes: 28-49 ms per uncached query (was 3-7 s); the first query of a process still pays the cold embedding model (~0.8 s).

## 18. Checkpoint 3: `harvest/` (as built)
- `free_master_harvester`: seed apps first (matched to Winget PackageIds), then the most recently maintained Winget entries (**the real index has columns PackageId, Version, Name, LastUpdate -- no Tags**; the brief's filter would have silently queued only the seeds), tier -1 = not yet classified. `youtube-transcript-api` 1.x `fetch()` (the brief's `get_transcript` no longer exists). Statuses: Downloaded | Cached | No_Subtitles | **Other_Language:<codes>** | Blocked | Error. Resumable, rate-limited, stops when blocked. Search is biased to English (first live run: 4 of 6 top-viewed results were Hindi-only).
- `free_hotkeys_and_macros_harvester`: seeds + shortcut tables (**robots.txt-respecting; an unreadable robots.txt means "not allowed"**), tldr-pages, opt-in model layer (trust `llm`). **The brief's "first two columns" table parser stored a votes column as the shortcut and the keys as its action** (`shortcut="5", action="Alt + 1"`); `parse_shortcut_table` finds the key column by content and repairs mnemonic-underline spacing ("m emory"). A fresh scrape replaces that app's stale scraped rows.
- `video_pipeline`: OpenCV scene changes + delta box (verified on a synthetic tutorial: events at 3.0 s and 6.0 s, box over the opened menu), action-moment sections via yt-dlp, CPU faster-whisper fallback, SoM of a still via `professor.sweeper.scan(image=..., mode="quick")` (classical CV + Tesseract; no model, no GPU, no live window). Delta-region rescans return full-frame coordinates.
- `video_explain`: transcript + keyframes + SoM -> RAG entries and Unsloth-shaped training pairs (system / user[image + numbered elements + goal] / assistant[JSON action list]); `target_id` is set only when the spoken target matches a numbered element; `grounded` says so; verify_expectation comes from the delta-region scan; pair ids make re-runs idempotent.
- `bridge`: transcripts / hotkeys / macros -> `knowledge_chunks` / `procedures` / `fast_paths` (the brief's `workflow_knowledge` / `fast_execution` do not exist; one schema serves every source). Hotkeys and macros are ingested BEFORE transcripts; actions from seed / published-table rows register low-trust commands in the Lexicon (model-written rows never do). Nothing is ever `verified`.
- **Not exercised live:** `download_section` (yt-dlp sections) and `transcribe_audio` (faster-whisper) -- both need a network download / model download and are explicit-use only; no video file was fetched.
- **First live batch (3 apps x 3 videos):** 6 English transcripts (Notepad 1, Calculator 3, Paint 2), 3 Other_Language, 1 subtitles-disabled; 50 clean Calculator shortcut rows from defkey (Notepad and Paint have no page at the guessed URL); 0 tldr rows (GUI apps).

## 19. Checkpoint 4: `train_qlora.py` and what the first real-footage pass changed (2026-10-17)
**Data quality, found on real footage, fixed at the source (HV9):**
- A loose YouTube search filed two general "Windows shortcuts" videos under the *calculator* partition (clipboard history, virtual desktops, magnifier). `free_master_harvester.on_topic()` now gates every transcript: the title names the app, or the speaker names it >= 5 times; otherwise status `Off_Topic` and the file moves to `transcripts_json/_off_topic/` (quarantined, not deleted). `bridge.audit_topics(rag, fix=True)` re-judges what is already stored and purges the chunks (`Procedures.forget_source`, which keeps the lexical index in sync).
- `video_pipeline.action_moments` counted "use" / "add" / "set" as UI actions ("use this, but it can come in handy"). Now: a key chord, or a UI verb (click, press, select, drag, type, open, ...) with a real object (not "this"/"it").
- `video_explain`: ONE instruction labels the FIRST scene change it causes (a step used once); later changes belong to later speech. Lookback 5 s. OCR debris ("McC", "ynVerter", "|||") is not shown as "what appeared".
- First real pass: 22 s of footage -> 3 pairs, 2 usable. The brief's target is 10-25k pairs; this pipeline is a trickle until it is run over many videos, so the trainer refuses to run below `--min-examples` (default 200) and defaults to grounded pairs only.

**`train_qlora.py` -- facts, measured on this machine (RTX 3050 6 GB, 5.03 GiB free to an allocation; torch 2.7.1+cu118, transformers 5.19, peft 0.21, bitsandbytes 0.50; Unsloth NOT installed):**
- Qwen3-VL-8B (architecture read from the local GGUF header: 36 layers, hidden 4096, FFN 12288, 32/8 heads, vocab 151,936 -> 6.95 B transformer params + 1.24 B embeddings/head + ~0.45 B vision) needs **8.3-9.2 GiB** for QLoRA even at seq 1024 with Unsloth. **It cannot be trained on this GPU.** 4B is borderline (4.9-5.0 GiB vs 5.03 free); **2B fits with ~1.2 GiB to spare**. The 4B/2B specs are the published configs, unverified locally until a config.json is downloaded.
- Free VRAM is taken from `torch.cuda.mem_get_info` (what an allocation sees), in a CHILD process: `nvidia-smi` reports ~1 GiB more free on Windows, and initialising CUDA in the caller poisons it -- **a CPU Trainer run in a process that has initialised CUDA segfaults on this stack** (reproduced: exit 139).
- The plain-transformers path computes logits and loss only over the answer positions (`logits_to_keep`); on the tiny model this equals the model's own loss to 6 digits (7.121584 = 7.121584). It removes ~2.9 GB of full-sequence logits at seq 2048.
- Not `peft.prepare_model_for_kbit_training` (it upcasts every non-quantised parameter to fp32: +1.2 GB for an 8B's embeddings).
- transformers 5.x Qwen3-VL REQUIRES `mm_token_type_ids` whenever images are passed; the processor emits it and the collator forwards/pads every per-token tensor.
- Verified on a tiny random Qwen3-VL built from config (no download): LoRA targets only language-model projections (14 of 14; vision blocks only with `--vision`; never embeddings/lm_head); training on the real GPU with `paged_adamw_8bit` + bf16 + gradient checkpointing + sliced loss runs and lowers the loss (TR9); adapters save and reload bit-identically.
- **NOT verified: training a real model.** No trainable weights are on disk (only inference GGUFs), Qwen3-VL-2B/4B would be a multi-GB download, and the Unsloth backend is untested (not installed). Export is a plan (merge -> llama.cpp GGUF + mmproj -> the same `llama-server` flags `start_hojaiga.bat` uses); Ollama cannot reliably load a custom vision GGUF + projector.
