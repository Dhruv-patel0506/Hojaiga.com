# NI overnight report (2026-11-07 02:38)

- run: `overnight_text_1107_0228`  cycles completed: **83**  rounds: **84**  elapsed: 0.17 h  status: **cycle 83 phase 1 text/ag_news**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **0.45 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| text/ag_news | 84 | 0.843 | 0.837 | 0.738 | 0.746 | 0.834 | 0.467 | 0.834 | 0.260 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| text/ag_news | 83 | 0.500 | 0.818 | 0.012 | 0.143 | 0.846 | 0.846 | 0.846 | 1.000 | 0.900 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| text/ag_news | n/a | n/a | n/a | n/a |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| text/ag_news | 0.858 | 0.843 | 0.978 | 0.966 |

### Inner net on its permanent hold-out (n=52914), after 264132 outcome records
- inner: AUC 0.507, ECE 0.011, Brier 0.133, acc@80% 0.844
- raw outer vote confidence: AUC 0.816, ECE 0.152, Brier 0.135, acc@80% 0.919
- base rate of outer being right: 0.844

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
