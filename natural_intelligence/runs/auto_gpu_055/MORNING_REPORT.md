# NI overnight report (2026-11-15 20:36)

- run: `auto_gpu_055`  cycles completed: **195**  rounds: **195**  elapsed: 1.01 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **0.91 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/image/food101 | 195 | 0.756 | 0.745 | 0.716 | 0.756 | 0.670 | 0.672 | 0.756 | 0.011 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/image/food101 | 189 | 0.898 | 0.883 | 0.017 | 0.038 | 0.859 | 0.851 | 0.754 | 0.821 | 0.875 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/image/food101 | 0.333 | 0.512 | 0.345 | 0.665 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/image/food101 | 0.961 | 0.756 | 0.823 | 0.924 |

### Inner net on its permanent hold-out (n=92582), after 469034 outcome records
- inner: AUC 0.897, ECE 0.008, Brier 0.109, acc@80% 0.871
- raw outer vote confidence: AUC 0.883, ECE 0.036, Brier 0.119, acc@80% 0.862
- base rate of outer being right: 0.755

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
