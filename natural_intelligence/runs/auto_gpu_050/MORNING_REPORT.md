# NI overnight report (2026-11-16 06:21)

- run: `auto_gpu_050`  cycles completed: **120**  rounds: **120**  elapsed: 4.10 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **1.54 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/audio/speech_commands_v0.02 | 120 | 0.726 | 0.714 | 0.679 | 0.727 | 0.370 | 0.408 | 0.727 | 0.038 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/audio/speech_commands_v0.02 | 117 | 0.886 | 0.863 | 0.014 | 0.029 | 0.922 | 0.907 | 0.727 | 0.623 | 0.837 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/audio/speech_commands_v0.02 | 0.189 | 0.509 | 0.414 | 0.437 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/audio/speech_commands_v0.02 | 0.972 | 0.726 | 0.707 | 0.872 |

### Inner net on its permanent hold-out (n=12901), after 63550 outcome records
- inner: AUC 0.883, ECE 0.010, Brier 0.123, acc@80% 0.837
- raw outer vote confidence: AUC 0.863, ECE 0.031, Brier 0.133, acc@80% 0.827
- base rate of outer being right: 0.725

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
