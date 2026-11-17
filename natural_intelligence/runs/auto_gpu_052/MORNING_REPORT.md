# NI overnight report (2026-11-16 01:08)

- run: `auto_gpu_052`  cycles completed: **873**  rounds: **873**  elapsed: 1.01 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **0.53 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/text/enron_spam | 873 | 0.993 | 0.991 | 0.983 | 0.991 | 0.992 | 0.974 | 0.992 | 0.509 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/text/enron_spam | 855 | 0.990 | 0.974 | 0.004 | 0.008 | 0.995 | 0.995 | 0.995 | 0.999 | 0.972 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/text/enron_spam | 0.007 | 0.584 | 0.484 | 0.849 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/text/enron_spam | 0.994 | 0.993 | 0.923 | 0.956 |

### Inner net on its permanent hold-out (n=80954), after 404575 outcome records
- inner: AUC 0.990, ECE 0.001, Brier 0.004, acc@80% 1.000
- raw outer vote confidence: AUC 0.971, ECE 0.006, Brier 0.004, acc@80% 1.000
- base rate of outer being right: 0.995

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
