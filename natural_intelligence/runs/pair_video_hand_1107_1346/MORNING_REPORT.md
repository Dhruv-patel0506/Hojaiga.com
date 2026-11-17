# NI overnight report (2026-11-07 15:53)

- run: `pair_video_hand_1107_1346`  cycles completed: **442**  rounds: **443**  elapsed: 2.11 h  status: **cycle 442 phase 5 hand/video/hmdb51**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **0.40 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| hand/video/hmdb51 | 443 | 0.160 | 0.159 | 0.095 | 0.158 | 0.111 | 0.131 | 0.158 | 0.081 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| hand/video/hmdb51 | 442 | 0.692 | 0.667 | 0.048 | 0.172 | 0.228 | 0.223 | 0.163 | 0.523 | 0.681 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| hand/video/hmdb51 | 0.991 | 0.190 | 0.115 | 0.623 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| hand/video/hmdb51 | 0.835 | 0.160 | 0.777 | 0.967 |

### Inner net on its permanent hold-out (n=184941), after 906916 outcome records
- inner: AUC 0.690, ECE 0.015, Brier 0.129, acc@80% 0.195
- raw outer vote confidence: AUC 0.653, ECE 0.152, Brier 0.164, acc@80% 0.193
- base rate of outer being right: 0.172

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
