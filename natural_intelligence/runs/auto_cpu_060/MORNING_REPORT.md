# NI overnight report (2026-11-17 16:52)

- run: `auto_cpu_060`  cycles completed: **96**  rounds: **97**  elapsed: 1.96 h  status: **cycle 96 phase 4 enc2/audio/music_genres_small**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/audio/music_genres_small | 97 | 0.564 | 0.563 | 0.552 | 0.543 | 0.557 | 0.560 | 0.560 | 0.100 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/audio/music_genres_small | 92 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.841 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/audio/music_genres_small | 0.780 | 0.476 | 0.350 | 0.922 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/audio/music_genres_small | 0.917 | 0.564 | 0.897 | 1.000 |

### Inner net on its permanent hold-out (n=1095), after 5736 outcome records
- inner: AUC 0.752, ECE 0.057, Brier 0.200, acc@80% 0.596
- raw outer vote confidence: AUC 0.721, ECE 0.046, Brier 0.212, acc@80% 0.588
- base rate of outer being right: 0.530

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
