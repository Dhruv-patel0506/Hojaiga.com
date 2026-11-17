# NI overnight report (2026-11-17 10:15)

- run: `auto_cpu_045`  cycles completed: **241**  rounds: **241**  elapsed: 2.05 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/graph/deezer_ego_nets | 241 | 0.549 | 0.535 | 0.519 | 0.520 | 0.545 | 0.549 | 0.549 | 0.568 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/graph/deezer_ego_nets | 235 | 0.535 | 0.519 | 0.035 | 0.028 | 0.551 | 0.548 | 0.544 | 0.873 | 0.867 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/graph/deezer_ego_nets | 1.000 | 0.557 | 0.493 | 0.888 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/graph/deezer_ego_nets | 0.982 | 0.549 | 0.931 | 1.000 |

### Inner net on its permanent hold-out (n=18677), after 92630 outcome records
- inner: AUC 0.536, ECE 0.013, Brier 0.247, acc@80% 0.556
- raw outer vote confidence: AUC 0.512, ECE 0.018, Brier 0.248, acc@80% 0.550
- base rate of outer being right: 0.546

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
