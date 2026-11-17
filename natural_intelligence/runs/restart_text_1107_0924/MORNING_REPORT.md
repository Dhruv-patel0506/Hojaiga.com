# NI overnight report (2026-11-07 13:19)

- run: `restart_text_1107_0924`  cycles completed: **165**  rounds: **166**  elapsed: 3.91 h  status: **cycle 165 phase 1 text/ag_news**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **3.17 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| text/ag_news | 166 | 0.890 | 0.886 | 0.773 | 0.826 | 0.887 | 0.512 | 0.887 | 0.250 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| text/ag_news | 165 | 0.881 | 0.822 | 0.010 | 0.072 | 0.912 | 0.907 | 0.889 | 0.962 | 0.873 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| text/ag_news | 0.144 | 0.577 | 0.392 | 0.788 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| text/ag_news | 0.928 | 0.890 | 0.891 | 0.736 |

### Inner net on its permanent hold-out (n=600174), after 3000000 outcome records
- inner: AUC 0.881, ECE 0.003, Brier 0.069, acc@80% 0.963
- raw outer vote confidence: AUC 0.824, ECE 0.073, Brier 0.089, acc@80% 0.949
- base rate of outer being right: 0.889

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
