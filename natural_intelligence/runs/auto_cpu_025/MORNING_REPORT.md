# NI overnight report (2026-11-17 14:35)

- run: `auto_cpu_025`  cycles completed: **162**  rounds: **162**  elapsed: 2.02 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/audio/cremad_parquet | 121 | 0.601 | 0.594 | 0.588 | 0.598 | 0.465 | 0.537 | 0.598 | 0.171 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/audio/cremad_parquet | 114 | 0.712 | 0.703 | 0.055 | 0.052 | 0.675 | 0.667 | 0.597 | 0.747 | 0.858 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/audio/cremad_parquet | 0.744 | 0.560 | 0.431 | 0.711 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/audio/cremad_parquet | 0.974 | 0.601 | 0.835 | 1.000 |

### Inner net on its permanent hold-out (n=12017), after 60338 outcome records
- inner: AUC 0.717, ECE 0.022, Brier 0.208, acc@80% 0.659
- raw outer vote confidence: AUC 0.706, ECE 0.016, Brier 0.212, acc@80% 0.653
- base rate of outer being right: 0.594

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
