# NI overnight report (2026-11-14 09:52)

- run: `auto_gpu_015`  cycles completed: **145**  rounds: **145**  elapsed: 1.02 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **1.85 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/image/gtsrb | 145 | 0.989 | 0.976 | 0.892 | 0.973 | 0.978 | 0.755 | 0.978 | 0.059 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/image/gtsrb | 143 | 0.991 | 0.985 | 0.003 | 0.029 | 0.993 | 0.992 | 0.988 | 0.992 | 0.919 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/image/gtsrb | 0.016 | 0.530 | 0.471 | 0.636 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/image/gtsrb | 0.972 | 0.989 | 0.815 | 0.846 |

### Inner net on its permanent hold-out (n=231007), after 1150796 outcome records
- inner: AUC 0.991, ECE 0.001, Brier 0.007, acc@80% 1.000
- raw outer vote confidence: AUC 0.984, ECE 0.028, Brier 0.013, acc@80% 1.000
- base rate of outer being right: 0.988

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
