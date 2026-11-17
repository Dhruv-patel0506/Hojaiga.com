# NI overnight report (2026-11-07 15:43)

- run: `pair_enc_1107_1331`  cycles completed: **69**  rounds: **350**  elapsed: 2.19 h  status: **cycle 69 phase 4 enc/audio/esc50**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **0.98 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/audio/esc50 | 70 | 0.955 | 0.949 | 0.930 | 0.955 | 0.937 | 0.943 | 0.955 | 0.020 |
| enc/image/cifar10 | 70 | 0.909 | 0.902 | 0.827 | 0.908 | 0.877 | 0.850 | 0.908 | 0.100 |
| enc/text/20_newsgroups | 70 | 0.765 | 0.766 | 0.664 | 0.714 | 0.761 | 0.658 | 0.761 | 0.053 |
| enc/text/ag_news | 70 | 0.929 | 0.925 | 0.868 | 0.919 | 0.919 | 0.865 | 0.919 | 0.250 |
| enc/text/banking77 | 70 | 0.932 | 0.926 | 0.870 | 0.927 | 0.922 | 0.905 | 0.927 | 0.017 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/audio/esc50 | 69 | 0.895 | 0.877 | 0.037 | 0.095 | 0.958 | 0.957 | 0.953 | 0.990 | 0.934 |
| enc/image/cifar10 | 69 | 0.928 | 0.912 | 0.011 | 0.046 | 0.939 | 0.936 | 0.910 | 0.949 | 0.921 |
| enc/text/20_newsgroups | 69 | 0.903 | 0.890 | 0.030 | 0.059 | 0.815 | 0.813 | 0.759 | 0.917 | 0.896 |
| enc/text/ag_news | 69 | 0.878 | 0.868 | 0.008 | 0.047 | 0.941 | 0.940 | 0.931 | 0.980 | 0.931 |
| enc/text/banking77 | 69 | 0.926 | 0.919 | 0.022 | 0.076 | 0.950 | 0.950 | 0.937 | 0.980 | 0.927 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/audio/esc50 | 0.070 | 0.651 | 0.487 | 0.863 |
| enc/image/cifar10 | 0.140 | 0.581 | 0.461 | 0.693 |
| enc/text/20_newsgroups | 0.350 | 0.493 | 0.254 | 0.806 |
| enc/text/ag_news | 0.095 | 0.635 | 0.525 | 0.813 |
| enc/text/banking77 | 0.105 | 0.589 | 0.430 | 0.812 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/audio/esc50 | 0.909 | 0.955 | 0.914 | 0.971 |
| enc/image/cifar10 | 0.958 | 0.909 | 0.840 | 0.953 |
| enc/text/20_newsgroups | 0.948 | 0.765 | 0.886 | 0.983 |
| enc/text/ag_news | 0.955 | 0.929 | 0.904 | 0.919 |
| enc/text/banking77 | 0.931 | 0.932 | 0.895 | 0.943 |

### Inner net on its permanent hold-out (n=598522), after 3000000 outcome records
- inner: AUC 0.908, ECE 0.004, Brier 0.056, acc@80% 0.978
- raw outer vote confidence: AUC 0.894, ECE 0.048, Brier 0.061, acc@80% 0.974
- base rate of outer being right: 0.911

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
