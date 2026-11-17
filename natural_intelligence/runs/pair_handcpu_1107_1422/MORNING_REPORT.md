# NI overnight report (2026-11-07 17:23)

- run: `pair_handcpu_1107_1422`  cycles completed: **28**  rounds: **192**  elapsed: 3.01 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| hand/audio/esc50 | 27 | 0.571 | 0.535 | 0.399 | 0.562 | 0.460 | 0.543 | 0.562 | 0.020 |
| hand/graph/imdb_binary | 27 | 0.707 | 0.708 | 0.706 | 0.709 | 0.699 | 0.705 | 0.709 | 0.500 |
| hand/graph/ogbg_molhiv | 27 | 0.967 | 0.968 | 0.493 | 0.968 | 0.969 | 0.966 | 0.969 | 0.965 |
| hand/image/cifar10 | 27 | 0.686 | 0.658 | 0.414 | 0.680 | 0.579 | 0.522 | 0.680 | 0.100 |
| hand/text/20_newsgroups | 28 | 0.594 | 0.585 | 0.446 | 0.475 | 0.536 | 0.200 | 0.536 | 0.053 |
| hand/text/ag_news | 28 | 0.894 | 0.886 | 0.774 | 0.827 | 0.887 | 0.510 | 0.887 | 0.250 |
| hand/text/banking77 | 28 | 0.831 | 0.665 | 0.480 | 0.829 | 0.601 | 0.505 | 0.829 | 0.017 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| hand/audio/esc50 | 26 | 0.744 | 0.743 | 0.118 | 0.148 | 0.656 | 0.654 | 0.561 | 0.696 | 0.808 |
| hand/graph/imdb_binary | 26 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.870 |
| hand/graph/ogbg_molhiv | 26 | 0.784 | 0.779 | 0.008 | 0.041 | 0.970 | 0.969 | 0.968 | 0.996 | 0.967 |
| hand/image/cifar10 | 26 | 0.825 | 0.805 | 0.025 | 0.063 | 0.816 | 0.807 | 0.688 | 0.706 | 0.863 |
| hand/text/20_newsgroups | 27 | 0.859 | 0.839 | 0.035 | 0.227 | 0.747 | 0.735 | 0.600 | 0.728 | 0.783 |
| hand/text/ag_news | 27 | 0.864 | 0.820 | 0.010 | 0.088 | 0.913 | 0.911 | 0.893 | 0.964 | 0.919 |
| hand/text/banking77 | 27 | 0.906 | 0.893 | 0.030 | 0.199 | 0.896 | 0.891 | 0.834 | 0.896 | 0.856 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| hand/audio/esc50 | 0.689 | 0.509 | 0.351 | 0.663 |
| hand/graph/imdb_binary | 0.493 | 0.587 | 0.531 | 0.766 |
| hand/graph/ogbg_molhiv | 0.020 | 0.575 | 0.521 | 0.883 |
| hand/image/cifar10 | 0.400 | 0.530 | 0.415 | 0.648 |
| hand/text/20_newsgroups | 0.598 | 0.466 | 0.270 | 0.655 |
| hand/text/ag_news | 0.137 | 0.597 | 0.433 | 0.779 |
| hand/text/banking77 | 0.269 | 0.576 | 0.376 | 0.691 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| hand/audio/esc50 | 0.884 | 0.571 | 0.778 | 1.000 |
| hand/graph/imdb_binary | 0.940 | 0.707 | 0.822 | 1.000 |
| hand/graph/ogbg_molhiv | 0.963 | 0.967 | 0.938 | 1.000 |
| hand/image/cifar10 | 0.940 | 0.686 | 0.815 | 1.000 |
| hand/text/20_newsgroups | 0.779 | 0.594 | 0.810 | 1.000 |
| hand/text/ag_news | 0.910 | 0.894 | 0.887 | 1.000 |
| hand/text/banking77 | 0.807 | 0.831 | 0.831 | 1.000 |

### Inner net on its permanent hold-out (n=408776), after 2037879 outcome records
- inner: AUC 0.893, ECE 0.004, Brier 0.088, acc@80% 0.935
- raw outer vote confidence: AUC 0.855, ECE 0.110, Brier 0.116, acc@80% 0.920
- base rate of outer being right: 0.833

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
