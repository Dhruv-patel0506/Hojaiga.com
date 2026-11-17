# NI overnight report (2026-11-17 14:23)

- run: `auto_cpu_024`  cycles completed: **224**  rounds: **224**  elapsed: 2.02 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/image/oxford_iiit_pet | 224 | 0.921 | 0.920 | 0.909 | 0.920 | 0.857 | 0.892 | 0.920 | 0.027 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/image/oxford_iiit_pet | 217 | 0.918 | 0.907 | 0.033 | 0.028 | 0.943 | 0.940 | 0.926 | 0.972 | 0.947 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/image/oxford_iiit_pet | 0.113 | 0.562 | 0.439 | 0.752 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/image/oxford_iiit_pet | 0.987 | 0.921 | 0.857 | 1.000 |

### Inner net on its permanent hold-out (n=22230), after 116997 outcome records
- inner: AUC 0.918, ECE 0.012, Brier 0.048, acc@80% 0.982
- raw outer vote confidence: AUC 0.906, ECE 0.007, Brier 0.052, acc@80% 0.979
- base rate of outer being right: 0.924

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
