# NI overnight report (2026-11-13 21:22)

- run: `auto_gpu_003`  cycles completed: **128**  rounds: **128**  elapsed: 1.00 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **1.49 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/image/tiny_imagenet | 128 | 0.812 | 0.807 | 0.767 | 0.810 | 0.786 | 0.752 | 0.810 | 0.005 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/image/tiny_imagenet | 126 | 0.918 | 0.898 | 0.012 | 0.038 | 0.906 | 0.895 | 0.809 | 0.842 | 0.884 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/image/tiny_imagenet | 0.200 | 0.512 | 0.336 | 0.702 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/image/tiny_imagenet | 0.961 | 0.812 | 0.846 | 0.876 |

### Inner net on its permanent hold-out (n=225248), after 1111289 outcome records
- inner: AUC 0.918, ECE 0.004, Brier 0.087, acc@80% 0.925
- raw outer vote confidence: AUC 0.898, ECE 0.038, Brier 0.099, acc@80% 0.914
- base rate of outer being right: 0.809

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
