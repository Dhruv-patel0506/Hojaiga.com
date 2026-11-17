# NI overnight report (2026-11-13 14:51)

- run: `auto_gpu_002`  cycles completed: **39**  rounds: **40**  elapsed: 0.39 h  status: **cycle 39 phase 3 enc/image/cifar100**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **0.91 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/image/cifar100 | 40 | 0.842 | 0.838 | 0.790 | 0.839 | 0.801 | 0.769 | 0.839 | 0.010 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/image/cifar100 | 38 | 0.910 | 0.889 | 0.013 | 0.056 | 0.898 | 0.892 | 0.843 | 0.912 | 0.895 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/image/cifar100 | 0.238 | 0.538 | 0.376 | 0.692 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/image/cifar100 | 0.946 | 0.843 | 0.839 | 0.927 |

### Inner net on its permanent hold-out (n=36466), after 180396 outcome records
- inner: AUC 0.914, ECE 0.006, Brier 0.081, acc@80% 0.943
- raw outer vote confidence: AUC 0.889, ECE 0.038, Brier 0.093, acc@80% 0.933
- base rate of outer being right: 0.840

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
