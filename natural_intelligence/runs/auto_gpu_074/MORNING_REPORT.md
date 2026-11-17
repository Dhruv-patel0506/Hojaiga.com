# NI overnight report (2026-11-16 15:55)

- run: `auto_gpu_074`  cycles completed: **35**  rounds: **35**  elapsed: 1.02 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **1.75 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/image/cifar100 | 35 | 0.896 | 0.896 | 0.865 | 0.894 | 0.873 | 0.854 | 0.894 | 0.010 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/image/cifar100 | 34 | 0.927 | 0.919 | 0.015 | 0.017 | 0.929 | 0.927 | 0.899 | 0.952 | 0.911 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/image/cifar100 | 0.146 | 0.534 | 0.384 | 0.721 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/image/cifar100 | 0.985 | 0.896 | 0.855 | 0.855 |

### Inner net on its permanent hold-out (n=126982), after 630548 outcome records
- inner: AUC 0.929, ECE 0.005, Brier 0.056, acc@80% 0.980
- raw outer vote confidence: AUC 0.916, ECE 0.004, Brier 0.061, acc@80% 0.975
- base rate of outer being right: 0.899

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
