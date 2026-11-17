# NI overnight report (2026-11-16 13:37)

- run: `auto_gpu_072`  cycles completed: **29**  rounds: **29**  elapsed: 1.03 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **1.46 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/image/cifar10 | 29 | 0.944 | 0.942 | 0.932 | 0.942 | 0.929 | 0.918 | 0.942 | 0.100 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/image/cifar10 | 28 | 0.948 | 0.939 | 0.012 | 0.011 | 0.957 | 0.956 | 0.943 | 0.976 | 0.933 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/image/cifar10 | 0.076 | 0.572 | 0.464 | 0.748 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/image/cifar10 | 0.991 | 0.944 | 0.870 | 0.879 |

### Inner net on its permanent hold-out (n=86212), after 434764 outcome records
- inner: AUC 0.948, ECE 0.006, Brier 0.036, acc@80% 0.995
- raw outer vote confidence: AUC 0.938, ECE 0.007, Brier 0.038, acc@80% 0.993
- base rate of outer being right: 0.943

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
