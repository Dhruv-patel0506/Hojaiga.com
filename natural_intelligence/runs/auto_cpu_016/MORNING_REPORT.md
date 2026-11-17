# NI overnight report (2026-11-17 23:52)

- run: `auto_cpu_016`  cycles completed: **331**  rounds: **331**  elapsed: 2.03 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/graph/deezer_ego_nets | 332 | 0.547 | 0.535 | 0.520 | 0.519 | 0.547 | 0.549 | 0.549 | 0.568 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/graph/deezer_ego_nets | 324 | 0.546 | 0.517 | 0.034 | 0.027 | 0.546 | 0.543 | 0.539 | 0.900 | 0.867 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/graph/deezer_ego_nets | 1.000 | 0.553 | 0.486 | 0.912 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/graph/deezer_ego_nets | 0.978 | 0.547 | 0.941 | 1.000 |

### Inner net on its permanent hold-out (n=25423), after 127289 outcome records
- inner: AUC 0.542, ECE 0.014, Brier 0.248, acc@80% 0.552
- raw outer vote confidence: AUC 0.518, ECE 0.011, Brier 0.249, acc@80% 0.546
- base rate of outer being right: 0.538

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
