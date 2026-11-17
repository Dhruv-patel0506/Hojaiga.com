"""
professor.knowledge.manual_rag -- the application's USER MANUAL as retrievable, cited, layer-mapped knowledge (agentic RAG, local).

Why: with the accessibility tree giving exact names and the manual giving meaning, the heavy semantic work moves to TEXT. The vision model keeps only spatial
grounding; the language model answers from retrieved manual passages instead of from memory.

  ingest      markdown / text / html / docx (and pdf when `pypdf` is installed) from a path, or a URL the USER names. Split at headings into ~150-word chunks that
              remember their heading path ("Insert > Pictures > Online pictures"). Each chunk is mapped onto one of the SEVEN Hojaiga divisions (knowledge.divisions).
  search      hybrid: BM25 keyword score + embedding cosine (Ollama nomic-embed-text on CPU when available), fused by reciprocal rank. Results carry their citation.
  agentic     `retrieve()` is a short loop, not one lookup: search -> if the best hit is weak and a language model is reachable, have it REWRITE the question into
              two manual-style queries (users say "add an image", manuals say "Insert Picture") -> search again -> merge. Every passage returned is quoted from
              the manual with its heading path; nothing is generated here.
Nothing is downloaded unless the caller passes a URL explicitly.
"""

from __future__ import annotations

import html as _html
import json
import math
import os
import re
import sqlite3
import time
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .. import config as CFG
from . import divisions

try:
    import requests
except Exception:                                                                       # pragma: no cover
    requests = None

_WORD = re.compile(r"[a-z0-9]+")
_STOP = set("a an the of to in on for and or is it this that with as at by be are was how do i you my me can what where when which from into your".split())
MANUAL_DB = os.path.join(CFG.DATA_DIR, "manuals.db")


def _terms(text: str) -> List[str]:
    out = []
    for w in _WORD.findall((text or "").lower()):
        if w in _STOP or len(w) < 2:
            continue
        out.append(w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w)
    return out


# ------------------------------------------------------------------------------------------------------------- readers
class _Strip(HTMLParser):
    """HTML -> text that KEEPS what a procedure needs: headings as '#', ordered / unordered list items as '1.' / '-', table cells as ' | ', and the words a manual marks as interface
    terms (<b> <strong> <kbd> <code> <samp>) as **bold** - those are the control names the steps refer to."""
    _SKIP = ("script", "style", "nav", "footer", "noscript", "aside", "form", "svg", "template")
    _EMPH = ("b", "strong", "kbd", "samp", "code")

    def __init__(self) -> None:
        super().__init__()
        self.parts: List[str] = []
        self._skip = 0
        self._lists: List[List[Any]] = []
        self._emph = 0
        self._head = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._SKIP:
            self._skip += 1
            return
        if self._skip:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.parts.append("\n" + "#" * min(4, int(tag[1])) + " ")
            self._head += 1
        elif tag in ("ol", "ul"):
            self._lists.append([tag, 0])
            self.parts.append("\n")
        elif tag == "li":
            if self._lists:
                self._lists[-1][1] += 1
                self.parts.append("\n" + (f"{self._lists[-1][1]}. " if self._lists[-1][0] == "ol" else "- "))
            else:
                self.parts.append("\n- ")
        elif tag in ("p", "div", "br", "tr", "section", "article", "pre", "table", "dt", "dd"):
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append(" | ")
        elif tag in self._EMPH and not self._head:
            if self._emph == 0:
                self.parts.append("**")
            self._emph += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP:
            if self._skip:
                self._skip -= 1
            return
        if self._skip:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.parts.append("\n")
            self._head = max(0, self._head - 1)
        elif tag in ("ol", "ul"):
            if self._lists:
                self._lists.pop()
            self.parts.append("\n")
        elif tag in ("p", "li", "tr", "div", "pre", "table"):
            self.parts.append("\n")
        elif tag in self._EMPH and self._emph:
            self._emph -= 1
            if self._emph == 0:
                self.parts.append("**")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(re.sub(r"\s+", " ", data))


def read_text(path: str) -> Tuple[str, str]:
    """(text with markdown-style '#' headings, kind). Raises ValueError for formats it cannot read, saying which package would."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".md", ".markdown", ".txt", ".rst", ".json"):
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(), ext[1:]
    if ext in (".html", ".htm"):
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return _html_to_text(fh.read()), "html"
    if ext == ".docx":
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
        lines = []
        for para in re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S):
            style = re.search(r'<w:pStyle w:val="(Heading|heading|Title)(\d?)"', para)
            text = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", para, flags=re.S))
            text = _html.unescape(text).strip()
            if not text:
                continue
            if style:
                lines.append("#" * (int(style.group(2) or 1)) + " " + text)
            else:
                lines.append(text)
        return "\n".join(lines), "docx"
    if ext == ".pdf":
        try:
            import pypdf
        except Exception:
            raise ValueError("pdf needs the optional `pypdf` package (pip install pypdf)")
        r = pypdf.PdfReader(path)
        return "\n".join((pg.extract_text() or "") for pg in r.pages), "pdf"
    raise ValueError(f"unsupported manual format: {ext}")


def _html_to_text(raw: str) -> str:
    p = _Strip()
    p.feed(raw)
    t = _html.unescape("".join(p.parts)).replace("\u00b6", "").replace("\u2020", "")                # pilcrow / dagger anchors that doc generators append to headings
    t = re.sub(r"\*\*\s*\*\*", "", t)                                   # empty emphasis
    t = re.sub(r"\*\*\s+([^*\n]+?)\s*\*\*", r"**\1**", t)                  # '** Save **' -> '**Save**'
    t = re.sub(r"[ \t]+", " ", t)
    t = "\n".join(line.strip() for line in t.splitlines())
    return re.sub(r"\n{3,}", "\n\n", t).strip() + "\n"


# -------------------------------------------------------------------------------------------------------------- chunks
@dataclass
class Passage:
    text: str
    cite: str                                  # "Insert > Pictures > Online pictures"
    app: str = ""
    division: str = ""
    score: float = 0.0
    source: str = ""
    via: str = "bm25"

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


def chunk_markdown(text: str, target_words: int = 150, max_words: int = 260) -> List[Tuple[str, str]]:
    """[(heading path, chunk text)]. Headings (# ...) form the path; long sections are cut at paragraph boundaries."""
    out: List[Tuple[str, str]] = []
    stack: List[Tuple[int, str]] = []
    buf: List[str] = []

    def flush() -> None:
        # LINES are kept (a numbered procedure is a list of lines: '1. Click ... 2. Choose ...'); only the white space inside a line is collapsed
        lines = [" ".join(l.split()) for l in buf if l.strip()]
        buf.clear()
        if not lines:
            return
        path = " > ".join(h for _l, h in stack) or "(untitled)"
        if sum(len(l.split()) for l in lines) <= max_words:
            out.append((path, "\n".join(lines)))
            return
        cur: List[str] = []
        n = 0
        for ln in lines:
            pieces = [ln] if len(ln.split()) <= max_words else re.split(r"(?<=[.!?])\s+", ln)
            for pc in pieces:
                cur.append(pc)
                n += len(pc.split())
                if n >= target_words:
                    out.append((path, "\n".join(cur)))
                    cur, n = [], 0
        if cur:
            out.append((path, "\n".join(cur)))

    for line in text.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*\S)\s*$", line)
        if m:
            flush()
            lvl = len(m.group(1))
            while stack and stack[-1][0] >= lvl:
                stack.pop()
            stack.append((lvl, m.group(2).strip()))
        elif line.strip():
            buf.append(line.strip())
        else:
            if sum(len(x.split()) for x in buf) >= target_words:
                flush()
    flush()
    return out


def _embed(texts: List[str], timeout: float = 30.0) -> Optional[List[List[float]]]:
    """Ollama embeddings on CPU (num_gpu 0: the GPU belongs to the vision model). None when unavailable."""
    if requests is None or CFG.OFFLINE or not texts:
        return None
    try:
        r = requests.post(CFG.OLLAMA_URL + "/api/embed", json={"model": "nomic-embed-text", "input": texts, "options": {"num_gpu": 0}}, timeout=timeout)
        r.raise_for_status()
        e = r.json().get("embeddings")
        return e if e and len(e) == len(texts) else None
    except Exception:
        return None


# ---------------------------------------------------------------------------------------------------------------- index
class ManualIndex:
    def __init__(self, path: Optional[str] = None):
        self.path = path or MANUAL_DB
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=120, check_same_thread=False)         # the corpus builder and a live run may share the file: wait for the lock, readers never block a writer (WAL)
        try:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA busy_timeout=120000")
        except Exception:
            pass
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS docs(id INTEGER PRIMARY KEY, app TEXT, title TEXT, source TEXT UNIQUE, kind TEXT, ingested REAL, chunks INTEGER);
        CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY, doc INTEGER, ord INTEGER, cite TEXT, text TEXT, division TEXT, terms TEXT, emb BLOB);
        CREATE INDEX IF NOT EXISTS i_chunk_doc ON chunks(doc);
        """)
        self.db.commit()
        self._cache: Dict[str, Any] = {}

    # --------------------------------------------------------------------------------------------------------- ingest
    def ingest_text(self, app: str, title: str, text: str, source: str = "", kind: str = "md", embed: bool = True) -> Dict[str, Any]:
        source = source or f"text:{title}"
        t0 = time.time()
        cur = self.db.cursor()
        old = cur.execute("SELECT id FROM docs WHERE source=?", (source,)).fetchone()
        if old:
            cur.execute("DELETE FROM chunks WHERE doc=?", (old[0],))
            cur.execute("DELETE FROM docs WHERE id=?", (old[0],))
        cur.execute("INSERT INTO docs(app,title,source,kind,ingested,chunks) VALUES(?,?,?,?,?,0)", (app, title, source, kind, time.time()))
        doc = cur.lastrowid
        pieces = chunk_markdown(text)
        embs = _embed([f"{c}: {t}"[:1500] for c, t in pieces]) if (embed and pieces) else None
        by_div: Dict[str, int] = {}
        for i, (cite, body) in enumerate(pieces):
            div, _s, _r, _why = divisions.classify(cite, body)
            by_div[div] = by_div.get(div, 0) + 1
            blob = np.asarray(embs[i], np.float32).tobytes() if embs else None
            cur.execute("INSERT INTO chunks(doc,ord,cite,text,division,terms,emb) VALUES(?,?,?,?,?,?,?)",
                        (doc, i, cite, body, div, " ".join(_terms(cite + " " + cite + " " + body)), blob))
        cur.execute("UPDATE docs SET chunks=? WHERE id=?", (len(pieces), doc))
        self.db.commit()
        self._cache.clear()
        return {"ok": True, "app": app, "title": title, "chunks": len(pieces), "embedded": bool(embs), "by_division": by_div, "seconds": round(time.time() - t0, 2)}

    def ingest_path(self, app: str, path: str, embed: bool = True) -> Dict[str, Any]:
        try:
            text, kind = read_text(path)
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return self.ingest_text(app, os.path.basename(path), text, os.path.abspath(path), kind, embed)

    def ingest_url(self, app: str, url: str, embed: bool = True, timeout: float = 30.0) -> Dict[str, Any]:
        """Fetch ONE page the user named. No crawling."""
        if requests is None or CFG.OFFLINE:
            return {"ok": False, "error": "offline or requests missing"}
        try:
            r = requests.get(url, timeout=timeout, headers={"User-Agent": "hojaiga-professor/1.0 (local, user-requested)"})
            r.raise_for_status()
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:120]}"}
        ct = r.headers.get("content-type", "")
        text = _html_to_text(r.text) if "html" in ct or r.text.lstrip().startswith("<") else r.text
        return self.ingest_text(app, url.rsplit("/", 1)[-1] or url, text, url, "html" if "html" in ct else "md", embed)

    # ---------------------------------------------------------------------------------------------------------- search
    def _load(self, app: str) -> Dict[str, Any]:
        key = app or "*"
        if key in self._cache:
            return self._cache[key]
        q = "SELECT c.id, c.cite, c.text, c.division, c.terms, c.emb, d.source FROM chunks c JOIN docs d ON d.id=c.doc" + (" WHERE d.app=?" if app else "")
        rows = self.db.execute(q, (app,) if app else ()).fetchall()
        df: Dict[str, int] = {}
        lens = []
        for r in rows:
            ts = r[4].split()
            lens.append(len(ts))
            for t in set(ts):
                df[t] = df.get(t, 0) + 1
        embs = None
        if rows and all(r[5] for r in rows):
            embs = np.vstack([np.frombuffer(r[5], np.float32) for r in rows])
            embs = embs / (np.linalg.norm(embs, axis=1, keepdims=True) + 1e-9)
        self._cache[key] = {"rows": rows, "df": df, "avg": (sum(lens) / len(lens)) if lens else 1.0, "embs": embs}
        return self._cache[key]

    def search(self, question: str, app: str = "", k: int = 4, division: str = "") -> List[Passage]:
        d = self._load(app)
        rows = d["rows"]
        if not rows:
            return []
        q = _terms(question)
        n = len(rows)
        bm: List[float] = []
        for r in rows:
            ts = r[4].split()
            tf: Dict[str, int] = {}
            for t in ts:
                tf[t] = tf.get(t, 0) + 1
            s = 0.0
            for t in q:
                f = tf.get(t, 0)
                if f:
                    idf = math.log(1 + (n - d["df"].get(t, 0) + 0.5) / (d["df"].get(t, 0) + 0.5))
                    s += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * len(ts) / d["avg"]))
            bm.append(s)
        order_bm = sorted(range(n), key=lambda i: -bm[i])
        rank: Dict[int, float] = {}
        for pos, i in enumerate(order_bm[:30]):
            if bm[i] > 0:
                rank[i] = rank.get(i, 0.0) + 1.0 / (60 + pos)
        via = "bm25"
        if d["embs"] is not None:
            qe = _embed([question], 20.0)
            if qe:
                v = np.asarray(qe[0], np.float32)
                v = v / (np.linalg.norm(v) + 1e-9)
                sims = d["embs"] @ v
                for pos, i in enumerate(np.argsort(-sims)[:30]):
                    rank[int(i)] = rank.get(int(i), 0.0) + 1.0 / (60 + pos)
                via = "bm25+embedding"
        out: List[Passage] = []
        for i, sc in sorted(rank.items(), key=lambda kv: -kv[1]):
            r = rows[i]
            if division and r[3] != division:
                continue
            out.append(Passage(r[2], r[1], app, r[3], round(sc * 60 / 2, 3), r[6], via if bm[i] > 0 or via != "bm25" else "embedding"))
            if len(out) >= k:
                break
        return out

    # -------------------------------------------------------------------------------------------------------- agentic
    def retrieve(self, question: str, app: str = "", k: int = 4, brain: Any = None, rounds: int = 2) -> Dict[str, Any]:
        """Search; if weak and a language model is reachable, rewrite the question into manual-style queries and search again. Returns passages + the trail."""
        trail: List[str] = [f"search: {question}"]
        hits = self.search(question, app, k)
        best = hits[0].score if hits else 0.0
        weak = best < 0.55 or len(hits) < 2
        if weak and brain is not None and rounds > 1:
            try:
                if brain.available():
                    r = brain.generate("You help search a software user manual. Rewrite the learner's question into 2 short search queries that use the words a MANUAL would use "
                                       "(menu names, command names, feature names). Reply JSON: {\"queries\": [\"...\", \"...\"]}",
                                       f'Question: "{question}"\nApplication: {app or "unknown"}', schema={"type": "object", "properties": {"queries": {"type": "array", "items": {"type": "string"}, "maxItems": 3}},
                                                                                                           "required": ["queries"]}, max_tokens=90, temperature=0.0, timeout=40)
                    qs = (r.json or {}).get("queries") if isinstance(r.json, dict) else None
                    for q2 in (qs or [])[:3]:
                        trail.append(f"rewritten: {q2}")
                        more = self.search(str(q2), app, k)
                        seen = {p.text for p in hits}
                        for p in more:
                            if p.text not in seen:
                                hits.append(p)
                                seen.add(p.text)
                    hits.sort(key=lambda p: -p.score)
                    hits = hits[:k]
            except Exception as exc:
                trail.append(f"rewrite failed: {type(exc).__name__}")
        return {"passages": hits, "trail": trail, "weak": weak, "best": best}

    # ----------------------------------------------------------------------------------------------------------- layers
    def layer_map(self, app: str = "") -> List[Dict[str, Any]]:
        """The manual framed in the seven Hojaiga divisions: chunk counts and the top headings per layer."""
        d = self._load(app)
        tally: Dict[str, List[str]] = {}
        for r in d["rows"]:
            tally.setdefault(r[3], []).append(r[1])
        out = []
        for div in divisions.load():
            heads = tally.get(div["id"], [])
            out.append({"id": div["id"], "name": div["name"], "chunks": len(heads), "top_headings": sorted(set(heads), key=lambda h: -heads.count(h))[:5]})
        if tally.get("unclassified"):
            out.append({"id": "unclassified", "name": "Unclassified", "chunks": len(tally["unclassified"]), "top_headings": sorted(set(tally["unclassified"]))[:5]})
        return out

    def apps(self) -> List[str]:
        return [r[0] for r in self.db.execute("SELECT DISTINCT app FROM docs")]

    def close(self) -> None:
        try:
            self.db.commit()
            self.db.close()
        except Exception:
            pass


_IDX: Optional[ManualIndex] = None


def index() -> Optional[ManualIndex]:
    """The shared index, or None when no manual was ever ingested (so callers skip the feature instead of creating empty files)."""
    global _IDX
    if _IDX is None and os.path.isfile(MANUAL_DB):
        try:
            _IDX = ManualIndex()
        except Exception:
            return None
    return _IDX


def _from_rag(question: str, app: str, max_chars: int, k: int) -> Tuple[str, List["Passage"]]:
    """Fallback to the federated RAG (Sub-RAG 3: transcripts, docs, self-generated crawl documentation) for this application. ('', []) when it has nothing or is off."""
    try:
        from core_organs.rag import hooks
        return hooks.prompt_lines(question, app, max_chars, k)
    except Exception:
        return "", []


def prompt_block(question: str, app: str, brain: Any = None, k: int = 3, max_chars: int = 520) -> Tuple[str, List[Passage]]:
    """'MANUAL EXCERPTS' text for the teacher's prompt (cited, trimmed), or ('', [])."""
    ix = index()
    if ix is None or not ix.apps() or app not in ix.apps():
        return _from_rag(question, app, max_chars, k)       # an application with no guide of its own gets NO excerpts from OTHER programs' manuals; the RAG only ever answers from the app's own knowledge
    res = ix.retrieve(question, app, k, brain)
    ps: List[Passage] = res["passages"]
    if not ps:
        return _from_rag(question, app, max_chars, k)
    lines = [f"[{i}] ({p.cite}) {p.text[:max_chars]}" for i, p in enumerate(ps, 1)]
    return "MANUAL EXCERPTS (quoted from the application's user manual; prefer these over memory):\n" + "\n".join(lines), ps
