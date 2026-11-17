# NI overnight report (2026-11-16 14:17)

- run: `auto_gpu_073`  cycles completed: **13**  rounds: **14**  elapsed: 0.56 h  status: **cycle 13 phase 3 enc2/image/imagenet_100**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **1.74 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/image/imagenet_100 | 14 | 0.935 | 0.932 | 0.915 | 0.933 | 0.915 | 0.907 | 0.933 | 0.011 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/image/imagenet_100 | 13 | 0.933 | 0.928 | 0.013 | 0.018 | 0.950 | 0.950 | 0.935 | 0.975 | 0.926 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/image/imagenet_100 | 0.091 | 0.576 | 0.403 | 0.780 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/image/imagenet_100 | 0.984 | 0.935 | 0.885 | 0.855 |

### Inner net on its permanent hold-out (n=50327), after 252059 outcome records
- inner: AUC 0.935, ECE 0.004, Brier 0.040, acc@80% 0.991
- raw outer vote confidence: AUC 0.929, ECE 0.015, Brier 0.043, acc@80% 0.989
- base rate of outer being right: 0.935

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
