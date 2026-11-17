# NI overnight report (2026-11-17 23:54)

- run: `auto_cpu_066`  cycles completed: **60**  rounds: **60**  elapsed: 2.00 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/audio/cremad_parquet | 60 | 0.752 | 0.736 | 0.738 | 0.748 | 0.531 | 0.671 | 0.748 | 0.171 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/audio/cremad_parquet | 56 | 0.801 | 0.798 | 0.055 | 0.053 | 0.790 | 0.791 | 0.748 | 0.893 | 0.901 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/audio/cremad_parquet | 0.419 | 0.572 | 0.452 | 0.782 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/audio/cremad_parquet | 0.966 | 0.752 | 0.877 | 1.000 |

### Inner net on its permanent hold-out (n=16582), after 82251 outcome records
- inner: AUC 0.797, ECE 0.014, Brier 0.148, acc@80% 0.827
- raw outer vote confidence: AUC 0.785, ECE 0.011, Brier 0.151, acc@80% 0.825
- base rate of outer being right: 0.754

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
