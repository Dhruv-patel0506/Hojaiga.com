# NI overnight report (2026-11-17 23:55)

- run: `auto_cpu_021`  cycles completed: **288**  rounds: **288**  elapsed: 2.02 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/image/dtd | 288 | 0.754 | 0.754 | 0.713 | 0.752 | 0.718 | 0.717 | 0.752 | 0.021 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/image/dtd | 280 | 0.887 | 0.868 | 0.049 | 0.066 | 0.801 | 0.798 | 0.750 | 0.910 | 0.903 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/image/dtd | 0.377 | 0.495 | 0.325 | 0.815 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/image/dtd | 0.965 | 0.754 | 0.882 | 1.000 |

### Inner net on its permanent hold-out (n=13032), after 66219 outcome records
- inner: AUC 0.885, ECE 0.013, Brier 0.116, acc@80% 0.866
- raw outer vote confidence: AUC 0.868, ECE 0.039, Brier 0.126, acc@80% 0.856
- base rate of outer being right: 0.753

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
