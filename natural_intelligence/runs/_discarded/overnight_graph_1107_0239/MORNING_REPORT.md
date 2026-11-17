# NI overnight report (2026-11-07 02:41)

- run: `overnight_graph_1107_0239`  cycles completed: **13**  rounds: **28**  elapsed: 0.03 h  status: **cycle 13 phase 2 graph/mutag**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **0.03 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| graph/mutag | 14 | 0.851 | 0.852 | 0.822 | 0.848 | 0.858 | 0.845 | 0.858 | 0.665 |
| graph/proteins | 14 | 0.773 | 0.772 | 0.739 | 0.767 | 0.742 | 0.760 | 0.767 | 0.596 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| graph/mutag | 13 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.898 |
| graph/proteins | 13 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.893 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| graph/mutag | 0.188 | 0.703 | 0.583 | 0.893 |
| graph/proteins | 0.260 | 0.674 | 0.554 | 0.869 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| graph/mutag | 0.902 | 0.848 | 0.854 | 0.998 |
| graph/proteins | 0.944 | 0.769 | 0.852 | 0.998 |

### Inner net on its permanent hold-out (n=1019), after 5567 outcome records
- inner: AUC 0.583, ECE 0.282, Brier 0.282, acc@80% 0.793
- raw outer vote confidence: AUC 0.714, ECE 0.035, Brier 0.158, acc@80% 0.821
- base rate of outer being right: 0.775

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
