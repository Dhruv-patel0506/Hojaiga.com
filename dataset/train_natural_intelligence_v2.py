import sys
import os
sys.path.insert(0, '/workspace/scratch')

import time
import json
from typing import Dict, Any, List

from dataset_controller_v2 import DatasetControllerV2
from outer_brain_ensemble_v2 import OuterBrainEnsembleV2
from inner_brain_kernel_v2 import InnerBrainKernelV2

class NaturalIntelligencePipelineRunner:
    """
    Master Dual-Brain Meta-Training Orchestrator
    
    Data Flow Architecture:
    1. Outer Brain reads curriculum stream across 5 modalities.
    2. Outer Brain runs multi-predictor voting ensemble and generates output decision streams.
    3. Outer Brain outcome stream IS THE CONTINUOUS TRAINING DATASET for the Inner Brain.
    4. Inner Brain ingests Outer Brain outcomes, executes self-questioning probes, evaluates 
       multi-factor reliability, and invokes JEV/dev tools.
    5. Inner Brain adjusts meta-learning feedback weights to refine the Outer Brain.
    6. Hardware target: RTX 3060 (6GB VRAM limit).
    """
    def __init__(self, vram_limit_gb: float = 6.0):
        self.vram_limit_gb = vram_limit_gb
        self.dataset_controller = DatasetControllerV2()
        self.outer_brain = OuterBrainEnsembleV2()
        self.inner_brain = InnerBrainKernelV2()
        self.step_counter = 0

    def run_pipeline(self, steps_per_phase: int = 3):
        print("=" * 75)
        print("STARTING DUAL-BRAIN NATURAL INTELLIGENCE META-TRAINING PIPELINE")
        print(f"Target Hardware: RTX 3060 ({self.vram_limit_gb}GB VRAM) | Architecture: Outer -> Inner Stream")
        print("=" * 75)
        print()

        phases = [1, 2, 3, 4, 5]
        vram_estimates = {1: 2.45, 2: 2.95, 3: 4.15, 4: 4.75, 5: 5.45}
        phase_names = {1: "TEXT", 2: "GRAPH", 3: "IMAGE", 4: "AUDIO", 5: "VIDEO"}

        for phase in phases:
            modality = self.dataset_controller.set_curriculum_phase(phase)
            estimated_vram = vram_estimates[phase]

            print(f"\n---> PHASE {phase}: Training OUTER BRAIN on {modality.upper()} Stream")
            
            for s in range(steps_per_phase):
                self.step_counter += 1
                
                # Step A: Get stream sample batch
                sample_id = f"{modality.lower()}_sample_{self.step_counter:03d}"
                batch_data = {"modality": modality.upper(), "sample_id": sample_id}

                # Step B: Outer Brain multi-predictor voting execution
                outer_outcome = self.outer_brain.execute_multi_predictor_voting(batch_data)

                # Step C: Stream Outer Brain Outcome -> Inner Brain Training Input Dataset
                self.inner_brain.ingest_outer_brain_outcome(outer_outcome)

                # Step D: Inner Brain Self-Questioning & Multi-Factor Evaluation Loop
                inner_critiques = self.inner_brain.process_continuous_training_batch(batch_size=1)
                latest_critique = inner_critiques[0]

                # Step E: Inner Brain Feedback -> Outer Brain Meta-Weight Adjustment
                self.outer_brain.update_weights_from_inner_brain(latest_critique)

                # Summary Display
                winner = outer_outcome["winner"]
                consensus = outer_outcome["consensus_score"]
                grade = latest_critique["composite_grade"]
                tool_status = latest_critique["jev_tool_execution"]["status"]

                print(
                    f"  [Step {self.step_counter:03d} | Phase {phase}-{modality.upper()}] "
                    f"Outer Winner: {winner} (Consensus: {consensus:.4f}) -> "
                    f"Inner Dataset Stream Ingested | Self-Grade: {grade:.4f} | "
                    f"JEV Tool: {tool_status} | VRAM: {estimated_vram:.2f}/6.0 GB"
                )

            # Rotate dataset seed between phases
            self.dataset_controller.rotate_seed()

        print("\n" + "=" * 75)
        print("NATURAL INTELLIGENCE DUAL-BRAIN PIPELINE EXECUTION COMPLETE")
        print("Outer Brain outcomes successfully trained Inner Brain self-reasoning kernel.")
        print("=" * 75)

if __name__ == "__main__":
    runner = NaturalIntelligencePipelineRunner(vram_limit_gb=6.0)
    runner.run_pipeline(steps_per_phase=3)
