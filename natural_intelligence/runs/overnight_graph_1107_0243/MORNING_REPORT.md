# NI overnight report (2026-11-07 05:06)

- run: `overnight_graph_1107_0243`  cycles completed: **400**  rounds: **800**  elapsed: 2.37 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **0.03 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| graph/mutag | 400 | 0.868 | 0.862 | 0.822 | 0.863 | 0.879 | 0.857 | 0.879 | 0.665 |
| graph/proteins | 400 | 0.763 | 0.771 | 0.735 | 0.761 | 0.739 | 0.758 | 0.761 | 0.596 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| graph/mutag | 399 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.890 |
| graph/proteins | 399 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.891 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| graph/mutag | 0.147 | 0.512 | 0.417 | 0.854 |
| graph/proteins | 0.410 | 0.651 | 0.568 | 0.799 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| graph/mutag | 0.895 | 0.868 | 0.799 | 0.998 |
| graph/proteins | 0.944 | 0.763 | 0.852 | 0.998 |

### Inner net on its permanent hold-out (n=28990), after 156356 outcome records
- inner: AUC 0.709, ECE 0.020, Brier 0.153, acc@80% 0.837
- raw outer vote confidence: AUC 0.726, ECE 0.014, Brier 0.151, acc@80% 0.836
- base rate of outer being right: 0.785

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
