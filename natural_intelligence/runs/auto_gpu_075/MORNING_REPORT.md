# NI overnight report (2026-11-16 17:02)

- run: `auto_gpu_075`  cycles completed: **33**  rounds: **33**  elapsed: 1.02 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **1.75 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/image/food101 | 33 | 0.834 | 0.818 | 0.793 | 0.833 | 0.758 | 0.760 | 0.833 | 0.011 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/image/food101 | 32 | 0.908 | 0.897 | 0.019 | 0.042 | 0.891 | 0.888 | 0.835 | 0.908 | 0.884 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/image/food101 | 0.268 | 0.556 | 0.373 | 0.709 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/image/food101 | 0.957 | 0.834 | 0.846 | 0.855 |

### Inner net on its permanent hold-out (n=117934), after 596591 outcome records
- inner: AUC 0.907, ECE 0.005, Brier 0.085, acc@80% 0.939
- raw outer vote confidence: AUC 0.896, ECE 0.051, Brier 0.093, acc@80% 0.933
- base rate of outer being right: 0.835

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
