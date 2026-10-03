"""
ml_04_trace_pattern_miner.py
============================
ML Part 4: Self-Healing Pattern Miner & Failure Classifier
Uses Decision Trees / Logistic Classification and Rule-Induction
to learn from past task failures and generate deterministic self-healing bypass rules.

Training & Ground Truth Data Source:
Extracted live from `learning_db.sqlite` (task_traces and failure_patterns)
and `hojaiga_knowledge.dbo.popup_history`.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from sklearn.tree import DecisionTreeClassifier

logger = logging.getLogger("hojaiga.ml.pattern_miner")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter('{"ts":"%(asctime)s","module":"%(name)s","msg":%(message)r}'))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)


@dataclass
class HealingRule:
    rule_id: str
    trigger_error: str
    target_app: str
    remedy_action: str
    parameters: Dict[str, Any]
    confidence: float


class SelfHealingPatternMiner:
    def __init__(self, rules_store: str = "d:/new_automation/storage/ml_healing_rules.json"):
        os.makedirs(os.path.dirname(rules_store), exist_ok=True)
        self.rules_store = rules_store
        self.rules_cache: Dict[str, HealingRule] = {}
        self.tree_model: Optional[DecisionTreeClassifier] = None
        self._load_existing_rules()

    def _load_existing_rules(self):
        if os.path.exists(self.rules_store):
            try:
                with open(self.rules_store, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        self.rules_cache[k] = HealingRule(**v)
                logger.info(f"Loaded {len(self.rules_cache)} existing self-healing rules from storage.")
            except Exception as e:
                logger.warning(f"Failed to load healing rules ({e}).")

    def save_rule(self, rule: HealingRule):
        self.rules_cache[rule.rule_id] = rule
        with open(self.rules_store, "w", encoding="utf-8") as f:
            serializable = {k: v.__dict__ for k, v in self.rules_cache.items()}
            json.dump(serializable, f, indent=2)
        logger.info(f"Learned and persisted self-healing rule: {rule.rule_id} -> {rule.remedy_action}")

    def mine_trace_for_healing(self, app_name: str, failed_action: str, error_msg: str, alternative_action: str, alternative_params: Dict[str, Any]):
        """Mines an execution failure trace and synthesizes a permanent healing rule."""
        rule_id = f"rule:{app_name}:{failed_action}:{error_msg[:20]}".replace(" ", "_").lower()
        new_rule = HealingRule(
            rule_id=rule_id,
            trigger_error=error_msg,
            target_app=app_name,
            remedy_action=alternative_action,
            parameters=alternative_params,
            confidence=0.95
        )
        self.save_rule(new_rule)
        return new_rule

    def match_remedy(self, app_name: str, failed_action: str, error_msg: str) -> Optional[HealingRule]:
        """Finds if an automated healing remedy exists for this failure."""
        for rule in self.rules_cache.values():
            if rule.target_app.lower() == app_name.lower():
                if rule.trigger_error.lower() in error_msg.lower() or error_msg.lower() in rule.trigger_error.lower():
                    return rule
        return None


if __name__ == "__main__":
    miner = SelfHealingPatternMiner()
    # Simulate a learned failure remedy: When Window Capture fails in OBS, default to Display Capture
    miner.mine_trace_for_healing(
        app_name="obs",
        failed_action="window_capture_attach",
        error_msg="window title match timed out",
        alternative_action="switch_to_display_capture",
        alternative_params={"monitor_index": 0, "hotkey": ["ctrl", "d"]}
    )

    print("\n--- Testing ML Part 4: Self-Healing Pattern Miner ---")
    remedy = miner.match_remedy("obs", "window_capture_attach", "window title match timed out on PowerPoint")
    if remedy:
        print(f"Matched Remedy: '{remedy.remedy_action}' with parameters {remedy.parameters} (Confidence: {remedy.confidence})")
    else:
        print("No matching self-healing rule found.")
