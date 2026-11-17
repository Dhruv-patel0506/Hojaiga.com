# NI overnight report (2026-11-07 02:25)

- run: `smoke1`  cycles completed: **2**  rounds: **10**  elapsed: 0.01 h  status: **finished**
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU  peak VRAM seen: **0.09 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| audio/urbansound8k | 2 | 0.910 | 0.910 | 0.609 | 0.927 | 0.919 | 0.882 | 0.927 | 0.147 |
| graph/mutag | 2 | 0.883 | 0.883 | 0.820 | 0.880 | 0.900 | 0.890 | 0.900 | 0.665 |
| graph/proteins | 2 | 0.777 | 0.777 | 0.741 | 0.775 | 0.732 | 0.774 | 0.775 | 0.596 |
| image/cifar10 | 2 | 0.403 | 0.403 | 0.346 | 0.410 | 0.330 | 0.374 | 0.410 | 0.116 |
| text/ag_news | 2 | 0.731 | 0.731 | 0.591 | 0.661 | 0.744 | 0.404 | 0.744 | 0.261 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| audio/urbansound8k | 1 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.896 |
| graph/mutag | 1 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.932 |
| graph/proteins | 1 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.852 |
| image/cifar10 | 1 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.798 |
| text/ag_news | 1 | 0.825 | 0.813 | 0.151 | 0.211 | 0.778 | 0.786 | 0.733 | 0.893 | 0.840 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| audio/urbansound8k | 0.077 | 0.273 | 0.250 | 0.717 |
| graph/mutag | 0.077 | 0.250 | n/a | 0.938 |
| graph/proteins | 0.220 | 0.554 | 0.500 | 0.811 |
| image/cifar10 | 0.672 | 0.390 | 0.271 | 0.773 |
| text/ag_news | 0.297 | 0.522 | 0.328 | 0.793 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| audio/urbansound8k | 0.851 | 0.910 | 0.858 | 0.998 |
| graph/mutag | 0.914 | 0.885 | 0.959 | 0.998 |
| graph/proteins | 0.930 | 0.739 | 0.713 | 0.996 |
| image/cifar10 | 0.916 | 0.403 | 0.885 | 0.997 |
| text/ag_news | 0.806 | 0.735 | 0.876 | 0.992 |

### Inner net on its permanent hold-out (n=647), after 3156 outcome records
- inner: AUC 0.751, ECE 0.210, Brier 0.222, acc@80% 0.785
- raw outer vote confidence: AUC 0.816, ECE 0.106, Brier 0.165, acc@80% 0.810
- base rate of outer being right: 0.705

## Problems logged

- cycle 0: video/hmdb51 has too little data yet (0)
- cycle 1: video/hmdb51 has too little data yet (0)

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
