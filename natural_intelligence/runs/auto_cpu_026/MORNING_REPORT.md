# NI overnight report (2026-11-17 14:40)

- run: `auto_cpu_026`  cycles completed: **386**  rounds: **387**  elapsed: 0.42 h  status: **cycle 386 phase 4 enc/audio/ravdess**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/audio/ravdess | 346 | 0.692 | 0.677 | 0.652 | 0.692 | 0.552 | 0.579 | 0.692 | 0.133 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/audio/ravdess | 339 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.857 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/audio/ravdess | 0.495 | 0.538 | 0.401 | 0.695 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/audio/ravdess | 0.934 | 0.692 | 0.785 | 1.000 |

### Inner net on its permanent hold-out (n=659), after 3469 outcome records
- inner: AUC 0.806, ECE 0.050, Brier 0.157, acc@80% 0.795
- raw outer vote confidence: AUC 0.793, ECE 0.035, Brier 0.159, acc@80% 0.805
- base rate of outer being right: 0.722

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
