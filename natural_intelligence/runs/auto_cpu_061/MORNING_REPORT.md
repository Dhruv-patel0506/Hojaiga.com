# NI overnight report (2026-11-18 00:02)

- run: `auto_cpu_061`  cycles completed: **43**  rounds: **43**  elapsed: 2.06 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/audio/ravdess | 43 | 0.879 | 0.869 | 0.856 | 0.878 | 0.733 | 0.751 | 0.878 | 0.133 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/audio/ravdess | 38 | 0.824 | 0.793 | 0.082 | 0.077 | 0.929 | 0.929 | 0.922 | 0.961 | 0.920 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/audio/ravdess | 0.171 | 0.561 | 0.501 | 0.752 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/audio/ravdess | 0.959 | 0.878 | 0.827 | 1.000 |

### Inner net on its permanent hold-out (n=1454), after 7371 outcome records
- inner: AUC 0.864, ECE 0.025, Brier 0.076, acc@80% 0.956
- raw outer vote confidence: AUC 0.858, ECE 0.024, Brier 0.081, acc@80% 0.955
- base rate of outer being right: 0.887

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
