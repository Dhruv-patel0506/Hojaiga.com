# NI overnight report (2026-11-17 19:51)

- run: `auto_gpu_005`  cycles completed: **282**  rounds: **282**  elapsed: 2.05 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/text/imdb | 282 | 0.808 | 0.812 | 0.784 | 0.794 | 0.782 | 0.768 | 0.794 | 0.500 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/text/imdb | 273 | 0.808 | 0.773 | 0.021 | 0.043 | 0.854 | 0.843 | 0.811 | 0.892 | 0.910 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/text/imdb | 0.323 | 0.616 | 0.543 | 0.729 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/text/imdb | 0.964 | 0.808 | 0.854 | 1.000 |

### Inner net on its permanent hold-out (n=66709), after 330156 outcome records
- inner: AUC 0.809, ECE 0.009, Brier 0.122, acc@80% 0.882
- raw outer vote confidence: AUC 0.769, ECE 0.039, Brier 0.134, acc@80% 0.868
- base rate of outer being right: 0.811

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
