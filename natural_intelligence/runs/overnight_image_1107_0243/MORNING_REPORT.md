# NI overnight report (2026-11-07 07:20)

- run: `overnight_image_1107_0243`  cycles completed: **456**  rounds: **457**  elapsed: 4.61 h  status: **cycle 456 phase 3 image/cifar10**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **0.49 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| image/cifar10 | 457 | 0.683 | 0.658 | 0.414 | 0.680 | 0.581 | 0.521 | 0.680 | 0.100 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| image/cifar10 | 456 | 0.836 | 0.809 | 0.025 | 0.045 | 0.834 | 0.817 | 0.681 | 0.672 | 0.863 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| image/cifar10 | 0.400 | 0.550 | 0.412 | 0.662 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| image/cifar10 | 0.961 | 0.683 | 0.821 | 0.959 |

### Inner net on its permanent hold-out (n=565401), after 2817845 outcome records
- inner: AUC 0.819, ECE 0.007, Brier 0.164, acc@80% 0.737
- raw outer vote confidence: AUC 0.792, ECE 0.021, Brier 0.175, acc@80% 0.727
- base rate of outer being right: 0.648

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
