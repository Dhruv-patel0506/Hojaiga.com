# NI overnight report (2026-11-17 21:49)

- run: `auto_gpu_007`  cycles completed: **458**  rounds: **458**  elapsed: 2.05 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/text/rotten_tomatoes | 459 | 0.765 | 0.773 | 0.762 | 0.751 | 0.732 | 0.751 | 0.762 | 0.500 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/text/rotten_tomatoes | 450 | 0.746 | 0.710 | 0.043 | 0.057 | 0.803 | 0.793 | 0.769 | 0.904 | 0.904 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/text/rotten_tomatoes | 0.443 | 0.637 | 0.558 | 0.805 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/text/rotten_tomatoes | 0.957 | 0.765 | 0.889 | 1.000 |

### Inner net on its permanent hold-out (n=19707), after 102442 outcome records
- inner: AUC 0.746, ECE 0.020, Brier 0.154, acc@80% 0.827
- raw outer vote confidence: AUC 0.696, ECE 0.023, Brier 0.164, acc@80% 0.812
- base rate of outer being right: 0.767

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
