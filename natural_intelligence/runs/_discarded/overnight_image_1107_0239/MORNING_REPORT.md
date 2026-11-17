# NI overnight report (2026-11-07 02:41)

- run: `overnight_image_1107_0239`  cycles completed: **21**  rounds: **22**  elapsed: 0.03 h  status: **cycle 21 phase 3 image/cifar10**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **0.09 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| image/cifar10 | 22 | 0.563 | 0.559 | 0.407 | 0.553 | 0.463 | 0.479 | 0.553 | 0.105 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| image/cifar10 | 21 | 0.651 | 0.748 | 0.256 | 0.084 | 0.611 | 0.634 | 0.567 | 0.791 | 0.829 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| image/cifar10 | 0.560 | 0.522 | 0.346 | 0.707 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| image/cifar10 | 0.935 | 0.563 | 0.809 | 0.993 |

### Inner net on its permanent hold-out (n=6762), after 32892 outcome records
- inner: AUC 0.643, ECE 0.222, Brier 0.292, acc@80% 0.600
- raw outer vote confidence: AUC 0.737, ECE 0.038, Brier 0.206, acc@80% 0.628
- base rate of outer being right: 0.565

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
