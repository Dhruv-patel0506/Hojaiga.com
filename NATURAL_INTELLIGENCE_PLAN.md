# Hojaiga Natural Intelligence — What Exists, What We Need

Goal: one brain that learns from everything it is fed and from every model it
asks, answers more and more on its own, and calls external APIs less over time.
External models (Claude, OpenRouter, Groq) and local Qwen are **teachers**. The
brain is the **student that becomes independent**.

## 1. Built so far (branch `natural-intelligence-core`)

| Piece | Where | What it does |
|---|---|---|
| Natural Intelligence Cortex | `All codes/core_organs/organ_08_learning.py` → `NaturalIntelligenceCortex` | Long-term memory (SQLite + FTS5 + vectors), confidence that climbs with agreement/success and erodes with contradiction/failure, curiosity queue, knowledge feeding, self-study, consolidation, fine-tune export, self-reliance stats |
| Teacher manager | `All codes/core_organs/organ_37_llm_gateway.py` → `_teachers`, `_ask_teachers`, `teach`, `report_outcome` | Every model call: memory first → local Qwen → external teachers ranked by learned reliability → learn the answer. Claude added as an optional teacher |
| Test | `run_system_intelligence_tests.py` → `NI1` | Proves memory takes over repeated questions, refuses to replay creative/other-role requests, injects fed knowledge |

### How a question flows
1. `recall` — is there a memory for this question, under the same role (system prompt), with confidence earned from evidence? → answer natively, no model call.
2. Otherwise build the teacher prompt (adds fed knowledge when `use_knowledge=True` or mode `full`).
3. Teachers in order: local Ollama Qwen first (free, private), then external ones by learned score.
4. `learn` — store the answer. Same answer from an **independent** teacher = strong evidence (+35%); same teacher repeating = weak (+12%); contradiction = −25%.
5. `report_outcome(success)` from the organ that used the answer = +30% / −30%.
6. Questions nobody could answer go to the curiosity queue for self-study.

### Commands (run from `All codes`)
```
python -m core_organs.organ_08_learning ni stats                  # size, self_reliance, teacher table
python -m core_organs.organ_08_learning ni feed <folder|file|url> # learn anything
python -m core_organs.organ_08_learning ni ask "question"         # answer with memory + knowledge
python -m core_organs.organ_08_learning ni study 50               # overnight: teachers fill knowledge gaps
python -m core_organs.organ_08_learning ni consolidate            # "sleep": decay/prune unconfirmed memory
python -m core_organs.organ_08_learning ni export ft.jsonl        # confirmed knowledge → fine-tune dataset
```

### Settings (env vars, no code edits)
| Var | Default | Meaning |
|---|---|---|
| `HOJAIGA_NI_MODE` | `on` | `off`, `learn` (record only, never serve), `on`, `full` (always add fed knowledge) |
| `HOJAIGA_NI_DB` | `storage/hdd/organ_06_learning/natural_intelligence.sqlite` | brain file |
| `HOJAIGA_NI_SERVE_SIM` / `_SERVE_CONF` | 0.97 / 0.75 | how alike + how proven a memory must be to answer natively |
| `HOJAIGA_NI_CREATIVE_TEMP` | 0.7 | at or above this temperature, never replay (creative output stays fresh) |
| `HOJAIGA_NI_EMBED_MODEL` | empty | e.g. `nomic-embed-text` in Ollama for semantic (not just lexical) recall |
| `ANTHROPIC_API_KEY`, `HOJAIGA_CLAUDE_MODEL` | none, `claude-opus-5-5` | turns Claude on as a teacher (paid; off when no key) |
| `HOJAIGA_TEACHER_ORDER` | empty | pin teacher order, e.g. `ollama:qwen2.5:7b,claude:claude-opus-5-5` |

## 2. Everything still needed for full natural intelligence

### A. Senses (input)
- [ ] **Screen-to-brain feed**: route organ_30/31/44 scan results and qwen-vl descriptions into `feed_text` so every scanned app becomes knowledge (scan once, recall after).
- [ ] **Video understanding**: frame sampler (scene change) → Qwen-VL description per frame → timeline summary fed to memory.
- [ ] **Photo deep description**: multi-pass VLM (whole → regions → text/OCR → relations) stored as facts.
- [ ] **Multi-page web digestion**: organ_19 CDP scroll + follow pagination → `feed_url` per page.
- [ ] **Message / email reading** (Gmail etc.) → thread memory + reply decisions, sending always needs approval.

### B. Memory (the brain itself)
- [x] Long-term Q&A memory with earned confidence.
- [x] Fact memory from fed files/URLs/text.
- [ ] **Semantic embeddings** by default (pull `nomic-embed-text` in Ollama, set `HOJAIGA_NI_EMBED_MODEL`).
- [ ] **Episodic memory**: full task runs (screen, elements, decision, action, result) — connect `desktop_grounding` learn step to the cortex.
- [ ] **Procedural memory**: organ_47 recipes and organ_04 knowledge share the same cortex search so one question searches everything.
- [ ] **User model**: writing style, tone, preferences learned from sent emails/docs.

### C. Reasoning & decisions
- [ ] Planner that asks memory for a matching past plan before asking a teacher (organ_36/organ_08 `StrategyOptimizer` → cortex).
- [ ] Self-check: before answering natively, a cheap local verifier can still reject a stale memory.
- [ ] Uncertainty reporting: every answer carries `native|teacher` + confidence so the UI can show it.

### D. Teachers & tools manager
- [x] Dynamic teacher ranking by reliability + downstream quality.
- [x] Claude teacher (optional).
- [ ] Cost/latency budget per task (prefer free local, escalate only when confidence is low).
- [ ] Tool registry (organ_18) exposed to the teacher manager so the brain picks tools the same way it picks teachers.

### E. Teaching on screen ("renders and teaches")
- [ ] Reuse the existing tutor/void renderers (`final_hojaiga_tutor`, `organ_34_teaching_void`, `hybrid_teaching_drawing_engine.py`) as the output layer: answer → diagram/steps rendered live → quiz.
- [ ] Learner profile (`hojaiga_learner_profile.json`) and quiz history feed back into the cortex so teaching adapts.

### F. Self-improvement loop (runs overnight)
- [x] `ni study` — teachers answer open questions.
- [x] `ni consolidate` — forget unproven memories.
- [x] `ni export` — dataset of confirmed knowledge.
- [ ] Windows Task Scheduler entry: `feed` new folders → `study` → `consolidate` → `export` nightly.
- [ ] **Fine-tuning step**: LoRA on Qwen2.5 (text) / Qwen2.5-VL (vision) with the exported JSONL (Unsloth or LLaMA-Factory). Needs a GPU with about 12–24 GB VRAM; your RTX 3050 handles small models (≤3B) with QLoRA only.
- [ ] Before/after evaluation: held-out question set, compare old vs fine-tuned model, only swap `HOJAIGA_BRAIN_MODEL` when it wins.

### G. Data you need to provide
- Folders of your documents, notes, code, sent emails/posts (style), course material.
- 100+ real tasks per capability with what "correct" looks like (the held-out test set).
- Corrections: whenever an answer is wrong, call `report_outcome(False)` (or say so in the UI) — this is how it learns quality.

## 3. Honest limits right now
- Native answers happen for **repeated** questions it has proven. Genuinely new questions still need a teacher model (local Qwen first). New reasoning without any model only comes after fine-tuning folds the knowledge into the local model weights.
- Lexical vectors match wording, not meaning, until an embedding model is set.
- Not yet tested on your Windows machine with Ollama running; NI1 uses a fake teacher.
- Claude is a paid API and goes against the free/local-only master rule. It stays off unless you set a key.
