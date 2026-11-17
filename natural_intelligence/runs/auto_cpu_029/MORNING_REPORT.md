# NI overnight report (2026-11-17 16:50)

- run: `auto_cpu_029`  cycles completed: **215**  rounds: **216**  elapsed: 1.88 h  status: **cycle 215 phase 1 enc2/text/sms_spam**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/text/sms_spam | 216 | 0.992 | 0.992 | 0.989 | 0.992 | 0.989 | 0.985 | 0.992 | 0.866 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/text/sms_spam | 209 | 0.916 | 0.913 | 0.007 | 0.018 | 0.992 | 0.992 | 0.991 | 0.999 | 0.959 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/text/sms_spam | 0.006 | 0.399 | 0.405 | 0.684 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/text/sms_spam | 0.984 | 0.992 | 0.836 | 1.000 |

### Inner net on its permanent hold-out (n=3445), after 16689 outcome records
- inner: AUC 0.910, ECE 0.007, Brier 0.008, acc@80% 0.997
- raw outer vote confidence: AUC 0.813, ECE 0.009, Brier 0.010, acc@80% 0.997
- base rate of outer being right: 0.990

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
