# NI overnight report (2026-11-17 12:21)

- run: `auto_cpu_049`  cycles completed: **161**  rounds: **161**  elapsed: 2.08 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/text/bbc_news | 161 | 0.977 | 0.978 | 0.972 | 0.977 | 0.969 | 0.975 | 0.977 | 0.230 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/text/bbc_news | 155 | 0.824 | 0.952 | 0.023 | 0.023 | 0.980 | 0.980 | 0.979 | 0.997 | 0.969 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/text/bbc_news | 0.026 | 0.634 | 0.466 | 0.826 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/text/bbc_news | 0.985 | 0.978 | 0.898 | 1.000 |

### Inner net on its permanent hold-out (n=2183), after 10677 outcome records
- inner: AUC 0.903, ECE 0.011, Brier 0.018, acc@80% 0.997
- raw outer vote confidence: AUC 0.930, ECE 0.008, Brier 0.017, acc@80% 0.998
- base rate of outer being right: 0.979

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
