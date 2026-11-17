# NI overnight report (2026-11-07 14:09)

- run: `pair2_enc_1107_1402`  cycles completed: **2**  rounds: **12**  elapsed: 0.12 h  status: **cycle 2 phase 4 enc/audio/gtzan**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **3.07 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/audio/gtzan | 3 | 0.868 | 0.868 | 0.840 | 0.856 | 0.855 | 0.851 | 0.856 | 0.100 |
| enc/image/cifar100 | 3 | 0.839 | 0.838 | 0.744 | 0.838 | 0.802 | 0.766 | 0.838 | 0.010 |
| enc/image/tiny_imagenet | 3 | 0.817 | 0.816 | 0.747 | 0.815 | 0.787 | 0.743 | 0.815 | 0.005 |
| enc/text/dbpedia_14 | 3 | 0.976 | 0.975 | 0.940 | 0.979 | 0.931 | 0.932 | 0.979 | 0.073 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/audio/gtzan | 2 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.904 |
| enc/image/cifar100 | 2 | 0.919 | 0.879 | 0.009 | 0.198 | 0.889 | 0.884 | 0.842 | 0.926 | 0.842 |
| enc/image/tiny_imagenet | 2 | 0.917 | 0.888 | 0.012 | 0.211 | 0.895 | 0.884 | 0.811 | 0.867 | 0.807 |
| enc/text/dbpedia_14 | 2 | 0.958 | 0.929 | 0.004 | 0.211 | 0.984 | 0.982 | 0.977 | 0.990 | 0.879 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/audio/gtzan | 0.161 | 0.507 | 0.292 | 0.860 |
| enc/image/cifar100 | 0.242 | 0.511 | 0.345 | 0.793 |
| enc/image/tiny_imagenet | 0.200 | 0.506 | 0.307 | 0.810 |
| enc/text/dbpedia_14 | 0.028 | 0.553 | 0.440 | 0.732 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/audio/gtzan | 0.922 | 0.855 | 0.867 | 0.971 |
| enc/image/cifar100 | 0.803 | 0.839 | 0.890 | 0.863 |
| enc/image/tiny_imagenet | 0.785 | 0.817 | 0.897 | 0.745 |
| enc/text/dbpedia_14 | 0.790 | 0.976 | 0.862 | 0.932 |

### Inner net on its permanent hold-out (n=47313), after 234991 outcome records
- inner: AUC 0.943, ECE 0.003, Brier 0.057, acc@80% 0.978
- raw outer vote confidence: AUC 0.912, ECE 0.208, Brier 0.118, acc@80% 0.967
- base rate of outer being right: 0.881

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
