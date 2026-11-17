# NI overnight report (2026-11-17 14:40)

- run: `auto_gpu_008`  cycles completed: **402**  rounds: **403**  elapsed: 0.29 h  status: **cycle 402 phase 1 enc/text/sst2**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/text/sst2 | 362 | 0.811 | 0.815 | 0.809 | 0.800 | 0.765 | 0.801 | 0.809 | 0.516 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/text/sst2 | 354 | 0.783 | 0.764 | 0.040 | 0.052 | 0.834 | 0.829 | 0.809 | 0.930 | 0.913 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/text/sst2 | 0.335 | 0.641 | 0.559 | 0.782 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/text/sst2 | 0.963 | 0.810 | 0.869 | 1.000 |

### Inner net on its permanent hold-out (n=3694), after 20133 outcome records
- inner: AUC 0.789, ECE 0.018, Brier 0.129, acc@80% 0.876
- raw outer vote confidence: AUC 0.742, ECE 0.030, Brier 0.138, acc@80% 0.862
- base rate of outer being right: 0.808

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
