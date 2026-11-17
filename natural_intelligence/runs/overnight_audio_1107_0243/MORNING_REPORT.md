# NI overnight report (2026-11-07 07:20)

- run: `overnight_audio_1107_0243`  cycles completed: **613**  rounds: **614**  elapsed: 4.61 h  status: **cycle 613 phase 4 audio/urbansound8k**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **0.08 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| audio/urbansound8k | 614 | 0.660 | 0.618 | 0.423 | 0.659 | 0.535 | 0.590 | 0.659 | 0.115 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| audio/urbansound8k | 613 | 0.824 | 0.826 | 0.084 | 0.078 | 0.819 | 0.820 | 0.651 | 0.640 | 0.844 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| audio/urbansound8k | 0.614 | 0.589 | 0.421 | 0.591 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| audio/urbansound8k | 0.962 | 0.660 | 0.719 | 0.993 |

### Inner net on its permanent hold-out (n=260121), after 1325294 outcome records
- inner: AUC 0.801, ECE 0.014, Brier 0.175, acc@80% 0.702
- raw outer vote confidence: AUC 0.801, ECE 0.043, Brier 0.178, acc@80% 0.703
- base rate of outer being right: 0.620

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
