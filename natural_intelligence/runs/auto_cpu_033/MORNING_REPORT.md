# NI overnight report (2026-11-17 19:48)

- run: `auto_cpu_033`  cycles completed: **159**  rounds: **159**  elapsed: 2.02 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/text/emotion | 159 | 0.780 | 0.779 | 0.745 | 0.792 | 0.739 | 0.693 | 0.792 | 0.338 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/text/emotion | 152 | 0.849 | 0.767 | 0.031 | 0.056 | 0.832 | 0.819 | 0.773 | 0.879 | 0.893 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/text/emotion | 0.349 | 0.547 | 0.439 | 0.718 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/text/emotion | 0.946 | 0.780 | 0.832 | 1.000 |

### Inner net on its permanent hold-out (n=29978), after 149836 outcome records
- inner: AUC 0.851, ECE 0.015, Brier 0.125, acc@80% 0.865
- raw outer vote confidence: AUC 0.769, ECE 0.048, Brier 0.147, acc@80% 0.846
- base rate of outer being right: 0.773

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
