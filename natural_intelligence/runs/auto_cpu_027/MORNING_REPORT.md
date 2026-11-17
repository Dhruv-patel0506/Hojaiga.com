# NI overnight report (2026-11-17 14:39)

- run: `auto_cpu_027`  cycles completed: **427**  rounds: **428**  elapsed: 0.36 h  status: **cycle 427 phase 4 enc/audio/music_genres_small**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/audio/music_genres_small | 387 | 0.551 | 0.558 | 0.547 | 0.528 | 0.554 | 0.542 | 0.554 | 0.100 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/audio/music_genres_small | 380 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.829 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/audio/music_genres_small | 0.734 | 0.451 | 0.319 | 0.883 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/audio/music_genres_small | 0.912 | 0.551 | 0.858 | 1.000 |

### Inner net on its permanent hold-out (n=482), after 2440 outcome records
- inner: AUC 0.718, ECE 0.067, Brier 0.211, acc@80% 0.595
- raw outer vote confidence: AUC 0.739, ECE 0.065, Brier 0.201, acc@80% 0.610
- base rate of outer being right: 0.556

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
