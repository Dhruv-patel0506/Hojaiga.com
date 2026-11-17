# NI overnight report (2026-11-17 21:53)

- run: `auto_cpu_065`  cycles completed: **89**  rounds: **89**  elapsed: 2.05 h  status: **finished**
- GPU: CPU  peak VRAM seen: **0.00 / 6.0 GB**

## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)

| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |
|---|---|---|---|---|---|---|---|---|---|
| enc2/audio/birdcleftop20 | 89 | 0.064 | 0.064 | 0.063 | 0.064 | 0.059 | 0.064 | 0.064 | 0.069 |

## Inner brain (trained only on outer outcomes; judged on samples it never trains on)

| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |
|---|---|---|---|---|---|---|---|---|---|---|
| enc2/audio/birdcleftop20 | 86 | 0.498 | 0.496 | 0.007 | 0.010 | 0.060 | 0.056 | 0.066 | 0.144 | 0.695 |

### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)

| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |
|---|---|---|---|---|
| enc2/audio/birdcleftop20 | 1.000 | 0.050 | 0.063 | 0.330 |

### Four factors (last 20 rounds, mean)

| task | reliability | truthfulness | adaptability | scalability |
|---|---|---|---|---|
| enc2/audio/birdcleftop20 | 0.993 | 0.064 | 0.656 | 1.000 |

### Inner net on its permanent hold-out (n=12947), after 67093 outcome records
- inner: AUC 0.512, ECE 0.002, Brier 0.062, acc@80% 0.067
- raw outer vote confidence: AUC 0.491, ECE 0.003, Brier 0.062, acc@80% 0.066
- base rate of outer being right: 0.067

## How to read this honestly
- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.
- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.
- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).
- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed.
