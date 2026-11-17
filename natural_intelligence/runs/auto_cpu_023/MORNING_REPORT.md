# NI overnight report (2026-11-17 14:21)

- run: `auto_cpu_023`  cycles completed: **120**  rounds: **120**  elapsed: 2.02 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/image/cats_vs_dogs | 121 | 0.994 | 0.993 | 0.993 | 0.993 | 0.989 | 0.990 | 0.993 | 0.502 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/image/cats_vs_dogs | 114 | 0.977 | 0.982 | 0.005 | 0.006 | 0.994 | 0.994 | 0.993 | 0.998 | 0.974 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/image/cats_vs_dogs | 0.007 | 0.661 | 0.577 | 0.771 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/image/cats_vs_dogs | 0.996 | 0.994 | 0.882 | 1.000 |

### Inner net on its permanent hold-out (n=38198), after 189204 outcome records
- inner: AUC 0.973, ECE 0.001, Brier 0.005, acc@80% 1.000
- raw outer vote confidence: AUC 0.972, ECE 0.002, Brier 0.005, acc@80% 1.000
- base rate of outer being right: 0.993

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
