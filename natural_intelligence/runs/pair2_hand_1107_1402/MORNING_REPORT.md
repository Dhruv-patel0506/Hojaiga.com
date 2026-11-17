# NI overnight report (2026-11-07 17:03)

- run: `pair2_hand_1107_1402`  cycles completed: **41**  rounds: **203**  elapsed: 3.01 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| hand/audio/gtzan | 40 | 0.689 | 0.662 | 0.472 | 0.683 | 0.564 | 0.649 | 0.683 | 0.100 |
| hand/graph/aids | 41 | 0.991 | 0.992 | 0.530 | 0.991 | 0.991 | 0.987 | 0.991 | 0.800 |
| hand/image/cifar100 | 41 | 0.375 | 0.371 | 0.182 | 0.366 | 0.305 | 0.242 | 0.366 | 0.010 |
| hand/image/tiny_imagenet | 40 | 0.207 | 0.187 | 0.098 | 0.202 | 0.122 | 0.109 | 0.202 | 0.005 |
| hand/text/dbpedia_14 | 41 | 0.942 | 0.954 | 0.853 | 0.937 | 0.897 | 0.603 | 0.937 | 0.073 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| hand/audio/gtzan | 39 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.848 |
| hand/graph/aids | 40 | 0.992 | 0.995 | 0.009 | 0.052 | 0.996 | 0.996 | 0.994 | 0.994 | 0.955 |
| hand/image/cifar100 | 40 | 0.828 | 0.789 | 0.018 | 0.049 | 0.745 | 0.693 | 0.374 | 0.312 | 0.782 |
| hand/image/tiny_imagenet | 39 | 0.775 | 0.760 | 0.015 | 0.047 | 0.649 | 0.609 | 0.209 | 0.109 | 0.738 |
| hand/text/dbpedia_14 | 40 | 0.960 | 0.934 | 0.007 | 0.122 | 0.965 | 0.957 | 0.941 | 0.967 | 0.908 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| hand/audio/gtzan | 0.481 | 0.530 | 0.413 | 0.612 |
| hand/graph/aids | 0.007 | 0.172 | 0.523 | 0.754 |
| hand/image/cifar100 | 0.333 | 0.369 | 0.196 | 0.568 |
| hand/image/tiny_imagenet | 0.200 | 0.274 | 0.128 | 0.539 |
| hand/text/dbpedia_14 | 0.075 | 0.479 | 0.372 | 0.660 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| hand/audio/gtzan | 0.945 | 0.689 | 0.724 | 1.000 |
| hand/graph/aids | 0.954 | 0.991 | 0.868 | 1.000 |
| hand/image/cifar100 | 0.951 | 0.375 | 0.777 | 1.000 |
| hand/image/tiny_imagenet | 0.955 | 0.207 | 0.762 | 1.000 |
| hand/text/dbpedia_14 | 0.877 | 0.942 | 0.826 | 1.000 |

### Inner net on its permanent hold-out (n=601059), after 3000000 outcome records
- inner: AUC 0.934, ECE 0.004, Brier 0.096, acc@80% 0.651
- raw outer vote confidence: AUC 0.922, ECE 0.095, Brier 0.121, acc@80% 0.648
- base rate of outer being right: 0.535

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
