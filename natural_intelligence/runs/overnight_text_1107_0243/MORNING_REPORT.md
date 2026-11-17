# NI overnight report (2026-11-07 07:17)

- run: `overnight_text_1107_0243`  cycles completed: **249**  rounds: **250**  elapsed: 4.55 h  status: **cycle 249 phase 1 text/ag_news**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **3.17 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| text/ag_news | 250 | 0.891 | 0.886 | 0.773 | 0.827 | 0.887 | 0.511 | 0.887 | 0.250 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| text/ag_news | 249 | 0.880 | 0.824 | 0.009 | 0.073 | 0.913 | 0.908 | 0.889 | 0.961 | 0.872 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| text/ag_news | 0.142 | 0.575 | 0.397 | 0.786 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| text/ag_news | 0.927 | 0.891 | 0.889 | 0.736 |

### Inner net on its permanent hold-out (n=600155), after 3000000 outcome records
- inner: AUC 0.879, ECE 0.001, Brier 0.071, acc@80% 0.961
- raw outer vote confidence: AUC 0.822, ECE 0.076, Brier 0.091, acc@80% 0.947
- base rate of outer being right: 0.887

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
