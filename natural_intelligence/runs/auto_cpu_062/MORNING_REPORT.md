# NI overnight report (2026-11-18 00:08)

- run: `auto_cpu_062`  cycles completed: **65**  rounds: **66**  elapsed: 0.25 h  status: **cycle 65 phase 4 enc2/audio/esc50**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/audio/esc50 | 66 | 0.975 | 0.972 | 0.972 | 0.973 | 0.952 | 0.959 | 0.973 | 0.020 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/audio/esc50 | 61 | 0.896 | 0.918 | 0.027 | 0.026 | 0.976 | 0.976 | 0.974 | 0.997 | 0.975 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/audio/esc50 | 0.038 | 0.600 | 0.495 | 0.913 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/audio/esc50 | 0.984 | 0.974 | 0.935 | 1.000 |

### Inner net on its permanent hold-out (n=667), after 2952 outcome records
- inner: AUC 0.930, ECE 0.021, Brier 0.021, acc@80% 0.998
- raw outer vote confidence: AUC 0.957, ECE 0.015, Brier 0.018, acc@80% 1.000
- base rate of outer being right: 0.978

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
