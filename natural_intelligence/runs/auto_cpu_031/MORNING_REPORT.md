# NI overnight report (2026-11-17 19:45)

- run: `auto_cpu_031`  cycles completed: **237**  rounds: **237**  elapsed: 2.01 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/text/banking77 | 237 | 0.942 | 0.939 | 0.910 | 0.939 | 0.936 | 0.918 | 0.939 | 0.017 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/text/banking77 | 230 | 0.928 | 0.923 | 0.020 | 0.019 | 0.955 | 0.955 | 0.948 | 0.986 | 0.964 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/text/banking77 | 0.089 | 0.577 | 0.436 | 0.846 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/text/banking77 | 0.990 | 0.942 | 0.912 | 1.000 |

### Inner net on its permanent hold-out (n=21382), after 110252 outcome records
- inner: AUC 0.933, ECE 0.008, Brier 0.034, acc@80% 0.994
- raw outer vote confidence: AUC 0.929, ECE 0.009, Brier 0.035, acc@80% 0.994
- base rate of outer being right: 0.948

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
