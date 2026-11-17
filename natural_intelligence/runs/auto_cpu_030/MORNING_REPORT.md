# NI overnight report (2026-11-17 16:53)

- run: `auto_cpu_030`  cycles completed: **293**  rounds: **294**  elapsed: 1.92 h  status: **cycle 293 phase 1 enc2/text/sst2**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/text/sst2 | 294 | 0.911 | 0.909 | 0.905 | 0.904 | 0.905 | 0.899 | 0.905 | 0.516 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/text/sst2 | 287 | 0.870 | 0.866 | 0.026 | 0.033 | 0.923 | 0.923 | 0.913 | 0.979 | 0.951 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/text/sst2 | 0.129 | 0.646 | 0.544 | 0.840 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/text/sst2 | 0.977 | 0.911 | 0.905 | 1.000 |

### Inner net on its permanent hold-out (n=16161), after 86560 outcome records
- inner: AUC 0.864, ECE 0.007, Brier 0.064, acc@80% 0.966
- raw outer vote confidence: AUC 0.859, ECE 0.016, Brier 0.065, acc@80% 0.965
- base rate of outer being right: 0.915

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
