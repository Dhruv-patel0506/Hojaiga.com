# NI overnight report (2026-11-17 12:19)

- run: `auto_cpu_047`  cycles completed: **67**  rounds: **67**  elapsed: 2.09 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/graph/twitch_egos | 67 | 0.688 | 0.685 | 0.682 | 0.612 | 0.658 | 0.683 | 0.683 | 0.538 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/graph/twitch_egos | 61 | 0.581 | 0.581 | 0.015 | 0.045 | 0.750 | 0.750 | 0.683 | 0.294 | 0.874 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/graph/twitch_egos | 0.157 | 0.687 | 0.561 | 0.923 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/graph/twitch_egos | 0.951 | 0.688 | 0.955 | 0.890 |

### Inner net on its permanent hold-out (n=76386), after 381617 outcome records
- inner: AUC 0.580, ECE 0.011, Brier 0.213, acc@80% 0.708
- raw outer vote confidence: AUC 0.580, ECE 0.043, Brier 0.216, acc@80% 0.708
- base rate of outer being right: 0.681

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
