# NI overnight report (2026-11-07 02:41)

- run: `overnight_text_1107_0239`  cycles completed: **16**  rounds: **17**  elapsed: 0.03 h  status: **cycle 16 phase 1 text/ag_news**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **0.46 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| text/ag_news | 17 | 0.857 | 0.845 | 0.748 | 0.752 | 0.841 | 0.472 | 0.841 | 0.262 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| text/ag_news | 16 | 0.770 | 0.824 | 0.086 | 0.181 | 0.881 | 0.886 | 0.862 | 0.946 | 0.873 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| text/ag_news | 0.212 | 0.715 | 0.435 | 0.807 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| text/ag_news | 0.822 | 0.858 | 0.894 | 0.962 |

### Inner net on its permanent hold-out (n=14333), after 71726 outcome records
- inner: AUC 0.769, ECE 0.071, Brier 0.115, acc@80% 0.921
- raw outer vote confidence: AUC 0.824, ECE 0.184, Brier 0.137, acc@80% 0.930
- base rate of outer being right: 0.862

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
