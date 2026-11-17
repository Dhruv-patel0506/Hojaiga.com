# NI overnight report (2026-11-17 14:41)

- run: `auto_gpu_009`  cycles completed: **370**  rounds: **371**  elapsed: 0.09 h  status: **cycle 370 phase 1 enc/text/sms_spam**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/text/sms_spam | 371 | 0.991 | 0.991 | 0.986 | 0.991 | 0.983 | 0.980 | 0.991 | 0.866 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/text/sms_spam | 363 | 0.727 | 0.884 | 0.008 | 0.010 | 0.993 | 0.993 | 0.992 | 0.997 | 0.961 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/text/sms_spam | 0.009 | 0.628 | 0.401 | 0.675 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/text/sms_spam | 0.991 | 0.991 | 0.832 | 1.000 |

### Inner net on its permanent hold-out (n=366), after 1631 outcome records
- inner: AUC 0.532, ECE 0.007, Brier 0.007, acc@80% 0.993
- raw outer vote confidence: AUC 0.845, ECE 0.007, Brier 0.006, acc@80% 0.997
- base rate of outer being right: 0.995

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
