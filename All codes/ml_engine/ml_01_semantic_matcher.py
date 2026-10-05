"""
ml_01_semantic_matcher.py
=========================
ML Part 1: Semantic UI Control & Intent Matcher
Uses TF-IDF Vectorization, N-gram Token Modeling, and Cosine Vector Similarity
to match noisy natural language instructions to precise UI controls in < 3ms.

Training & Ground Truth Data Source:
Extracted live from SQL Server `hojaiga_knowledge.dbo.ui_scanned` (5,962 controls)
and fallback cached from `all_apps_scan_master.json`.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger("hojaiga.ml.semantic_matcher")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter('{"ts":"%(asctime)s","module":"%(name)s","msg":%(message)r}'))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)


@dataclass
class ControlCandidate:
    app_name: str
    name: str
    control_type: str
    coords: Dict[str, Any]
    score: float


class SemanticUIMatcher:
    def __init__(self, master_json_path: str = "d:/new_automation/all_apps_scan_master.json"):
        self.master_json_path = master_json_path
        self.corpus_records: List[Dict[str, Any]] = []
        self.corpus_texts: List[str] = []
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.tfidf_matrix = None
        self.train_on_live_data()

    def train_on_live_data(self) -> int:
        """Extracts dataset from SQL Server or master JSON to train vector model."""
        self.corpus_records.clear()
        self.corpus_texts.clear()
        
        loaded_from_db = False
        try:
            import pyodbc
            conn = pyodbc.connect('Driver={ODBC Driver 17 for SQL Server};Server=localhost\\SQLEXPRESS;Database=hojaiga_knowledge;Trusted_Connection=yes;', timeout=2)
            cur = conn.cursor()
            cur.execute("SELECT app_id, info FROM dbo.ui_scanned")
            rows = cur.fetchall()
            for r in rows:
                app_id = r[0]
                info_raw = r[1]
                if not info_raw:
                    continue
                try:
                    info = json.loads(info_raw) if isinstance(info_raw, str) else info_raw
                except:
                    continue
                
                name = str(info.get("name") or info.get("title") or info.get("text") or "").strip()
                if not name:
                    continue
                ctype = str(info.get("type") or info.get("detected_type") or "Control")
                app_name = str(info.get("parent_path") or app_id or "App").lower()
                text_repr = f"{app_name} {name} {ctype}".lower()
                
                coords = {"x": info.get("x"), "y": info.get("y"), "box": info.get("box")}
                self.corpus_records.append({
                    "app_name": app_name,
                    "name": name,
                    "type": ctype,
                    "coords": coords
                })
                self.corpus_texts.append(text_repr)
            conn.close()
            loaded_from_db = True
            logger.info(f"Loaded {len(self.corpus_records)} training controls directly from SQL Server dbo.ui_scanned.")
        except Exception as e:
            logger.warning(f"SQL Server extraction failed ({e}). Falling back to master JSON.")

        if not loaded_from_db and os.path.exists(self.master_json_path):
            with open(self.master_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for app_name, app_data in data.items():
                elems = app_data.get("elements", app_data.get("controls", []))
                for elem in elems:
                    name = str(elem.get("name") or elem.get("title") or "").strip()
                    if not name:
                        continue
                    ctype = str(elem.get("type") or "Control")
                    text_repr = f"{app_name} {name} {ctype}".lower()
                    self.corpus_records.append({
                        "app_name": app_name.lower(),
                        "name": name,
                        "type": ctype,
                        "coords": elem.get("coords", {})
                    })
                    self.corpus_texts.append(text_repr)
            logger.info(f"Loaded {len(self.corpus_records)} training controls from master JSON file.")

        if self.corpus_texts:
            self.vectorizer = TfidfVectorizer(ngram_range=(1, 3), analyzer="word", min_df=1)
            self.tfidf_matrix = self.vectorizer.fit_transform(self.corpus_texts)
            logger.info(f"TF-IDF Vector Space successfully trained on {len(self.corpus_texts)} tokens.")
            return len(self.corpus_texts)
        return 0

    def query_control(self, user_intent: str, app_context: Optional[str] = None, top_k: int = 3, threshold: float = 0.2) -> List[ControlCandidate]:
        if not self.vectorizer or self.tfidf_matrix is None:
            return []

        search_query = user_intent.lower()
        if app_context:
            search_query = f"{app_context.lower()} {search_query}"

        q_vec = self.vectorizer.transform([search_query])
        similarities = cosine_similarity(q_vec, self.tfidf_matrix)[0]

        top_indices = np.argsort(similarities)[::-1]
        matches: List[ControlCandidate] = []

        for idx in top_indices:
            score = float(similarities[idx])
            if score < threshold:
                break
            rec = self.corpus_records[idx]
            if app_context and app_context.lower() not in rec["app_name"]:
                continue
            matches.append(ControlCandidate(
                app_name=rec["app_name"],
                name=rec["name"],
                control_type=rec["type"],
                coords=rec["coords"],
                score=round(score, 4)
            ))
            if len(matches) >= top_k:
                break

        return matches


if __name__ == "__main__":
    matcher = SemanticUIMatcher()
    tests = [
        ("start recording", "obs"),
        ("hide from screen capture", "obs"),
        ("minimize", "calculator"),
        ("new document", "word"),
        ("save as", "excel")
    ]
    print("\n--- Testing ML Part 1: Semantic UI Matcher ---")
    for intent, app in tests:
        t0 = time.perf_counter()
        hits = matcher.query_control(intent, app, top_k=1)
        lat = (time.perf_counter() - t0) * 1000
        if hits:
            h = hits[0]
            print(f"[{lat:.2f}ms] Intent: '{intent}' ({app}) -> Matched: '{h.name}' (Score: {h.score}) at {h.coords}")
        else:
            print(f"[{lat:.2f}ms] Intent: '{intent}' ({app}) -> No confident match.")
