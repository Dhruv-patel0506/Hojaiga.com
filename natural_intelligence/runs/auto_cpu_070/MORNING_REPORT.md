# NI overnight report (2026-11-17 10:09)

- run: `auto_cpu_070`  cycles completed: **39**  rounds: **39**  elapsed: 2.00 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/image/oxford_iiit_pet | 39 | 0.947 | 0.943 | 0.935 | 0.947 | 0.903 | 0.927 | 0.947 | 0.027 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/image/oxford_iiit_pet | 38 | 0.924 | 0.913 | 0.023 | 0.022 | 0.955 | 0.954 | 0.948 | 0.987 | 0.959 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/image/oxford_iiit_pet | 0.059 | 0.567 | 0.516 | 0.786 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/image/oxford_iiit_pet | 0.985 | 0.947 | 0.885 | 1.000 |

### Inner net on its permanent hold-out (n=16504), after 86182 outcome records
- inner: AUC 0.931, ECE 0.010, Brier 0.038, acc@80% 0.991
- raw outer vote confidence: AUC 0.919, ECE 0.009, Brier 0.041, acc@80% 0.989
- base rate of outer being right: 0.945

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
