# HoJaiga / Codex Handover: Blunt Technical Confession

**Snapshot date:** 2026-10-20 (Asia/Kolkata).  
**Scope:** facts directly inspected in this workspace during this Codex session. “Verified” below means verified by stored data or a visible app outcome, not inferred from a passing unit test.

## 1. EXACT FILES CREATED OR MODIFIED BY CODEX:

### Attribution warning

This repository was already heavily dirty and shared when this session began. `git status` currently shows 37 modified tracked files plus a very large set of untracked files/directories. Do **not** stage or commit the whole working tree. I can confidently attribute only the files below to my work in this session; I cannot truthfully attribute the rest.

| Full path | Codex change / what it does today | Git state / known import status |
|---|---|---|
| `D:\new_automation\All codes\core_organs\harvest\web_search_failover.py` | Modified source acquisition. Adds vendor-document hosts, labels source trust, stores cited document text, and prevents recovery/troubleshooting articles from becoming generic procedures or visual training pairs. It still performs web harvest; it does **not** make an action verified or executable. | Modified, uncommitted. Imported indirectly by the curriculum test without an import error. |
| `D:\new_automation\All codes\core_organs\harvest\curriculum.py` | Created curriculum planner for the 25 static archetypes. It selects official source URLs, reports evidence coverage, and aliases `WhatsApp` to `whatsapp_desktop`. It is an acquisition/coverage helper, not a live executor or trainer. | Untracked. Imported successfully under Python 3.13. |
| `D:\new_automation\All codes\core_organs\rag\router.py` | Modified tutor retrieval: if there is no procedure, it can return official document chunks as cited teaching evidence without fabricating a `Plan`. | Modified, uncommitted. Imported successfully under Python 3.13. |
| `D:\new_automation\All codes\core_organs\train_qlora.py` | Modified evaluation parsing to distinguish strict valid JSON from a recoverable truncated action, and added deterministic app/action-balanced bounded evaluation slicing. This changes reporting only; it does not improve the existing adapter by itself. | Modified, uncommitted. Imported successfully under Python 3.13. |
| `D:\new_automation\All codes\core_organs\si_tests_rag.py` | Modified offline regression fixture for “official document can teach but cannot become a plan.” This is test-only. | Modified, uncommitted. |
| `D:\new_automation\All codes\core_organs\si_tests_train.py` | Modified offline regression fixture for strict JSON accounting and balanced slice selection. This is test-only. | Modified, uncommitted. |
| `D:\new_automation\All codes\core_organs\si_tests_curriculum.py` | Created offline contract checks for the curriculum/source-admission helpers. This is test-only. | Untracked. It imports the new curriculum module successfully. |

No `run_visible_live_test.py` was created. Creating one that claimed to use Qwen/RAG would have been dishonest: the visible trial used the supported foreground controller directly, not HoJaiga’s end-to-end runtime.

### Known broken or incompatible entry point

`D:\new_automation\All codes\run_live_rag_verification.py` is present but is not compatible with the current sources as written: it imports `ArchetypeRouter` and `build_rag_70_30_split` from `core_organs.harvest.curriculum`. The current router class is in `core_organs.rag.archetypes`, and `build_rag_70_30_split` does not exist in `curriculum.py`. Do not use that script as evidence.

### Runtime defect encountered while inspecting stores

Calling `r.proc.stats()` with an empty `app_key` throws a LanceDB SQL parser error because it can pass an empty `WHERE` expression to `count_rows`. Store totals below were obtained from `RagStatus.tables` and direct store inspection instead. This is a real defect, not an import failure.

## 2. TRUE STATE OF THE 5 RAG STORES & 25 ARCHETYPES:

### Exact current store counts

RAG root: `D:\new_automation\data\ai_root\rag`.

| Store | Exact persisted count | Important qualification |
|---|---:|---|
| Icon Memory | **380** icon records; **389** UIA votes; 367 dHash buckets | These are visual/icon associations, not a proof that a command can be executed safely. |
| UI State / Action Graph | **303** UI states, **680** edges, **1,056** observations | All 680 edges have source `observed` / trust `learned`. A learned edge is not equivalent to a robust, reusable workflow. |
| Manuals / Procedures | **277** knowledge chunks and **1,434** procedure rows | Procedure trust: 916 `learned`, 499 `web`, 12 `official_doc`, 6 `verified`, 1 `transcript`. Count is not quality. Blender alone supplies 848 procedure rows. |
| Verified Fast Paths | **242** total fast-path rows; only **2** have `verified=True`; **240** are not verified | Source/trust breakdown: 111 catalog/keymap, 108 web, 21 seed, 2 verified. Calling all 242 “verified fast paths” is false. |
| Popup / Error Recovery | **51** playbooks | 9 seed playbooks; 42 rows have no populated trust value. No live foreground popup recovery was verified in this session. |

### What the 25 archetypes really are

**Real, autonomous executable archetype plans: 0 of 25.**

Every one of the following is presently a static classification prior and non-executable skeleton, not a proven universal action plan:

`word_processor`, `spreadsheet`, `presentation`, `text_editor`, `code_ide`, `raster_editor`, `vector_editor`, `diagram_whiteboard`, `3d_modeler`, `cad_engineering`, `video_editor`, `audio_daw`, `browser`, `email_client`, `chat_messenger`, `media_player`, `pdf_reader`, `file_manager`, `terminal`, `calculator`, `settings_panel`, `database_client`, `note_taking`, `screen_capture_stream`, `system_utility`.

`core_organs/rag/archetypes.py` explicitly makes an archetype fallback a confidence-0.45 **skeleton only**. It lists phases, conventional shortcuts, and traps; it does not return verified coordinates or resolved `PlanStep`s. `fit_weight` is deliberately 0 by default because the sparse fitted control-word centroids reportedly hurt held-out routing. The 25 names/examples are hand-authored labels, not a learned model of all software.

Some archetypes have app-specific stored material, but that is not the same as a working archetype executor. Examples: Notepad has 110 graph edges/253 observations/11 fast-path rows; Calculator has 42 graph edges/48 fast-path rows; PowerPoint has 31 graph edges/5 fast-path rows; Paint has 20 graph edges; Excel has 15 graph edges/2 fast-path rows. Most of those fast paths are still unverified and none was demonstrated through the current foreground Qwen+RAG pipeline.

The clearest counterexample is `file_explorer`: a query against the actual scanned Explorer semantics (“navigate to `D:\new_automation` using Address Bar, not search”) returned one official Microsoft support chunk and **0 plans**. It had 5 document chunks, 0 procedures, 0 fast paths, 0 commands before the manually logged run, and no executable RAG route.

### Known RAG retrieval, deduplication, and routing defects

1. **No real universal archetype executor exists.** The router can classify from words and emit advice, but it does not bind a skeleton to live controls and verify an action chain.
2. **Namespace fragmentation is severe.** Examples in the stores include `paint`, `ms_paint`, and `microsoft_paint`; `chrome` and `google_chrome`; `code` and `visual_studio_code`; `whatsapp_desktop`; `winword` and `word`. Knowledge, fast paths, and graph edges under one key are often unreachable from another key for the same application.
3. **The File Explorer live outcome was logged with the wrong snapshot shape.** `rag.statekey.features()` reads `nodes`, not the manual `controls` field I supplied. The before state, wrong-folder state, and correct-folder state all collapsed to state ID `0250e9c36fd14ab4ac25d1d23d0fca23`. Two outcome rows exist, but they are not a useful navigation transition graph. The error/success text is real; the topology learning is not adequate.
4. **State identity intentionally drops paths, document text, and list contents.** That prevents content churn from minting a state, but also means it cannot distinguish `D:\weltec ai-ml` from `D:\new_automation` without a separate semantic postcondition layer. It is unsafe to use state equality as destination verification.
5. **Procedure deduplication is source-sensitive.** Procedure IDs include `source_ref`, so semantic duplicates from different sources can remain distinct. The 1,434 count should not be read as 1,434 distinct capabilities.
6. **The collection code’s source trust is only an admission label.** A page on a `docs`/`support`-named subdomain can be called `official_doc`; host ownership is not cryptographically verified. No web statement becomes a verified action, but the label can still overstate provenance.
7. **Many “learned” records are harvested/inferred, not live-tested foreground experience.** The trust vocabulary is inconsistent across stores (for example, 42 recovery rows have blank trust).
8. **The current router may return useful cited documents while producing no plan.** That is intentional safety behavior, but callers must handle it as “cannot execute,” not silently switch to arbitrary UI control heuristics.
9. **The user-pasted live archetype script is incompatible with the actual API** (see section 1). Any claimed 70/30 routing score from it is not reproducible from this checkout.

## 3. TRUE STATE OF QWEN3-VL-2B QLORA TRAINING & EVALUATION:

### Latest saved adapter and data

- Latest identifiable adapter: `D:\new_automation\data\ai_root\harvest\training\runs\run_20261019_v3split\adapter\adapter_model.safetensors`
- Matching resumable checkpoint: `D:\new_automation\data\ai_root\harvest\training\runs\run_20261019_v3split\checkpoint-200\adapter_model.safetensors`
- Base configured in `adapter_config.json`: `Qwen/Qwen3-VL-2B-Instruct`
- LoRA rank/alpha: 16/16; target modules are language-model projections. This is a LoRA adapter, not a full model checkpoint.
- Adapter file size: 69,788,264 bytes. Last write: 2026-10-19 03:36 local time.
- Training reached 200 steps / 1.9608 epochs. Training loss began at **1.015692** (step 5), reached a minimum recorded **0.136265** (step 195), and ended at **0.285250** (step 200). This is training loss, not evidence of live generalization.
- Dataset at `D:\new_automation\data\ai_root\harvest\training\ui_training_dataset.jsonl`: **1,305** total valid-JSON rows; **1,208** rows marked grounded; **1,205 valid grounded visual pairs** after UI-frame validation; **3 grounded rows rejected** because their frames were not verified software UI. There are 97 ungrounded rows.

The complete recorded loss sequence is in `checkpoint-200\trainer_state.json`; it contains 40 logging points at steps 5..200. Do not interpret a falling loss curve as app-operating ability.

### `eval_balanced16.json`: exact saved results

Path: `D:\new_automation\data\ai_root\harvest\training\runs\run_20261019_v3split\eval_balanced16.json`.

This is a deterministic, app/action-balanced **16-example slice of 205 held-out rows**. It loads saved screenshots; it does not operate a desktop.

| Model | n | Valid JSON | Right action kind | Exact target/action |
|---|---:|---:|---:|---:|
| Base Qwen3-VL-2B | 16 | 0.875 (14/16) | 0.562 (9/16) | 0.438 (7/16) |
| Adapter | 16 | 1.000 (16/16) | 1.000 (16/16) | 0.688 (11/16) |

Adapter failure breakdown in that 16-row file:

- **5/16** were valid JSON with the right action kind but selected the wrong target ID.
- Errors were: Home item gold 15 → predicted 10; Customize Quick Access Toolbar gold 8 → 15; W3Schools Adventure App gold 12 → 11; View/Space+drag gold 11 → 7; View Results gold 59 → 56.
- There is **no coordinate-miss metric** in this report. The model predicts a numbered target ID, not an `(x,y)` coordinate, and the report never clicks it.
- There is **no labelled-vs-unlabelled-icon breakdown** in this report. It cannot prove performance on unlabeled icons.

The base failures in the same file also include malformed action strings such as `click|target`, missing target IDs, and wrong target IDs. The adapter’s 100% JSON/action-kind score on 16 saved examples does not establish robust target selection.

### `eval_full205.json`: truth

There is **no** `eval_full205.json` anywhere under `D:\new_automation`, no persisted partial output, and no persistent log/counter from which an exact completed-example count can be recovered.

A full GPU evaluation was attempted earlier. When asked to stop it, the referenced process (PID 8308) had already exited. Because it wrote no `eval_full205.json` and no durable progress log was found, the exact number of examples completed is **unknown**. It must not be reported as 205, 0, or “finished.” The reason it exited is also unknown from available evidence (could be normal completion without report, crash, or an earlier stop).

`eval_v3_summary.json` exists and mentions 250 held-out rows / 205 rows kept by a Top-40 filter with composite values such as `pipeline: 0.672`. It is **not** named `eval_full205.json`, has no complete per-example Qwen responses, and must not be relabelled as a completed 205-example Qwen evaluation.

## 4. THE BRAIN-BODY DISCONNECT (WHY LIVE TESTS FAILED OR BYPASSED QWEN/RAG):

### Actual architecture versus the visible trial

`core_organs/agent_executor.py` contains an injectable design for `observe -> retrieve -> ground -> guard -> act -> verify -> learn`. In principle its `AdapterGrounder`, RAG object, observer, and actor can be composed. In this session they were **not** composed into a foreground production run.

The visible trial used the supported native foreground controller directly:

1. it read live accessibility information;
2. it directly clicked, typed, pressed keys, and dragged in Windows apps;
3. it checked visible/app accessibility state afterward.

RAG was queried separately for Explorer **after** live control discovery and returned 0 plans. Qwen3-VL-2B + this adapter was **not loaded or asked to select a target**. The App Scanner used in the visible trial was the controller’s accessibility scan, not a recorded invocation of HoJaiga’s production `app_scan`/`fast_uia` pipeline. Therefore these trials prove only that a foreground controller can manipulate three simple apps; they do **not** prove HoJaiga intelligence, RAG routing, Qwen grounding, or autonomous closed-loop operation.

### Every observed live-trial failure/limitation

1. **Notepad first-pass verification failure:** I initially believed text had been typed into a disposable Notepad tab. A later live capture showed that active tab blank. The claimed first completion was wrong and was retracted.
2. **Notepad second pass:** the exact requested string was then visibly typed and selected (44 characters). A Font settings pane had been opened in an earlier view, but the typed-text → Ctrl+A → Font-controls sequence was not reverified as one uninterrupted end-to-end run before the controller lost access to the app windows. Thus the complete Notepad task is not proven end-to-end.
3. **Paint:** a visible black diagonal stroke was made by a real drag. Paint’s Undo control became enabled, which is credible application-level evidence of a changed canvas. It was not chosen by RAG/Qwen and did not create a Qwen pair.
4. **Explorer wrong destination:** the first attempt landed in `D:\weltec ai-ml`, not `D:\new_automation`. The live breadcrumb exposed the mistake. This was a real failure, not a pass.
5. **Explorer recovery:** `Ctrl+L`, type `D:\new_automation`, Enter produced title/breadcrumb for `new_automation` and a status count of 909 items. This is a successful manual recovery, not a retrieved plan.
6. **Missing executable RAG plan:** the actual Explorer RAG lookup returned official documentation and **0 executable plans**. Any later action was an external controller heuristic, not RAG execution.
7. **Focus/controller loss:** later calls could no longer enumerate Notepad, Paint, or Explorer although they had previously been visible. The cause is not known. This prevented a final contiguous verification and demonstrates brittleness around foreground ownership/focus.
8. **No durable visual proof files:** no `live_visual_proof\before.png`, red-box overlay, or `after.png` files were produced. The supported controller displayed protected in-session captures but did not permit exporting the screenshot buffer or drawing fake overlay files. Do not claim those files exist.
9. **No programmed 0.4-second cursor glide guarantee:** the controller could issue real foreground input but did not expose a configurable mouse-duration API. There is no measured “duration=0.4” proof.
10. **No live Qwen training data was harvested.** Protected live screenshots could not be exported to the existing JSONL/frames format. The two manual Explorer outcomes were written to RAG telemetry, but, because of the malformed snapshot shape described in section 2, they are not valid graph transition training data and are not grounded visual pairs.

## 5. CURRENT ENVIRONMENT & GPU/PYTHON SPLIT:

| Runtime | Exact executable | Relevant packages / capability |
|---|---|---|
| Main QLoRA + current RAG inspection runtime | `C:\Users\dhruv\AppData\Local\Programs\Python\Python313\python.exe` | `torch 2.7.1+cu118`, CUDA available, `peft`, `transformers`, `bitsandbytes`, and `lancedb` installed. This is the only inspected Python that has the needed QLoRA stack. |
| `hojaiga_env` | `D:\new_automation\hojaiga_env\Scripts\python.exe` | `torch 2.14.1+cpu`, `transformers`, `lancedb`; **no** `peft`, **no** `bitsandbytes`, **no** CUDA, **no** `unsloth`. It cannot run the present 4-bit QLoRA evaluation/training. |
| Anaconda / user Jupyter | `D:\Anaconda\python.exe` | In the inspected environment: no `torch`, `peft`, `transformers`, `lancedb`, `bitsandbytes`, or `unsloth`. Existing Anaconda/Jupyter processes were intentionally left running. |

Hardware observed: **NVIDIA GeForce RTX 3050 6GB Laptop GPU**, driver 592.82, 6,144 MiB total VRAM.

### Jobs stopped before this handover

The following workspace jobs were identified and stopped:

- PID 5668: `tail.exe` following `gauntlet_blender6.log`
- PID 29192: `tail.exe` following `gauntlet_d2.log`
- PID 13324: `tail.exe` following `gauntlet_FINAL.log`
- PID 956: `llama-server.exe` serving **Qwen2.5-VL-7B GGUF** on port 8081 (this is not the Qwen3-VL-2B LoRA adapter)
- PID 29912: Python 3.13 `core_organs\vision_server.py --port 18765`

After stopping them, no listener remained on ports 8081 or 18765; `nvidia-smi` showed 0 MiB GPU memory used and no compute-app entry. Codex desktop may still use graphics, but there was no reported compute allocation. No Ollama process was identified/stopped; the RAG status labels the embedder `nomic-embed-text@ollama-cpu` and was healthy at inspection time.

## 6. PRIORITIZED FLAW LIST FOR OVERNIGHT AUTO-FIX:

1. **Build one real foreground closed-loop runner before adding data or retraining.** It must call the actual HoJaiga scanner, RAG retrieval, Qwen adapter grounder, guard, actuator, verifier, and `rag.observe` in one traceable process. Reject any run where a stage is bypassed.
2. **Create a durable live-run recorder.** For each step, persist masked before/target-overlay/after frames, exact scan/SoM, model prompt and reply, selected control identity/rectangle, actuation result, and postcondition verdict. Generate Qwen pairs only after verified success; generate hard negatives for wrong lookalikes. Do not fake screenshots from old files.
3. **Fix state representation and postconditions.** Feed graph localization valid `nodes`/SoM data, not an ignored `controls` field. Add semantic destination assertions (address value, breadcrumb, document text, dialog title) so different file paths cannot collapse to one state.
4. **Make target disambiguation the training objective.** The adapter’s demonstrated weakness is wrong target ID among similar controls. Gather contrastive live examples such as Address Bar vs Search, composer vs contact search, toolbar lookalikes, and modal-vs-background controls. Do not train further solely on the existing 1,205 pairs.
5. **Run a persistent full held-out evaluation correctly.** Use Python313/CUDA, write progress after every example, save raw replies plus error buckets, and make `eval_full205.json` resumable. Report valid strict JSON, action kind, target ID, coordinate/actuator miss, labelled/unlabelled icon, modal, and app-level breakdowns separately.
6. **Canonicalize application keys and migrate/alias data.** Choose one canonical key per app (`paint`, `chrome`, `visual_studio_code`, etc.); resolve aliases before every store lookup and migrate or merge duplicate namespaces. Otherwise evidence and fast paths remain unreachable.
7. **Tighten promotion.** A fast path must require at least two independent verified live successes on the same canonical app/version/state plus valid postconditions. Do not display the 242-row table as verified; its true verified count is 2.
8. **Clean the procedure corpus.** Deduplicate across source references, preserve provenance, quarantine low-quality web procedures, and distinguish documentation, hypotheses, observations, and verified workflows in every query/result UI.
9. **Treat archetypes as priors, never action authority.** Replace static word-overlap confidence with calibrated live scan evidence; require a resolved visible control and task-specific postcondition before executing any archetype-derived step.
10. **Unify the runtime/model boundary.** The running llama server was Qwen2.5-VL-7B, while the trained adapter targets Qwen3-VL-2B. Build an explicit launcher that loads the correct base+adapter under Python313, emits model/version metadata, and refuses silent fallback to a different model.
11. **Harden foreground ownership, focus, and recovery.** Establish a controlled test profile/window lifecycle; re-enumerate handles after each action; explicitly detect lost focus/window disappearance; stop rather than continue on an unknown foreground window.
12. **Implement real safety and rollback for live testing.** Restrict overnight experiments to disposable documents/profiles/sandboxes; verify focus and target before each input; make failed steps reversible where possible; never use user accounts, messaging sends, purchases, deletes, or external submissions as “training.”
13. **Set no 85–90% claim until it is measured end-to-end.** The current 68.8% target-ID result is a 16-example saved-image metric. It does not justify an autonomous cross-app accuracy claim. Define the target metric as successful, safe, verified completion on held-out live apps/tasks, then measure it with durable evidence.

