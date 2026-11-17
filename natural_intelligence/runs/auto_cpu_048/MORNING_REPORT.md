# NI overnight report (2026-11-08 07:13)

- run: `auto_cpu_048`  cycles completed: **19**  rounds: **19**  elapsed: 2.10 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/graph/reddit_threads | 19 | 0.774 | 0.772 | 0.776 | 0.764 | 0.739 | 0.763 | 0.776 | 0.512 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/graph/reddit_threads | 18 | 0.703 | 0.694 | 0.012 | 0.042 | 0.839 | 0.837 | 0.774 | 0.729 | 0.918 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/graph/reddit_threads | 0.099 | 0.645 | 0.535 | 0.894 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/graph/reddit_threads | 0.959 | 0.774 | 0.944 | 1.000 |

### Inner net on its permanent hold-out (n=230952), after 1156871 outcome records
- inner: AUC 0.703, ECE 0.006, Brier 0.159, acc@80% 0.824
- raw outer vote confidence: AUC 0.693, ECE 0.041, Brier 0.162, acc@80% 0.822
- base rate of outer being right: 0.774

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
