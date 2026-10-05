"""
TrajectoryReplayEngine — Historical Execution Path Miner & Replay Engine for Hojaiga OS.

Capabilities:
1. Queries historical task traces and patterns from SQLite (hojaiga_knowledge.sqlite).
2. Extracts proven, high-confidence action sequences that achieved successful outcomes.
3. Allows immediate re-execution of verified paths without re-deriving workflows from scratch.
4. Auto-saves newly discovered successful action trajectories for permanent retention.
"""

from __future__ import annotations

import os
import re
import json
import time
import sqlite3
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("trajectory_replay_engine")

DB_PATH = Path(r"D:\new_automation\storage\hojaiga_knowledge.sqlite")


class TrajectoryReplayEngine:
    """Discovers, catalogs, and provides fast-path replay of proven action sequences."""

    _instance: Optional["TrajectoryReplayEngine"] = None

    @classmethod
    def get_instance(cls) -> "TrajectoryReplayEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS action_trajectories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    intent_pattern TEXT UNIQUE,
                    description TEXT,
                    actions_json TEXT,
                    success_count INTEGER DEFAULT 1,
                    failure_count INTEGER DEFAULT 0,
                    confidence REAL DEFAULT 0.9,
                    last_used REAL
                )"""
            )
            conn.commit()

        # Seed standard reliable canonical workflows if table is empty
        self._seed_canonical_workflows()

    def _seed_canonical_workflows(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM action_trajectories").fetchone()[0]
            if count == 0:
                canonical = [
                    (
                        "lead_generation_directory",
                        "Extract leads from Google Maps/Search and compile into Excel",
                        json.dumps([
                            {"action": "NAVIGATE", "parameters": {"url": "https://www.google.com/maps"}},
                            {"action": "TYPE", "parameters": {"text": "{query}", "element": "searchbox"}},
                            {"action": "PRESS_KEY", "parameters": {"key": "Enter"}},
                            {"action": "EXTRACT_LEADS", "parameters": {"query": "{query}", "min_leads": "{min_leads}", "output_file": "{output_file}"}},
                            {"action": "LAUNCH_APP", "parameters": {"target": "excel", "file_path": "{output_file}"}}
                        ]),
                        10, 0, 0.98, time.time()
                    ),
                    (
                        "document_open_and_view",
                        "Locate and view data document or spreadsheet",
                        json.dumps([
                            {"action": "LAUNCH_APP", "parameters": {"target": "{app_name}", "file_path": "{file_path}"}}
                        ]),
                        15, 0, 0.99, time.time()
                    )
                ]
                conn.executemany(
                    "INSERT INTO action_trajectories (intent_pattern, description, actions_json, success_count, failure_count, confidence, last_used) VALUES (?,?,?,?,?,?,?)",
                    canonical
                )
                conn.commit()

    def find_proven_trajectory(self, intent_text: str) -> Optional[Dict[str, Any]]:
        """Find a high-confidence action trajectory matching the user's intent."""
        if not intent_text:
            return None
        text_lower = intent_text.lower()

        pattern_matches = []
        if any(w in text_lower for w in ["lead", "interior designer", "architect", "business", "contact", "maps", "directory"]):
            pattern_matches.append("lead_generation_directory")
        if any(w in text_lower for w in ["open excel", "view spreadsheet", "show data", "launch file"]):
            pattern_matches.append("document_open_and_view")

        with sqlite3.connect(self.db_path) as conn:
            for pattern in pattern_matches:
                row = conn.execute(
                    "SELECT intent_pattern, description, actions_json, confidence, success_count FROM action_trajectories WHERE intent_pattern=? AND confidence >= 0.7",
                    (pattern,)
                ).fetchone()
                if row:
                    actions = json.loads(row[2])
                    return {
                        "pattern": row[0],
                        "description": row[1],
                        "actions": actions,
                        "confidence": row[3],
                        "success_count": row[4]
                    }

            # Fallback keyword search
            rows = conn.execute(
                "SELECT intent_pattern, description, actions_json, confidence, success_count FROM action_trajectories WHERE confidence >= 0.7 ORDER BY success_count DESC"
            ).fetchall()
            for r in rows:
                desc = r[1].lower()
                tokens = [t for t in desc.split() if len(t) > 3]
                if any(t in text_lower for t in tokens):
                    return {
                        "pattern": r[0],
                        "description": r[1],
                        "actions": json.loads(r[2]),
                        "confidence": r[3],
                        "success_count": r[4]
                    }

        return None

    def record_successful_trajectory(self, intent_pattern: str, description: str, actions: List[Dict[str, Any]]) -> None:
        """Record or update a proven trajectory that succeeded in live execution."""
        clean_pattern = re.sub(r"[^a-zA-Z0-9_]", "_", intent_pattern.lower()).strip("_")
        actions_json = json.dumps(actions)

        with sqlite3.connect(self.db_path) as conn:
            existing = conn.execute(
                "SELECT id, success_count, confidence FROM action_trajectories WHERE intent_pattern=?",
                (clean_pattern,)
            ).fetchone()
            if existing:
                new_count = existing[1] + 1
                new_conf = min(0.99, existing[2] + 0.02)
                conn.execute(
                    "UPDATE action_trajectories SET success_count=?, confidence=?, actions_json=?, last_used=? WHERE id=?",
                    (new_count, new_conf, actions_json, time.time(), existing[0])
                )
            else:
                conn.execute(
                    "INSERT INTO action_trajectories (intent_pattern, description, actions_json, success_count, confidence, last_used) VALUES (?,?,?, 1, 0.85, ?)",
                    (clean_pattern, description, actions_json, time.time())
                )
            conn.commit()
        logger.info("[TrajectoryReplay] Saved proven trajectory for '%s' (%d actions)", clean_pattern, len(actions))
