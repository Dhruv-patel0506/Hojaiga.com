# NI overnight report (2026-11-16 17:35)

- run: `auto_gpu_076`  cycles completed: **12**  rounds: **13**  elapsed: 0.44 h  status: **cycle 12 phase 3 enc2/image/resisc45**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **2.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/image/resisc45 | 13 | 0.943 | 0.934 | 0.863 | 0.943 | 0.904 | 0.768 | 0.943 | 0.025 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/image/resisc45 | 12 | 0.969 | 0.958 | 0.009 | 0.027 | 0.966 | 0.964 | 0.942 | 0.962 | 0.908 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/image/resisc45 | 0.088 | 0.551 | 0.404 | 0.653 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/image/resisc45 | 0.976 | 0.943 | 0.821 | 0.834 |

### Inner net on its permanent hold-out (n=53331), after 270313 outcome records
- inner: AUC 0.970, ECE 0.002, Brier 0.031, acc@80% 0.999
- raw outer vote confidence: AUC 0.955, ECE 0.024, Brier 0.035, acc@80% 0.996
- base rate of outer being right: 0.942

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
