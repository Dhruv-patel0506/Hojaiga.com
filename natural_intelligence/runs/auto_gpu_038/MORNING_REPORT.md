# NI overnight report (2026-11-15 17:18)

- run: `auto_gpu_038`  cycles completed: **144**  rounds: **144**  elapsed: 1.00 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **1.74 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/text/ag_news | 144 | 0.933 | 0.926 | 0.910 | 0.929 | 0.927 | 0.900 | 0.929 | 0.250 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/text/ag_news | 142 | 0.893 | 0.881 | 0.006 | 0.028 | 0.946 | 0.944 | 0.935 | 0.981 | 0.925 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/text/ag_news | 0.087 | 0.620 | 0.520 | 0.804 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/text/ag_news | 0.975 | 0.933 | 0.898 | 0.856 |

### Inner net on its permanent hold-out (n=180441), after 900338 outcome records
- inner: AUC 0.893, ECE 0.003, Brier 0.046, acc@80% 0.983
- raw outer vote confidence: AUC 0.880, ECE 0.027, Brier 0.049, acc@80% 0.982
- base rate of outer being right: 0.935

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
