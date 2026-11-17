# NI overnight report (2026-11-07 15:42)

- run: `pair2_enc2_1107_1422`  cycles completed: **64**  rounds: **195**  elapsed: 1.34 h  status: **cycle 64 phase 4 enc/audio/gtzan**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **1.65 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc/audio/gtzan | 65 | 0.859 | 0.862 | 0.828 | 0.857 | 0.842 | 0.842 | 0.857 | 0.100 |
| enc/image/cifar100 | 65 | 0.841 | 0.838 | 0.745 | 0.839 | 0.802 | 0.764 | 0.839 | 0.010 |
| enc/text/dbpedia_14 | 65 | 0.979 | 0.975 | 0.939 | 0.978 | 0.931 | 0.931 | 0.978 | 0.073 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc/audio/gtzan | 64 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.917 |
| enc/image/cifar100 | 64 | 0.914 | 0.890 | 0.014 | 0.073 | 0.898 | 0.892 | 0.843 | 0.910 | 0.876 |
| enc/text/dbpedia_14 | 64 | 0.949 | 0.934 | 0.005 | 0.082 | 0.984 | 0.983 | 0.979 | 0.990 | 0.920 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc/audio/gtzan | 0.208 | 0.533 | 0.388 | 0.864 |
| enc/image/cifar100 | 0.241 | 0.530 | 0.371 | 0.691 |
| enc/text/dbpedia_14 | 0.027 | 0.608 | 0.533 | 0.683 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc/audio/gtzan | 0.942 | 0.859 | 0.881 | 0.981 |
| enc/image/cifar100 | 0.930 | 0.841 | 0.840 | 0.863 |
| enc/text/dbpedia_14 | 0.918 | 0.979 | 0.840 | 0.932 |

### Inner net on its permanent hold-out (n=601321), after 3000000 outcome records
- inner: AUC 0.949, ECE 0.001, Brier 0.040, acc@80% 0.993
- raw outer vote confidence: AUC 0.921, ECE 0.101, Brier 0.059, acc@80% 0.987
- base rate of outer being right: 0.927

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
