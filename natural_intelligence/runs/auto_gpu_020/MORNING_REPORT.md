# NI overnight report (2026-11-14 15:15)

- run: `auto_gpu_020`  cycles completed: **106**  rounds: **106**  elapsed: 1.02 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **2.10 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/image/emnist_letters | 106 | 0.936 | 0.913 | 0.887 | 0.936 | 0.846 | 0.791 | 0.936 | 0.038 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/image/emnist_letters | 104 | 0.925 | 0.920 | 0.006 | 0.008 | 0.954 | 0.953 | 0.937 | 0.964 | 0.917 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/image/emnist_letters | 0.100 | 0.622 | 0.536 | 0.707 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/image/emnist_letters | 0.994 | 0.936 | 0.849 | 0.825 |

### Inner net on its permanent hold-out (n=251951), after 1266107 outcome records
- inner: AUC 0.925, ECE 0.001, Brier 0.043, acc@80% 0.991
- raw outer vote confidence: AUC 0.920, ECE 0.005, Brier 0.044, acc@80% 0.990
- base rate of outer being right: 0.937

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
