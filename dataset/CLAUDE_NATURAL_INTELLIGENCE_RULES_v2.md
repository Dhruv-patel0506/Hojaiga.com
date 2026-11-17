# Master Rule File ("Grill File"): Natural Intelligence (NI) Meta-Controller
**Target Model / Environment:** Claude / Claude Code (CLI & IDE Integration)  
**Hardware Specs & Constraints:** NVIDIA RTX 3060 (6 GB VRAM) | Local GPU Micro-Batching  
**Version:** 2.0 (Dual-Brain Architecture with Multi-Predictor Voting Ensemble)

---

## 1. System Vision & The Core Problem We Are Solving

### Current World Limitations in AI (Monolithic Predictor Fragility)
Standard machine learning models operate on passive input-to-output pattern matching:
- **Single-Predictor Failure**: Conventional models rely on a single predictor head. If that head hallucinates or makes a logical error, the entire system fails without self-correction.
- **Lack of Self-Awareness & Self-Questioning**: Traditional LLMs do not question their own output, evaluate their reliability, or stress-test logical consistency before taking action.
- **Static Dataset Overfitting**: Models trained on static data splits lose the ability to handle unexpected, real-world distribution shifts.

### Our Solution: Natural Intelligence (NI) Meta-Controller
We are constructing a **Self-Sufficient Natural Intelligence (NI) Meta-Controller** that acts as a autonomous decision engine rather than a simple orchestrator.

---

## 2. Key Architectural Highlights

### A. Dual-Brain Meta-Controller Architecture
1. **Outer Brain (Multi-Predictor Voting Ensemble)**:
   - Does **not** rely on a single predictor.
   - Operates a **Mixture-of-Agents (MoA)** consensus loop with specialist heads:
     - `Predictor_Logic`: Symbolic reasoning and formal proof checks.
     - `Predictor_Pattern`: Deep pattern recognition and neural embeddings.
     - `Predictor_Verifier`: Safety, edge-case validation, and code sanity checks.
     - `Predictor_Exploratory`: Creative hypothesis generation and out-of-distribution discovery.
   - Computes weighted majority voting based on self-reported confidence and Inner Brain quality grades.
   - Dispatches execution to developer tools (`Claude_Code_CLI`, `PyTorch_CUDA_Engine`, `PyG_Graph_Engine`, `HuggingFace_Streaming`).

2. **Inner Brain (Meta-Memory & Self-Evaluation Kernel)**:
   - **Interception & Grading**: Intercepts candidate outputs from the Outer Brain and grades them from **0.0 to 1.0** across:
     - *Reliability*: Verifiability and freedom from hallucination.
     - *Scalability*: Computational efficiency and token economy.
     - *Logical Consistency*: Structural rigor and non-contradiction.
   - **Self-Questioning Loop**: Automatically generates diagnostic critiques:
     - *"Why is this answer chosen over alternatives?"*
     - *"Under what edge cases will this specific logic fail?"*
     - *"Is the memory consumption scalable under 6GB VRAM bounds?"*
   - **Adaptive Meta-Loss Weighting**: Dynamically scales the learning rate and meta-loss penalty based on historical memory performance.

---

### B. 5-Phase Hardware-Constrained Curriculum Training (6GB VRAM Bounds)
To strictly fit within your **NVIDIA RTX 3060 (6 GB VRAM)** limit without memory overflows, training progresses from easiest to toughest:

| Phase | Modality | Primary Dataset Stream | VRAM Target | Optimization Strategy |
| :--- | :--- | :--- | :--- | :--- |
| **Phase 1** | **Text & Logic** | FineWeb / RedPajama (500M+ tokens) | ~2.5 GB | 4-bit NF4 Quantization, QLoRA ($r=8, \alpha=16$) |
| **Phase 2** | **Knowledge Graphs** | OGB Papers100M (111M nodes) | ~3.0 GB | PyTorch Geometric (PyG) Neighbor Sampling |
| **Phase 3** | **Image / Vision** | LAION-2B / OpenImages | ~4.2 GB | Frozen CLIP/MobileNetV4 visual encoder backbones |
| **Phase 4** | **Audio Spectrograms** | LibriSpeech / AudioSet | ~4.8 GB | 16kHz windowed Mel-spectrograms (Whisper-tiny) |
| **Phase 5** | **Video & Multimodal** | WebVid-10M | ~5.5 GB | Subsampled 4-frame temporal sequence micro-batches |

---

### C. Dynamic 70/30 Rotational Seed Splitting
- Uses a deterministic MD5 hash-window generator with seed rotation.
- Instead of static train/val splits, data is continuously rotated so the model receives randomized 70% train and 30% val slices across epochs.

---

### D. 6GB VRAM Optimization Constraints & Rules for Claude Code
When generating or refactoring code, Claude / Claude Code **MUST** adhere strictly to:
1. **Quantization**: Force `bitsandbytes` 4-bit NF4 quantization (`load_in_4bit=True`, `bnb_4bit_compute_dtype=torch.float16`).
2. **Adapters**: Use PEFT QLoRA matrices ($r=8, \alpha=16$, target modules: `q_proj`, `v_proj`).
3. **Micro-Batching**: Keep micro-batch size $\le 4$ and execute gradient accumulation over 16–32 steps.
4. **Cache Purging**: Invoke `torch.cuda.empty_cache()` and `gc.collect()` after every micro-step.
5. **Data Streaming**: Utilize `datasets.load_dataset(..., streaming=True)` so 500M+ web records are processed as network generators without saving full raw datasets to local disk.

---

## 3. Developer Tool Integration Rules for Claude Code

When Claude Code is working on this repository, it must:
- Read and respect `inner_brain_kernel.py`, `outer_brain_ensemble.py`, `dataset_controller_v2.py`, and `train_natural_intelligence.py`.
- Never rewrite single-predictor code paths—always maintain the **Multi-Predictor Voting Ensemble**.
- Log all Inner Brain self-questioning critiques to stdout and file logs during execution.
