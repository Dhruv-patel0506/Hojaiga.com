# NI overnight report (2026-11-16 01:03)

- run: `auto_gpu_001`  cycles completed: **98**  rounds: **385**  elapsed: 1.02 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **1.14 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/text/ag_news | 96 | 0.927 | 0.917 | 0.894 | 0.918 | 0.923 | 0.884 | 0.923 | 0.250 |
| enc/text/banking77 | 98 | 0.932 | 0.926 | 0.890 | 0.930 | 0.922 | 0.903 | 0.930 | 0.017 |
| enc/text/dbpedia_14 | 98 | 0.978 | 0.974 | 0.966 | 0.978 | 0.945 | 0.950 | 0.978 | 0.073 |
| enc/video/hmdb51 | 93 | 0.639 | 0.627 | 0.614 | 0.632 | 0.479 | 0.548 | 0.632 | 0.081 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/text/ag_news | 91 | 0.883 | 0.876 | 0.011 | 0.026 | 0.937 | 0.936 | 0.927 | 0.980 | 0.935 |
| enc/text/banking77 | 93 | 0.931 | 0.924 | 0.021 | 0.021 | 0.953 | 0.952 | 0.937 | 0.974 | 0.950 |
| enc/text/dbpedia_14 | 93 | 0.949 | 0.939 | 0.005 | 0.006 | 0.984 | 0.983 | 0.978 | 0.990 | 0.945 |
| enc/video/hmdb51 | 88 | 0.802 | 0.786 | 0.073 | 0.085 | 0.682 | 0.678 | 0.623 | 0.865 | 0.850 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/text/ag_news | 0.097 | 0.628 | 0.529 | 0.822 |
| enc/text/banking77 | 0.098 | 0.556 | 0.441 | 0.770 |
| enc/text/dbpedia_14 | 0.026 | 0.588 | 0.513 | 0.673 |
| enc/video/hmdb51 | 0.575 | 0.488 | 0.302 | 0.806 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/text/ag_news | 0.974 | 0.927 | 0.907 | 0.905 |
| enc/text/banking77 | 0.990 | 0.932 | 0.872 | 0.979 |
| enc/text/dbpedia_14 | 0.995 | 0.978 | 0.835 | 0.928 |
| enc/video/hmdb51 | 0.933 | 0.639 | 0.854 | 0.964 |

### Inner net on its permanent hold-out (n=115282), after 573618 outcome records
- inner: AUC 0.921, ECE 0.002, Brier 0.040, acc@80% 0.989
- raw outer vote confidence: AUC 0.912, ECE 0.013, Brier 0.042, acc@80% 0.988
- base rate of outer being right: 0.940

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
