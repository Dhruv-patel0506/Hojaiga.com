# NI overnight report (2026-11-07 13:20)

- run: `restart_audio_1107_0924`  cycles completed: **711**  rounds: **712**  elapsed: 3.93 h  status: **cycle 711 phase 4 audio/urbansound8k**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **0.08 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| audio/urbansound8k | 712 | 0.650 | 0.605 | 0.411 | 0.650 | 0.522 | 0.577 | 0.650 | 0.115 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| audio/urbansound8k | 711 | 0.810 | 0.818 | 0.084 | 0.084 | 0.798 | 0.806 | 0.663 | 0.680 | 0.837 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| audio/urbansound8k | 0.591 | 0.557 | 0.400 | 0.585 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| audio/urbansound8k | 0.952 | 0.650 | 0.715 | 0.993 |

### Inner net on its permanent hold-out (n=360566), after 1863945 outcome records
- inner: AUC 0.809, ECE 0.028, Brier 0.170, acc@80% 0.725
- raw outer vote confidence: AUC 0.819, ECE 0.037, Brier 0.166, acc@80% 0.732
- base rate of outer being right: 0.643

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
