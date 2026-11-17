# NI overnight report (2026-11-16 02:10)

- run: `auto_gpu_019`  cycles completed: **193**  rounds: **193**  elapsed: 1.01 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **1.03 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/image/kmnist | 193 | 0.971 | 0.949 | 0.907 | 0.971 | 0.883 | 0.809 | 0.971 | 0.100 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/image/kmnist | 187 | 0.961 | 0.954 | 0.006 | 0.012 | 0.984 | 0.983 | 0.971 | 0.976 | 0.927 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/image/kmnist | 0.039 | 0.576 | 0.522 | 0.560 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/image/kmnist | 0.990 | 0.971 | 0.776 | 0.914 |

### Inner net on its permanent hold-out (n=109245), after 547262 outcome records
- inner: AUC 0.959, ECE 0.002, Brier 0.019, acc@80% 0.998
- raw outer vote confidence: AUC 0.952, ECE 0.009, Brier 0.020, acc@80% 0.998
- base rate of outer being right: 0.972

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
