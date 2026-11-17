# NI overnight report (2026-11-17 16:53)

- run: `auto_cpu_064`  cycles completed: **81**  rounds: **82**  elapsed: 1.96 h  status: **cycle 81 phase 5 enc2/video/hmdb51**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/video/hmdb51 | 82 | 0.706 | 0.682 | 0.601 | 0.705 | 0.594 | 0.644 | 0.705 | 0.081 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/video/hmdb51 | 78 | 0.816 | 0.812 | 0.068 | 0.090 | 0.729 | 0.729 | 0.689 | 0.915 | 0.877 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/video/hmdb51 | 0.474 | 0.510 | 0.301 | 0.847 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/video/hmdb51 | 0.931 | 0.706 | 0.876 | 0.999 |

### Inner net on its permanent hold-out (n=12298), after 52874 outcome records
- inner: AUC 0.815, ECE 0.025, Brier 0.159, acc@80% 0.776
- raw outer vote confidence: AUC 0.805, ECE 0.055, Brier 0.166, acc@80% 0.774
- base rate of outer being right: 0.687

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
