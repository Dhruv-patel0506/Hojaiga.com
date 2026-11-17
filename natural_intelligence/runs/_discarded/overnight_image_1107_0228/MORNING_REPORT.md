# NI overnight report (2026-11-07 02:38)

- run: `overnight_image_1107_0228`  cycles completed: **140**  rounds: **141**  elapsed: 0.17 h  status: **cycle 140 phase 3 image/cifar10**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **0.09 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| image/cifar10 | 141 | 0.538 | 0.540 | 0.407 | 0.535 | 0.451 | 0.463 | 0.535 | 0.107 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| image/cifar10 | 140 | 0.500 | 0.753 | 0.033 | 0.107 | 0.533 | 0.642 | 0.539 | 0.714 | 0.820 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| image/cifar10 | 1.000 | 0.608 | 0.367 | 0.761 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| image/cifar10 | 0.904 | 0.538 | 0.850 | 0.994 |

### Inner net on its permanent hold-out (n=28183), after 134437 outcome records
- inner: AUC 0.502, ECE 0.012, Brier 0.252, acc@80% 0.513
- raw outer vote confidence: AUC 0.737, ECE 0.094, Brier 0.217, acc@80% 0.581
- base rate of outer being right: 0.518

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
