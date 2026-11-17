# NI overnight report (2026-11-07 02:39)

- run: `overnight_graph_1107_0232`  cycles completed: **74**  rounds: **150**  elapsed: 0.12 h  status: **cycle 74 phase 2 graph/mutag**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **0.03 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| graph/mutag | 75 | 0.867 | 0.863 | 0.816 | 0.857 | 0.872 | 0.859 | 0.872 | 0.665 |
| graph/proteins | 75 | 0.764 | 0.770 | 0.751 | 0.761 | 0.741 | 0.756 | 0.761 | 0.596 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| graph/mutag | 74 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.885 |
| graph/proteins | 74 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.894 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| graph/mutag | 0.148 | 0.610 | 0.550 | 0.779 |
| graph/proteins | 0.406 | 0.634 | 0.553 | 0.787 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| graph/mutag | 0.886 | 0.867 | 0.790 | 0.998 |
| graph/proteins | 0.953 | 0.764 | 0.847 | 0.998 |

### Inner net on its permanent hold-out (n=5421), after 29547 outcome records
- inner: AUC 0.703, ECE 0.032, Brier 0.154, acc@80% 0.839
- raw outer vote confidence: AUC 0.725, ECE 0.015, Brier 0.149, acc@80% 0.842
- base rate of outer being right: 0.791

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
