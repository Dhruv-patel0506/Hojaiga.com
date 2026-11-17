# NI overnight report (2026-11-15 21:43)

- run: `auto_gpu_056`  cycles completed: **207**  rounds: **207**  elapsed: 1.01 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **0.91 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/image/imagenet_100 | 207 | 0.894 | 0.893 | 0.862 | 0.894 | 0.872 | 0.853 | 0.894 | 0.011 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/image/imagenet_100 | 201 | 0.935 | 0.920 | 0.012 | 0.026 | 0.931 | 0.926 | 0.895 | 0.946 | 0.918 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/image/imagenet_100 | 0.152 | 0.528 | 0.377 | 0.695 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/image/imagenet_100 | 0.976 | 0.894 | 0.841 | 0.925 |

### Inner net on its permanent hold-out (n=100253), after 504444 outcome records
- inner: AUC 0.935, ECE 0.004, Brier 0.055, acc@80% 0.981
- raw outer vote confidence: AUC 0.920, ECE 0.024, Brier 0.063, acc@80% 0.976
- base rate of outer being right: 0.894

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
