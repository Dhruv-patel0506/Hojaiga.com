# NI overnight report (2026-11-17 21:53)

- run: `auto_cpu_004`  cycles completed: **175**  rounds: **520**  elapsed: 2.03 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| hand/graph/aids | 175 | 0.996 | 0.996 | 0.983 | 0.992 | 0.990 | 0.996 | 0.996 | 0.800 |
| hand/graph/imdb_binary | 177 | 0.720 | 0.718 | 0.721 | 0.717 | 0.702 | 0.718 | 0.721 | 0.500 |
| hand/graph/ogbg_molhiv | 171 | 0.932 | 0.967 | 0.963 | 0.959 | 0.968 | 0.965 | 0.968 | 0.965 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| hand/graph/aids | 168 | 0.989 | 0.980 | 0.004 | 0.007 | 0.998 | 0.998 | 0.998 | 1.000 | 0.987 |
| hand/graph/imdb_binary | 169 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.873 |
| hand/graph/ogbg_molhiv | 164 | 0.880 | 0.808 | 0.009 | 0.092 | 0.960 | 0.945 | 0.933 | 0.968 | 0.897 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| hand/graph/aids | 0.004 | 0.807 | 0.889 | 0.866 |
| hand/graph/imdb_binary | 0.556 | 0.626 | 0.521 | 0.779 |
| hand/graph/ogbg_molhiv | 0.062 | 0.329 | 0.169 | 0.597 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| hand/graph/aids | 0.993 | 0.996 | 0.949 | 1.000 |
| hand/graph/imdb_binary | 0.925 | 0.721 | 0.844 | 1.000 |
| hand/graph/ogbg_molhiv | 0.910 | 0.932 | 0.728 | 1.000 |

### Inner net on its permanent hold-out (n=47653), after 238106 outcome records
- inner: AUC 0.905, ECE 0.004, Brier 0.031, acc@80% 0.985
- raw outer vote confidence: AUC 0.826, ECE 0.085, Brier 0.071, acc@80% 0.969
- base rate of outer being right: 0.929

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
