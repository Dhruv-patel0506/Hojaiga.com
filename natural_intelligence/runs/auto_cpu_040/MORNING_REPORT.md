# NI overnight report (2026-11-18 00:06)

- run: `auto_cpu_040`  cycles completed: **293**  rounds: **294**  elapsed: 0.19 h  status: **cycle 293 phase 1 enc/text/bbc_news**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/text/bbc_news | 295 | 0.970 | 0.972 | 0.965 | 0.966 | 0.962 | 0.964 | 0.966 | 0.230 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/text/bbc_news | 288 | 0.897 | 0.917 | 0.027 | 0.032 | 0.971 | 0.969 | 0.969 | 0.995 | 0.961 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/text/bbc_news | 0.023 | 0.539 | 0.356 | 0.786 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/text/bbc_news | 0.983 | 0.969 | 0.872 | 1.000 |

### Inner net on its permanent hold-out (n=441), after 2065 outcome records
- inner: AUC 0.867, ECE 0.011, Brier 0.019, acc@80% 0.994
- raw outer vote confidence: AUC 0.912, ECE 0.019, Brier 0.021, acc@80% 0.994
- base rate of outer being right: 0.977

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
