# NI overnight report (2026-11-17 19:49)

- run: `auto_cpu_032`  cycles completed: **163**  rounds: **163**  elapsed: 2.05 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/text/20_newsgroups | 163 | 0.798 | 0.778 | 0.726 | 0.757 | 0.796 | 0.718 | 0.796 | 0.053 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/text/20_newsgroups | 156 | 0.913 | 0.900 | 0.032 | 0.075 | 0.843 | 0.843 | 0.801 | 0.941 | 0.907 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/text/20_newsgroups | 0.297 | 0.486 | 0.250 | 0.834 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/text/20_newsgroups | 0.932 | 0.798 | 0.905 | 1.000 |

### Inner net on its permanent hold-out (n=28771), after 147184 outcome records
- inner: AUC 0.911, ECE 0.006, Brier 0.090, acc@80% 0.917
- raw outer vote confidence: AUC 0.896, ECE 0.067, Brier 0.104, acc@80% 0.908
- base rate of outer being right: 0.801

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
