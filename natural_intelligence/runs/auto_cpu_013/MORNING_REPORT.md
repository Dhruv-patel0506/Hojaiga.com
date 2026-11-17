# NI overnight report (2026-11-17 21:50)

- run: `auto_cpu_013`  cycles completed: **213**  rounds: **213**  elapsed: 2.03 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/text/emotion | 214 | 0.732 | 0.739 | 0.689 | 0.746 | 0.701 | 0.654 | 0.746 | 0.338 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/text/emotion | 206 | 0.843 | 0.772 | 0.031 | 0.036 | 0.815 | 0.793 | 0.727 | 0.823 | 0.885 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/text/emotion | 0.428 | 0.531 | 0.412 | 0.670 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/text/emotion | 0.971 | 0.732 | 0.809 | 1.000 |

### Inner net on its permanent hold-out (n=36129), after 180178 outcome records
- inner: AUC 0.841, ECE 0.013, Brier 0.140, acc@80% 0.825
- raw outer vote confidence: AUC 0.773, ECE 0.018, Brier 0.162, acc@80% 0.800
- base rate of outer being right: 0.728

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
