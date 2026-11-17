# NI overnight report (2026-11-16 02:19)

- run: `auto_gpu_041`  cycles completed: **160**  rounds: **161**  elapsed: 0.15 h  status: **cycle 160 phase 1 enc/text/amazon_polarity**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **1.16 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/text/amazon_polarity | 161 | 0.877 | 0.871 | 0.862 | 0.876 | 0.808 | 0.841 | 0.876 | 0.502 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/text/amazon_polarity | 157 | 0.833 | 0.821 | 0.009 | 0.013 | 0.914 | 0.912 | 0.879 | 0.900 | 0.910 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/text/amazon_polarity | 0.166 | 0.649 | 0.605 | 0.639 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/text/amazon_polarity | 0.991 | 0.877 | 0.815 | 0.903 |

### Inner net on its permanent hold-out (n=29113), after 143589 outcome records
- inner: AUC 0.823, ECE 0.008, Brier 0.089, acc@80% 0.937
- raw outer vote confidence: AUC 0.811, ECE 0.007, Brier 0.090, acc@80% 0.934
- base rate of outer being right: 0.879

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
