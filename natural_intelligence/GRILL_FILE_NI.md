# GRILL FILE - Natural Intelligence (NI) dual-brain trainer  (v4.0, supersedes dataset/GRILL_FILE v3.0)

```yaml
skill_name: natural-intelligence-grill
version: 4.0.0
architecture: outer_brain -> outcome_stream -> inner_brain -> feedback -> outer_brain
hardware_target: NVIDIA RTX 3050 6GB Laptop (this machine; the old files said 3060) - hard ceiling 6.0 GB, run budget 5.5 GB
python: D:\new_automation\venv\Scripts\python.exe   # torch 2.7.1+cu118, cv2, PIL, soundfile, scipy. NOT hojaiga_env (CPU-only torch).
max_files_per_session: 8
determinism: seeds come from ni_common.seed_for(task, cycle) - never random.randint, never time-based
```

## 0. Why this file exists (what changed vs v3)
v3 + the old `*_v2.py` files were a simulation: `random.uniform` produced the inner brain's scores, samples were the string
"Subsampled web stream payload", and "VRAM" was a hard-coded number. Nothing could be learned from them.
v4 rules make every number **measured against ground-truth labels**. If a metric cannot be measured, it is not reported.

## 1. Invariants (Claude MUST obey every turn)
1. **Outer first, inner after.** Cycle 0 trains only the outer brain on all 5 phases and collects its outcomes. Only then is the inner brain trained, on that outcome dataset. Later cycles interleave: outer round -> inner assess -> feedback -> inner learns.
2. **Outer outcomes ARE the inner dataset.** The inner brain never reads raw modality data. Its inputs are the outer brain's per-predictor confidence / entropy / agreement, vote margin, k-NN evidence, current meta-weights and modality. Its target is "was the outer decision correct" (taken from the stream's labels).
3. **Never one predictor.** Four different predictors vote (Logic = Gaussian NB, Pattern = MLP, Verifier = cosine k-NN, Exploratory = bagged random-Fourier linear heads). A change that collapses them to one model is a violation.
4. **Self-questioning = measured probes, not prose.** Q1 leave-one-predictor-out flip rate; Q2 input-perturbation consistency; Q3 weakest class / low margin / low k-NN similarity; Q4 round-to-round accuracy drift and predictor disagreement. Each answer carries a number.
5. **JEV sandbox = executable verification.** For decisions whose inner trust < 0.75 the outer brain is re-run on perturbed inputs (4 draws, sigma 0.5 in standardised units) and with each predictor removed; VERIFIED needs consistency >= 0.75 AND leave-one-out stability >= 0.75, else REJECTED. (The user's word "JEV" is treated as "execution/verification tool"; if they meant something else they will say so.)
6. **No leakage.** 70/30 windows rotate with the seed (`split_train_mask`). Groups that share a source (UrbanSound fsID, HMDB film name) hash as one unit. The inner brain additionally has a PERMANENT 20% hold-out (`HOLDOUT_SEED`) it never trains on; every inner metric in a report comes from there.
7. **Honest reporting.** Always report the inner brain against the raw outer vote-confidence baseline (AUC, ECE, accuracy-at-coverage) and the weighted vote against the uniform vote. If the inner brain does not beat the baseline, say so.
8. **VRAM telemetry** (`torch.cuda.max_memory_allocated`) is printed per round; hard fail above 5.5 GB. Do not print an estimated number.
9. **No hardcoded per-input facts.** Class counts, feature sizes, class names (video top-K) come from the data.

## 2. Phases (easiest -> hardest) and real data
| Phase | Modality | Task (all with ground-truth labels) | Source (streamed via datasets-server REST, bounded shards) |
|---|---|---|---|
| 1 | text | AG News topic (4 classes) | fancyzhx/ag_news |
| 2 | graph | PROTEINS + MUTAG graph classification | graphs-datasets/PROTEINS, MUTAG |
| 3 | image | CIFAR-10 (32x32) | uoft-cs/cifar10 |
| 4 | audio | UrbanSound8K (10 classes), grouped by fsID | danavery/urbansound8K |
| 5 | video | HMDB51 top-10 classes by filled count, grouped by film | divm/hmdb51 |

Not used, with reasons: FineWeb/RedPajama/LAION/WebVid/OGB-Papers100M (no labels for the correctness target, or removed/gated/too large for the viewer API). They can be registered later in `ni_fill.SOURCES` once a labelled proxy task is defined.

## 3. Four factors and the grade (all measured)
- reliability  = 1 - ECE(outer vote confidence)
- truthfulness = outer weighted-vote accuracy on the held-out window
- adaptability = 0.5 * perturbation consistency + 0.5 * (1 - 5*|acc - previous window acc|, floored at 0)
- scalability  = 0.5 * (1 - peak VRAM/6 GB) + 0.5 * min(1, inference samples-per-second / 200)
- **grade = 0.35 reliability + 0.25 truthfulness + 0.20 adaptability + 0.20 scalability**  (one formula; v3 contradicted itself)

## 4. Feedback rule
`w_p <- w_p * exp(1.5 * advantage_p)`, advantage from predictor errors weighted by inner distrust (1 - trust + 0.1); weights clipped to [0.2, 5] and renormalised to mean 1. The ablation weighted-vs-uniform vote is reported every round.

## 5. Files (session order, max 8)
1. `GRILL_FILE_NI.md` (this)  2. `ni_common.py`  3. `ni_features.py`  4. `ni_fill.py`  5. `ni_data.py`  6. `ni_outer.py`  7. `ni_inner.py`  8. `ni_run.py`
Outputs to read next session: `runs/<id>/MORNING_REPORT.md`, `status.json`, `metrics.jsonl`, `transcripts.jsonl`, `checkpoint.pt`, `log.txt`.

## 6. Claude response contract
Before delivering anything: (a) state which cycle/phase the numbers are from, (b) show inner-vs-baseline, (c) list any task that was skipped or failed and why, (d) never claim QLoRA/NF4/LLM fine-tuning happened - it did not (bitsandbytes/peft are not installed and the heads are < 1M params).

## 7. Known limits (write these in every report)
- Predictors are small heads on hand-built features, not foundation models; CIFAR-10 accuracy ~40-50 % is expected.
- Video/audio rely on summary features, not learned encoders.
- The inner brain can only learn what the outer outcome stream exposes; it cannot see raw inputs.
