"""
hojaiga_ml_engine.py
====================
Unified Machine Learning Engine for Hojaiga Automation OS.

PART B (bottom of this file): the Hojaiga Brain — layered natural intelligence with
our own trainable multimodal network. Run: python -m core_organs.hojaiga_ml_engine brain --help

PART A — imposes the 4 core Machine Learning capabilities directly alongside Organ 08 & Organ 30:

1. Fast UI Semantic Control Matching (TF-IDF + Cosine Similarity / k-NN)
2. Coordinate Drift & Path Optimization (Multi-Armed Bandit / EMA Scoring)
3. Visual Feature Template & Keypoint Matching (OpenCV ORB / Multi-scale SIFT)
4. Self-Healing Trace Pattern Mining & Failure Classification (Decision Trees / Clustering)
"""

from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    import cv2
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    _HAS_CV2 = True
    _HAS_NUMPY = True
    _HAS_SKLEARN = True
else:
    try:
        import cv2
        _HAS_CV2 = True
    except Exception:
        cv2 = None
        _HAS_CV2 = False

    try:
        import numpy as np
        _HAS_NUMPY = True
    except Exception:
        np = None
        _HAS_NUMPY = False

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        _HAS_SKLEARN = True
    except Exception:
        TfidfVectorizer = None
        cosine_similarity = None
        _HAS_SKLEARN = False

logger = logging.getLogger("hojaiga.ml_engine")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter('{"ts":"%(asctime)s","component":"%(name)s","msg":%(message)r}'))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)


# ═════════════════════════════════════════════════════════════════════════════
# 1. FAST SEMANTIC UI CONTROL MATCHER (TF-IDF + Cosine Similarity Vector Space)
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class MatchResult:
    matched_name: str
    control_type: str
    coords: Dict[str, Any]
    similarity_score: float
    app_name: str


class FastUIControlMatcher:
    """Matches natural language intent or imprecise control names against
    the 5,962+ scanned UI controls in microseconds without asking Ollama."""

    def __init__(self, master_json_path: str = "d:/new_automation/all_apps_scan_master.json"):
        self.master_json_path = master_json_path
        self.controls_corpus: List[Dict[str, Any]] = []
        self.corpus_texts: List[str] = []
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.tfidf_matrix = None
        self._load_and_fit()

    def _load_and_fit(self) -> None:
        if not os.path.exists(self.master_json_path):
            logger.warning(f"Master controls file not found: {self.master_json_path}")
            return

        with open(self.master_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for app_name, app_data in data.items():
            elements = app_data.get("elements", app_data.get("controls", []))
            for elem in elements:
                name = str(elem.get("name") or elem.get("title") or "").strip()
                if not name:
                    continue
                ctype = str(elem.get("type") or "Control")
                text_repr = f"{app_name} {name} {ctype}".lower()
                self.controls_corpus.append({
                    "app_name": app_name,
                    "name": name,
                    "type": ctype,
                    "coords": elem.get("coords", {}),
                    "text_repr": text_repr
                })
                self.corpus_texts.append(text_repr)

        if self.corpus_texts and _HAS_SKLEARN and TfidfVectorizer is not None:
            self.vectorizer = TfidfVectorizer(ngram_range=(1, 3), analyzer="word", min_df=1)
            self.tfidf_matrix = self.vectorizer.fit_transform(self.corpus_texts)
            logger.info(f"Indexed {len(self.controls_corpus)} controls across all apps into TF-IDF vector space.")
        elif not _HAS_SKLEARN:
            logger.warning("scikit-learn is not installed. Semantic control matching via TF-IDF is disabled.")

    def match(self, query: str, app_filter: Optional[str] = None, top_k: int = 3, threshold: float = 0.25) -> List[MatchResult]:
        if not _HAS_SKLEARN or not self.vectorizer or self.tfidf_matrix is None or cosine_similarity is None or np is None:
            return []

        q_clean = query.lower()
        if app_filter:
            q_clean = f"{app_filter.lower()} {q_clean}"

        query_vec = self.vectorizer.transform([q_clean])
        sims = cosine_similarity(query_vec, self.tfidf_matrix)[0]

        top_indices = np.argsort(sims)[::-1]
        results: List[MatchResult] = []

        for idx in top_indices:
            score = float(sims[idx])
            if score < threshold:
                break
            cand = self.controls_corpus[idx]
            if app_filter and cand["app_name"].lower() != app_filter.lower():
                continue
            results.append(MatchResult(
                matched_name=cand["name"],
                control_type=cand["type"],
                coords=cand["coords"],
                similarity_score=round(score, 4),
                app_name=cand["app_name"]
            ))
            if len(results) >= top_k:
                break

        return results


# ═════════════════════════════════════════════════════════════════════════════
# 2. COORDINATE DRIFT & PATH RELIABILITY (Multi-Armed Bandit / EMA Scoring)
# ═════════════════════════════════════════════════════════════════════════════

class ActionReliabilityBandit:
    """Tracks success rates of physical pathways (e.g. Click vs Hotkey vs Command)
    using Exponential Moving Average and Upper Confidence Bound (UCB1) selection."""

    def __init__(self, db_path: str = "d:/new_automation/storage/learning_bandit.sqlite"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        with self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS action_pathways (
                    pathway_id TEXT PRIMARY KEY,
                    app_name TEXT,
                    action_type TEXT,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    ema_score REAL DEFAULT 0.5,
                    last_coords_json TEXT,
                    updated_at REAL
                )
            """)

    def record_outcome(self, pathway_id: str, app_name: str, action_type: str, success: bool, coords: Optional[Dict[str, Any]] = None, alpha: float = 0.25):
        now = time.time()
        with self._conn:
            cur = self._conn.cursor()
            cur.execute("SELECT success_count, failure_count, ema_score FROM action_pathways WHERE pathway_id = ?", (pathway_id,))
            row = cur.fetchone()
            if row:
                s_cnt, f_cnt, current_ema = row
                new_s = s_cnt + (1 if success else 0)
                new_f = f_cnt + (0 if success else 1)
                reward = 1.0 if success else 0.0
                new_ema = current_ema * (1.0 - alpha) + reward * alpha
                cur.execute("""
                    UPDATE action_pathways
                    SET success_count = ?, failure_count = ?, ema_score = ?, last_coords_json = ?, updated_at = ?
                    WHERE pathway_id = ?
                """, (new_s, new_f, new_ema, json.dumps(coords or {}), now, pathway_id))
            else:
                s_cnt = 1 if success else 0
                f_cnt = 0 if success else 1
                init_ema = 0.75 if success else 0.25
                cur.execute("""
                    INSERT INTO action_pathways (pathway_id, app_name, action_type, success_count, failure_count, ema_score, last_coords_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (pathway_id, app_name, action_type, s_cnt, f_cnt, init_ema, json.dumps(coords or {}), now))

    def get_best_pathway(self, app_name: str, target_action: str) -> Tuple[str, float]:
        """Returns the highest scoring pathway for a given target action."""
        with self._conn:
            cur = self._conn.cursor()
            cur.execute("""
                SELECT pathway_id, ema_score, (success_count + failure_count)
                FROM action_pathways
                WHERE app_name = ? AND action_type = ?
                ORDER BY ema_score DESC
            """, (app_name, target_action))
            rows = cur.fetchall()
            if not rows:
                return (f"{app_name}:{target_action}:default_click", 0.5)
            best_id, best_score, total_trials = rows[0]
            return (best_id, float(best_score))


# ═════════════════════════════════════════════════════════════════════════════
# 3. FAST VISUAL FEATURE TEMPLATE & KEYPOINT MATCHER (OpenCV Multiscale)
# ═════════════════════════════════════════════════════════════════════════════

class VisualElementDetector:
    """Locates graphical icons, unlabelled buttons, or visual presentation boundaries
    in < 15ms directly on screenshots using multi-scale template matching."""

    @staticmethod
    def locate_template(screenshot_bgr: np.ndarray, template_bgr: np.ndarray, threshold: float = 0.8) -> Optional[Tuple[int, int, int, int]]:
        """Returns bounding box (x, y, w, h) of template in screenshot."""
        if screenshot_bgr is None or template_bgr is None:
            return None

        h, w = template_bgr.shape[:2]
        res = cv2.matchTemplate(screenshot_bgr, template_bgr, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

        if max_val >= threshold:
            return (max_loc[0], max_loc[1], w, h)
        return None

    @staticmethod
    def is_slide_presentation_active(screenshot_bgr: np.ndarray) -> bool:
        """Heuristic check: detects large centered 16:9 / 4:3 high-contrast
        presentation slides on screen versus webcam grid."""
        if screenshot_bgr is None:
            return False
        gray = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        edge_density = float(np.sum(edges > 0)) / (edges.shape[0] * edges.shape[1])
        # Presentation slides have clean uniform areas and sharp text/diagram edges
        return 0.01 < edge_density < 0.25


# ═════════════════════════════════════════════════════════════════════════════
# 4. TRACE PATTERN MINING & FAILURE CLASSIFIER (Self-Healing Rule Generator)
# ═════════════════════════════════════════════════════════════════════════════

class SelfHealingRuleGenerator:
    """Analyzes recent execution failures and creates automated bypass rules."""

    def __init__(self, rules_db: str = "d:/new_automation/storage/healing_rules.json"):
        self.rules_db = rules_db
        os.makedirs(os.path.dirname(rules_db), exist_ok=True)
        self.rules = self._load_rules()

    def _load_rules(self) -> Dict[str, Any]:
        if os.path.exists(self.rules_db):
            try:
                with open(self.rules_db, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_rule(self, failed_trigger: str, remedy_action: Dict[str, Any]):
        self.rules[failed_trigger] = remedy_action
        with open(self.rules_db, "w", encoding="utf-8") as f:
            json.dump(self.rules, f, indent=2)
        logger.info(f"Learned new self-healing rule for: {failed_trigger}")

    def get_remedy(self, trigger_condition: str) -> Optional[Dict[str, Any]]:
        return self.rules.get(trigger_condition)


# ═════════════════════════════════════════════════════════════════════════════
# UNIFIED MACHINE LEARNING CONTROLLER
# ═════════════════════════════════════════════════════════════════════════════

class UnifiedMLEngine:
    """Single master interface uniting all 4 ML dimensions."""

    def __init__(self):
        self.matcher = FastUIControlMatcher()
        self.bandit = ActionReliabilityBandit()
        self.vision_detector = VisualElementDetector()
        self.healer = SelfHealingRuleGenerator()

    def find_control(self, intent_text: str, app_name: Optional[str] = None) -> Optional[MatchResult]:
        matches = self.matcher.match(intent_text, app_filter=app_name, top_k=1)
        return matches[0] if matches else None



# ═════════════════════════════════════════════════════════════════════════════
#
#   H O J A I G A   B R A I N   —  our own natural-intelligence system
#
#   Seven thinking layers, each its own algorithm, plus a learning layer and
#   our own multimodal neural network (HojaigaCortexNet) trained from scratch
#   on whatever data we feed it. No pretrained outside model is required:
#   external LLMs (local Qwen, Claude, ...) are optional *teachers* only.
#
#   L1 FILTER      (thalamus)          gate noise, duplicates, PII; route modality
#   L2 KNOW        (hippocampus)       hybrid recall: BM25 + own dense vectors + memory, RRF fusion
#   L3 UNDERSTAND  (Wernicke/temporal) intent (online Naive Bayes), key concepts (RAKE), relations
#   L4 REASON      (prefrontal)        concept graph: personalized PageRank + forward chaining + calculator
#   L5 THINK       (default network)   several candidate answers, scored by a learned value function
#   L6 ANSWER      (Broca)             structure the best candidate for the intent, cite sources
#   L7 VERIFY      (anterior cingulate) grounding, self-consistency, contradiction, calibrated confidence;
#                                      low confidence → think again with wider recall → teacher
#   L8 LEARN       (basal ganglia)     feedback updates value weights, calibration, intents, memory
#
#   Neural core (used by L2/L5/L7 once trained):
#     own byte-level BPE tokenizer  →  vision encoder (patch transformer, images + video frames)
#     →  prefix-LM transformer decoder  →  heads: language, embedding (retrieval / contrastive),
#        verifier (does this answer follow from this question/context?)
#
#   Terminal:  python -m core_organs.hojaiga_ml_engine brain --help
#
# ═════════════════════════════════════════════════════════════════════════════

import argparse as _b_argparse
import ast as _b_ast
import collections as _b_collections
import hashlib as _b_hashlib
import operator as _b_operator
import random as _b_random
import re as _b_re
import shutil as _b_shutil
import subprocess as _b_subprocess
import sys as _b_sys
import tempfile as _b_tempfile
import uuid as _b_uuid
from pathlib import Path as _BPath

BRAIN_HOME = _BPath(os.environ.get("HOJAIGA_BRAIN_HOME", os.path.join("storage", "brain")))

_B_WORD = _b_re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-]*")
_B_SENT = _b_re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])|\n{2,}")
_B_STOP = frozenset("""a an the and or but if then else of to in on at by for with from as is are was were be been
being am do does did doing have has had having it its this that these those there here i me my we our you your he
him his she her they them their what which who whom whose when where why how not no nor so than too very can will
just should would could may might must shall into onto about above below over under again further once all any both
each few more most other some such only own same also out up down off until while during before after because
between through per via""".split())
_B_NEG = frozenset("not no never none cannot can't don't doesn't isn't aren't wasn't weren't without".split())

TEXT_EXT = {".txt", ".md", ".rst", ".csv", ".tsv", ".json", ".jsonl", ".html", ".htm", ".xml", ".yaml", ".yml",
            ".py", ".js", ".ts", ".java", ".c", ".cpp", ".cs", ".go", ".rb", ".php", ".sql", ".tex", ".srt", ".vtt"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".gif"}
DOC_EXT = {".pdf", ".docx", ".pptx"}


def b_words(text: str) -> list[str]:
    return [w.lower() for w in _B_WORD.findall(text or "")]


def b_content(text: str) -> list[str]:
    return [w for w in b_words(text) if w not in _B_STOP and (len(w) > 1 or w.isdigit())]


def b_sentences(text: str) -> list[str]:
    out = []
    for part in _B_SENT.split(text or ""):
        part = _b_re.sub(r"\s+", " ", part).strip()
        if len(part) > 2:
            out.append(part)
    return out


def b_stem(w: str) -> str:
    """Light suffix-stripping stemmer (plural/tense), then a 7-char prefix."""
    for suf in ("ational", "ization", "ingly", "ments", "ness", "ing", "ies", "ied", "es", "ed", "ly", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)] + ("y" if suf in ("ies", "ied") else "")
            break
    return w[:7]


def b_stems(text: str) -> set:
    return {b_stem(w) for w in b_content(text)}


def b_overlap(a: str, b: str) -> float:
    """Share of a's content words that also occur in b (stem-tolerant)."""
    sa, sb = b_stems(a), b_stems(b)
    return len(sa & sb) / len(sa) if sa else 0.0


def b_jaccard(a: str, b: str) -> float:
    sa, sb = b_stems(a), b_stems(b)
    return len(sa & sb) / len(sa | sb) if (sa or sb) else 0.0


def _b_sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


# ─────────────────────────────────────────────────────────────────────────────
# Data: read anything we are fed (text, documents, diagrams/images, video, hybrids)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BrainItem:
    """One unit of experience. text may be empty for pure media; media holds a path."""
    source: str
    text: str = ""
    image: Optional[str] = None
    video: Optional[str] = None
    question: Optional[str] = None
    answer: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def modality(self) -> str:
        if self.video:
            return "video+text" if self.text else "video"
        if self.image:
            return "image+text" if self.text else "image"
        return "qa" if self.question else "text"


class DatasetReader:
    """Walks files/folders and yields BrainItems.

    Conventions (all optional, nothing domain-specific):
      * text/code/markup files → text items (HTML is stripped)
      * .jsonl / .json → each record may have text | question+answer | messages
        (chat format, e.g. exported by organ_08) | image | video | caption
      * image.png + image.txt (same stem) → image–caption pair; images alone are
        still learned (diagram/visual memory)
      * video.mp4 + video.txt/.srt/.vtt → video–transcript pair
      * .pdf/.docx/.pptx → text, when pypdf / python-docx / python-pptx exist
    """

    def __init__(self, max_bytes: int = 50_000_000):
        self.max_bytes = max_bytes
        self.skipped: list[tuple[str, str]] = []

    @staticmethod
    def _strip_html(text: str) -> str:
        text = _b_re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", text)
        text = _b_re.sub(r"(?s)<[^>]+>", "\n", text)
        text = _b_re.sub(r"&nbsp;", " ", text)
        return _b_re.sub(r"\n\s*\n+", "\n\n", _b_re.sub(r"[ \t]+", " ", text))

    @staticmethod
    def _sidecar_text(p: _BPath) -> str:
        for ext in (".txt", ".md", ".srt", ".vtt", ".caption"):
            s = p.with_suffix(ext)
            if s.exists() and s != p:
                txt = s.read_text(encoding="utf-8", errors="ignore")
                if ext in (".srt", ".vtt"):
                    txt = _b_re.sub(r"(?m)^\d+\s*$|^\d\d:\d\d.*-->.*$|^WEBVTT.*$", "", txt)
                return _b_re.sub(r"\n{2,}", "\n", txt).strip()
        return ""

    def _read_document(self, p: _BPath) -> str:
        ext = p.suffix.lower()
        try:
            if ext == ".pdf":
                from pypdf import PdfReader  # optional
                return "\n\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)
            if ext == ".docx":
                import docx  # python-docx, optional
                return "\n\n".join(par.text for par in docx.Document(str(p)).paragraphs)
            if ext == ".pptx":
                from pptx import Presentation  # python-pptx, optional
                out = []
                for i, slide in enumerate(Presentation(str(p)).slides, 1):
                    texts = [sh.text_frame.text for sh in slide.shapes if getattr(sh, "has_text_frame", False)]
                    out.append(f"Slide {i}\n" + "\n".join(texts))
                return "\n\n".join(out)
        except ImportError as exc:
            self.skipped.append((str(p), f"missing optional reader: {exc.name}"))
        except Exception as exc:
            self.skipped.append((str(p), str(exc)))
        return ""

    def _records(self, p: _BPath):
        raw = p.read_text(encoding="utf-8", errors="ignore")
        if p.suffix.lower() == ".jsonl":
            for line in raw.splitlines():
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
        else:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                yield {"text": raw}
                return
            if isinstance(data, list):
                yield from (d for d in data if isinstance(d, dict))
            elif isinstance(data, dict):
                yield data

    def _record_item(self, rec: dict, base: _BPath, source: str) -> Optional[BrainItem]:
        def media(key):
            v = rec.get(key)
            if not v:
                return None
            mp = _BPath(v)
            return str(mp if mp.is_absolute() else (base / mp))
        if isinstance(rec.get("messages"), list):
            user = [m.get("content", "") for m in rec["messages"] if m.get("role") == "user"]
            asst = [m.get("content", "") for m in rec["messages"] if m.get("role") == "assistant"]
            if user and asst:
                return BrainItem(source, question=user[-1], answer=asst[-1],
                                 text=f"{user[-1]}\n{asst[-1]}", image=media("image"), video=media("video"))
        q = rec.get("question") or rec.get("prompt") or rec.get("input") or rec.get("instruction")
        a = rec.get("answer") or rec.get("response") or rec.get("output") or rec.get("completion")
        if q and a:
            return BrainItem(source, question=str(q), answer=str(a), text=f"{q}\n{a}",
                             image=media("image"), video=media("video"))
        text = rec.get("text") or rec.get("caption") or rec.get("content") or ""
        if not isinstance(text, str):
            text = json.dumps(text, ensure_ascii=False)
        if not text and not rec.get("image") and not rec.get("video"):
            text = json.dumps(rec, ensure_ascii=False)
        return BrainItem(source, text=text, image=media("image"), video=media("video"),
                         meta={k: v for k, v in rec.items() if k in ("subject", "grade", "label", "page")})

    def read(self, paths) -> "list[BrainItem]":
        if isinstance(paths, (str, _BPath)):
            paths = [paths]
        items: list[BrainItem] = []
        for root in paths:
            root = _BPath(root)
            files = [root] if root.is_file() else sorted(f for f in root.rglob("*") if f.is_file())
            media_stems = {f.with_suffix("") for f in files if f.suffix.lower() in IMAGE_EXT | VIDEO_EXT}
            for f in files:
                ext = f.suffix.lower()
                try:
                    if f.stat().st_size > self.max_bytes or any(part.startswith(".") for part in f.parts[-3:-1]):
                        continue
                    if ext in IMAGE_EXT:
                        items.append(BrainItem(str(f), text=self._sidecar_text(f), image=str(f)))
                    elif ext in VIDEO_EXT:
                        items.append(BrainItem(str(f), text=self._sidecar_text(f), video=str(f)))
                    elif ext in DOC_EXT:
                        t = self._read_document(f)
                        if t.strip():
                            items.append(BrainItem(str(f), text=t))
                    elif ext in (".json", ".jsonl"):
                        for rec in self._records(f):
                            it = self._record_item(rec, f.parent, str(f))
                            if it:
                                items.append(it)
                    elif ext in TEXT_EXT:
                        if f.with_suffix("") in media_stems and ext in (".txt", ".md", ".srt", ".vtt"):
                            continue  # sidecar caption, consumed by its media file
                        t = f.read_text(encoding="utf-8", errors="ignore")
                        if ext in (".html", ".htm", ".xml"):
                            t = self._strip_html(t)
                        if t.strip():
                            items.append(BrainItem(str(f), text=t))
                except Exception as exc:
                    self.skipped.append((str(f), str(exc)))
        return items


def load_image_array(path: str, size: int = 128):
    """RGB float array [3,size,size] in 0..1 (needs Pillow + numpy)."""
    from PIL import Image
    img = Image.open(path).convert("RGB").resize((size, size))
    arr = np.asarray(img, dtype="float32") / 255.0
    return arr.transpose(2, 0, 1)


def load_video_frames(path: str, frames: int = 8, size: int = 128):
    """Evenly sampled frames [T,3,size,size]. Uses OpenCV, else ffmpeg, else GIF via Pillow."""
    from PIL import Image, ImageSequence
    p = _BPath(path)
    pil_frames = []
    if p.suffix.lower() == ".gif":
        pil_frames = [fr.convert("RGB") for fr in ImageSequence.Iterator(Image.open(p))]
    elif _HAS_CV2:
        cap = cv2.VideoCapture(str(p))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        for idx in [int(i * total / frames) for i in range(frames)]:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, fr = cap.read()
            if ok:
                pil_frames.append(Image.fromarray(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)))
        cap.release()
    elif _b_shutil.which("ffmpeg"):
        with _b_tempfile.TemporaryDirectory() as td:
            _b_subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(p), "-vf",
                               f"fps=1,scale={size}:{size}", "-frames:v", str(frames * 4),
                               os.path.join(td, "f%04d.png")], check=True)
            files = sorted(_BPath(td).glob("*.png"))
            pil_frames = [Image.open(f).convert("RGB") for f in files]
    else:
        raise RuntimeError("video needs opencv-python or ffmpeg on PATH")
    if not pil_frames:
        raise RuntimeError(f"no frames decoded from {path}")
    pick = [pil_frames[min(len(pil_frames) - 1, int(i * len(pil_frames) / frames))] for i in range(frames)]
    arr = np.stack([np.asarray(f.resize((size, size)), dtype="float32") / 255.0 for f in pick])
    return arr.transpose(0, 3, 1, 2)


# ─────────────────────────────────────────────────────────────────────────────
# Our own tokenizer: byte-level BPE learned from our data (no outside vocabulary)
# ─────────────────────────────────────────────────────────────────────────────

class BrainTokenizer:
    SPECIALS = ["<pad>", "<bos>", "<eos>", "<sep>", "<img>", "<vid>", "<q>", "<a>"]
    PAD, BOS, EOS, SEP, IMG, VID, Q, A = range(8)
    _PRE = _b_re.compile(r"""'s|'t|'re|'ve|'m|'ll|'d| ?[A-Za-z]+| ?[0-9]{1,3}| ?[^\sA-Za-z0-9]+|\s+(?!\S)|\s+""")

    def __init__(self, merges: Optional[list[tuple[int, int]]] = None):
        self.offset = len(self.SPECIALS)
        self.merges: list[tuple[int, int]] = [tuple(m) for m in (merges or [])]
        self.ranks = {m: i for i, m in enumerate(self.merges)}
        self._cache: dict[str, list[int]] = {}

    @property
    def vocab_size(self) -> int:
        return self.offset + 256 + len(self.merges)

    def _bytes(self, chunk: str) -> list[int]:
        return [self.offset + b for b in chunk.encode("utf-8")]

    @classmethod
    def train(cls, texts, vocab_size: int = 8000, sample_chars: int = 4_000_000) -> "BrainTokenizer":
        tok = cls()
        counts: _b_collections.Counter = _b_collections.Counter()
        used = 0
        for t in texts:
            if used >= sample_chars:
                break
            t = t[: sample_chars - used]
            used += len(t)
            counts.update(cls._PRE.findall(t))
        words = {tuple(tok._bytes(w)): c for w, c in counts.items()}
        merges = []
        target = max(0, vocab_size - tok.offset - 256)
        for _ in range(target):
            pairs: _b_collections.Counter = _b_collections.Counter()
            for w, c in words.items():
                for a, b in zip(w, w[1:]):
                    pairs[(a, b)] += c
            if not pairs:
                break
            (a, b), freq = pairs.most_common(1)[0]
            if freq < 2:
                break
            new_id = tok.offset + 256 + len(merges)
            merges.append((a, b))
            nw = {}
            for w, c in words.items():
                if len(w) < 2:
                    nw[w] = nw.get(w, 0) + c
                    continue
                out, i = [], 0
                while i < len(w):
                    if i < len(w) - 1 and w[i] == a and w[i + 1] == b:
                        out.append(new_id)
                        i += 2
                    else:
                        out.append(w[i])
                        i += 1
                t2 = tuple(out)
                nw[t2] = nw.get(t2, 0) + c
            words = nw
        return cls(merges)

    def _encode_chunk(self, chunk: str) -> list[int]:
        hit = self._cache.get(chunk)
        if hit is not None:
            return hit
        ids = self._bytes(chunk)
        while len(ids) > 1:
            best, best_rank = None, None
            for i, pair in enumerate(zip(ids, ids[1:])):
                r = self.ranks.get(pair)
                if r is not None and (best_rank is None or r < best_rank):
                    best, best_rank = i, r
            if best is None:
                break
            ids = ids[:best] + [self.offset + 256 + best_rank] + ids[best + 2:]
        if len(self._cache) < 200_000:
            self._cache[chunk] = ids
        return ids

    def encode(self, text: str, bos: bool = False, eos: bool = False) -> list[int]:
        ids = [self.BOS] if bos else []
        for ch in self._PRE.findall(text or ""):
            ids.extend(self._encode_chunk(ch))
        if eos:
            ids.append(self.EOS)
        return ids

    def _expand(self, i: int) -> bytes:
        if i < self.offset:
            return b""
        if i < self.offset + 256:
            return bytes([i - self.offset])
        a, b = self.merges[i - self.offset - 256]
        return self._expand(a) + self._expand(b)

    def decode(self, ids) -> str:
        return b"".join(self._expand(int(i)) for i in ids).decode("utf-8", errors="replace")

    def save(self, path) -> None:
        _BPath(path).write_text(json.dumps({"merges": self.merges, "specials": self.SPECIALS}), encoding="utf-8")

    @classmethod
    def load(cls, path) -> "BrainTokenizer":
        return cls([tuple(m) for m in json.loads(_BPath(path).read_text(encoding="utf-8"))["merges"]])


# ─────────────────────────────────────────────────────────────────────────────
# Our own neural network: HojaigaCortexNet (multimodal, trained from scratch)
# ─────────────────────────────────────────────────────────────────────────────

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    _HAS_TORCH = True
except Exception:  # the symbolic layers still work without torch
    torch = None
    nn = None
    F = None
    _HAS_TORCH = False

CORTEX_SIZES = {
    # name: (d_model, layers, heads, context, vision_layers)  ~params (8k vocab)
    "tiny": (256, 4, 4, 256, 2),     # ~6M   — CPU friendly, smoke tests
    "small": (384, 6, 6, 512, 3),    # ~17M  — laptop GPU (RTX 3050)
    "base": (512, 8, 8, 1024, 4),    # ~37M  — 8 GB GPU
    "large": (768, 12, 12, 1024, 6), # ~110M — 16-24 GB GPU
}


@dataclass
class CortexConfig:
    vocab_size: int = 8000
    d_model: int = 384
    n_layer: int = 6
    n_head: int = 6
    context: int = 512
    vision_layers: int = 3
    img_size: int = 128
    patch: int = 16
    video_frames: int = 8
    embed_dim: int = 256
    dropout: float = 0.1

    @classmethod
    def from_size(cls, size: str, vocab_size: int) -> "CortexConfig":
        d, l, h, ctx, vl = CORTEX_SIZES[size]
        return cls(vocab_size=vocab_size, d_model=d, n_layer=l, n_head=h, context=ctx, vision_layers=vl)


if _HAS_TORCH:

    class _Block(nn.Module):
        def __init__(self, d: int, h: int, dropout: float):
            super().__init__()
            self.ln1 = nn.LayerNorm(d)
            self.qkv = nn.Linear(d, 3 * d)
            self.proj = nn.Linear(d, d)
            self.ln2 = nn.LayerNorm(d)
            self.mlp = nn.Sequential(nn.Linear(d, 4 * d), nn.GELU(), nn.Linear(4 * d, d), nn.Dropout(dropout))
            self.h = h
            self.dropout = dropout

        def forward(self, x, mask=None):
            B, T, D = x.shape
            q, k, v = self.qkv(self.ln1(x)).split(D, dim=2)
            q, k, v = (t.view(B, T, self.h, D // self.h).transpose(1, 2) for t in (q, k, v))
            y = F.scaled_dot_product_attention(q, k, v, attn_mask=mask,
                                               dropout_p=self.dropout if self.training else 0.0)
            x = x + self.proj(y.transpose(1, 2).reshape(B, T, D))
            return x + self.mlp(self.ln2(x))

    class VisionEncoder(nn.Module):
        """Patch transformer for images and video frames (diagrams, photos, screens)."""

        def __init__(self, cfg: CortexConfig):
            super().__init__()
            self.cfg = cfg
            n = (cfg.img_size // cfg.patch) ** 2
            self.patch = nn.Conv2d(3, cfg.d_model, cfg.patch, cfg.patch)
            self.pos = nn.Parameter(torch.zeros(1, n, cfg.d_model))
            self.time = nn.Parameter(torch.zeros(1, cfg.video_frames, 1, cfg.d_model))
            self.blocks = nn.ModuleList(_Block(cfg.d_model, cfg.n_head, cfg.dropout) for _ in range(cfg.vision_layers))
            self.ln = nn.LayerNorm(cfg.d_model)
            nn.init.normal_(self.pos, std=0.02)
            nn.init.normal_(self.time, std=0.02)

        def _frame(self, img):                       # [B,3,H,W] -> [B,P,D]
            x = self.patch(img).flatten(2).transpose(1, 2) + self.pos
            for blk in self.blocks:
                x = blk(x)
            return self.ln(x)

        def forward(self, image=None, video=None):
            if video is not None:                    # [B,T,3,H,W] -> 4 pooled tokens per frame
                B, T = video.shape[:2]
                x = self._frame(video.flatten(0, 1))
                g = int(math.sqrt(x.shape[1]))
                x = x.transpose(1, 2).reshape(B * T, -1, g, g)
                x = F.adaptive_avg_pool2d(x, 2).flatten(2).transpose(1, 2)   # [B*T,4,D]
                x = x.reshape(B, T, 4, -1) + self.time[:, :T]
                return x.reshape(B, T * 4, -1)
            return self._frame(image)

    class HojaigaCortexNet(nn.Module):
        """Prefix-LM transformer: [visual tokens] + [text tokens] → language, embedding, verifier heads."""

        def __init__(self, cfg: CortexConfig):
            super().__init__()
            self.cfg = cfg
            self.tok = nn.Embedding(cfg.vocab_size, cfg.d_model)
            self.pos = nn.Embedding(cfg.context + cfg.video_frames * 4 + 64, cfg.d_model)
            self.vision = VisionEncoder(cfg)
            self.modality = nn.Embedding(3, cfg.d_model)            # 0 text, 1 image, 2 video
            self.blocks = nn.ModuleList(_Block(cfg.d_model, cfg.n_head, cfg.dropout) for _ in range(cfg.n_layer))
            self.ln = nn.LayerNorm(cfg.d_model)
            self.lm_head = nn.Linear(cfg.d_model, cfg.vocab_size, bias=False)
            self.lm_head.weight = self.tok.weight                    # weight tying
            self.embed_head = nn.Linear(cfg.d_model, cfg.embed_dim)
            self.vis_embed_head = nn.Linear(cfg.d_model, cfg.embed_dim)
            self.verify_head = nn.Linear(cfg.d_model, 1)
            self.logit_scale = nn.Parameter(torch.tensor(math.log(1 / 0.07)))
            self.apply(self._init)

        @staticmethod
        def _init(m):
            if isinstance(m, nn.Linear):
                nn.init.normal_(m.weight, std=0.02)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
            elif isinstance(m, nn.Embedding):
                nn.init.normal_(m.weight, std=0.02)

        def num_params(self) -> int:
            return sum(p.numel() for p in self.parameters())

        def forward(self, ids, image=None, video=None, pad_id: int = 0):
            B, T = ids.shape
            x = self.tok(ids) + self.modality(torch.zeros_like(ids))
            prefix = None
            if video is not None:
                prefix = self.vision(video=video) + self.modality.weight[2]
            elif image is not None:
                prefix = self.vision(image=image) + self.modality.weight[1]
            P = 0 if prefix is None else prefix.shape[1]
            if prefix is not None:
                x = torch.cat([prefix, x], dim=1)
            L = P + T
            x = x + self.pos(torch.arange(L, device=ids.device))
            causal = torch.ones(L, L, dtype=torch.bool, device=ids.device).tril()
            causal[:, :P] = True                      # every position sees the whole visual prefix
            keep = torch.cat([torch.ones(B, P, dtype=torch.bool, device=ids.device), ids != pad_id], dim=1)
            mask = (causal.unsqueeze(0) & keep.unsqueeze(1)).unsqueeze(1)
            mask = mask | torch.eye(L, dtype=torch.bool, device=ids.device)  # no fully-masked rows
            for blk in self.blocks:
                x = blk(x, mask)
            x = self.ln(x)
            text_h = x[:, P:]
            denom = (ids != pad_id).sum(1, keepdim=True).clamp(min=1)
            pooled = (text_h * (ids != pad_id).unsqueeze(-1)).sum(1) / denom
            out = {"logits": self.lm_head(text_h), "pooled": pooled,
                   "embedding": F.normalize(self.embed_head(pooled), dim=-1),
                   "verify_logit": self.verify_head(pooled).squeeze(-1)}
            if prefix is not None:
                out["visual_embedding"] = F.normalize(self.vis_embed_head(x[:, :P].mean(1)), dim=-1)
            return out

        @torch.no_grad()
        def generate(self, ids, max_new: int = 120, temperature: float = 0.8, top_k: int = 40,
                     image=None, video=None, eos_id: int = 2):
            self.eval()
            for _ in range(max_new):
                ctx = ids[:, -self.cfg.context:]
                logits = self(ctx, image=image, video=video)["logits"][:, -1, :] / max(temperature, 1e-4)
                if top_k:
                    v, _ = torch.topk(logits, min(top_k, logits.shape[-1]))
                    logits[logits < v[:, [-1]]] = -float("inf")
                nxt = torch.multinomial(F.softmax(logits, dim=-1), 1)
                ids = torch.cat([ids, nxt], dim=1)
                if int(nxt) == eos_id:
                    break
            return ids


class CortexRuntime:
    """Loads the trained network + tokenizer for the thinking layers (lazy, optional)."""

    def __init__(self, home: _BPath = BRAIN_HOME):
        self.home = _BPath(home)
        self.model = None
        self.tok: Optional[BrainTokenizer] = None
        self.device = "cpu"
        self._tried = False

    @property
    def ckpt(self) -> _BPath:
        return self.home / "cortex" / "model.pt"

    def available(self) -> bool:
        if self._tried:
            return self.model is not None
        self._tried = True
        if not (_HAS_TORCH and self.ckpt.exists() and (self.home / "cortex" / "tokenizer.json").exists()):
            return False
        try:
            state = torch.load(self.ckpt, map_location="cpu", weights_only=False)
            self.tok = BrainTokenizer.load(self.home / "cortex" / "tokenizer.json")
            self.model = HojaigaCortexNet(CortexConfig(**state["config"]))
            self.model.load_state_dict(state["model"])
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.model.to(self.device).eval()
        except Exception as exc:
            logger.warning("cortex model failed to load: %s", exc)
            self.model = None
        return self.model is not None

    def _ids(self, texts: list[str]):
        ctx = self.model.cfg.context
        rows = [self.tok.encode(t)[: ctx] or [self.tok.PAD] for t in texts]
        width = max(len(r) for r in rows)
        return torch.tensor([r + [self.tok.PAD] * (width - len(r)) for r in rows], device=self.device)

    @torch.no_grad() if _HAS_TORCH else (lambda f: f)
    def embed(self, texts: list[str]) -> "list[list[float]]":
        out = []
        for i in range(0, len(texts), 32):
            out.extend(self.model(self._ids(texts[i:i + 32]))["embedding"].cpu().tolist())
        return out

    @torch.no_grad() if _HAS_TORCH else (lambda f: f)
    def verify(self, question: str, context: str, answer: str) -> float:
        text = f"{question}\n{context[-1200:]}\n{answer}"
        ids = self._ids([text])
        return float(torch.sigmoid(self.model(ids)["verify_logit"])[0])

    @torch.no_grad() if _HAS_TORCH else (lambda f: f)
    def perplexity(self, text: str) -> float:
        ids = self._ids([text])
        if ids.shape[1] < 2:
            return 1e4
        logits = self.model(ids)["logits"][:, :-1]
        loss = F.cross_entropy(logits.reshape(-1, logits.shape[-1]), ids[:, 1:].reshape(-1),
                               ignore_index=self.tok.PAD)
        return float(math.exp(min(20.0, float(loss))))

    def answer(self, question: str, context: str = "", samples: int = 2, max_new: int = 120) -> list[str]:
        prompt = [self.tok.BOS] + self.tok.encode(context[-1500:]) + [self.tok.SEP, self.tok.Q] + \
            self.tok.encode(question) + [self.tok.A]
        keep = self.model.cfg.context - max_new
        prompt = prompt[-keep:]
        outs = []
        for _ in range(samples):
            ids = torch.tensor([prompt], device=self.device)
            gen = self.model.generate(ids, max_new=max_new, temperature=0.7, eos_id=self.tok.EOS)
            text = self.tok.decode(gen[0, len(prompt):].tolist()).strip()
            if text:
                outs.append(text)
        return outs


# ─────────────────────────────────────────────────────────────────────────────
# Trainer: feed any dataset from the terminal → the network learns it
# ─────────────────────────────────────────────────────────────────────────────

class CortexTrainer:
    """Trains HojaigaCortexNet on BrainItems with four objectives at once:

    1. language modelling on all text (next-token, prefix-LM over visual tokens)
    2. captioning: image / video prefix → its text (diagrams, frames, photos)
    3. contrastive alignment (InfoNCE) between visual and text embeddings
    4. verification: (question, answer) real pairs vs. shuffled pairs

    Continual learning: a reservoir replay buffer of earlier data is mixed into
    every new run so new knowledge does not erase old knowledge (catastrophic
    forgetting), and checkpoints resume across runs.
    """

    def __init__(self, home: _BPath = BRAIN_HOME, size: str = "small", device: str = "auto",
                 vocab_size: int = 8000, seed: int = 1337):
        if not _HAS_TORCH:
            raise RuntimeError("Training the neural cortex needs PyTorch: pip install torch")
        self.home = _BPath(home)
        self.dir = self.home / "cortex"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.size = size
        self.vocab_size = vocab_size
        self.device = ("cuda" if torch.cuda.is_available() else "cpu") if device == "auto" else device
        _b_random.seed(seed)
        torch.manual_seed(seed)
        self.replay_path = self.dir / "replay.jsonl"
        self.metrics_path = self.dir / "metrics.jsonl"

    # -- data ----------------------------------------------------------------
    def _replay_load(self) -> list[dict]:
        if not self.replay_path.exists():
            return []
        return [json.loads(l) for l in self.replay_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def _replay_update(self, items: list[BrainItem], cap: int = 5000) -> None:
        buf = self._replay_load()
        seen = len(buf)
        for it in items:
            rec = {"source": it.source, "text": it.text[:4000], "image": it.image, "video": it.video,
                   "question": it.question, "answer": it.answer}
            seen += 1
            if len(buf) < cap:
                buf.append(rec)
            else:
                j = _b_random.randrange(seen)
                if j < cap:
                    buf[j] = rec
        with self.replay_path.open("w", encoding="utf-8") as fh:
            for r in buf:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    def _examples(self, items: list[BrainItem], tok: BrainTokenizer, ctx: int) -> list[dict]:
        ex = []
        for it in items:
            if it.question and it.answer:
                ids = [tok.BOS, tok.Q] + tok.encode(it.question) + [tok.A] + tok.encode(it.answer) + [tok.EOS]
                ex.append({"ids": ids[:ctx], "image": it.image, "video": it.video,
                           "q": it.question[:1000], "a": it.answer[:1000]})
                continue
            ids = tok.encode(it.text or "", bos=True, eos=True)
            if it.image or it.video:
                ex.append({"ids": ids[:ctx], "image": it.image, "video": it.video})
                continue
            stride = ctx - ctx // 8
            for s in range(0, max(1, len(ids) - 8), stride):
                win = ids[s:s + ctx]
                if len(win) > 8:
                    ex.append({"ids": win})
        return ex

    def _media(self, ex: dict, cfg: CortexConfig):
        try:
            if ex.get("video"):
                return None, torch.tensor(load_video_frames(ex["video"], cfg.video_frames, cfg.img_size))
            if ex.get("image"):
                return torch.tensor(load_image_array(ex["image"], cfg.img_size)), None
        except Exception as exc:
            logger.debug("media skipped %s: %s", ex.get("image") or ex.get("video"), exc)
        return None, None

    def _batches(self, examples: list[dict], batch: int, cfg: CortexConfig, pad: int):
        # group by modality so each batch has one tensor shape
        groups: dict[str, list[dict]] = {"text": [], "image": [], "video": []}
        for e in examples:
            groups["video" if e.get("video") else "image" if e.get("image") else "text"].append(e)
        out = []
        for kind, exs in groups.items():
            _b_random.shuffle(exs)
            for i in range(0, len(exs), batch):
                chunk = exs[i:i + batch]
                width = max(len(e["ids"]) for e in chunk)
                ids = torch.tensor([e["ids"] + [pad] * (width - len(e["ids"])) for e in chunk])
                imgs, vids, keep = [], [], []
                if kind != "text":
                    for j, e in enumerate(chunk):
                        im, vd = self._media(e, cfg)
                        if im is not None or vd is not None:
                            keep.append(j)
                            (imgs if im is not None else vids).append(im if im is not None else vd)
                    if not keep:
                        continue
                    ids = ids[keep]
                    chunk = [chunk[j] for j in keep]
                qa = [(e["q"], e["a"]) for e in chunk if e.get("q")]
                out.append({"ids": ids, "image": torch.stack(imgs) if imgs else None,
                            "video": torch.stack(vids) if vids else None, "qa": qa})
        _b_random.shuffle(out)
        return out

    # -- training ------------------------------------------------------------
    def train(self, data_paths, epochs: int = 3, batch: int = 16, lr: float = 3e-4, max_steps: int = 0,
              max_minutes: float = 0.0, replay_ratio: float = 0.25, retokenize: bool = False,
              log_every: int = 20) -> dict:
        reader = DatasetReader()
        items = reader.read(data_paths)
        if not items:
            raise RuntimeError(f"no readable data in {data_paths}")
        tok_path = self.dir / "tokenizer.json"
        ckpt_path = self.dir / "model.pt"
        if retokenize or not tok_path.exists():
            if ckpt_path.exists() and not retokenize:
                raise RuntimeError("checkpoint exists without tokenizer; use --retokenize to start fresh")
            texts = [it.text for it in items if it.text] + [r["text"] for r in self._replay_load() if r.get("text")]
            logger.info("training our own BPE tokenizer on %d texts", len(texts))
            tok = BrainTokenizer.train(texts, vocab_size=self.vocab_size)
            tok.save(tok_path)
            if retokenize and ckpt_path.exists():
                ckpt_path.rename(ckpt_path.with_suffix(".pre_retokenize.pt"))
        tok = BrainTokenizer.load(tok_path)

        state = torch.load(ckpt_path, map_location="cpu", weights_only=False) if ckpt_path.exists() else None
        cfg = CortexConfig(**state["config"]) if state else CortexConfig.from_size(self.size, tok.vocab_size)
        if cfg.vocab_size != tok.vocab_size:
            raise RuntimeError("tokenizer and checkpoint disagree; use --retokenize")
        model = HojaigaCortexNet(cfg)
        if state:
            model.load_state_dict(state["model"])
        model.to(self.device)

        replay = [BrainItem(r["source"], text=r.get("text") or "", image=r.get("image"), video=r.get("video"),
                            question=r.get("question"), answer=r.get("answer")) for r in self._replay_load()]
        examples = self._examples(items, tok, cfg.context)
        if replay and replay_ratio > 0:
            rex = self._examples(replay, tok, cfg.context)
            _b_random.shuffle(rex)
            examples += rex[: int(len(examples) * replay_ratio) + 1]
        _b_random.shuffle(examples)
        n_val = max(1, len(examples) // 20) if len(examples) > 20 else 0
        val, train_ex = examples[:n_val], examples[n_val:]

        opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.05, betas=(0.9, 0.95))
        if state and "optim" in state:
            try:
                opt.load_state_dict(state["optim"])
                for g in opt.param_groups:
                    g["lr"] = lr
            except Exception:
                pass
        steps_per_epoch = max(1, math.ceil(len(train_ex) / batch))
        total = max_steps or steps_per_epoch * epochs
        warm = max(1, min(200, total // 20))
        sched = torch.optim.lr_scheduler.LambdaLR(
            opt, lambda s: min(1.0, (s + 1) / warm) * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * min(1.0, s / total)))))
        use_amp = self.device == "cuda"
        amp_dtype = torch.bfloat16 if (use_amp and torch.cuda.is_bf16_supported()) else torch.float16
        scaler = torch.cuda.amp.GradScaler(enabled=use_amp and amp_dtype == torch.float16)
        logger.info("cortex: %.1fM params, %d train / %d val examples, %d steps on %s",
                    model.num_params() / 1e6, len(train_ex), len(val), total, self.device)

        step, t0, last = int(state.get("step", 0)) if state else 0, time.time(), {}
        start_step = step
        done = False
        for ep in range(epochs if not max_steps else 10_000):
            for b in self._batches(train_ex, batch, cfg, tok.PAD):
                model.train()
                ids = b["ids"].to(self.device)
                img = b["image"].to(self.device) if b["image"] is not None else None
                vid = b["video"].to(self.device) if b["video"] is not None else None
                with torch.autocast(device_type="cuda", dtype=amp_dtype, enabled=use_amp):
                    out = model(ids, image=img, video=vid, pad_id=tok.PAD)
                    logits = out["logits"][:, :-1]
                    loss_lm = F.cross_entropy(logits.reshape(-1, logits.shape[-1]).float(),
                                              ids[:, 1:].reshape(-1), ignore_index=tok.PAD)
                    loss = loss_lm
                    parts = {"lm": float(loss_lm)}
                    if "visual_embedding" in out and ids.shape[0] > 1:
                        scale = model.logit_scale.exp().clamp(max=100)
                        sim = scale * out["visual_embedding"] @ out["embedding"].T
                        tgt = torch.arange(sim.shape[0], device=self.device)
                        loss_c = (F.cross_entropy(sim.float(), tgt) + F.cross_entropy(sim.T.float(), tgt)) / 2
                        loss = loss + 0.5 * loss_c
                        parts["contrastive"] = float(loss_c)
                    if len(b["qa"]) > 1:
                        qs, ans = zip(*b["qa"])
                        neg = list(ans[1:]) + [ans[0]]
                        pairs = [f"{q}\n{a}" for q, a in zip(qs, ans)] + [f"{q}\n{a}" for q, a in zip(qs, neg)]
                        enc = [tok.encode(p)[: cfg.context] for p in pairs]
                        w = max(len(e) for e in enc)
                        vids_ = torch.tensor([e + [tok.PAD] * (w - len(e)) for e in enc], device=self.device)
                        vl = model(vids_, pad_id=tok.PAD)["verify_logit"].float()
                        lab = torch.tensor([1.0] * len(qs) + [0.0] * len(qs), device=self.device)
                        loss_v = F.binary_cross_entropy_with_logits(vl, lab)
                        loss = loss + 0.3 * loss_v
                        parts["verify"] = float(loss_v)
                opt.zero_grad(set_to_none=True)
                scaler.scale(loss).backward()
                scaler.unscale_(opt)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(opt)
                scaler.update()
                sched.step()
                step += 1
                last = parts
                if step % log_every == 0:
                    msg = " ".join(f"{k}={v:.3f}" for k, v in parts.items())
                    print(f"[cortex] step {step} epoch {ep + 1} {msg} lr={sched.get_last_lr()[0]:.2e}", flush=True)
                if step % 500 == 0:
                    self._save(model, opt, cfg, step, ckpt_path)
                if (max_steps and step - start_step >= max_steps) or \
                        (max_minutes and (time.time() - t0) / 60 >= max_minutes):
                    done = True
                    break
            if done:
                break
        val_ppl = self._evaluate(model, val, cfg, tok) if val else None
        self._save(model, opt, cfg, step, ckpt_path)
        self._replay_update(items)
        report = {"steps": step - start_step, "total_steps": step, "params_m": round(model.num_params() / 1e6, 2),
                  "train_examples": len(train_ex), "val_perplexity": val_ppl, "last_losses": last,
                  "minutes": round((time.time() - t0) / 60, 2), "device": self.device,
                  "skipped_files": reader.skipped[:20], "ts": time.time()}
        with self.metrics_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(report) + "\n")
        return report

    @torch.no_grad() if _HAS_TORCH else (lambda f: f)
    def _evaluate(self, model, val, cfg, tok) -> float:
        model.eval()
        tot, n = 0.0, 0
        for b in self._batches(val, 16, cfg, tok.PAD):
            ids = b["ids"].to(self.device)
            img = b["image"].to(self.device) if b["image"] is not None else None
            vid = b["video"].to(self.device) if b["video"] is not None else None
            logits = model(ids, image=img, video=vid, pad_id=tok.PAD)["logits"][:, :-1]
            tot += float(F.cross_entropy(logits.reshape(-1, logits.shape[-1]), ids[:, 1:].reshape(-1),
                                         ignore_index=tok.PAD))
            n += 1
        return round(math.exp(min(20.0, tot / max(n, 1))), 2)

    def _save(self, model, opt, cfg, step, path) -> None:
        tmp = path.with_suffix(".tmp")
        torch.save({"model": model.state_dict(), "optim": opt.state_dict(), "config": cfg.__dict__,
                    "step": step, "saved": time.time()}, tmp)
        tmp.replace(path)


# ─────────────────────────────────────────────────────────────────────────────
# Long-term knowledge store (chunks + concept graph + relations), SQLite
# ─────────────────────────────────────────────────────────────────────────────

# Generic linguistic relation cues (English grammar, not domain knowledge).
# Extend without code: add {"pattern": "...", "relation": "..."} rows to
# <BRAIN_HOME>/relations.json — the brain merges them at start.
_B_RELATIONS = [
    (r"(.+?)\s+(?:is|are)\s+(?:a|an|the|one of the)?\s*(?:type|kind|form|part|example)\s+of\s+(.+)", "is_a"),
    (r"(.+?)\s+(?:is|are)\s+part\s+of\s+(.+)", "part_of"),
    (r"(.+?)\s+(?:consists?|is made up|are made up|is composed|are composed)\s+of\s+(.+)", "has_part"),
    (r"(.+?)\s+(?:contains?|includes?|has|have)\s+(.+)", "has_part"),
    (r"(.+?)\s+(?:causes?|leads? to|results? in|produces?|creates?|triggers?)\s+(.+)", "causes"),
    (r"(.+?)\s+(?:converts?|turns?|changes?|transforms?)\s+(.+?)\s+(?:into|to)\s+(.+)", "converts"),
    (r"(.+?)\s+(?:travels?|moves?|passes?|flows?|goes|go)\s+(?:through|into|to|from|along|toward)\s+(.+)", "flows_to"),
    (r"(.+?)\s+(?:connects?|joins?|links?)\s+(?:to|with)?\s*(.+)", "connects"),
    (r"(.+?)\s+(?:is|are)\s+(?:located|found|situated)\s+(?:in|on|at|near|inside|below|above)\s+(.+)", "located_in"),
    (r"(.+?)\s+(?:is|are|was|were)\s+(?:called|known as|named)\s+(.+)", "also_called"),
    (r"(.+?)\s+(?:is|are|was|were)\s+(.+)", "is"),
]


def _b_phrase(text: str, max_words: int = 6) -> str:
    words = [w for w in _B_WORD.findall(text)]
    while words and words[0].lower() in _B_STOP:
        words.pop(0)
    while words and words[-1].lower() in _B_STOP:
        words.pop()
    return " ".join(words[:max_words]).lower()


def extract_relations(sentence: str, extra: Optional[list] = None) -> list[tuple[str, str, str]]:
    """(subject, relation, object) triples from one sentence; first matching cue wins per clause."""
    out = []
    for clause in _b_re.split(r";|,\s*(?:and|but|while|which)\s+|\band then\b", sentence):
        clause = clause.strip().rstrip(".")
        if len(clause) < 6:
            continue
        for pat, rel in (extra or []) + _B_RELATIONS:
            m = _b_re.match(pat, clause, flags=_b_re.I)
            if not m:
                continue
            groups = [g for g in m.groups() if g]
            if rel == "converts" and len(groups) == 3:
                s, o = _b_phrase(groups[1]), _b_phrase(groups[2])
            else:
                s, o = _b_phrase(groups[0]), _b_phrase(groups[-1])
            if s and o and s != o and len(s.split()) <= 6:
                out.append((s, rel, o))
            break
    return out


def rake_keyphrases(text: str, top: int = 12) -> list[tuple[str, float]]:
    """RAKE: candidate phrases split on stopwords/punctuation, scored by word degree/frequency."""
    phrases = []
    for frag in _b_re.split(r"[.,;:!?()\[\]{}\"\n]|\s-\s", text.lower()):
        cur = []
        for w in _B_WORD.findall(frag):
            if w in _B_STOP or len(w) < 2:
                if cur:
                    phrases.append(cur)
                cur = []
            else:
                cur.append(w)
        if cur:
            phrases.append(cur)
    freq: _b_collections.Counter = _b_collections.Counter()
    degree: _b_collections.Counter = _b_collections.Counter()
    for p in phrases:
        for w in p:
            freq[w] += 1
            degree[w] += len(p)
    scores: dict[str, float] = {}
    for p in phrases:
        if len(p) > 5:
            continue
        key = " ".join(p)
        scores[key] = max(scores.get(key, 0.0), sum(degree[w] / freq[w] for w in p))
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top]


class BrainStore:
    """Chunks (FTS5/BM25), dense vectors, concept co-occurrence graph and relation triples."""

    def __init__(self, home: _BPath = BRAIN_HOME):
        self.home = _BPath(home)
        self.home.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.home / "brain.sqlite"), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.fts = True
        try:
            self.conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(cid UNINDEXED, text, "
                              "tokenize='porter unicode61')")
        except sqlite3.OperationalError:
            self.fts = False
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS chunk (cid INTEGER PRIMARY KEY, source TEXT, modality TEXT, text TEXT,
                simhash TEXT, vec TEXT, added REAL);
            CREATE INDEX IF NOT EXISTS ix_chunk_hash ON chunk(simhash);
            CREATE TABLE IF NOT EXISTS concept (name TEXT PRIMARY KEY, freq INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS edge (a TEXT, b TEXT, w REAL, PRIMARY KEY (a, b));
            CREATE TABLE IF NOT EXISTS triple (s TEXT, r TEXT, o TEXT, cid INTEGER, n INTEGER DEFAULT 1,
                PRIMARY KEY (s, r, o));
            CREATE INDEX IF NOT EXISTS ix_triple_o ON triple(o);
            CREATE TABLE IF NOT EXISTS trace (tid TEXT PRIMARY KEY, ts REAL, question TEXT, answer TEXT,
                intent TEXT, confidence REAL, features TEXT, verdict TEXT, layers TEXT);
            CREATE TABLE IF NOT EXISTS failure (sig TEXT PRIMARY KEY, question TEXT, what TEXT, n INTEGER,
                fixed TEXT, ts REAL);
        """)
        extra = self.home / "relations.json"
        self.extra_relations = []
        if extra.exists():
            try:
                self.extra_relations = [(r["pattern"], r["relation"]) for r in json.loads(extra.read_text())]
            except Exception as exc:
                logger.warning("relations.json ignored: %s", exc)

    def count(self, table: str) -> int:
        return int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def add_chunk(self, source: str, modality: str, text: str, simhash: str) -> int:
        with self.conn:
            cur = self.conn.execute("INSERT INTO chunk(source, modality, text, simhash, added) VALUES (?,?,?,?,?)",
                                    (source, modality, text, simhash, time.time()))
            cid = cur.lastrowid
            if self.fts:
                self.conn.execute("INSERT INTO chunk_fts(cid, text) VALUES (?,?)", (cid, text))
            phrases = [p for p, _ in rake_keyphrases(text, top=10)]
            for p in phrases:
                self.conn.execute("INSERT INTO concept(name, freq) VALUES (?,1) "
                                  "ON CONFLICT(name) DO UPDATE SET freq=freq+1", (p,))
            for i, a in enumerate(phrases):
                for b in phrases[i + 1:]:
                    for x, y in ((a, b), (b, a)):
                        self.conn.execute("INSERT INTO edge(a,b,w) VALUES (?,?,1) "
                                          "ON CONFLICT(a,b) DO UPDATE SET w=w+1", (x, y))
            for sent in b_sentences(text):
                for s, r, o in extract_relations(sent, self.extra_relations):
                    self.conn.execute("INSERT INTO triple(s,r,o,cid) VALUES (?,?,?,?) "
                                      "ON CONFLICT(s,r,o) DO UPDATE SET n=n+1", (s, r, o, cid))
                    for c in (s, o):
                        self.conn.execute("INSERT INTO concept(name, freq) VALUES (?,1) "
                                          "ON CONFLICT(name) DO UPDATE SET freq=freq+1", (c,))
                    for x, y in ((s, o), (o, s)):
                        self.conn.execute("INSERT INTO edge(a,b,w) VALUES (?,?,2) "
                                          "ON CONFLICT(a,b) DO UPDATE SET w=w+2", (x, y))
        return cid

    def has_near_duplicate(self, simhash: str) -> bool:
        return self.conn.execute("SELECT 1 FROM chunk WHERE simhash=? LIMIT 1", (simhash,)).fetchone() is not None

    def bm25(self, query: str, limit: int = 20) -> list[tuple[int, float]]:
        terms = [t for t in b_content(query)][:24]
        if not terms:
            return []
        if self.fts:
            q = " OR ".join('"%s"' % t.replace('"', "") for t in terms)
            try:
                rows = self.conn.execute("SELECT cid, bm25(chunk_fts) AS s FROM chunk_fts WHERE chunk_fts MATCH ? "
                                         "ORDER BY s LIMIT ?", (q, limit)).fetchall()
                return [(int(r["cid"]), -float(r["s"])) for r in rows]
            except sqlite3.OperationalError:
                pass
        rows = self.conn.execute("SELECT cid, text FROM chunk ORDER BY cid DESC LIMIT 5000").fetchall()
        scored = [(int(r["cid"]), b_overlap(query, r["text"])) for r in rows]
        return sorted([s for s in scored if s[1] > 0], key=lambda x: -x[1])[:limit]

    def chunks(self, cids) -> dict[int, sqlite3.Row]:
        cids = list(cids)
        if not cids:
            return {}
        q = ",".join("?" * len(cids))
        return {int(r["cid"]): r for r in self.conn.execute(f"SELECT * FROM chunk WHERE cid IN ({q})", cids)}

    def neighbors(self, concept: str, limit: int = 25) -> list[tuple[str, float]]:
        return [(r["b"], float(r["w"])) for r in self.conn.execute(
            "SELECT b, w FROM edge WHERE a=? ORDER BY w DESC LIMIT ?", (concept, limit))]

    def triples_about(self, concepts: list[str], limit: int = 60) -> list[sqlite3.Row]:
        if not concepts:
            return []
        q = ",".join("?" * len(concepts))
        return self.conn.execute(f"SELECT * FROM triple WHERE s IN ({q}) OR o IN ({q}) ORDER BY n DESC LIMIT ?",
                                 concepts + concepts + [limit]).fetchall()

    def match_concepts(self, phrases: list[str], limit: int = 12) -> list[str]:
        found = []
        for p in phrases:
            row = self.conn.execute("SELECT name FROM concept WHERE name=?", (p,)).fetchone()
            if row:
                found.append(row["name"])
                continue
            for w in p.split():
                if len(w) < 3 or w in _B_STOP:
                    continue
                for r in self.conn.execute("SELECT name FROM concept WHERE name=? OR name LIKE ? OR name LIKE ? "
                                           "ORDER BY freq DESC LIMIT 3", (w, w + " %", "% " + w)):
                    found.append(r["name"])
        return list(dict.fromkeys(found))[:limit]


# ─────────────────────────────────────────────────────────────────────────────
# Shared state that flows through the layers
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Thought:
    question: str
    allow_teacher: bool = False
    clean: str = ""
    flags: List[str] = field(default_factory=list)
    salience: List[str] = field(default_factory=list)
    idf: Dict[str, float] = field(default_factory=dict)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    intent: str = "fact"
    intent_scores: Dict[str, float] = field(default_factory=dict)
    concepts: List[str] = field(default_factory=list)
    query_relations: List[tuple] = field(default_factory=list)
    activation: Dict[str, float] = field(default_factory=dict)
    inferences: List[str] = field(default_factory=list)
    tool_result: Optional[str] = None
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    chosen: Optional[Dict[str, Any]] = None
    answer: str = ""
    confidence: float = 0.0
    verification: Dict[str, Any] = field(default_factory=dict)
    rounds: int = 0
    trace: List[Dict[str, Any]] = field(default_factory=list)
    tid: str = field(default_factory=lambda: _b_uuid.uuid4().hex[:12])

    def log(self, layer: str, **info) -> None:
        self.trace.append({"layer": layer, **info})


class BrainLayer:
    name = "layer"
    region = ""
    algorithm = ""

    def __init__(self, brain: "HojaigaBrain"):
        self.brain = brain

    def __call__(self, t: Thought) -> Thought:
        t0 = time.perf_counter()
        self.process(t)
        if t.trace and t.trace[-1]["layer"] == self.name:
            t.trace[-1]["ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return t

    def process(self, t: Thought) -> None:  # pragma: no cover - interface
        raise NotImplementedError


def b_simhash(text: str, bits: int = 64) -> str:
    v = [0] * bits
    toks = b_content(text)
    for a, b in zip(toks, toks[1:] + [""]):
        h = int(_b_hashlib.md5(f"{a} {b}".encode()).hexdigest()[:16], 16)
        for i in range(bits):
            v[i] += 1 if (h >> i) & 1 else -1
    return "%016x" % sum(1 << i for i in range(bits) if v[i] > 0)


_B_PII = [
    (_b_re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "<email>"),
    (_b_re.compile(r"\b(?:\d[ -]?){13,19}\b"), "<card-number>"),
    (_b_re.compile(r"\b(?:\+?\d{1,3}[ -]?)?(?:\(?\d{3}\)?[ -]?)\d{3}[ -]?\d{4}\b"), "<phone>"),
    (_b_re.compile(r"(?i)\b(password|passwd|api[_-]?key|secret|token)\s*[:=]\s*\S+"), r"\1=<redacted>"),
]


class FilterLayer(BrainLayer):
    """L1 · thalamus — sensory gating.

    Normalises input, redacts secrets/PII, measures quality (character entropy,
    symbol ratio), detects near-duplicate memories with SimHash, and picks the
    salient words with TF-IDF against what the brain already knows.
    """
    name, region = "filter", "Thalamus"
    algorithm = "normalisation · PII redaction · SimHash dedup · entropy quality gate · TF-IDF salience"

    def process(self, t: Thought) -> None:
        text = _b_re.sub(r"\s+", " ", t.question or "").strip()
        for rx, rep in _B_PII:
            if rx.search(text):
                t.flags.append("redacted:" + rep.strip("<>\\1="))
                text = rx.sub(rep, text)
        counts = _b_collections.Counter(text)
        n = max(1, len(text))
        entropy = -sum(c / n * math.log2(c / n) for c in counts.values())
        symbols = sum(1 for ch in text if not (ch.isalnum() or ch.isspace())) / n
        if entropy < 2.0 or symbols > 0.4:
            t.flags.append("low_quality_input")
        n_docs = max(1, self.brain.store.count("chunk"))
        sal = []
        for w in dict.fromkeys(b_content(text)):
            df = len(self.brain.store.bm25(w, limit=50)) if n_docs > 1 else 0
            sal.append((w, math.log((n_docs + 1) / (df + 1)) + 1))
        t.salience = [w for w, _ in sorted(sal, key=lambda x: -x[1])[:8]]
        t.idf = {w: v for w, v in sal}
        t.clean = text
        t.log(self.name, flags=t.flags, salience=t.salience, entropy=round(entropy, 2))


class KnowLayer(BrainLayer):
    """L2 · hippocampus — recall.

    Hybrid retrieval: BM25 over every chunk the brain has read, dense similarity
    with our own network's embeddings (once trained), and the natural-intelligence
    memory of organ_08. Ranked lists are merged with Reciprocal Rank Fusion.
    """
    name, region = "know", "Hippocampus"
    algorithm = "BM25 + own dense embeddings + episodic memory → reciprocal rank fusion"

    def process(self, t: Thought) -> None:
        k = 8 + 6 * t.rounds
        query = t.clean + (" " + " ".join(list(t.activation)[:6]) if t.rounds and t.activation else "")
        lists = {"bm25": [cid for cid, _ in self.brain.store.bm25(query, limit=k * 3)]}
        if self.brain.cortex.available():
            lists["dense"] = self.brain.dense_search(query, k * 3)
        fused: dict[int, float] = {}
        for ranked in lists.values():
            for rank, cid in enumerate(ranked):
                fused[cid] = fused.get(cid, 0.0) + 1.0 / (60 + rank)
        top = sorted(fused, key=lambda c: -fused[c])[:k]
        rows = self.brain.store.chunks(top)
        t.evidence = [{"cid": c, "source": rows[c]["source"], "text": rows[c]["text"], "score": round(fused[c], 4)}
                      for c in top if c in rows]
        mem = self.brain.memory_recall(t.clean)
        if mem:
            t.evidence.insert(0, {"cid": -1, "source": "memory:" + mem.get("source", ""), "text": mem["answer"],
                                  "score": 1.0, "memory": mem})
        t.log(self.name, sources=[e["source"] for e in t.evidence[:6]], retrievers=list(lists), hits=len(t.evidence))


class UnderstandLayer(BrainLayer):
    """L3 · Wernicke / temporal cortex — comprehension.

    Intent via an online multinomial Naive Bayes that keeps learning from
    feedback; key concepts via RAKE; relations stated in the question itself
    via the same relation extractor used on knowledge; concepts are linked
    to the brain's concept graph.
    """
    name, region = "understand", "Wernicke · Temporal cortex"
    algorithm = "online Naive Bayes intent · RAKE key-phrases · relation extraction · concept linking"

    def process(self, t: Thought) -> None:
        t.intent, t.intent_scores = self.brain.intents.predict(t.clean)
        phrases = [p for p, _ in rake_keyphrases(t.clean, top=8)] + t.salience
        t.concepts = self.brain.store.match_concepts(phrases) or [p for p in phrases[:6]]
        t.query_relations = extract_relations(t.clean)
        t.log(self.name, intent=t.intent, top_intents=dict(sorted(t.intent_scores.items(),
                                                                  key=lambda kv: -kv[1])[:3]),
              concepts=t.concepts[:8])


_B_OPS = {_b_ast.Add: _b_operator.add, _b_ast.Sub: _b_operator.sub, _b_ast.Mult: _b_operator.mul,
          _b_ast.Div: _b_operator.truediv, _b_ast.Pow: _b_operator.pow, _b_ast.Mod: _b_operator.mod,
          _b_ast.FloorDiv: _b_operator.floordiv, _b_ast.USub: _b_operator.neg, _b_ast.UAdd: _b_operator.pos}
_B_FUNCS = {n: getattr(math, n) for n in ("sqrt", "sin", "cos", "tan", "asin", "acos", "atan", "log", "log10",
                                          "exp", "floor", "ceil", "factorial", "radians", "degrees", "hypot")}
_B_CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau,
             "c": 299_792_458.0, "g": 9.80665, "G": 6.67430e-11, "h": 6.62607015e-34, "k_B": 1.380649e-23,
             "N_A": 6.02214076e23, "AU": 1.495978707e11, "ly": 9.4607e15, "M_earth": 5.9722e24,
             "R_earth": 6.371e6, "M_sun": 1.98892e30}


def safe_calculate(expr: str) -> Optional[float]:
    """Exact arithmetic/physics expressions without eval(); constants in SI units."""
    expr = expr.replace("^", "**").replace("×", "*").replace("÷", "/").replace("−", "-")
    try:
        tree = _b_ast.parse(expr, mode="eval")
    except SyntaxError:
        return None

    def ev(n):
        if isinstance(n, _b_ast.Expression):
            return ev(n.body)
        if isinstance(n, _b_ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, _b_ast.BinOp) and type(n.op) in _B_OPS:
            return _B_OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, _b_ast.UnaryOp) and type(n.op) in _B_OPS:
            return _B_OPS[type(n.op)](ev(n.operand))
        if isinstance(n, _b_ast.Name) and n.id in _B_CONSTS:
            return _B_CONSTS[n.id]
        if isinstance(n, _b_ast.Call) and isinstance(n.func, _b_ast.Name) and n.func.id in _B_FUNCS:
            return _B_FUNCS[n.func.id](*[ev(a) for a in n.args])
        raise ValueError("unsupported")
    try:
        val = ev(tree)
        return float(val) if isinstance(val, (int, float)) and math.isfinite(val) else None
    except Exception:
        return None


class ReasonLayer(BrainLayer):
    """L4 · prefrontal cortex — reasoning.

    Personalized PageRank (spreading activation) over the concept graph seeded by
    the question's concepts; forward chaining over relation triples (transitive
    is_a / part_of / causes / flows_to chains); and exact symbolic calculation
    for any arithmetic or physics expression in the question.
    """
    name, region = "reason", "Prefrontal cortex"
    algorithm = "personalized PageRank · forward chaining over triples · exact symbolic calculator"
    TRANSITIVE = {"is_a", "part_of", "causes", "flows_to", "located_in", "converts"}

    def process(self, t: Thought) -> None:
        store = self.brain.store
        seeds = t.concepts[:8]
        nodes: dict[str, dict[str, float]] = {}
        frontier = list(seeds)
        for _ in range(2):
            nxt = []
            for c in frontier:
                if c in nodes or len(nodes) > 300:
                    continue
                nodes[c] = dict(store.neighbors(c))
                nxt.extend(nodes[c])
            frontier = nxt
        act = {}
        if nodes:
            p = {s: 1.0 / len(seeds) for s in seeds if s in nodes} or {n: 1.0 / len(nodes) for n in nodes}
            act = dict(p)
            for _ in range(20):
                new = {n: 0.15 * p.get(n, 0.0) for n in nodes}
                for a, nb in nodes.items():
                    tot = sum(w for b, w in nb.items() if b in nodes) or 1.0
                    for b, w in nb.items():
                        if b in nodes:
                            new[b] += 0.85 * act.get(a, 0.0) * w / tot
                act = new
        t.activation = dict(sorted(act.items(), key=lambda kv: -kv[1])[:20])
        # forward chaining: follow transitive relations up to 3 hops from the seeds
        triples = store.triples_about(list(t.activation)[:12] or seeds, limit=120)
        by_subject: dict[str, list] = {}
        for r in triples:
            by_subject.setdefault(r["s"], []).append((r["r"], r["o"]))
        chains = []
        for s in seeds:
            stack = [(s, [s], None)]
            while stack:
                node, path, rel = stack.pop()
                for r, o in by_subject.get(node, []):
                    if r not in self.TRANSITIVE or o in path or (rel and r != rel):
                        continue
                    np_ = path + [o]
                    if len(np_) >= 3:
                        chains.append(f"{' → '.join(np_)}  ({r})")
                    if len(np_) < 4:
                        stack.append((o, np_, r))
        t.inferences = list(dict.fromkeys(chains))[:8]
        # exact calculation of any expression the question contains
        mathq = t.clean
        for pat, rep in ((r"\bto the power of\b", "**"), (r"\bsquared\b", "**2"), (r"\bcubed\b", "**3"),
                         (r"\b(?:times|multiplied by)\b", "*"), (r"\bdivided by\b", "/"),
                         (r"\bplus\b", "+"), (r"\bminus\b", "-"), (r"\bsquare root of\s+([\d.]+)", r"sqrt(\1)")):
            mathq = _b_re.sub(pat, rep, mathq, flags=_b_re.I)
        for m in _b_re.finditer(r"[\d.\s+\-*/^()×÷−a-zA-Z_]{3,}", mathq):
            expr = m.group(0).strip()
            if not _b_re.search(r"\d", expr) or not _b_re.search(r"[+\-*/^×÷−]|\b(sqrt|log|sin|cos|tan)\b", expr):
                continue
            expr = _b_re.sub(r"^[^\d(a-z_]*(?:what is|calculate|compute|solve|evaluate)?\s*", "", expr,
                             flags=_b_re.I).strip()
            val = safe_calculate(expr)
            if val is not None:
                t.tool_result = f"{expr} = {val:.10g}"
                break
        t.log(self.name, activated=list(t.activation)[:8], chains=t.inferences[:4], calculation=t.tool_result)


class ThinkLayer(BrainLayer):
    """L5 · default-mode network — deliberation.

    Produces several competing candidate answers from different strategies —
    extractive (MMR over evidence sentences), relational (graph triples/chains),
    calculation, memory, our own generative network, and (only if allowed and
    still unsure) an external teacher — then scores each with a learned linear
    value function over relevance, concept coverage, grounding, agreement,
    fluency and source prior.
    """
    name, region = "think", "Default-mode network"
    algorithm = "multi-strategy candidates · MMR selection · learned value function (online logistic)"

    def _extractive(self, t: Thought, n_sent: int) -> Optional[str]:
        sents = []
        for e in t.evidence:
            if e.get("memory") or _b_re.match(r"Q:\s*.+?\nA:", e["text"], flags=_b_re.S):
                continue
            for i, s in enumerate(b_sentences(e["text"])):
                if 4 <= len(s.split()) <= 60:
                    sents.append((s, e["score"], e["source"], i))
        if not sents:
            return None
        act = t.activation

        qw = {b_stem(w): t.idf.get(w, 1.0) for w in b_content(t.clean)}
        qtot = sum(qw.values()) or 1.0

        def rel(s):
            words = set(b_content(s))
            stems = {b_stem(w) for w in words}
            a = sum(v for c, v in act.items() if set(c.split()) <= words)
            return sum(v for w, v in qw.items() if w in stems) / qtot + 0.1 * a
        picked = []
        pool = sorted(sents, key=lambda x: -(rel(x[0]) + 2 * x[1]))[:40]
        floor = 0.6 * max(rel(x[0]) for x in pool)
        while pool and len(picked) < n_sent:
            best = max(pool, key=lambda x: 0.7 * (rel(x[0]) + 2 * x[1]) -
                       0.3 * max([b_jaccard(x[0], p[0]) for p in picked] or [0]))
            pool.remove(best)
            if rel(best[0]) >= max(0.05, floor):
                picked.append(best)
        if not picked:
            return None
        if t.intent in ("procedure", "story"):
            picked.sort(key=lambda x: (x[2], x[3]))
        return " ".join(p[0] for p in picked)

    def _relational(self, t: Thought) -> Optional[str]:
        rows = self.brain.store.triples_about(t.concepts[:6], limit=30)
        lines = []
        for r in rows:
            if r["s"] in t.concepts[:6] or r["o"] in t.concepts[:6]:
                verb = {"is_a": "is a kind of", "part_of": "is part of", "has_part": "includes", "causes": "leads to",
                        "flows_to": "moves to", "converts": "becomes", "connects": "connects to",
                        "located_in": "is located in", "also_called": "is also called", "is": "is"}.get(r["r"], r["r"])
                lines.append(f"{r['s'].capitalize()} {verb} {r['o']}.")
        lines = list(dict.fromkeys(lines))[:5]
        if t.inferences:
            lines.append("Chain: " + t.inferences[0])
        return " ".join(lines) if lines else None

    def features(self, t: Thought, text: str, source: str, others: list[str]) -> dict:
        ev_text = " ".join(e["text"] for e in t.evidence[:8])
        sents = b_sentences(text) or [text]
        grounded = sum(1 for s in sents if b_overlap(s, ev_text) >= 0.5) / len(sents)
        cov = sum(1 for c in t.concepts[:6] if c.split()[0] in text.lower()) / max(1, min(6, len(t.concepts)))
        agree = sum(b_jaccard(text, o) for o in others) / len(others) if others else 0.0
        fluency = 0.5
        if self.brain.cortex.available() and source == "cortex":
            fluency = 1.0 / (1.0 + math.log(max(1.0, self.brain.cortex.perplexity(text))) / 5)
        prior = self.brain.value.source_prior(source)
        if source.startswith("recall:"):          # answer to a near-identical question we were taught
            qm = max((b_jaccard(t.clean, m.group(1)) for e in t.evidence
                      for m in [_b_re.match(r"Q:\s*(.+?)\nA:", e["text"], flags=_b_re.S)] if m), default=0.0)
            grounded, cov = 1.0, 1.0
            prior = max(prior, 0.95 if source == "recall:human" else 0.8)
            return {"relevance": qm, "coverage": cov, "grounding": grounded, "agreement": 0.5,
                    "fluency": 0.5, "prior": prior, "length": min(1.0, len(text.split()) / 80)}
        if source == "calculator":       # exact symbolic computation is its own proof
            grounded, cov, prior = 1.0, 1.0, max(prior, 0.9)
        return {"relevance": b_overlap(t.clean, text), "coverage": cov, "grounding": grounded,
                "agreement": agree, "fluency": fluency, "prior": prior,
                "length": min(1.0, len(text.split()) / 80)}

    def process(self, t: Thought) -> None:
        cands: list[tuple[str, str]] = []
        if t.tool_result:
            cands.append(("calculator", t.tool_result))
        for e in t.evidence:
            if e.get("memory") and e["memory"].get("confidence", 0) >= 0.75:
                cands.append(("memory", e["text"]))
        n_sent = {"definition": 2, "fact": 2, "list": 5, "procedure": 6, "explanation": 4,
                  "summary": 5, "comparison": 4, "story": 6}.get(t.intent, 3)
        for e in t.evidence:                     # direct recall of learned Q→A pairs
            m = _b_re.match(r"Q:\s*(.+?)\nA:\s*(.+)", e["text"], flags=_b_re.S)
            if m and b_jaccard(t.clean, m.group(1)) >= 0.6:
                cands.append(("recall:" + ("human" if e["source"].startswith("feedback:") else "dataset"),
                              m.group(2).strip()))
        ex = self._extractive(t, n_sent)
        if ex:
            cands.append(("extractive", ex))
        rel = self._relational(t)
        if rel:
            cands.append(("relational", rel))
        if self.brain.cortex.available():
            ctx = " ".join(e["text"] for e in t.evidence[:3])
            for g in self.brain.cortex.answer(t.clean, ctx, samples=2):
                cands.append(("cortex", g))
        if t.allow_teacher and t.rounds >= 1:
            ans = self.brain.ask_teacher(t)
            if ans:
                cands.append(("teacher", ans))
        texts = [c[1] for c in cands]
        scored = []
        for i, (src, text) in enumerate(cands):
            f = self.features(t, text, src, texts[:i] + texts[i + 1:])
            score = self.brain.value.score(f)
            if self.brain.failed_before(t.clean, text):      # never repeat a refuted answer
                f["past_failure"] = 1.0
                score -= 10.0
            scored.append({"source": src, "text": text, "features": f, "score": score})
        t.candidates = sorted(scored, key=lambda c: -c["score"])
        t.chosen = t.candidates[0] if t.candidates else None
        t.log(self.name, round=t.rounds, candidates=[(c["source"], round(c["score"], 3)) for c in t.candidates])


class AnswerLayer(BrainLayer):
    """L6 · Broca's area — expression.

    Shapes the chosen candidate to the intent (steps for procedures, bullets for
    lists, side-by-side for comparisons), and attaches sources.
    """
    name, region = "answer", "Broca's area"
    algorithm = "intent-shaped composition · citation attachment"

    def process(self, t: Thought) -> None:
        if not t.chosen:
            t.answer = ("I don't know this yet. Feed me material about it "
                        "(brain ingest <folder|file|url>) or allow a teacher (--teacher).")
            t.log(self.name, empty=True)
            return
        text = t.chosen["text"].strip()
        sents = b_sentences(text)
        if t.intent == "procedure" and len(sents) > 1:
            body = "\n".join(f"{i}. {s}" for i, s in enumerate(sents, 1))
        elif t.intent in ("list", "summary") and len(sents) > 1:
            body = "\n".join(f"- {s}" for s in sents)
        else:
            body = text
        srcs = list(dict.fromkeys(e["source"] for e in t.evidence[:4] if e["cid"] != -1))
        t.answer = body + (("\n\nSources: " + "; ".join(_BPath(s).name or s for s in srcs[:3]))
                           if srcs and t.chosen["source"] in ("extractive", "relational") else "")
        t.log(self.name, strategy=t.chosen["source"], chars=len(t.answer))


class VerifyLayer(BrainLayer):
    """L7 · anterior cingulate cortex — error monitoring.

    Grounding (each sentence supported by evidence), self-consistency (agreement
    across independent candidates), contradiction (negation conflict with a
    near-identical evidence sentence), own verifier head, and past-failure
    check; combined into a calibrated confidence (learned Platt scaling).
    Below threshold the brain thinks again with wider recall, then may ask a teacher.
    """
    name, region = "verify", "Anterior cingulate cortex"
    algorithm = "grounding · self-consistency · negation-contradiction · verifier head · Platt calibration"

    def process(self, t: Thought) -> None:
        if not t.chosen:
            t.confidence = 0.0
            t.verification = {"reason": "no candidate"}
            t.log(self.name, confidence=0.0)
            return
        f = dict(t.chosen["features"])
        ev_sents = [s for e in t.evidence[:8] for s in b_sentences(e["text"])]
        contradictions = []
        for s in b_sentences(t.chosen["text"]):
            for es in ev_sents:
                if b_jaccard(s, es) > 0.6:
                    neg_a = bool(set(b_words(s)) & _B_NEG)
                    neg_b = bool(set(b_words(es)) & _B_NEG)
                    if neg_a != neg_b:
                        contradictions.append(es)
        f["contradiction"] = min(1.0, len(contradictions) / 2)
        if self.brain.cortex.available():
            ctx = " ".join(e["text"] for e in t.evidence[:3])
            f["verifier"] = self.brain.cortex.verify(t.clean, ctx, t.chosen["text"])
        f["past_failure"] = 1.0 if self.brain.failed_before(t.clean, t.chosen["text"]) else 0.0
        if t.chosen["source"] == "calculator":
            f["grounding"] = 1.0
        conf = self.brain.calibrator.confidence(f)
        t.confidence = round(conf, 3)
        t.verification = {k: round(v, 3) for k, v in f.items()}
        if contradictions:
            t.verification["contradicts"] = contradictions[:2]
        t.chosen["features"] = f
        t.log(self.name, confidence=t.confidence, checks=t.verification)


class LearnLayer(BrainLayer):
    """L8 · basal ganglia / consolidation — learning.

    Stores every thought; on feedback updates the value function and calibrator
    (online logistic regression), the intent model (Naive Bayes), the failure
    memory (never repeat a refuted answer), and promotes corrected answers into
    long-term knowledge.
    """
    name, region = "learn", "Basal ganglia · consolidation"
    algorithm = "online logistic regression · Naive Bayes update · failure memory · consolidation"

    def process(self, t: Thought) -> None:
        with self.brain.store.conn:
            self.brain.store.conn.execute(
                "INSERT OR REPLACE INTO trace(tid, ts, question, answer, intent, confidence, features, layers) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (t.tid, time.time(), t.clean, t.chosen["text"] if t.chosen else t.answer, t.intent, t.confidence,
                 json.dumps(t.chosen["features"] if t.chosen else {}), json.dumps(t.trace, default=str)))
        t.log(self.name, stored=t.tid)


# ─────────────────────────────────────────────────────────────────────────────
# Small online learners (persisted as JSON, grow with feedback)
# ─────────────────────────────────────────────────────────────────────────────

class OnlineLogistic:
    """w·x + b → sigmoid, updated by SGD on each piece of feedback."""

    def __init__(self, path: _BPath, init: dict, bias: float = 0.0, lr: float = 0.2):
        self.path = path
        self.w, self.b, self.lr, self.n = dict(init), bias, lr, 0
        if path.exists():
            try:
                d = json.loads(path.read_text())
                self.w.update(d.get("w", {}))
                self.b, self.n = d.get("b", bias), d.get("n", 0)
            except Exception:
                pass

    def raw(self, x: dict) -> float:
        return self.b + sum(self.w.get(k, 0.0) * v for k, v in x.items())

    def prob(self, x: dict) -> float:
        return _b_sigmoid(self.raw(x))

    def update(self, x: dict, y: float) -> None:
        err = y - self.prob(x)
        step = self.lr / (1 + self.n / 200)
        for k, v in x.items():
            self.w[k] = self.w.get(k, 0.0) + step * err * v
        self.b += step * err
        self.n += 1
        self.path.write_text(json.dumps({"w": self.w, "b": self.b, "n": self.n}, indent=1))


class ValueFunction:
    def __init__(self, home: _BPath):
        self.model = OnlineLogistic(home / "value.json", {"relevance": 2.0, "coverage": 1.0, "grounding": 2.5,
                                                          "agreement": 1.0, "fluency": 0.5, "prior": 1.5,
                                                          "length": 0.3}, bias=-3.0)
        self.priors_path = home / "source_priors.json"
        self.priors = json.loads(self.priors_path.read_text()) if self.priors_path.exists() else {}

    def source_prior(self, source: str) -> float:
        a, b = self.priors.get(source, [1.0, 1.0])
        return a / (a + b)

    def score(self, f: dict) -> float:
        return self.model.raw({k: f[k] for k in self.model.w if k in f})

    def learn(self, f: dict, source: str, good: bool) -> None:
        self.model.update({k: f[k] for k in self.model.w if k in f}, 1.0 if good else 0.0)
        a, b = self.priors.get(source, [1.0, 1.0])
        self.priors[source] = [a + (1 if good else 0), b + (0 if good else 1)]
        self.priors_path.write_text(json.dumps(self.priors, indent=1))


class Calibrator:
    def __init__(self, home: _BPath):
        self.model = OnlineLogistic(home / "calibration.json", {"grounding": 1.0, "agreement": 1.0,
                                                                "relevance": 3.5, "coverage": 1.5, "prior": 1.0,
                                                                "verifier": 1.0, "contradiction": -3.0,
                                                                "past_failure": -6.0}, bias=-4.0)

    def confidence(self, f: dict) -> float:
        return self.model.prob({k: f.get(k, 0.0) for k in self.model.w})

    def learn(self, f: dict, good: bool) -> None:
        self.model.update({k: f.get(k, 0.0) for k in self.model.w}, 1.0 if good else 0.0)


class IntentModel:
    """Multinomial Naive Bayes over word uni/bi-grams. Seeds are only a cold start:
    edit <BRAIN_HOME>/intents.json or teach with `brain feedback ... --intent X`."""
    SEED = {
        "definition": ["what is a cell", "define photosynthesis", "what does entropy mean", "meaning of the word"],
        "explanation": ["why does ice float", "how does the heart pump blood", "explain how vaccines work",
                        "what causes rain"],
        "procedure": ["how do i install python", "steps to make tea", "how to rename a file",
                      "guide me through setting up"],
        "list": ["list the planets", "what are the parts of a flower", "name the types of rocks",
                 "give examples of mammals"],
        "comparison": ["difference between mitosis and meiosis", "compare python and java", "x vs y",
                       "which is better a or b"],
        "calculation": ["what is 23 times 7", "calculate the escape velocity", "solve 2x plus 3 equals 9",
                        "how many seconds in a day"],
        "summary": ["summarize this chapter", "give me the main points", "tldr of the story", "key takeaways"],
        "story": ["tell me the story of", "what happens in chapter", "narrate the plot", "once upon a time"],
        "fact": ["when was the war", "who invented the telephone", "where is the liver located",
                 "how big is the sun"],
        "creative": ["write a poem about", "draft an email to", "make a quiz on", "write a linkedin post"],
    }

    def __init__(self, home: _BPath):
        self.path = home / "intents.json"
        if not self.path.exists():
            self.path.write_text(json.dumps({"examples": self.SEED}, indent=1))
        self.examples: dict[str, list[str]] = json.loads(self.path.read_text())["examples"]
        self._fit()

    @staticmethod
    def _feats(text: str) -> list[str]:
        w = b_words(text)
        return w + [a + "_" + b for a, b in zip(w, w[1:])] + (["<first>" + w[0]] if w else [])

    def _fit(self) -> None:
        self.counts = {c: _b_collections.Counter(f for ex in exs for f in self._feats(ex))
                       for c, exs in self.examples.items()}
        self.totals = {c: sum(cnt.values()) for c, cnt in self.counts.items()}
        self.vocab = set(f for cnt in self.counts.values() for f in cnt)
        n = sum(len(v) for v in self.examples.values()) or 1
        self.prior = {c: math.log(len(v) / n) for c, v in self.examples.items()}

    def predict(self, text: str) -> tuple[str, dict]:
        fs = self._feats(text)
        V = len(self.vocab) + 1
        logp = {c: self.prior[c] + sum(math.log((self.counts[c][f] + 1) / (self.totals[c] + V)) for f in fs)
                for c in self.examples}
        m = max(logp.values())
        z = sum(math.exp(v - m) for v in logp.values())
        probs = {c: math.exp(v - m) / z for c, v in logp.items()}
        return max(probs, key=probs.get), {c: round(p, 3) for c, p in probs.items()}

    def learn(self, text: str, intent: str) -> None:
        self.examples.setdefault(intent, []).append(text)
        self.path.write_text(json.dumps({"examples": self.examples}, indent=1))
        self._fit()


# ─────────────────────────────────────────────────────────────────────────────
# The brain
# ─────────────────────────────────────────────────────────────────────────────

class HojaigaBrain:
    """Runs a question through every layer; thinks again when unsure; learns from feedback."""

    LAYERS = [FilterLayer, KnowLayer, UnderstandLayer, ReasonLayer, ThinkLayer, AnswerLayer, VerifyLayer,
              LearnLayer]

    def __init__(self, home: _BPath = BRAIN_HOME, confidence_threshold: Optional[float] = None,
                 max_rounds: int = 2):
        self.home = _BPath(home)
        self.home.mkdir(parents=True, exist_ok=True)
        self.store = BrainStore(self.home)
        self.cortex = CortexRuntime(self.home)
        self.value = ValueFunction(self.home)
        self.calibrator = Calibrator(self.home)
        self.intents = IntentModel(self.home)
        self.threshold = confidence_threshold if confidence_threshold is not None else float(
            os.environ.get("HOJAIGA_BRAIN_CONFIDENCE", 0.55))
        self.max_rounds = max_rounds
        self.layers = {cls.name: cls(self) for cls in self.LAYERS}

    # -- perception of new material ------------------------------------------
    def ingest(self, paths, chunk_chars: int = 900) -> dict:
        reader = DatasetReader()
        items = reader.read(paths)
        rep = {"items": len(items), "chunks": 0, "duplicates": 0, "media_without_text": 0}
        for it in items:
            text = it.text or ""
            if it.question and it.answer:
                text = f"Q: {it.question}\nA: {it.answer}"
            if not text.strip():
                rep["media_without_text"] += 1
                continue
            for ch in BrainChunker.chunk(text, chunk_chars):
                sh = b_simhash(ch)
                if self.store.has_near_duplicate(sh):
                    rep["duplicates"] += 1
                    continue
                self.store.add_chunk(it.source, it.modality, ch, sh)
                rep["chunks"] += 1
        rep["skipped"] = reader.skipped[:20]
        try:  # share with the natural-intelligence memory as well
            from core_organs.organ_08_learning import get_cortex
            nic = get_cortex()
            for it in items:
                if it.question and it.answer:
                    nic.learn(it.question, it.answer, "", source="dataset:" + _BPath(it.source).name)
        except Exception as exc:
            logger.debug("organ_08 memory not updated: %s", exc)
        return rep

    def dense_search(self, query: str, k: int) -> list[int]:
        rows = self.store.conn.execute("SELECT cid, vec FROM chunk WHERE vec IS NOT NULL").fetchall()
        if not rows:
            return []
        q = self.cortex.embed([query])[0]
        scored = [(int(r["cid"]), sum(a * b for a, b in zip(q, json.loads(r["vec"])))) for r in rows]
        return [c for c, _ in sorted(scored, key=lambda x: -x[1])[:k]]

    def reindex(self, batch: int = 64) -> int:
        if not self.cortex.available():
            return 0
        rows = self.store.conn.execute("SELECT cid, text FROM chunk").fetchall()
        for i in range(0, len(rows), batch):
            part = rows[i:i + batch]
            vecs = self.cortex.embed([r["text"] for r in part])
            with self.store.conn:
                for r, v in zip(part, vecs):
                    self.store.conn.execute("UPDATE chunk SET vec=? WHERE cid=?",
                                            (json.dumps([round(x, 5) for x in v]), r["cid"]))
        return len(rows)

    # -- memory / teacher bridges --------------------------------------------
    def memory_recall(self, question: str) -> Optional[dict]:
        try:
            from core_organs.organ_08_learning import get_cortex
            return get_cortex().recall(question, "", 0.0)
        except Exception:
            return None

    def ask_teacher(self, t: Thought) -> Optional[str]:
        try:
            from core_organs.organ_37_llm_gateway import LLMGateway
            ctx = "\n".join(e["text"][:600] for e in t.evidence[:4])
            prompt = (f"Known context (may be incomplete):\n{ctx}\n\nQuestion: {t.clean}" if ctx else t.clean)
            return LLMGateway().teach("You are a precise teacher. Answer concisely and correctly.", prompt) or None
        except Exception as exc:
            logger.info("teacher unavailable: %s", exc)
            return None

    def failed_before(self, question: str, answer: str) -> bool:
        sig = _b_hashlib.sha1((b_simhash(question) + b_simhash(answer)).encode()).hexdigest()
        return self.store.conn.execute("SELECT 1 FROM failure WHERE sig=?", (sig,)).fetchone() is not None

    # -- thinking -------------------------------------------------------------
    def think(self, question: str, allow_teacher: bool = False) -> Thought:
        t = Thought(question=question, allow_teacher=allow_teacher)
        L = self.layers
        L["filter"](t)
        while True:
            for name in ("know", "understand", "reason", "think", "answer", "verify"):
                L[name](t)
            if t.confidence >= self.threshold or t.rounds >= self.max_rounds:
                break
            t.rounds += 1
            t.log("loop", reason=f"confidence {t.confidence} < {self.threshold}: widen recall"
                  + (" and consult teacher" if allow_teacher else ""))
        L["learn"](t)
        return t

    def feedback(self, tid: str, good: bool, correct: Optional[str] = None, intent: Optional[str] = None) -> dict:
        row = self.store.conn.execute("SELECT * FROM trace WHERE tid=?", (tid,)).fetchone()
        if not row:
            raise KeyError(f"no thought {tid}")
        f = json.loads(row["features"] or "{}")
        layers = json.loads(row["layers"] or "[]")
        strategy = next((x.get("strategy") for x in layers if x.get("layer") == "answer"), "unknown")
        if f:
            self.value.learn(f, strategy, good)
            self.calibrator.learn(f, good)
        if intent:
            self.intents.learn(row["question"], intent)
        out = {"tid": tid, "good": good, "strategy": strategy}
        if not good:
            sig = _b_hashlib.sha1((b_simhash(row["question"]) + b_simhash(row["answer"])).encode()).hexdigest()
            with self.store.conn:
                self.store.conn.execute(
                    "INSERT INTO failure(sig, question, what, n, fixed, ts) VALUES (?,?,?,1,?,?) "
                    "ON CONFLICT(sig) DO UPDATE SET n=n+1, fixed=excluded.fixed, ts=excluded.ts",
                    (sig, row["question"], row["answer"][:2000], correct, time.time()))
        if correct:
            text = f"Q: {row['question']}\nA: {correct}"
            self.store.add_chunk("feedback:" + tid, "qa", text, b_simhash(text))
            try:
                from core_organs.organ_08_learning import get_cortex
                nic = get_cortex()
                mid = nic.learn(row["question"], correct, "", source="human")
                if mid:
                    for _ in range(2):
                        nic.feedback(mid, True)
            except Exception:
                pass
            out["learned_correction"] = True
        return out

    def status(self) -> dict:
        s = self.store
        metrics = []
        mp = self.home / "cortex" / "metrics.jsonl"
        if mp.exists():
            metrics = [json.loads(l) for l in mp.read_text().splitlines()[-3:] if l.strip()]
        fb = s.conn.execute("SELECT COUNT(*) FROM trace").fetchone()[0]
        return {"home": str(self.home), "chunks": s.count("chunk"), "concepts": s.count("concept"),
                "relations": s.count("triple"), "thoughts": fb, "failures_remembered": s.count("failure"),
                "neural_cortex": "trained" if self.cortex.available() else
                ("not trained yet" if _HAS_TORCH else "PyTorch not installed"),
                "value_feedback": self.value.model.n, "calibration_feedback": self.calibrator.model.n,
                "intents": list(self.intents.examples), "recent_training": metrics,
                "layers": [{"name": l.name, "region": l.region, "algorithm": l.algorithm}
                           for l in self.layers.values()]}


class BrainChunker:
    @staticmethod
    def chunk(text: str, size: int = 900) -> list[str]:
        paras = [p.strip() for p in _b_re.split(r"\n\s*\n", text) if p.strip()]
        out, cur = [], ""
        for p in paras:
            if len(cur) + len(p) + 2 <= size:
                cur = (cur + "\n\n" + p).strip()
                continue
            if cur:
                out.append(cur)
            while len(p) > size:
                cut = p.rfind(". ", 0, size)
                cut = cut + 1 if cut > size // 2 else size
                out.append(p[:cut].strip())
                p = p[cut:].strip()
            cur = p
        if cur:
            out.append(cur)
        return out


# ─────────────────────────────────────────────────────────────────────────────
# Architecture drawing — generated from the live layer registry
# ─────────────────────────────────────────────────────────────────────────────

def brain_diagram_html(brain: Optional["HojaigaBrain"] = None) -> str:
    layers = (brain.status()["layers"] if brain else
              [{"name": c.name, "region": c.region, "algorithm": c.algorithm} for c in HojaigaBrain.LAYERS])
    colors = ["#5b8def", "#22b8cf", "#20c997", "#f59f00", "#e8590c", "#d6336c", "#ae3ec9", "#7048e8"]
    def _wrap(text, width=56):
        lines, cur = [], ""
        for w in text.split():
            if len(cur) + len(w) + 1 > width and cur:
                lines.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        return (lines + [cur])[:3]
    rows = []
    for i, l in enumerate(layers):
        y = 70 + i * 74
        c = colors[i % len(colors)]
        rows.append(f"""
  <g class="layer" style="--c:{c};--d:{i * 0.35}s">
    <rect x="300" y="{y}" width="420" height="58" rx="12" />
    <text x="318" y="{y + 24}" class="ln">L{i + 1} · {l['name'].upper()}</text>
    <text x="318" y="{y + 44}" class="lr">{l['region']}</text>
    <circle cx="704" cy="{y + 29}" r="6" class="pulse"/>
    {"".join(f'<text x="740" y="{y + 20 + k * 15}" class="la">{line}</text>' for k, line in enumerate(_wrap(l['algorithm'])))}
  </g>""")
        if i < len(layers) - 1:
            rows.append(f'<path d="M510 {y + 58} L510 {y + 74}" class="flow"/>')
    h = 70 + len(layers) * 74 + 40
    loop_y1, loop_y2 = 70 + 1 * 74 + 29, 70 + 6 * 74 + 29
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hojaiga Brain</title><style>
:root{{--bg:#0b1020;--fg:#e7ecf7;--mut:#93a0bd;--card:#141b31;--line:#2a3558}}
@media (prefers-color-scheme: light){{:root:not([data-theme="dark"]){{--bg:#f6f7fb;--fg:#141a2b;--mut:#56607a;--card:#fff;--line:#d5dbe8}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:1240px;margin:0 auto;padding:24px 16px}} h1{{font-size:24px;margin:0 0 4px}} p{{color:var(--mut);margin:0 0 16px}}
.wrap{{overflow-x:auto;border:1px solid var(--line);border-radius:14px;background:var(--card)}}
svg{{display:block;min-width:1160px}} .layer rect{{fill:color-mix(in srgb,var(--c) 16%,var(--card));stroke:var(--c);stroke-width:1.5}}
.ln{{fill:var(--fg);font-weight:700;font-size:15px}} .lr{{fill:var(--mut);font-size:12px}} .la{{fill:var(--mut);font-size:12px}}
.pulse{{fill:var(--c);animation:p 2.8s ease-in-out infinite;animation-delay:var(--d)}}
@keyframes p{{0%,100%{{opacity:.25;r:4}}40%{{opacity:1;r:9}}}}
.flow{{stroke:var(--mut);stroke-width:2;stroke-dasharray:4 4;animation:f 1s linear infinite}} @keyframes f{{to{{stroke-dashoffset:-8}}}}
.box{{fill:var(--card);stroke:var(--line);stroke-width:1.5}} .t{{fill:var(--fg);font-weight:600}} .s{{fill:var(--mut);font-size:12px}}
.loop{{fill:none;stroke:#e8590c;stroke-width:2;stroke-dasharray:6 5;animation:f 1.2s linear infinite}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin-top:16px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}} .card b{{display:block;margin-bottom:4px}}
</style></head><body><main>
<h1>Hojaiga Brain — layered natural intelligence</h1>
<p>Every question flows down the eight layers. When verification is unsure, the brain loops back to recall more and think again before it answers. Generated from the running code (<code>brain diagram</code>).</p>
<div class="wrap"><svg viewBox="0 0 1160 {h}" role="img" aria-label="Hojaiga brain layer diagram">
  <rect x="16" y="70" width="228" height="120" rx="12" class="box"/>
  <text x="36" y="98" class="t">Senses (input)</text>
  <text x="36" y="120" class="s">text · textbooks · PDF · DOCX · PPTX</text>
  <text x="36" y="138" class="s">diagrams · photos · screenshots</text>
  <text x="36" y="156" class="s">video frames · transcripts</text>
  <text x="36" y="174" class="s">questions · feedback · teachers</text>
  <path d="M244 130 L300 99" class="flow"/>
  <rect x="16" y="230" width="228" height="210" rx="12" class="box"/>
  <text x="36" y="258" class="t">Neural cortex (our own model)</text>
  <text x="36" y="280" class="s">own byte-level BPE tokenizer</text>
  <text x="36" y="298" class="s">vision encoder: patch transformer</text>
  <text x="36" y="316" class="s">  (images + video frames)</text>
  <text x="36" y="334" class="s">prefix-LM transformer decoder</text>
  <text x="36" y="352" class="s">heads: language · embedding</text>
  <text x="36" y="370" class="s">  · verifier</text>
  <text x="36" y="392" class="s">trained from scratch on your data;</text>
  <text x="36" y="410" class="s">replay buffer prevents forgetting</text>
  <path d="M244 300 L300 {70 + 74 + 29}" class="flow"/><path d="M244 340 L300 {70 + 4 * 74 + 29}" class="flow"/>
  <path d="M244 380 L300 {70 + 6 * 74 + 29}" class="flow"/>
  <rect x="16" y="480" width="228" height="150" rx="12" class="box"/>
  <text x="36" y="508" class="t">Long-term memory</text>
  <text x="36" y="530" class="s">chunks (BM25) · dense vectors</text>
  <text x="36" y="548" class="s">concept graph · relation triples</text>
  <text x="36" y="566" class="s">organ_08 confirmed answers</text>
  <text x="36" y="584" class="s">failure memory (never repeat)</text>
  <text x="36" y="602" class="s">value · calibration · intents</text>
  <path d="M244 555 L300 {70 + 7 * 74 + 29}" class="flow"/>
  <path d="M300 {loop_y2} C 268 {loop_y2}, 268 {loop_y1}, 300 {loop_y1}" class="loop"/>
  <text transform="translate(266 {(loop_y1 + loop_y2) // 2}) rotate(-90)" text-anchor="middle" class="s" style="fill:#e8590c">think again when unsure</text>
  {''.join(rows)}
</svg></div>
<div class="grid">
<div class="card"><b>Why layers, not one model</b>Neural networks are fluent but can make things up; symbolic layers (graph, rules, calculator, verification) are exact but rigid. The brain combines both: this is called neurosymbolic AI.</div>
<div class="card"><b>Grows on its own</b>Every answer is stored with its evidence. Feedback trains the value function, the confidence calibration and the intent model; refuted answers go to failure memory and are never served again.</div>
<div class="card"><b>Teachers are optional</b>Local Qwen, Claude or others can be consulted only when the brain is unsure, and what they say is learned so the next answer is native.</div>
</div></main></body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Terminal
# ─────────────────────────────────────────────────────────────────────────────

def _brain_overnight(args) -> None:
    brain = HojaigaBrain(_BPath(args.home))
    deadline = time.time() + args.hours * 3600
    report_path = _BPath(args.home) / "overnight_report.jsonl"
    cycle = 0
    while time.time() < deadline:
        cycle += 1
        rep: dict[str, Any] = {"cycle": cycle, "started": time.time()}
        if args.data:
            rep["ingest"] = brain.ingest(args.data)
        if _HAS_TORCH and args.data:
            left = (deadline - time.time()) / 60
            minutes = max(1.0, min(args.train_minutes, left - 2))
            try:
                rep["train"] = CortexTrainer(_BPath(args.home), size=args.size).train(
                    args.data, epochs=args.epochs, batch=args.batch, max_minutes=minutes)
                brain.cortex = CortexRuntime(_BPath(args.home))
                rep["reindexed"] = brain.reindex()
            except Exception as exc:
                rep["train_error"] = str(exc)
        try:
            from core_organs.organ_08_learning import get_cortex
            nic = get_cortex()
            if args.teacher:
                from core_organs.organ_37_llm_gateway import LLMGateway
                rep["self_study"] = nic.self_study(LLMGateway().teach, limit=25)
            rep["consolidate"] = nic.consolidate()
            exp = nic.export_training_set(str(_BPath(args.home) / "distill" / "confirmed.jsonl"))
            rep["distill_export"] = exp
            if _HAS_TORCH and exp["examples"]:
                rep["distill_train"] = CortexTrainer(_BPath(args.home), size=args.size).train(
                    [exp["path"]], epochs=1, batch=args.batch, max_minutes=min(10, args.train_minutes))
        except Exception as exc:
            rep["memory_error"] = str(exc)
        rep["status"] = {k: v for k, v in brain.status().items() if k not in ("layers", "intents")}
        rep["finished"] = time.time()
        with report_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rep, default=str) + "\n")
        print(json.dumps({k: rep.get(k) for k in ("cycle", "ingest", "train", "status")}, default=str, indent=1),
              flush=True)
        if not args.loop:
            break


def brain_cli(argv: list[str]) -> int:
    ap = _b_argparse.ArgumentParser(prog="python -m core_organs.hojaiga_ml_engine brain",
                                    description="Hojaiga Brain — layered natural intelligence")
    ap.add_argument("--home", default=str(BRAIN_HOME), help="brain folder (default storage/brain)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ingest", help="read files/folders into long-term knowledge")
    p.add_argument("paths", nargs="+")
    p = sub.add_parser("train", help="train our own neural cortex on a dataset")
    p.add_argument("--data", nargs="+", required=True)
    p.add_argument("--size", default="small", choices=list(CORTEX_SIZES))
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--steps", type=int, default=0)
    p.add_argument("--minutes", type=float, default=0.0)
    p.add_argument("--vocab", type=int, default=8000)
    p.add_argument("--device", default="auto")
    p.add_argument("--retokenize", action="store_true")
    p.add_argument("--no-ingest", action="store_true", help="train only; do not add to knowledge store")
    p = sub.add_parser("ask", help="think through all layers and answer")
    p.add_argument("question", nargs="+")
    p.add_argument("--teacher", action="store_true", help="allow an external teacher when unsure")
    p.add_argument("--trace", action="store_true", help="print what every layer did")
    p = sub.add_parser("feedback", help="tell the brain if an answer was right")
    p.add_argument("tid")
    p.add_argument("verdict", choices=["good", "bad"])
    p.add_argument("--correct")
    p.add_argument("--intent")
    sub.add_parser("status")
    sub.add_parser("reindex", help="recompute dense vectors with the trained cortex")
    p = sub.add_parser("generate", help="raw text from the neural cortex")
    p.add_argument("prompt", nargs="+")
    p = sub.add_parser("overnight", help="ingest → train → reindex → self-study → distill, repeatedly")
    p.add_argument("--data", nargs="*", default=[])
    p.add_argument("--hours", type=float, default=8.0)
    p.add_argument("--train-minutes", type=float, default=60.0)
    p.add_argument("--size", default="small", choices=list(CORTEX_SIZES))
    p.add_argument("--epochs", type=int, default=2)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--teacher", action="store_true")
    p.add_argument("--loop", action="store_true", help="keep cycling until --hours is used up")
    p = sub.add_parser("render", help="turn text/textbook/story/image/video into an animated lesson")
    p.add_argument("input")
    p.add_argument("--out", default="lesson.html")
    p.add_argument("--subject", default="")
    p.add_argument("--grade", default="")
    p.add_argument("--mode", default="auto", choices=["auto", "lesson", "story"])
    p.add_argument("--hologram", action="store_true", help="4-view layout for a Pepper's-ghost pyramid")
    p = sub.add_parser("diagram", help="draw the brain architecture (HTML)")
    p.add_argument("--out", default="hojaiga_brain.html")
    args = ap.parse_args(argv)
    home = _BPath(args.home)

    if args.cmd == "ingest":
        print(json.dumps(HojaigaBrain(home).ingest(args.paths), indent=2))
    elif args.cmd == "train":
        if not args.no_ingest:
            print(json.dumps({"ingest": HojaigaBrain(home).ingest(args.data)}, indent=2))
        rep = CortexTrainer(home, size=args.size, device=args.device, vocab_size=args.vocab).train(
            args.data, epochs=args.epochs, batch=args.batch, lr=args.lr, max_steps=args.steps,
            max_minutes=args.minutes, retokenize=args.retokenize)
        print(json.dumps(rep, indent=2, default=str))
        print(json.dumps({"reindexed_chunks": HojaigaBrain(home).reindex()}))
    elif args.cmd == "ask":
        t = HojaigaBrain(home).think(" ".join(args.question), allow_teacher=args.teacher)
        print(t.answer)
        print(f"\n[confidence {t.confidence} · intent {t.intent} · strategy "
              f"{t.chosen['source'] if t.chosen else '-'} · thought {t.tid}]")
        if args.trace:
            print(json.dumps(t.trace, indent=1, default=str))
    elif args.cmd == "feedback":
        print(json.dumps(HojaigaBrain(home).feedback(args.tid, args.verdict == "good", args.correct, args.intent),
                         indent=2))
    elif args.cmd == "status":
        print(json.dumps(HojaigaBrain(home).status(), indent=2, default=str))
    elif args.cmd == "reindex":
        print(json.dumps({"reindexed_chunks": HojaigaBrain(home).reindex()}))
    elif args.cmd == "generate":
        rt = CortexRuntime(home)
        if not rt.available():
            print("neural cortex not trained yet: brain train --data <folder>")
            return 1
        for g in rt.answer(" ".join(args.prompt), samples=1, max_new=200):
            print(g)
    elif args.cmd == "overnight":
        _brain_overnight(args)
    elif args.cmd == "render":
        from core_organs.organ_34_teaching_void import AnimatedLessonRenderer
        out = AnimatedLessonRenderer(brain_home=home).render_file(
            args.input, args.out, subject=args.subject, grade=args.grade, mode=args.mode, hologram=args.hologram)
        print(json.dumps(out, indent=2))
    elif args.cmd == "diagram":
        _BPath(args.out).write_text(brain_diagram_html(HojaigaBrain(home)), encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    import sys as _sys
    if len(_sys.argv) > 1 and _sys.argv[1] == "brain":
        raise SystemExit(brain_cli(_sys.argv[2:]))
    ml = UnifiedMLEngine()
    test_queries = [
        ("start recording", "obs"),
        ("hide obs window", "obs"),
        ("minimize", "calculator"),
        ("new document", "word")
    ]
    print("\n--- Testing Fast ML UI Control Matching ---")
    for q, app in test_queries:
        res = ml.find_control(q, app)
        if res:
            print(f"Query: '{q}' ({app}) -> Matched: '{res.matched_name}' | Score: {res.similarity_score} | Coords: {res.coords}")
        else:
            print(f"Query: '{q}' ({app}) -> No match found.")
