# Hojaiga Natural Intelligence — What Exists, What We Need

Goal: one brain that learns from everything it is fed and from every model it
asks, answers more and more on its own, and calls external APIs less over time.
External models (Claude, OpenRouter, Groq) and local Qwen are **teachers**. The
brain is the **student that becomes independent**.

## 0. Morning quickstart: feed data, train, ask, render

**Windows, simplest:** `All codes\brain.bat` sets the venv, PYTHONPATH and storage paths for you
(brain in `D:\new_automation\storage\brain`; override with `HOJAIGA_ROOT` / `HOJAIGA_BRAIN_HOME`).

```
brain.bat pipeline --data D:\datasets\biology --size small     # EVERYTHING: ingest → train → layers → eval
brain.bat finetune --data D:\datasets\gmail --name gmail       # LoRA adapter on top of the trained base
brain.bat --adapter gmail ask "Reply to the last message from Rahul"
brain.bat eval --data D:\datasets\biology\qa.jsonl             # accuracy, F1, calibration, by question type
brain.bat train-layers --data D:\datasets\biology\qa.jsonl     # train layers 3/5/7/8, held-out before/after
brain.bat merge-adapter gmail                                  # bake an adapter into the base (backup kept)
```
The brain is also wired into the LLM gateway (`organ_37`): every organ's question goes to the brain first and
is answered natively when its confidence ≥ `HOJAIGA_BRAIN_GATEWAY_CONF` (0.8); JSON/structured roles and
creative requests skip it. Turn off with `HOJAIGA_BRAIN_GATEWAY=0`.

Manual equivalents (from `All codes`, venv active):

```
# one-time: neural training needs PyTorch (CPU works; an NVIDIA GPU is much faster)
pip install torch

# 1. feed anything: a folder may mix text, md, pdf, docx, pptx, json/jsonl, images, gifs, videos
python -m core_organs.hojaiga_ml_engine brain ingest  D:\datasets\biology

# 2. train our own neural cortex on the same data (tokenizer is learned from your data first)
python -m core_organs.hojaiga_ml_engine brain train --data D:\datasets\biology --size small --epochs 3
#    sizes: tiny (~6M params, CPU) · small (~17M, RTX 3050) · base (~37M, 8 GB) · large (~110M, 16-24 GB)
#    re-running train continues from the checkpoint and mixes in a replay sample of older data

# 3. ask: every layer runs; --trace shows what each layer did
python -m core_organs.hojaiga_ml_engine brain ask "How does sperm travel to the urethra?" --trace

# 4. teach it: wrong answers are never repeated, corrections are remembered
python -m core_organs.hojaiga_ml_engine brain feedback <thought-id> bad --correct "..." --intent explanation

# 5. animated lesson from a textbook page, storybook, image or video
python -m core_organs.hojaiga_ml_engine brain render chapter3.md --out chapter3.html --subject biology --grade 8
python -m core_organs.hojaiga_ml_engine brain render storybook.pdf --out story.html --mode story
python -m core_organs.hojaiga_ml_engine brain render photo.jpg --out traced.html
#    in the page: 3D button = living 3D model (drag/zoom, zoom in to read details) · Hologram = 4 views for a pyramid

# 6. leave it learning all night (ingest → train → reindex → self-study → distill, repeated)
python -m core_organs.hojaiga_ml_engine brain overnight --data D:\datasets --hours 8 --loop [--teacher]

# 7. see the architecture and the brain's state
python -m core_organs.hojaiga_ml_engine brain diagram --out hojaiga_brain.html
python -m core_organs.hojaiga_ml_engine brain status
```

### Dataset formats it understands (no conversion needed)
| You give | It learns |
|---|---|
| `.txt .md .html .csv .json` and code files | language + knowledge chunks + concept graph + relations |
| `.pdf .docx .pptx` | same, if `pypdf` / `python-docx` / `python-pptx` are installed |
| `image.png` + `image.txt` (same name) | image ↔ caption (diagrams, photos, screenshots) |
| `clip.mp4` + `clip.srt`/`.txt` | video frames ↔ transcript (needs `opencv-python` or ffmpeg; `.gif` works with Pillow alone) |
| `.jsonl` rows `{"question","answer"}`, `{"messages":[...]}`, `{"text"}`, `{"image","caption"}` | Q&A (also trains the verifier head), chat distillation, captions |

### The brain's layers (`All codes/core_organs/hojaiga_ml_engine.py`, Part B)
| Layer | Brain analogue | Algorithm |
|---|---|---|
| L1 Filter | thalamus | normalisation, PII/secret redaction, SimHash near-duplicate, entropy quality gate, TF-IDF salience |
| L2 Know | hippocampus | BM25 + our own dense embeddings + organ_08 memory, reciprocal rank fusion |
| L3 Understand | Wernicke / temporal | online Naive Bayes intent, RAKE key-phrases, relation extraction, concept linking |
| L4 Reason | prefrontal | personalized PageRank over the concept graph, forward chaining over triples, exact calculator with physical constants |
| L5 Think | default-mode network | competing candidates (recall, extractive MMR, relational, calculator, memory, own generator, optional teacher), learned value function |
| L6 Answer | Broca | intent-shaped composition (steps / bullets / prose), sources |
| L7 Verify | anterior cingulate | grounding, self-consistency, negation contradiction, own verifier head, past-failure check, Platt-calibrated confidence → think again if unsure |
| L8 Learn | basal ganglia | online logistic updates to value + calibration, Naive Bayes intent update, failure memory, corrections promoted to knowledge |
| Neural cortex | cortex | own BPE tokenizer · patch-transformer vision encoder (images + video frames) · prefix-LM decoder · language / embedding / verifier heads · replay buffer against forgetting |

### Verified in the build environment (CPU, 4 Nov 2026)
- Tiny cortex (5.3M params) trained from scratch on a mixed sample (text, 40 captioned diagrams, a GIF clip,
  Q&A): about 5 minutes of CPU training. It then captioned **unseen** images correctly ("A blue triangle drawn
  on a white background") and the clip exactly ("A yellow ball moves from left to right across a dark sky").
- Raw generation from such a small model still memorises: asked "What gas do plants absorb?" it returned
  another fact from the same data. The layered brain answered correctly from grounded recall instead.
  Real fluency needs much more data and GPU time.
- Suite tests NI1, BR1, RN1 pass: all 8 layers run, answers are grounded, the calculator wins on math, a
  corrected answer is recalled (also for a paraphrase) and the refuted one is never repeated; textbook and story
  pages render to the right scene types.
- `brain overnight` completes a full cycle (ingest → train → reindex → consolidate → distill).

Industry research and positioning: `INDUSTRY_GAPS_AND_POSITIONING.md`.

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
