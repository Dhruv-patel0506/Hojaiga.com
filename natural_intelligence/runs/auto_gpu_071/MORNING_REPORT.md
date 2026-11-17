# NI overnight report (2026-11-16 09:43)

- run: `auto_gpu_071`  cycles completed: **21**  rounds: **21**  elapsed: 1.02 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **0.89 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/image/cats_vs_dogs | 21 | 0.997 | 0.997 | 0.997 | 0.997 | 0.995 | 0.995 | 0.997 | 0.502 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/image/cats_vs_dogs | 20 | 0.937 | 0.953 | 0.003 | 0.003 | 0.998 | 0.998 | 0.997 | 1.000 | 0.974 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/image/cats_vs_dogs | 0.004 | 0.620 | 0.477 | 0.904 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/image/cats_vs_dogs | 0.997 | 0.997 | 0.950 | 0.927 |

### Inner net on its permanent hold-out (n=29775), after 147834 outcome records
- inner: AUC 0.922, ECE 0.000, Brier 0.002, acc@80% 1.000
- raw outer vote confidence: AUC 0.914, ECE 0.002, Brier 0.002, acc@80% 0.999
- base rate of outer being right: 0.997

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
