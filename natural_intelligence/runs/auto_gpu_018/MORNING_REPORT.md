# NI overnight report (2026-11-16 02:04)

- run: `auto_gpu_018`  cycles completed: **131**  rounds: **131**  elapsed: 1.01 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **1.03 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/image/resisc45 | 131 | 0.934 | 0.927 | 0.831 | 0.934 | 0.901 | 0.761 | 0.934 | 0.025 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/image/resisc45 | 125 | 0.972 | 0.945 | 0.008 | 0.012 | 0.966 | 0.960 | 0.932 | 0.949 | 0.923 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/image/resisc45 | 0.099 | 0.515 | 0.393 | 0.604 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/image/resisc45 | 0.992 | 0.934 | 0.798 | 0.914 |

### Inner net on its permanent hold-out (n=106831), after 540503 outcome records
- inner: AUC 0.972, ECE 0.003, Brier 0.033, acc@80% 0.998
- raw outer vote confidence: AUC 0.945, ECE 0.008, Brier 0.041, acc@80% 0.992
- base rate of outer being right: 0.932

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
