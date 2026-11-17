# NI overnight report (2026-11-07 13:20)

- run: `restart_image_1107_0924`  cycles completed: **330**  rounds: **331**  elapsed: 3.93 h  status: **cycle 330 phase 3 image/cifar10**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **0.49 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| image/cifar10 | 331 | 0.683 | 0.657 | 0.415 | 0.680 | 0.581 | 0.521 | 0.680 | 0.100 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| image/cifar10 | 330 | 0.833 | 0.807 | 0.020 | 0.045 | 0.826 | 0.810 | 0.681 | 0.685 | 0.863 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| image/cifar10 | 0.400 | 0.535 | 0.410 | 0.653 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| image/cifar10 | 0.961 | 0.683 | 0.819 | 0.959 |

### Inner net on its permanent hold-out (n=598628), after 3000000 outcome records
- inner: AUC 0.834, ECE 0.004, Brier 0.152, acc@80% 0.775
- raw outer vote confidence: AUC 0.807, ECE 0.040, Brier 0.165, acc@80% 0.765
- base rate of outer being right: 0.682

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
