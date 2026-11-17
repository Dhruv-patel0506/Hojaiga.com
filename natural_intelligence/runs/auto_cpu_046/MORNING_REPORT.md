# NI overnight report (2026-11-17 12:13)

- run: `auto_cpu_046`  cycles completed: **266**  rounds: **266**  elapsed: 2.05 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/graph/ogbg_molhiv | 266 | 0.954 | 0.971 | 0.964 | 0.967 | 0.970 | 0.968 | 0.970 | 0.965 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/graph/ogbg_molhiv | 260 | 0.867 | 0.815 | 0.008 | 0.091 | 0.955 | 0.953 | 0.952 | 0.997 | 0.947 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/graph/ogbg_molhiv | 0.041 | 0.346 | 0.165 | 0.944 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/graph/ogbg_molhiv | 0.909 | 0.954 | 0.949 | 1.000 |

### Inner net on its permanent hold-out (n=84602), after 419886 outcome records
- inner: AUC 0.868, ECE 0.003, Brier 0.025, acc@80% 0.986
- raw outer vote confidence: AUC 0.817, ECE 0.088, Brier 0.049, acc@80% 0.982
- base rate of outer being right: 0.954

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
