# NI overnight report (2026-11-17 10:15)

- run: `auto_cpu_058`  cycles completed: **75**  rounds: **75**  elapsed: 2.09 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/audio/gtzan | 75 | 0.879 | 0.875 | 0.879 | 0.874 | 0.823 | 0.849 | 0.879 | 0.100 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/audio/gtzan | 70 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.922 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/audio/gtzan | 0.170 | 0.550 | 0.419 | 0.823 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/audio/gtzan | 0.945 | 0.880 | 0.859 | 1.000 |

### Inner net on its permanent hold-out (n=1007), after 5046 outcome records
- inner: AUC 0.925, ECE 0.046, Brier 0.064, acc@80% 0.970
- raw outer vote confidence: AUC 0.930, ECE 0.026, Brier 0.060, acc@80% 0.975
- base rate of outer being right: 0.893

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
