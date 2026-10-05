"""
ml_02_path_bandit.py
====================
ML Part 2: Reinforcement Learning & Path Reliability Bandit
Uses Upper Confidence Bound (UCB1) and Exponential Moving Average (EMA)
to continuously learn whether a click, hotkey, or shortcut is most reliable for any action.

Training & Ground Truth Data Source:
Extracted live from execution feedback logs and stored in SQLite `storage/learning_bandit.sqlite`.
"""

from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("hojaiga.ml.bandit")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter('{"ts":"%(asctime)s","module":"%(name)s","msg":%(message)r}'))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)


@dataclass
class PathwayDecision:
    pathway_id: str
    action_type: str
    predicted_score: float
    exploration_bonus: float
    total_score: float


class PathReliabilityBandit:
    def __init__(self, db_path: str = "d:/new_automation/storage/learning_bandit.sqlite", alpha: float = 0.25):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.alpha = alpha
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_tables()

    def _init_tables(self):
        with self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS action_pathways (
                    pathway_id TEXT PRIMARY KEY,
                    app_name TEXT,
                    target_action TEXT,
                    action_type TEXT,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    ema_score REAL DEFAULT 0.5,
                    last_coords_json TEXT,
                    updated_at REAL
                )
            """)

    def record_feedback(self, app_name: str, target_action: str, action_type: str, success: bool, coords: Optional[Dict[str, Any]] = None):
        """Reinforcement update step: updates EMA score and success counters."""
        pathway_id = f"{app_name}:{target_action}:{action_type}".lower()
        now = time.time()
        with self._conn:
            cur = self._conn.cursor()
            cur.execute("SELECT success_count, failure_count, ema_score FROM action_pathways WHERE pathway_id = ?", (pathway_id,))
            row = cur.fetchone()
            if row:
                s_cnt, f_cnt, cur_ema = row
                new_s = s_cnt + (1 if success else 0)
                new_f = f_cnt + (0 if success else 1)
                reward = 1.0 if success else 0.0
                new_ema = cur_ema * (1.0 - self.alpha) + reward * self.alpha
                cur.execute("""
                    UPDATE action_pathways
                    SET success_count = ?, failure_count = ?, ema_score = ?, last_coords_json = ?, updated_at = ?
                    WHERE pathway_id = ?
                """, (new_s, new_f, new_ema, json.dumps(coords or {}), now, pathway_id))
            else:
                s_cnt = 1 if success else 0
                f_cnt = 0 if success else 1
                init_ema = 0.8 if success else 0.2
                cur.execute("""
                    INSERT INTO action_pathways (pathway_id, app_name, target_action, action_type, success_count, failure_count, ema_score, last_coords_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (pathway_id, app_name.lower(), target_action.lower(), action_type.lower(), s_cnt, f_cnt, init_ema, json.dumps(coords or {}), now))
        logger.info(f"Bandit updated {pathway_id} -> success={success}")

    def select_best_pathway(self, app_name: str, target_action: str, candidate_methods: List[str]) -> PathwayDecision:
        """Uses UCB1 Multi-Armed Bandit algorithm to select the best action method
        while balancing exploration of newly discovered methods."""
        with self._conn:
            cur = self._conn.cursor()
            cur.execute("""
                SELECT pathway_id, action_type, ema_score, (success_count + failure_count)
                FROM action_pathways
                WHERE app_name = ? AND target_action = ?
            """, (app_name.lower(), target_action.lower()))
            rows = {r[1]: (r[0], float(r[2]), int(r[3])) for r in cur.fetchall()}

        total_trials = sum(r[2] for r in rows.values()) or 1
        best_decision: Optional[PathwayDecision] = None
        highest_ucb = -1.0

        for method in candidate_methods:
            method_key = method.lower()
            if method_key in rows:
                p_id, ema, pulls = rows[method_key]
                # UCB1 exploration term
                bonus = math.sqrt((2 * math.log(max(1, total_trials))) / max(1, pulls))
                ucb_val = ema + 0.2 * bonus
            else:
                p_id = f"{app_name}:{target_action}:{method_key}".lower()
                ema = 0.5
                bonus = 1.0  # High curiosity for untried options
                ucb_val = 1.5

            if ucb_val > highest_ucb:
                highest_ucb = ucb_val
                best_decision = PathwayDecision(
                    pathway_id=p_id,
                    action_type=method_key,
                    predicted_score=round(ema, 3),
                    exploration_bonus=round(bonus, 3),
                    total_score=round(ucb_val, 3)
                )

        return best_decision or PathwayDecision(
            pathway_id=f"{app_name}:{target_action}:{candidate_methods[0]}",
            action_type=candidate_methods[0],
            predicted_score=0.5,
            exploration_bonus=0.0,
            total_score=0.5
        )


if __name__ == "__main__":
    bandit = PathReliabilityBandit()
    # Simulate RL feedback
    bandit.record_feedback("obs", "start_recording", "ui_click", success=True)
    bandit.record_feedback("obs", "start_recording", "ui_click", success=True)
    bandit.record_feedback("obs", "start_recording", "hotkey", success=False)
    
    decision = bandit.select_best_pathway("obs", "start_recording", ["ui_click", "hotkey", "system_tray"])
    print("\n--- Testing ML Part 2: Pathway Bandit Decision ---")
    print(f"Optimal Chosen Pathway: {decision.action_type} (Score: {decision.predicted_score}, UCB: {decision.total_score})")
