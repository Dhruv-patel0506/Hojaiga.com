# NI overnight report (2026-11-15 19:30)

- run: `auto_gpu_012`  cycles completed: **117**  rounds: **117**  elapsed: 1.00 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **0.98 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/text/yelp_polarity | 118 | 0.874 | 0.868 | 0.863 | 0.873 | 0.818 | 0.847 | 0.873 | 0.501 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/text/yelp_polarity | 113 | 0.839 | 0.826 | 0.010 | 0.015 | 0.900 | 0.898 | 0.872 | 0.921 | 0.914 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/text/yelp_polarity | 0.193 | 0.642 | 0.589 | 0.669 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/text/yelp_polarity | 0.989 | 0.874 | 0.829 | 0.919 |

### Inner net on its permanent hold-out (n=181615), after 903686 outcome records
- inner: AUC 0.838, ECE 0.005, Brier 0.091, acc@80% 0.935
- raw outer vote confidence: AUC 0.825, ECE 0.013, Brier 0.093, acc@80% 0.932
- base rate of outer being right: 0.871

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
