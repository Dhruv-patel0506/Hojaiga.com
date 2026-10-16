"""
rag.procedures -- Sub-RAG 3: procedural workflow knowledge (DESIGN.md section 5.3). Lakhs of transcripts, manuals, guides and self-generated crawl documents, GROUNDED to commands.

    ingest_transcript(app, segments, video_id, title, ...)   caption lines -> ~25-45 s windows -> imperative steps -> command grounding -> chunks (+ procedures)
    ingest_document(app, text, source_ref, kind, ...)        markdown/text split at headings -> same pipeline
    ingest_procedure(...)                                    an already-structured procedure (a guide workflow, a skill, a crawl path)
    query(app, text, ...)                                    app-prefiltered FTS + vector (RRF), re-ranked by quality x trust x grounding in the current state
    find_procedures(app, goal)                               runnable procedures for a goal
    explore_targets(app)                                     terms that recur across sources but resolve to no known command: what the crawler should find next

No LLM is used at ingest: steps are extracted by rules (verb lexicon, quoted labels, chord regex). Nothing here is generated; every returned passage is quoted with its citation.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import config as C
from . import lt
from .lexicon import Lexicon, canon, surface, toks
from .types import Evidence, Outcome, UpsertReport

_VERBS = ("click", "double-click", "double click", "right-click", "right click", "press", "hit", "select", "choose", "open", "go to", "navigate to", "type", "enter", "drag", "drop",
          "hold", "use", "add", "create", "set", "turn on", "turn off", "toggle", "check", "uncheck", "scroll", "apply", "save", "export", "import", "tap", "pick", "insert", "switch to",
          "expand", "collapse", "extrude", "bevel", "move", "rotate", "scale", "draw", "run", "start", "stop", "close", "delete", "remove", "rename", "duplicate", "copy", "paste")
_VERB_RX = re.compile(r"^(?:(?:now|then|next|first|finally|also|and|so|just|go ahead and|you(?:'ll| will| can| need to)?|we(?:'ll| will| can)?|let's|please)\s+)*(" + "|".join(sorted((re.escape(v) for v in _VERBS), key=len, reverse=True)) + r")\b\s*(.*)$", re.I)
_CHORD = re.compile(r"\b((?:ctrl|control|alt|shift|win|cmd)(?:\s*\+\s*(?:ctrl|alt|shift|[a-z0-9]|f\d{1,2}|enter|space|tab|esc|del|home|end|up|down|left|right))+|f\d{1,2})\b", re.I)
_QUOTE = re.compile(r"[\"'“‘]([^\"'”’]{1,60})[\"'”’]")
_SENT = re.compile(r"(?<=[.!?])\s+|\n+")
_MARKERS = re.compile(r"\b(next|now|then|first|second|third|finally|step \d+|moving on|alright|okay so)\b", re.I)
_PATH_ARROW = re.compile(r"\s*(?:>|→|->|›)\s*")
_VERSION_MAJOR = re.compile(r"\d+")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def _sha(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def goal_norm(goal: str) -> str:
    return " ".join(toks(goal)) or surface(goal)


def split_sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENT.split(text or "") if s and s.strip()]


_JOIN_RX = re.compile(r"\s*(?:,\s*(?:and\s+)?(?:then\s+)?|\band\s+then\s+|\bthen\s+|\band\s+)(?=(?:" + "|".join(sorted((re.escape(v) for v in _VERBS), key=len, reverse=True)) + r")\b)", re.I)


def extract_steps(text: str, lines: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    """Imperative steps of a passage: {text, verb, target, chord, quoted, route_hint, menu_path}. Rules only; a sentence that is not an instruction yields nothing.
    `lines` (caption lines of a transcript window, which carry no punctuation) are used as the sentences when given; a sentence is further split where 'and/then' introduces another verb."""
    sents: List[str] = []
    for sent in (list(lines) if lines else split_sentences(text)):
        sents.extend(p for p in _JOIN_RX.split(sent) if p and p.strip())
    steps = []
    for sent in sents:
        m = _VERB_RX.match(re.sub(r"^[-*\d.)\s]+", "", sent.strip()))
        chord = _CHORD.search(sent)
        if not m and not chord:
            continue
        verb = (m.group(1).lower() if m else "press")
        rest = (m.group(2) if m else sent).strip(" .:;,")
        quoted = _QUOTE.findall(sent)
        target = quoted[0] if quoted else _PATH_ARROW.split(rest)[-1].strip() if _PATH_ARROW.search(rest) else re.sub(r"^(?:the|a|an|on|in|to|into|your)\s+", "", rest, flags=re.I)
        target = re.sub(r"\s+(?:button|tool|menu|tab|option|icon|field|panel|to\s+\w+.*)\b.*$", "", target, flags=re.I).strip()[:80] if not quoted else target
        hint = "hotkey" if chord else ("menu_path" if _PATH_ARROW.search(rest) else ("type" if verb in ("type", "enter") else "control_click"))
        steps.append({"text": sent.strip()[:240], "verb": verb, "target": target, "chord": re.sub(r"\s*\+\s*", "+", chord.group(1).lower()) if chord else "", "quoted": quoted, "route_hint": hint,
                      "menu_path": [p.strip() for p in _PATH_ARROW.split(rest)] if _PATH_ARROW.search(rest) else []})
    return steps


def ground_steps(lex: Lexicon, app_key: str, steps: List[Dict[str, Any]], live: Optional[Iterable[str]] = None) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """Attach command_id to each step (best Lexicon match for its target, then its quoted label, then its text). Returns (steps, mentions, unresolved_terms)."""
    mentions, unresolved = [], []
    for s in steps:
        cand = [s["target"]] + s["quoted"] + [s["text"]]
        cid, hit = None, None
        for c in cand:
            if c:
                hit = lex.best(app_key, c, live)
                if hit:
                    cid = hit.command_id
                    break
        s["command_id"] = cid
        if cid:
            mentions.append(cid)
        elif s["target"] and len(s["target"]) > 2:
            unresolved.append(surface(s["target"]))
    return steps, sorted(set(mentions)), sorted(set(unresolved))


def window_transcript(segments: Sequence[Dict[str, Any]], min_s: float = 25.0, max_s: float = 45.0, pause_s: float = 1.2) -> List[Dict[str, Any]]:
    """Merge caption lines into windows of about min_s..max_s seconds, split at a pause or a discourse marker. Each window keeps t0/t1."""
    wins, cur = [], None
    for seg in segments:
        t0 = float(seg.get("start", 0.0))
        t1 = t0 + float(seg.get("duration", 0.0))
        txt = str(seg.get("text", "")).replace("\n", " ").strip()
        if not txt:
            continue
        if cur is not None:
            dur = cur["t1"] - cur["t0"]
            gap = t0 - cur["t1"]
            if dur >= max_s or (dur >= min_s and (gap >= pause_s or _MARKERS.search(txt[:30]))):
                wins.append(cur)
                cur = None
        if cur is None:
            cur = {"t0": t0, "t1": t1, "text": txt, "lines": [txt]}
        else:
            cur["t1"] = max(cur["t1"], t1)
            cur["text"] += " " + txt
            cur["lines"].append(txt)
    if cur:
        wins.append(cur)
    return wins


def chunk_document(text: str, target_words: int = 150, max_words: int = 260) -> List[Tuple[str, str]]:
    """(heading_path, text) pieces of ~target_words. The Professor's manual_rag.chunk_markdown when importable (one chunker for the project), a faithful local one otherwise."""
    try:
        from core_organs.professor.knowledge.manual_rag import chunk_markdown
        return chunk_markdown(text, target_words, max_words)
    except Exception:
        pass
    out, path, buf = [], [], []

    def flush():
        body = " ".join(buf).strip()
        if body:
            out.append((" > ".join(p for p in path if p), body))
        buf.clear()
    for line in (text or "").splitlines():
        m = _HEADING.match(line.strip())
        if m:
            flush()
            lvl = len(m.group(1))
            path[:] = path[:lvl - 1] + [m.group(2).strip()]
            continue
        buf.append(line.strip())
        if len(" ".join(buf).split()) >= target_words and line.strip().endswith((".", "!", "?")):
            flush()
    flush()
    return out


def _major(v: str) -> str:
    m = _VERSION_MAJOR.search(v or "")
    return m.group(0) if m else ""


class Procedures:
    name = "procedure"

    def __init__(self, st, lexicon: Lexicon):
        self.st, self.lex = st, lexicon
        self._targets: Dict[Tuple[str, int, int], Tuple[int, List[str]]] = {}

    # ---- ingest -------------------------------------------------------------------------------------------------------------------------------------
    def _make_chunk(self, app_key: str, version: str, source_kind: str, source_ref: str, heading: str, text: str, trust: str, lang: str = "en", live=None, lines: Optional[Sequence[str]] = None) -> Optional[Dict[str, Any]]:
        steps = extract_steps(text, lines)
        steps, mentions, unresolved = ground_steps(self.lex, app_key, steps, live)
        if not steps:                                   # a chunk with no instruction is still knowledge, but it has nothing to ground
            m = [mm.command_id for mm in self.lex.resolve(app_key, text, live, 6)]
            mentions = sorted(set(m))
        grounded = sum(1 for s in steps if s.get("command_id")) / len(steps) if steps else (1.0 if mentions else 0.0)
        quality = C.CHUNK_QUALITY.get(source_kind, 0.5) * min(1.0, grounded + 0.3)
        step_sig = _sha(*[s["target"] or s["text"] for s in steps]) if steps else ""
        div = ""
        try:
            from core_organs.professor.knowledge import divisions
            res = divisions.classify(heading, text[:400])          # (division, score, why, matched_terms)
            div = res[0] if res and res[1] else ""
        except Exception:
            div = ""
        return {"chunk_id": _sha(source_ref, heading, surface(text)), "app_key": app_key, "app_version": version, "source_kind": source_kind, "source_ref": source_ref,
                "heading_path": heading, "text": text.strip(), "steps_json": json.dumps(steps, ensure_ascii=False), "mentions": mentions, "unresolved": unresolved,
                "division": div if isinstance(div, str) else "", "lang": lang, "trust": trust, "quality": float(round(quality, 4)), "ingested_at": time.time(),
                "extra_json": json.dumps({"step_sig": step_sig, "grounded_ratio": round(grounded, 3)}), "_grounded": grounded, "_steps": steps}

    def _finish(self, app_key: str, chunks: List[Dict[str, Any]], title: str, build_procedures: bool) -> UpsertReport:
        # near-duplicate chunks (same grounded step signature) keep one row; the extra source_refs are recorded on it
        seen: Dict[str, Dict[str, Any]] = {}
        rows, procs = [], []
        for c in chunks:
            sig = json.loads(c["extra_json"]).get("step_sig", "")
            if sig and sig in seen:
                dup = json.loads(seen[sig]["extra_json"])
                dup.setdefault("dupes", []).append(c["source_ref"])
                seen[sig]["extra_json"] = json.dumps(dup)
                continue
            if sig:
                seen[sig] = c
            rows.append(c)
        for c in rows:
            steps, grounded = c.pop("_steps"), c.pop("_grounded")
            if build_procedures and len([s for s in steps if s.get("command_id")]) >= 2:
                goal = title or c["heading_path"] or steps[0]["text"]
                pid = _sha(c["app_key"], goal_norm(goal), c["source_ref"], *[s["text"] for s in steps])
                c["procedure_id"] = pid
                procs.append({"procedure_id": pid, "app_key": c["app_key"], "app_version": c["app_version"], "goal": goal[:200], "goal_norm": goal_norm(goal),
                              "steps_json": json.dumps([{k: s[k] for k in ("text", "command_id", "route_hint", "chord", "target", "menu_path")} for s in steps], ensure_ascii=False),
                              "sources": [c["source_ref"]], "grounded_ratio": float(round(grounded, 3)), "trust": c["trust"], "last_run_ts": 0.0})
        ins, upd, deg = lt.upsert(self.st, "knowledge_chunks", rows, "text", lambda r: f"{r['heading_path']} :: {r['text']}")
        if procs:
            lt.upsert(self.st, "procedures", procs, "goal", lambda r: r["goal"])
        if len(rows) >= 500:
            lt.optimize(self.st, "knowledge_chunks")
        self.st.bump(f"proc:{app_key}")
        return UpsertReport(self.name, ins, upd, len(chunks) - len(rows), deg)

    def ingest_transcript(self, app_key: str, segments: Sequence[Dict[str, Any]], video_id: str, title: str = "", version: str = "", caption: str = "auto_caption",
                          build_procedures: bool = True) -> UpsertReport:
        chunks = []
        for w in window_transcript(segments):
            ref = f"{video_id}@{int(w['t0'])}-{int(w['t1'])}"
            c = self._make_chunk(app_key, version, "video_transcript", ref, title, w["text"], "transcript", lines=w["lines"])
            if c:
                c["quality"] = float(round(C.CHUNK_QUALITY.get(caption, 0.5) * min(1.0, c["_grounded"] + 0.3), 4))
                chunks.append(c)
        return self._finish(app_key, chunks, title, build_procedures)

    def ingest_document(self, app_key: str, text: str, source_ref: str, kind: str = "manual", title: str = "", version: str = "", trust: str = "official_doc",
                        build_procedures: bool = True) -> UpsertReport:
        chunks = []
        for i, (heading, body) in enumerate(chunk_document(text)):
            c = self._make_chunk(app_key, version, kind if kind in C.CHUNK_QUALITY else "web_doc", f"{source_ref}#{heading or i}", heading, body, trust)
            if c:
                chunks.append(c)
        return self._finish(app_key, chunks, title, build_procedures)

    def ingest_procedure(self, app_key: str, goal: str, steps: Sequence[Dict[str, Any]], source_ref: str, version: str = "", trust: str = "learned",
                         procedure_id: str = "", grounded_ratio: Optional[float] = None) -> UpsertReport:
        """A structured procedure (guide workflow, verified skill, crawl path). Steps: {text, command_id?, route_hint?, chord?, target?}."""
        steps = [dict(s) for s in steps]
        for s in steps:
            if not s.get("command_id") and (s.get("target") or s.get("text")):
                hit = self.lex.best(app_key, s.get("target") or s["text"])
                s["command_id"] = hit.command_id if hit else None
        gr = grounded_ratio if grounded_ratio is not None else (sum(1 for s in steps if s.get("command_id")) / len(steps) if steps else 0.0)
        pid = procedure_id or _sha(app_key, goal_norm(goal), source_ref, *[s.get("text", "") for s in steps])
        row = {"procedure_id": pid, "app_key": app_key, "app_version": version, "goal": goal[:200], "goal_norm": goal_norm(goal), "steps_json": json.dumps(steps, ensure_ascii=False),
               "sources": [source_ref], "grounded_ratio": float(round(gr, 3)), "trust": trust, "last_run_ts": 0.0}
        ins, upd, deg = lt.upsert(self.st, "procedures", [row], "goal", lambda r: r["goal"])
        self.st.bump(f"proc:{app_key}")
        return UpsertReport(self.name, ins, upd, 0, deg)

    # ---- query --------------------------------------------------------------------------------------------------------------------------------------
    def query(self, app_key: str, text: str, version: str = "", state_commands: Optional[Iterable[str]] = None, k: int = 4, min_quality: float = 0.0) -> List[Evidence]:
        have = set(state_commands or ())
        out: List[Tuple[float, Dict[str, Any]]] = []
        major = _major(version)
        for r in lt.search(self.st, "knowledge_chunks", text, app_key, limit=k * 3):
            if r["quality"] < min_quality:
                continue
            ment = list(r.get("mentions") or [])
            bonus = (len([m for m in ment if m in have]) / len(ment)) if (ment and have) else 0.0
            vmul = 1.0 if (not major or not r["app_version"] or _major(r["app_version"]) == major) else C.VERSION_OTHER_MULT
            score = r["_rrf"] * max(0.05, r["quality"]) * C.TRUST_W.get(r["trust"], 0.4) * (1 + 0.5 * bonus) * vmul
            out.append((score, r))
        out.sort(key=lambda x: -x[0])
        ev = []
        for score, r in out[:k]:
            ev.append(Evidence("procedure", r["app_key"], "chunk", r["text"], list(r.get("mentions") or []),
                               {"chunk_id": r["chunk_id"], "heading_path": r["heading_path"], "steps": json.loads(r["steps_json"] or "[]"), "procedure_id": r["procedure_id"],
                                "unresolved": list(r.get("unresolved") or []), "source_kind": r["source_kind"], "rrf": r["_rrf"]},
                               r["trust"], float(r["quality"]), 0.0, "allow", r["source_ref"], "", score))
        return ev

    def find_procedures(self, app_key: str, goal: str, version: str = "", k: int = 3) -> List[Evidence]:
        out = []
        major = _major(version)
        rows = lt.search(self.st, "procedures", goal, app_key, limit=k * 2)
        if rows:
            ids = ", ".join("?" for _ in rows)
            ps = {s["procedure_id"]: s for s in self.st.sql("learn").rows(f"SELECT * FROM proc_stats WHERE procedure_id IN ({ids})", [r["procedure_id"] for r in rows])}
            for r in rows:
                s_ = ps.get(r["procedure_id"])
                if s_:
                    r["n_runs"], r["n_ok"] = int(r["n_runs"]) + s_["n_runs"], int(r["n_ok"]) + s_["n_ok"]
        for r in rows:
            vmul = 1.0 if (not major or not r["app_version"] or _major(r["app_version"]) == major) else C.VERSION_OTHER_MULT
            run_rate = (r["n_ok"] + 1) / (r["n_runs"] + 2)
            steps = json.loads(r["steps_json"] or "[]")
            out.append(Evidence("procedure", r["app_key"], "procedure", r["goal"], sorted({s["command_id"] for s in steps if s.get("command_id")}),
                                {"procedure_id": r["procedure_id"], "steps": steps, "grounded_ratio": float(r["grounded_ratio"]), "n_runs": int(r["n_runs"]), "n_ok": int(r["n_ok"])},
                                r["trust"], float(round(run_rate * vmul, 4)), 0.0, "allow", (r["sources"] or [""])[0], "", r["_rrf"] * vmul))
        out.sort(key=lambda e: -e.score)
        return out[:k]

    def chunk_count(self, app_key: str) -> int:
        return int(self.st.table("knowledge_chunks").count_rows(lt.where_app(app_key))) if self.st.count("knowledge_chunks") else 0

    def explore_targets(self, app_key: str, min_sources: int = C.EXPLORE_TARGET_MIN_SOURCES, limit: int = 20) -> List[str]:
        """Unresolved terms that recur across at least min_sources DISTINCT sources: the crawler's wish list."""
        gen = self.st.gen(f"proc:{app_key}")
        ck = (app_key, min_sources, limit)
        hit = self._targets.get(ck)
        if hit and hit[0] == gen:
            return list(hit[1])
        seen: Dict[str, set] = {}
        for r in lt.fetch(self.st, "knowledge_chunks", lt.where_app(app_key), 50000, ["unresolved", "source_ref"]):
            for t in (r.get("unresolved") or []):
                seen.setdefault(t, set()).add(str(r["source_ref"]).split("@")[0].split("#")[0])
        out = [t for t, s in sorted(seen.items(), key=lambda kv: -len(kv[1])) if len(s) >= min_sources][:limit]
        self._targets[ck] = (gen, out)
        return list(out)

    # ---- learning -----------------------------------------------------------------------------------------------------------------------------------
    def observe(self, o: Outcome) -> None:
        a = o.step.args or {}
        pid = a.get("procedure_id")
        if pid:
            db = self.st.sql("learn")
            with db.lock:
                db.execute("INSERT OR IGNORE INTO proc_stats(procedure_id) VALUES(?)", (pid,))
                db.execute("UPDATE proc_stats SET n_runs=n_runs+1, n_ok=n_ok+?, last_run_ts=? WHERE procedure_id=?", (1 if o.ok else 0, time.time(), pid))
                db.commit()
        if o.ok and a.get("surface") and o.step.command_id:                    # an executed, grounded phrase becomes a known way to say the command
            self.lex.add_alias(o.app_key, str(a["surface"]), o.step.command_id, "transcript_term", "observed", "learned")
        self.st.bump(f"proc:{o.app_key}")

    def stats(self, app_key: str = "") -> Dict[str, Any]:
        return {"chunks": self.chunk_count(app_key) if app_key else self.st.count("knowledge_chunks"), "procedures": int(self.st.table("procedures").count_rows(lt.where_app(app_key))) if self.st.count("procedures") else 0}

    def forget_app(self, app_key: str) -> int:
        n = lt.drop_app(self.st, "knowledge_chunks", app_key) + lt.drop_app(self.st, "procedures", app_key)
        self.st.bump(f"proc:{app_key}")
        return n
