# NI overnight report (2026-11-07 15:43)

- run: `pair_video_enc_1107_1346`  cycles completed: **426**  rounds: **427**  elapsed: 1.94 h  status: **cycle 426 phase 5 enc/video/hmdb51**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **1.34 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/video/hmdb51 | 427 | 0.618 | 0.581 | 0.479 | 0.615 | 0.475 | 0.487 | 0.615 | 0.081 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/video/hmdb51 | 426 | 0.799 | 0.782 | 0.066 | 0.076 | 0.665 | 0.663 | 0.598 | 0.843 | 0.834 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/video/hmdb51 | 0.623 | 0.492 | 0.295 | 0.798 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/video/hmdb51 | 0.948 | 0.618 | 0.847 | 0.891 |

### Inner net on its permanent hold-out (n=199246), after 868255 outcome records
- inner: AUC 0.799, ECE 0.013, Brier 0.179, acc@80% 0.677
- raw outer vote confidence: AUC 0.785, ECE 0.040, Brier 0.187, acc@80% 0.673
- base rate of outer being right: 0.590

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
