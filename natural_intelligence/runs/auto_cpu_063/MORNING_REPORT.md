# NI overnight report (2026-11-17 12:15)

- run: `auto_cpu_063`  cycles completed: **80**  rounds: **80**  elapsed: 2.04 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/video/ucf101_subset | 80 | 0.987 | 0.982 | 0.973 | 0.987 | 0.966 | 0.978 | 0.987 | 0.109 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/video/ucf101_subset | 76 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.975 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/video/ucf101_subset | 0.011 | 0.333 | n/a | 0.875 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/video/ucf101_subset | 0.987 | 0.989 | 0.953 | 0.961 |

### Inner net on its permanent hold-out (n=564), after 2418 outcome records
- inner: AUC 0.657, ECE 0.020, Brier 0.020, acc@80% 0.980
- raw outer vote confidence: AUC 0.995, ECE 0.023, Brier 0.022, acc@80% 1.000
- base rate of outer being right: 0.968

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
