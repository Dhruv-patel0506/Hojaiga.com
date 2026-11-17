# NI overnight report (2026-11-17 08:03)

- run: `auto_cpu_069`  cycles completed: **29**  rounds: **30**  elapsed: 1.69 h  status: **cycle 29 phase 3 enc2/image/dtd**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/image/dtd | 30 | 0.789 | 0.781 | 0.750 | 0.784 | 0.747 | 0.746 | 0.784 | 0.021 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/image/dtd | 29 | 0.868 | 0.858 | 0.067 | 0.078 | 0.828 | 0.829 | 0.799 | 0.944 | 0.910 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/image/dtd | 0.351 | 0.536 | 0.360 | 0.869 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/image/dtd | 0.946 | 0.789 | 0.910 | 1.000 |

### Inner net on its permanent hold-out (n=10128), after 50974 outcome records
- inner: AUC 0.869, ECE 0.017, Brier 0.111, acc@80% 0.895
- raw outer vote confidence: AUC 0.859, ECE 0.070, Brier 0.122, acc@80% 0.890
- base rate of outer being right: 0.795

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
