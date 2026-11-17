# NI overnight report (2026-11-18 00:10)

- run: `auto_cpu_042`  cycles completed: **320**  rounds: **321**  elapsed: 0.23 h  status: **cycle 320 phase 2 enc2/graph/csl**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/graph/csl | 321 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.100 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/graph/csl | 314 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 1.000 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/graph/csl | n/a | n/a | n/a | n/a |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/graph/csl | 1.000 | 1.000 | 1.000 | 1.000 |

### Inner net on its permanent hold-out (n=158), after 658 outcome records
- inner: AUC nan, ECE 0.000, Brier 0.000, acc@80% 1.000
- raw outer vote confidence: AUC nan, ECE 0.000, Brier 0.000, acc@80% 1.000
- base rate of outer being right: 1.000

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
