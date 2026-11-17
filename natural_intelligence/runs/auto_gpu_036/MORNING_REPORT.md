# NI overnight report (2026-11-15 23:56)

- run: `auto_gpu_036`  cycles completed: **139**  rounds: **139**  elapsed: 1.02 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **1.46 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/text/yelp_polarity | 139 | 0.950 | 0.949 | 0.946 | 0.949 | 0.933 | 0.942 | 0.949 | 0.501 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/text/yelp_polarity | 136 | 0.916 | 0.901 | 0.007 | 0.022 | 0.960 | 0.960 | 0.951 | 0.979 | 0.931 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/text/yelp_polarity | 0.067 | 0.642 | 0.573 | 0.745 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/text/yelp_polarity | 0.981 | 0.950 | 0.870 | 0.878 |

### Inner net on its permanent hold-out (n=157682), after 783274 outcome records
- inner: AUC 0.916, ECE 0.002, Brier 0.036, acc@80% 0.991
- raw outer vote confidence: AUC 0.902, ECE 0.019, Brier 0.037, acc@80% 0.990
- base rate of outer being right: 0.951

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
