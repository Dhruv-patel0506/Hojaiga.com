# NI overnight report (2026-11-17 10:12)

- run: `auto_cpu_044`  cycles completed: **311**  rounds: **311**  elapsed: 2.02 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/graph/aids | 311 | 0.996 | 0.991 | 0.990 | 0.988 | 0.980 | 0.990 | 0.990 | 0.800 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/graph/aids | 305 | 0.351 | 0.697 | 0.009 | 0.011 | 0.993 | 0.993 | 0.993 | 0.999 | 0.988 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/graph/aids | 0.003 | 1.000 | 1.000 | 0.883 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/graph/aids | 0.991 | 0.996 | 0.962 | 1.000 |

### Inner net on its permanent hold-out (n=3909), after 19315 outcome records
- inner: AUC 0.354, ECE 0.006, Brier 0.007, acc@80% 0.992
- raw outer vote confidence: AUC 0.629, ECE 0.006, Brier 0.008, acc@80% 0.994
- base rate of outer being right: 0.993

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
