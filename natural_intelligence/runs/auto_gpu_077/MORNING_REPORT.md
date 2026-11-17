# NI overnight report (2026-11-16 19:59)

- run: `auto_gpu_077`  cycles completed: **31**  rounds: **31**  elapsed: 1.04 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **2.02 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/image/kmnist | 31 | 0.974 | 0.954 | 0.927 | 0.974 | 0.882 | 0.801 | 0.974 | 0.100 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/image/kmnist | 30 | 0.958 | 0.954 | 0.008 | 0.012 | 0.983 | 0.982 | 0.973 | 0.982 | 0.916 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/image/kmnist | 0.037 | 0.576 | 0.517 | 0.602 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/image/kmnist | 0.990 | 0.974 | 0.798 | 0.832 |

### Inner net on its permanent hold-out (n=130672), after 650233 outcome records
- inner: AUC 0.955, ECE 0.002, Brier 0.018, acc@80% 0.998
- raw outer vote confidence: AUC 0.947, ECE 0.014, Brier 0.020, acc@80% 0.997
- base rate of outer being right: 0.973

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
