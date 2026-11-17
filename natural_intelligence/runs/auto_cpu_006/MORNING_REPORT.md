# NI overnight report (2026-11-17 14:37)

- run: `auto_cpu_006`  cycles completed: **219**  rounds: **654**  elapsed: 0.26 h  status: **cycle 219 phase 2 enc/graph/ogbg_molhiv**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/graph/aids | 213 | 0.991 | 0.984 | 0.984 | 0.977 | 0.971 | 0.990 | 0.990 | 0.800 |
| enc/graph/imdb_binary | 215 | 0.711 | 0.705 | 0.690 | 0.680 | 0.687 | 0.707 | 0.707 | 0.500 |
| enc/graph/ogbg_molhiv | 209 | 0.950 | 0.971 | 0.963 | 0.967 | 0.970 | 0.968 | 0.970 | 0.965 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/graph/aids | 205 | 0.645 | 0.696 | 0.010 | 0.027 | 0.993 | 0.993 | 0.993 | 1.000 | 0.977 |
| enc/graph/imdb_binary | 207 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.869 |
| enc/graph/ogbg_molhiv | 201 | 0.870 | 0.789 | 0.009 | 0.085 | 0.952 | 0.949 | 0.946 | 0.993 | 0.938 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/graph/aids | 0.015 | 0.330 | 0.288 | 0.859 |
| enc/graph/imdb_binary | 0.587 | 0.634 | 0.535 | 0.764 |
| enc/graph/ogbg_molhiv | 0.046 | 0.354 | 0.176 | 0.883 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/graph/aids | 0.977 | 0.991 | 0.938 | 1.000 |
| enc/graph/imdb_binary | 0.939 | 0.710 | 0.816 | 1.000 |
| enc/graph/ogbg_molhiv | 0.914 | 0.950 | 0.903 | 1.000 |

### Inner net on its permanent hold-out (n=7988), after 39800 outcome records
- inner: AUC 0.912, ECE 0.004, Brier 0.028, acc@80% 0.987
- raw outer vote confidence: AUC 0.816, ECE 0.091, Brier 0.066, acc@80% 0.971
- base rate of outer being right: 0.930

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
