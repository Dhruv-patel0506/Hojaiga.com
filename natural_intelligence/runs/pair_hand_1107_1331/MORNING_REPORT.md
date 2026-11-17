# NI overnight report (2026-11-07 14:09)

- run: `pair_hand_1107_1331`  cycles completed: **14**  rounds: **105**  elapsed: 0.63 h  status: **cycle 14 phase 4 hand/audio/esc50**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **3.54 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| hand/audio/esc50 | 15 | 0.556 | 0.532 | 0.391 | 0.564 | 0.455 | 0.536 | 0.564 | 0.020 |
| hand/graph/imdb_binary | 15 | 0.714 | 0.713 | 0.711 | 0.718 | 0.707 | 0.707 | 0.718 | 0.500 |
| hand/graph/ogbg_molhiv | 15 | 0.966 | 0.967 | 0.558 | 0.967 | 0.968 | 0.965 | 0.968 | 0.965 |
| hand/image/cifar10 | 15 | 0.683 | 0.658 | 0.413 | 0.680 | 0.580 | 0.522 | 0.680 | 0.100 |
| hand/text/20_newsgroups | 15 | 0.590 | 0.585 | 0.446 | 0.473 | 0.537 | 0.202 | 0.537 | 0.053 |
| hand/text/ag_news | 15 | 0.894 | 0.887 | 0.773 | 0.827 | 0.887 | 0.510 | 0.887 | 0.250 |
| hand/text/banking77 | 15 | 0.801 | 0.665 | 0.479 | 0.828 | 0.600 | 0.506 | 0.828 | 0.017 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| hand/audio/esc50 | 14 | 0.764 | 0.757 | 0.117 | 0.160 | 0.677 | 0.665 | 0.562 | 0.690 | 0.802 |
| hand/graph/imdb_binary | 14 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.876 |
| hand/graph/ogbg_molhiv | 14 | 0.785 | 0.783 | 0.009 | 0.050 | 0.968 | 0.968 | 0.966 | 0.997 | 0.956 |
| hand/image/cifar10 | 14 | 0.826 | 0.800 | 0.023 | 0.123 | 0.817 | 0.804 | 0.686 | 0.705 | 0.838 |
| hand/text/20_newsgroups | 14 | 0.862 | 0.832 | 0.037 | 0.251 | 0.742 | 0.725 | 0.599 | 0.733 | 0.760 |
| hand/text/ag_news | 14 | 0.863 | 0.828 | 0.010 | 0.133 | 0.915 | 0.912 | 0.893 | 0.959 | 0.866 |
| hand/text/banking77 | 14 | 0.916 | 0.903 | 0.031 | 0.218 | 0.880 | 0.877 | 0.817 | 0.900 | 0.780 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| hand/audio/esc50 | 0.686 | 0.501 | 0.317 | 0.663 |
| hand/graph/imdb_binary | 0.544 | 0.597 | 0.569 | 0.798 |
| hand/graph/ogbg_molhiv | 0.020 | 0.539 | 0.530 | 0.887 |
| hand/image/cifar10 | 0.399 | 0.534 | 0.408 | 0.678 |
| hand/text/20_newsgroups | 0.599 | 0.440 | 0.284 | 0.667 |
| hand/text/ag_news | 0.139 | 0.595 | 0.449 | 0.780 |
| hand/text/banking77 | 0.255 | 0.475 | 0.336 | 0.696 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| hand/audio/esc50 | 0.883 | 0.558 | 0.775 | 0.989 |
| hand/graph/imdb_binary | 0.933 | 0.713 | 0.858 | 0.997 |
| hand/graph/ogbg_molhiv | 0.953 | 0.966 | 0.939 | 0.966 |
| hand/image/cifar10 | 0.879 | 0.685 | 0.828 | 0.966 |
| hand/text/20_newsgroups | 0.759 | 0.590 | 0.821 | 0.915 |
| hand/text/ag_news | 0.865 | 0.894 | 0.887 | 0.813 |
| hand/text/banking77 | 0.787 | 0.811 | 0.806 | 0.705 |

### Inner net on its permanent hold-out (n=221717), after 1107275 outcome records
- inner: AUC 0.894, ECE 0.005, Brier 0.088, acc@80% 0.934
- raw outer vote confidence: AUC 0.858, ECE 0.132, Brier 0.122, acc@80% 0.920
- base rate of outer being right: 0.832

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
