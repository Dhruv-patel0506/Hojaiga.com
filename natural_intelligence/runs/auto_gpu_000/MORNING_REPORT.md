# NI overnight report (2026-11-15 23:16)

- run: `auto_gpu_000`  cycles completed: **201**  rounds: **782**  elapsed: 1.01 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **0.65 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/audio/esc50 | 189 | 0.954 | 0.954 | 0.950 | 0.953 | 0.937 | 0.945 | 0.953 | 0.020 |
| enc/audio/gtzan | 195 | 0.859 | 0.859 | 0.857 | 0.857 | 0.836 | 0.848 | 0.857 | 0.100 |
| enc/image/cifar10 | 200 | 0.907 | 0.902 | 0.881 | 0.906 | 0.877 | 0.867 | 0.906 | 0.100 |
| enc/text/20_newsgroups | 204 | 0.768 | 0.748 | 0.686 | 0.720 | 0.765 | 0.680 | 0.765 | 0.053 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/audio/esc50 | 173 | 0.914 | 0.920 | 0.037 | 0.039 | 0.962 | 0.960 | 0.957 | 0.992 | 0.957 |
| enc/audio/gtzan | 179 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.907 |
| enc/image/cifar10 | 184 | 0.926 | 0.904 | 0.017 | 0.031 | 0.937 | 0.933 | 0.908 | 0.947 | 0.927 |
| enc/text/20_newsgroups | 188 | 0.894 | 0.878 | 0.038 | 0.088 | 0.815 | 0.814 | 0.765 | 0.925 | 0.888 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/audio/esc50 | 0.059 | 0.623 | 0.493 | 0.848 |
| enc/audio/gtzan | 0.208 | 0.513 | 0.411 | 0.848 |
| enc/image/cifar10 | 0.154 | 0.593 | 0.466 | 0.711 |
| enc/text/20_newsgroups | 0.365 | 0.504 | 0.285 | 0.831 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/audio/esc50 | 0.974 | 0.955 | 0.895 | 0.990 |
| enc/audio/gtzan | 0.916 | 0.858 | 0.880 | 0.978 |
| enc/image/cifar10 | 0.974 | 0.907 | 0.850 | 0.946 |
| enc/text/20_newsgroups | 0.914 | 0.769 | 0.898 | 0.979 |

### Inner net on its permanent hold-out (n=21198), after 107114 outcome records
- inner: AUC 0.924, ECE 0.006, Brier 0.067, acc@80% 0.966
- raw outer vote confidence: AUC 0.891, ECE 0.031, Brier 0.077, acc@80% 0.957
- base rate of outer being right: 0.874

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
