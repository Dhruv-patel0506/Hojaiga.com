# NI overnight report (2026-11-15 16:11)

- run: `auto_gpu_037`  cycles completed: **118**  rounds: **118**  elapsed: 1.02 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **1.74 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/text/yahoo_answers_topics | 118 | 0.747 | 0.743 | 0.724 | 0.734 | 0.738 | 0.712 | 0.738 | 0.101 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/text/yahoo_answers_topics | 116 | 0.819 | 0.816 | 0.014 | 0.039 | 0.855 | 0.854 | 0.744 | 0.736 | 0.883 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/text/yahoo_answers_topics | 0.167 | 0.537 | 0.350 | 0.903 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/text/yahoo_answers_topics | 0.960 | 0.747 | 0.946 | 0.856 |

### Inner net on its permanent hold-out (n=200845), after 1007755 outcome records
- inner: AUC 0.819, ECE 0.006, Brier 0.143, acc@80% 0.831
- raw outer vote confidence: AUC 0.816, ECE 0.038, Brier 0.146, acc@80% 0.830
- base rate of outer being right: 0.743

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
