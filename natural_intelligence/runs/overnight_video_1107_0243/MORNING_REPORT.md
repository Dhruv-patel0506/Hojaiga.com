# NI overnight report (2026-11-07 11:43)

- run: `overnight_video_1107_0243`  cycles completed: **1541**  rounds: **1541**  elapsed: 9.00 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **0.05 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| video/hmdb51 | 1541 | 0.323 | 0.311 | 0.207 | 0.300 | 0.279 | 0.304 | 0.304 | 0.264 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| video/hmdb51 | 1540 | 0.638 | 0.647 | 0.105 | 0.092 | 0.415 | 0.410 | 0.369 | 0.709 | 0.765 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| video/hmdb51 | 0.987 | 0.345 | 0.244 | 0.765 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| video/hmdb51 | 0.934 | 0.323 | 0.789 | 0.996 |

### Inner net on its permanent hold-out (n=177037), after 656184 outcome records
- inner: AUC 0.644, ECE 0.067, Brier 0.224, acc@80% 0.411
- raw outer vote confidence: AUC 0.643, ECE 0.020, Brier 0.220, acc@80% 0.410
- base rate of outer being right: 0.376

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
