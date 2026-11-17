# NI overnight report (2026-11-18 00:10)

- run: `auto_cpu_039`  cycles completed: **337**  rounds: **338**  elapsed: 0.27 h  status: **cycle 337 phase 1 enc/text/enron_spam**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/text/enron_spam | 338 | 0.990 | 0.986 | 0.972 | 0.986 | 0.987 | 0.965 | 0.987 | 0.509 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/text/enron_spam | 331 | 0.986 | 0.979 | 0.004 | 0.010 | 0.993 | 0.992 | 0.991 | 0.997 | 0.971 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/text/enron_spam | 0.014 | 0.609 | 0.568 | 0.768 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/text/enron_spam | 0.991 | 0.990 | 0.882 | 1.000 |

### Inner net on its permanent hold-out (n=10033), after 50320 outcome records
- inner: AUC 0.985, ECE 0.002, Brier 0.007, acc@80% 1.000
- raw outer vote confidence: AUC 0.967, ECE 0.007, Brier 0.008, acc@80% 1.000
- base rate of outer being right: 0.989

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
