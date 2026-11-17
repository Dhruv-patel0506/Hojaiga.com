# NI overnight report (2026-11-14 08:47)

- run: `auto_gpu_035`  cycles completed: **85**  rounds: **86**  elapsed: 0.20 h  status: **cycle 85 phase 1 enc2/text/dbpedia_14**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **1.46 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/text/dbpedia_14 | 86 | 0.987 | 0.985 | 0.979 | 0.987 | 0.970 | 0.964 | 0.987 | 0.073 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/text/dbpedia_14 | 83 | 0.953 | 0.948 | 0.004 | 0.008 | 0.989 | 0.989 | 0.986 | 0.995 | 0.941 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/text/dbpedia_14 | 0.014 | 0.566 | 0.490 | 0.716 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/text/dbpedia_14 | 0.993 | 0.987 | 0.856 | 0.879 |

### Inner net on its permanent hold-out (n=42229), after 209982 outcome records
- inner: AUC 0.958, ECE 0.002, Brier 0.010, acc@80% 0.999
- raw outer vote confidence: AUC 0.954, ECE 0.006, Brier 0.010, acc@80% 0.999
- base rate of outer being right: 0.987

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
