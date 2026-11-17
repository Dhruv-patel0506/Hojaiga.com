# NI overnight report (2026-11-17 21:57)

- run: `auto_cpu_014`  cycles completed: **148**  rounds: **148**  elapsed: 2.11 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/graph/twitch_egos | 149 | 0.689 | 0.687 | 0.688 | 0.626 | 0.636 | 0.679 | 0.688 | 0.538 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/graph/twitch_egos | 141 | 0.576 | 0.577 | 0.013 | 0.044 | 0.754 | 0.754 | 0.685 | 0.252 | 0.890 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/graph/twitch_egos | 0.157 | 0.693 | 0.594 | 0.856 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/graph/twitch_egos | 0.951 | 0.690 | 0.922 | 1.000 |

### Inner net on its permanent hold-out (n=137311), after 685864 outcome records
- inner: AUC 0.577, ECE 0.010, Brier 0.212, acc@80% 0.710
- raw outer vote confidence: AUC 0.577, ECE 0.043, Brier 0.215, acc@80% 0.711
- base rate of outer being right: 0.685

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
