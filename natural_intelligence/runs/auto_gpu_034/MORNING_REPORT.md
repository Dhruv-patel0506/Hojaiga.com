# NI overnight report (2026-11-15 22:49)

- run: `auto_gpu_034`  cycles completed: **524**  rounds: **524**  elapsed: 1.01 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **0.75 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/text/imdb | 524 | 0.923 | 0.921 | 0.914 | 0.917 | 0.922 | 0.911 | 0.922 | 0.500 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/text/imdb | 513 | 0.896 | 0.876 | 0.013 | 0.020 | 0.931 | 0.929 | 0.925 | 0.990 | 0.955 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/text/imdb | 0.111 | 0.609 | 0.551 | 0.927 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/text/imdb | 0.985 | 0.923 | 0.958 | 0.937 |

### Inner net on its permanent hold-out (n=90840), after 449650 outcome records
- inner: AUC 0.894, ECE 0.005, Brier 0.053, acc@80% 0.979
- raw outer vote confidence: AUC 0.874, ECE 0.016, Brier 0.057, acc@80% 0.976
- base rate of outer being right: 0.924

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
