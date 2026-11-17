# NI overnight report (2026-11-18 00:06)

- run: `auto_cpu_068`  cycles completed: **31**  rounds: **32**  elapsed: 0.07 h  status: **cycle 31 phase 3 enc2/image/beans**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/image/beans | 32 | 0.957 | 0.955 | 0.957 | 0.956 | 0.896 | 0.915 | 0.957 | 0.337 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/image/beans | 29 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.948 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/image/beans | 0.048 | 0.536 | 0.543 | 0.765 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/image/beans | 0.969 | 0.957 | 0.844 | 1.000 |

### Inner net on its permanent hold-out (n=83), after 382 outcome records
- inner: AUC 0.967, ECE 0.052, Brier 0.042, acc@80% 1.000
- raw outer vote confidence: AUC 0.996, ECE 0.042, Brier 0.018, acc@80% 1.000
- base rate of outer being right: 0.964

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
