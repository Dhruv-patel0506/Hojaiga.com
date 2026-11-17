# NI overnight report (2026-11-17 19:49)

- run: `auto_cpu_011`  cycles completed: **100**  rounds: **100**  elapsed: 2.07 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/graph/reddit_threads | 100 | 0.773 | 0.771 | 0.772 | 0.768 | 0.725 | 0.755 | 0.772 | 0.512 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/graph/reddit_threads | 92 | 0.698 | 0.695 | 0.014 | 0.012 | 0.839 | 0.838 | 0.773 | 0.708 | 0.914 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/graph/reddit_threads | 0.098 | 0.656 | 0.559 | 0.816 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/graph/reddit_threads | 0.989 | 0.773 | 0.904 | 0.969 |

### Inner net on its permanent hold-out (n=121628), after 609484 outcome records
- inner: AUC 0.697, ECE 0.005, Brier 0.161, acc@80% 0.821
- raw outer vote confidence: AUC 0.693, ECE 0.006, Brier 0.161, acc@80% 0.820
- base rate of outer being right: 0.772

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
