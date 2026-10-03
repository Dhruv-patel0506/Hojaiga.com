"""
ml_master_orchestrator.py
=========================
Master Integrator uniting all 4 Machine Learning components:
1. Semantic UI Matcher (ml_01_semantic_matcher)
2. Path Reliability Bandit (ml_02_path_bandit)
3. Visual Presentation Detector (ml_03_visual_detector)
4. Self-Healing Pattern Miner (ml_04_trace_pattern_miner)

Acts as the high-speed co-pilot to Ollama Llama 3 during autonomous execution.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ml_01_semantic_matcher import SemanticUIMatcher, ControlCandidate
from ml_02_path_bandit import PathReliabilityBandit, PathwayDecision
from ml_03_visual_detector import VisualPresentationDetector
from ml_04_trace_pattern_miner import SelfHealingPatternMiner, HealingRule

logger = logging.getLogger("hojaiga.ml.master")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter('{"ts":"%(asctime)s","module":"%(name)s","msg":%(message)r}'))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)


class HojaigaMLSuite:
    def __init__(self):
        logger.info("Initializing Hojaiga 4-Part ML Suite...")
        self.matcher = SemanticUIMatcher()
        self.bandit = PathReliabilityBandit()
        self.visual = VisualPresentationDetector()
        self.healer = SelfHealingPatternMiner()
        logger.info("Hojaiga 4-Part ML Suite online and ready.")

    def resolve_action(self, intent_query: str, app_name: str, available_methods: List[str] = ["ui_click", "hotkey"]) -> Dict[str, Any]:
        """Resolves the best UI control, exact coordinates, and optimal execution pathway."""
        # 1. Semantic Control Lookup (< 3ms)
        candidates = self.matcher.query_control(intent_query, app_context=app_name, top_k=1)
        matched_control = candidates[0] if candidates else None

        # 2. Path Reliability Bandit (< 1ms)
        best_path = self.bandit.select_best_pathway(app_name, intent_query, available_methods)

        return {
            "intent": intent_query,
            "app_name": app_name,
            "matched_control": matched_control.name if matched_control else None,
            "coordinates": matched_control.coords if matched_control else None,
            "match_confidence": matched_control.score if matched_control else 0.0,
            "recommended_pathway": best_path.action_type,
            "pathway_reliability_score": best_path.predicted_score
        }

    def inspect_visual_presentation(self, frame_bgr: np.ndarray) -> Dict[str, Any]:
        """Runs fast visual perception check for active presentation slides."""
        return self.visual.detect_active_presentation_slide(frame_bgr)

    def recover_from_failure(self, app_name: str, failed_action: str, error_msg: str) -> Optional[HealingRule]:
        """Queries self-healing pattern miner for known automated workarounds."""
        return self.healer.match_remedy(app_name, failed_action, error_msg)


if __name__ == "__main__":
    suite = HojaigaMLSuite()
    print("\n--- Testing End-to-End Integrated ML Suite ---")
    action_plan = suite.resolve_action("start recording", "obs", ["ui_click", "hotkey"])
    print("Resolved Action Plan:\n", action_plan)
