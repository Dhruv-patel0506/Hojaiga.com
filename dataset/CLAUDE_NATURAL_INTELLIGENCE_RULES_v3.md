# CLAUDE CODE RULES & ARCHITECTURE DIRECTORY (v3)
## SYSTEM NAME: NATURAL INTELLIGENCE (NI) DUAL-BRAIN META-CONTROLLER

---

### 1. CORE MISSION & PROBLEM DEFINITION
Current Machine Learning models suffer from **monolithic predictor fragility**:
- They rely on a single predictor output without self-verification.
- If the predictor makes an error, the system propagates hallucinations.
- Training relies on static dataset splits rather than dynamic, self-questioning meta-learning.

**The Natural Intelligence Solution**:
We build a dual-brain meta-controller system designed like human cognition:
1. **Outer Brain**: Specialist multi-predictor ensemble (`Predictor_Logic`, `Predictor_Pattern`, `Predictor_Verifier`, `Predictor_Exploratory`) voting on multimodal tasks.
2. **Inner Brain**: Meta-cognitive kernel. **CRITICAL DATA FLOW RULE**: The outcomes, decisions, and execution metadata produced by the Outer Brain form the continuous **TRAINING DATASET** for the Inner Brain.
3. **Inner Brain Self-Reasoning**: The Inner Brain ingests the Outer Brain dataset stream, initiates human-like self-questioning probes, distinguishes multiple dynamic factors (Reliability, Scalability, Adaptability, Truthfulness), and invokes JEV / developer execution tools to stress-test outcomes.

---

### 2. DUAL-BRAIN PIPELINE DATA FLOW ARCHITECTURE

```
+-----------------------------------------------------------------------------------+
|                            MULTIMODAL WEB STREAM                                  |
|         [Text (FineWeb)] -> [Graph (OGB)] -> [Vision (LAION)] -> [Audio]          |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                 OUTER BRAIN                                       |
|  - Multi-Predictor Voting Ensemble (Logic, Pattern, Verifier, Exploratory)        |
|  - Generates Candidate Predictions, Voting Consensus, & Action Logs               |
+-----------------------------------------------------------------------------------+
                                          |
                        CONTINUOUS OUTCOME STREAM DATASET
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                 INNER BRAIN                                       |
|  - Continuous Training Input: Ingests Outer Brain Outcomes                        |
|  - Human-Like Self-Questioning & Reasoning Probes                                 |
|  - Distinguishes Multi-Factor Scores (Reliability, Scalability, Adaptability)     |
|  - JEV / Developer Execution Tools Verification Sandbox                           |
+-----------------------------------------------------------------------------------+
                                          |
                              META-FEEDBACK ADJUSTMENTS
                                          v
                         [Outer Brain Weight Updates]
```

---

### 3. HARDWARE & CURRICULUM BOUNDS (RTX 3060 - 6GB VRAM)

- **Curriculum Training Order (Easiest to Toughest)**:
  - **Phase 1: TEXT** (~2.45 GB VRAM) — FineWeb / RedPajama symbolic reasoning.
  - **Phase 2: GRAPH** (~2.95 GB VRAM) — OGB Papers100M knowledge topology.
  - **Phase 3: IMAGE** (~4.15 GB VRAM) — Frozen CLIP/MobileNet feature projections.
  - **Phase 4: AUDIO** (~4.75 GB VRAM) — Whisper-tiny acoustic spectrograms.
  - **Phase 5: VIDEO** (~5.45 GB VRAM) — Subsampled temporal frame fusion.

- **VRAM Enforcement**:
  - 4-bit NF4 Quantization via `bitsandbytes`.
  - QLoRA Adapter Matrices ($r=8, \alpha=16$).
  - Micro-batch size = 1, Gradient Accumulation = 16 steps.
  - Automatic `torch.cuda.empty_cache()` between curriculum phase shifts.

---

### 4. DYNAMIC 70/30 ROTATIONAL DATASET ENGINE
- Dynamic hash window generator shifts random seed per epoch.
- 70% Train / 30% Validation split continuously rotates to prevent dataset alignment or memorization.

---

### 5. TERMINAL LAUNCH INSTRUCTIONS FOR CLAUDE CODE

To initiate training directly in the terminal, execute:
```bash
python3 train_natural_intelligence_v2.py --mode dual-pipeline --vram-limit 6.0
```
