"""
app_qa -- ask anything about an application the system has learned (REA reverse engineering, static program facts, scans, vendor help pages, crawled web app) and get an answer that comes FROM that knowledge.

    python -m core_organs.mind.app_qa ask "what is the shortcut for bold in Google Docs?"
    python -m core_organs.mind.app_qa ask --app "Visual Studio Code" "how do I open the command palette?"
    python -m core_organs.mind.app_qa apps          the applications it knows, how much it knows about each

How an answer is made (no cloud, no API key):
  1. which app?   the app named in the question or by --app: matched against the machine ledger (display names), the RAG's app keys and web apps (webapp:<host>)
  2. evidence     documents about that app (REA reverse engineering, manifests, scans, help pages), commands in its lexicon, hotkeys (verified ones marked), procedures
  3. the answer   the local model (Ollama) is given ONLY that evidence and must cite it; if the model is not reachable the evidence is returned as an extractive answer
  4. honesty      each evidence line says where it came from and how far it is trusted (verified on the live app / read from the program or vendor / inferred); if nothing relevant exists the answer
                  says what was NOT found and what scan would fill it, instead of guessing
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
import time
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

LLM_URL = os.environ.get("HOJAIGA_BRAIN_URL", "http://127.0.0.1:11434/api/chat")
LLM_MODEL = os.environ.get("HOJAIGA_QA_MODEL", os.environ.get("HOJAIGA_JUDGE_MODEL", "qwen2.5:7b"))
_STOP = set("a an the of to in on for is are be do does how what which where when who why can i you it its my me and or with from this that about app application use using get make".split())
TRUST_NOTE = {"verified": "verified live", "learned": "learned from a scan", "catalog": "read from the program / vendor", "web": "read from the web", "transcript": "said in a video", "distilled": "inferred"}


def words(text: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9][a-z0-9+#.\-]*", (text or "").lower()) if w not in _STOP and len(w) > 1]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


# ---- 1 which app ------------------------------------------------------------------------------------------------------------------------------------------
def app_names(rag: Any = None, led: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """display name (normalised) -> rag app key: from the machine ledger first, then every key the RAG holds."""
    out: Dict[str, str] = {}
    if led is None:
        try:
            from core_organs.harvest import machine_sweep as MS
            led = MS.load()
        except Exception:
            led = {"entries": {}}
    for e in (led.get("entries") or {}).values():
        if e.get("rag_key") and e.get("kind") == "app" and e.get("state") != "merged":
            out[_norm(e["name"])] = e["rag_key"]
            out[_norm(re.sub(r"\s*[\(\[].*$|\s+\d[\d.]*.*$", "", e["name"]))] = e["rag_key"]
    try:                                                                            # every key the lexicon holds commands for (a scanned app may have no procedure row)
        import sqlite3
        db = sqlite3.connect(f"file:{os.path.join(r'D:' + os.sep, 'new_automation', 'data', 'ai_root', 'rag', 'lexicon.db')}?mode=ro", uri=True)
        lex_keys = [r[0] for r in db.execute("SELECT DISTINCT app_key FROM commands")]
        db.close()
        for k in lex_keys:
            out.setdefault(_norm(k.split(":")[-1]), k)
    except Exception:
        pass
    if rag is not None:
        try:
            from core_organs.rag import hybrid as HY
            for k in HY.known_keys(rag):
                host = k.split(":")[-1]
                out.setdefault(_norm(host), k)
                out.setdefault(_norm(host.split(".")[0]) if k.startswith("webapp:") else _norm(k), k)
        except Exception:
            pass
    out.pop("", None)
    return {k: v for k, v in out.items() if len(k) >= 3}


_ALIASES = {"googledocs": "webapp:docs.google.com", "docs": "webapp:docs.google.com", "googlesheets": "webapp:docs.google.com/spreadsheets", "sheets": "webapp:docs.google.com/spreadsheets",
            "googleslides": "webapp:docs.google.com/presentation", "slides": "webapp:docs.google.com/presentation", "googledrive": "webapp:drive.google.com", "gmail": "webapp:mail.google.com",
            "googlecalendar": "webapp:calendar.google.com", "vscode": "visual_studio_code", "chrome": "google_chrome", "msword": "word", "msexcel": "excel", "mspaint": "paint"}


def find_app(question: str, hint: str = "", names: Optional[Dict[str, str]] = None, rag: Any = None) -> List[Tuple[str, str, float]]:
    """[(display, rag_key, score)] best first. The hint (--app) wins; otherwise the longest app name found in the question."""
    names = names if names is not None else app_names(rag)
    cands: Dict[str, Tuple[str, float]] = {}
    q = _norm(question)
    if hint:
        h = _norm(hint)
        if h in _ALIASES:
            cands[_ALIASES[h]] = (hint, 3.0)
        for n, k in names.items():
            if n == h:
                cands[k] = (hint, 3.0)
            elif h in n or n in h:
                cands.setdefault(k, (hint, 2.0 + min(len(n), len(h)) / max(len(n), len(h))))
        return sorted(((d, k, s) for k, (d, s) in cands.items()), key=lambda x: -x[2])[:4]
    toks = [_norm(t) for t in re.findall(r"[A-Za-z0-9.+#]+", question)]
    grams = {"".join(toks[i:i + n]) for n in (1, 2, 3) for i in range(len(toks) - n + 1)}
    for g in grams:
        if g in _ALIASES:
            cands[_ALIASES[g]] = (g, 2.5 + len(g) / 40)
    for n, k in names.items():
        if len(n) >= 4 and n in grams:
            cands[k] = (n, max(cands.get(k, ("", 0))[1], 2.0 + len(n) / 40))
        elif len(n) >= 5 and n in q:
            cands.setdefault(k, (n, 1.0 + len(n) / 40))
    return sorted(((d, k, s) for k, (d, s) in cands.items()), key=lambda x: -x[2])[:4]


# ---- 2 evidence -----------------------------------------------------------------------------------------------------------------------------------------
def _overlap(want: Sequence[str], text: str) -> float:
    have = set(words(text))
    if not want:
        return 0.0
    return sum(1 for w in want if w in have or any(len(w) >= 4 and len(h) >= 4 and (h.startswith(w[:4]) or w.startswith(h[:4])) for h in have)) / len(want)


def evidence(rag: Any, keys: Sequence[str], question: str, k: int = 10) -> List[Dict[str, Any]]:
    from core_organs.rag import lt
    st = rag.proc.st
    want = words(question)
    pool: List[Dict[str, Any]] = []
    for kind, table in (("document", "knowledge_chunks"), ("procedure", "procedures")):
        try:
            rows = lt.search(st, table, question, list(keys), limit=k * 2)
        except Exception:
            rows = []
        for r in rows:
            if kind == "document":
                txt = (r.get("heading_path") or "") + " " + (r.get("text") or "")
                src = f"{r.get('source_kind', '')}:{str(r.get('source_ref', ''))[:40]}"
            else:
                try:
                    steps = " -> ".join(str(s.get("text", "")) for s in json.loads(r.get("steps_json") or "[]")[:8])
                except Exception:
                    steps = ""
                txt = f"{r.get('goal', '')}: {steps}"
                src = "procedure"
            ov = _overlap(want, txt)
            pool.append({"kind": kind, "text": re.sub(r"\s+", " ", txt).strip()[:900], "source": src, "trust": r.get("trust") or "", "app": r.get("app_key"), "score": float(r.get("_rrf", 0.0)) + 0.5 * ov, "overlap": round(ov, 2)})
    generic = {"keyboard", "shortcut", "shortcuts", "key", "keys", "hotkey", "hotkeys", "press", "command", "chord", "combination", "short", "cut"}
    app_words = {w for k_ in keys for w in words(k_.replace("webapp:", "").replace("_", " ").replace(".", " "))}
    core = [w for w in want if w not in generic and w not in app_words and w not in ("google", "microsoft")]
    try:                                                                            # hotkeys: the exact chord for an action is the most useful single fact
        for fp in rag.fast._overlay(lt.fetch(rag.fast.st, "fast_paths", lt.where_app(list(keys)), 3000)):
            ov = _overlap(core or want, fp.get("task_pattern", ""))
            if ov >= 0.5:
                pool.append({"kind": "hotkey", "text": f"{fp.get('task_pattern')}: press {fp.get('payload')}", "source": str(fp.get("source", "")), "trust": "verified" if fp.get("verified") else (fp.get("trust") or ""),
                             "app": fp.get("app_key"), "score": 0.5 + ov, "overlap": round(ov, 2)})
    except Exception:
        pass
    try:                                                                            # commands of the app that mention the question's words
        from core_organs.rag import hybrid as HY
        import sqlite3
        db = sqlite3.connect(f"file:{os.path.join(r'D:' + os.sep, 'new_automation', 'data', 'ai_root', 'rag', 'lexicon.db')}?mode=ro", uri=True)
        for key in keys:
            labs = [r[0] for r in db.execute("SELECT label FROM commands WHERE app_key=?", (key,))]
            hit = [(l, _overlap(want, l)) for l in labs]
            hit = sorted([(l, o) for l, o in hit if o >= 0.5], key=lambda x: -x[1])[:6]
            if hit:
                pool.append({"kind": "commands", "text": f"commands found in the app: {'; '.join(l for l, _ in hit)} (of {len(labs)} known)", "source": "lexicon", "trust": "learned", "app": key, "score": 0.4 + hit[0][1], "overlap": round(hit[0][1], 2)})
        db.close()
    except Exception:
        pass
    pool.sort(key=lambda x: -x["score"])
    seen, out = set(), []
    for p in pool:
        sig = p["text"][:80]
        if sig in seen:
            continue
        seen.add(sig)
        out.append(p)
    return out[:k]


def overview(rag: Any, keys: Sequence[str]) -> Dict[str, Any]:
    from core_organs.rag import lt
    st = rag.proc.st
    out: Dict[str, Any] = {}
    for key in keys:
        n_doc = len(lt.fetch(st, "knowledge_chunks", lt.where_app(key), 5000, ["chunk_id"]))
        n_proc = len(lt.fetch(st, "procedures", lt.where_app(key), 5000, ["procedure_id"]))
        n_hot = len(lt.fetch(rag.fast.st, "fast_paths", lt.where_app(key), 5000, ["fast_id"]))
        out[key] = {"documents": n_doc, "procedures": n_proc, "hotkeys": n_hot}
    return out


# ---- 3 the answer --------------------------------------------------------------------------------------------------------------------------------------
_EYE = {"t": 0.0, "up": False}


def eye_chat(system: str, prompt: str, timeout: float = 90.0, max_tokens: int = 420, json_mode: bool = False) -> Optional[str]:
    """The text turn on the big vision model (:8081, Qwen3-VL-8B) while it is up: it holds the GPU, so a second model in Ollama would run on the CPU (measured
    Oct-28: a screen check took 120 s with qwen2.5:7b squeezed out). OFF unless HOJAIGA_BRAIN_ON_EYE=1: measured the same day, with 20 of its layers on the 6 GB GPU it
    was no faster (70-150 s) and, as the judge, called 'the Wikipedia article on Alan Turing' missing from its own description of that page. None when off, down or hot."""
    if os.environ.get("HOJAIGA_BRAIN_ON_EYE", "0") != "1":
        return None
    url = os.environ.get("HOJAIGA_BIG_EYE_URL", "http://127.0.0.1:8081")
    if time.time() - _EYE["t"] > 30:
        _EYE["t"] = time.time()
        try:
            with urllib.request.urlopen(url + "/health", timeout=1.5) as r:
                _EYE["up"] = r.status == 200
        except Exception:
            _EYE["up"] = False
    if not _EYE["up"]:
        return None
    with contextlib.suppress(Exception):
        from core_organs import hojaiga_run as HR
        if HR.gpu_hot():
            return None
    body: Dict[str, Any] = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    try:
        req = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
        return (((d.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip() or None
    except Exception:
        _EYE["up"] = False
        return None


def ask_llm(prompt: str, system: str, timeout: float = 90.0, private: bool = False, model: str = "", max_tokens: int = 420, json_mode: bool = False) -> Optional[str]:
    """The local model, with the gateway's free hosted models first (HOJAIGA_CLOUD=first) or when the local one does not answer (fallback).
    private=True (the person's own messages) never leaves the machine."""
    try:
        from core_organs import organ_37_llm_gateway as GW
    except Exception:
        GW = None
    if GW is not None and GW.cloud_mode() == "first":
        out = GW.cloud_chat(system, prompt, temperature=0.1, timeout=timeout, private=private)
        if out:
            return out
    if not model:
        out = eye_chat(system, prompt, timeout, max_tokens, json_mode)
        if out:
            return out
    body = {"model": model or LLM_MODEL, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}], "stream": False, "options": {"temperature": 0.1, "num_predict": max_tokens}}
    if json_mode:
        body["format"] = "json"                                                                       # the local model's output is held to valid JSON (a 7B planner appended a second object after the first)
    try:
        req = urllib.request.Request(LLM_URL, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
        out = (d.get("message", {}).get("content") or d.get("response") or "").strip() or None
    except Exception:
        out = None
    if out is None and GW is not None and GW.cloud_mode() == "fallback":
        out = GW.cloud_chat(system, prompt, temperature=0.1, timeout=timeout, private=private)
    return out


SYSTEM = ("You answer questions about a software application using ONLY the numbered evidence given. Cite the evidence numbers like [2] after each claim. "
          "If the evidence does not contain the answer, reply with exactly 'NOT IN EVIDENCE: ' followed by what is missing, and nothing else: no general advice, no guesses, never invent menus, shortcuts or steps. "
          "Keep it short and practical.")


def grounded(text: str, n_evidence: int) -> Tuple[bool, str]:
    """(ok, why). A usable answer cites at least one piece of evidence that exists; 'NOT IN EVIDENCE' is an honest 'no'; anything else is not trusted."""
    t = (text or "").strip()
    if t.upper().startswith("NOT IN EVIDENCE"):
        return False, "not_in_evidence"
    cites = [int(x) for x in re.findall(r"\[(\d{1,2})\]", t)]
    if len(re.sub(r"\[\d{1,2}\]|[\s.,;:\-]", "", t)) < 8:
        return False, "empty_answer"                                  # measured: the model once answered with the bare citation '[3]'
    if not cites:
        return False, "no_citation"
    if any(c < 1 or c > n_evidence for c in cites):
        return False, "cites_missing_evidence"
    return True, ""


def answer(question: str, app: str = "", rag: Any = None, llm: Optional[Callable[[str, str], Optional[str]]] = None, names: Optional[Dict[str, str]] = None, k: int = 8) -> Dict[str, Any]:
    if rag is None:
        from core_organs import rag as R
        rag = R.get_rag()
    names = names if names is not None else app_names(rag)
    found = find_app(question, app, names, rag)
    if not found:
        return {"answer": "I could not tell which application you mean. Name it (for example 'in Blender' or 'in Google Docs').", "app": None, "evidence": [], "confidence": 0.0, "used_llm": False}
    keys = []
    for _d, key, _s in found[:3]:
        if key not in keys:
            keys.append(key)
    top = keys[0]                                                                    # the same product is filed under several keys (blender / blender_3d / blender_5_2; a web app's sub-areas): ask all of them
    if not top.startswith(("web:", "webapp:")):
        first = _norm(top.split("_")[0])
        if len(first) >= 4:
            keys += [k2 for k2 in sorted(set(names.values())) if k2 not in keys and not k2.startswith(("web:", "webapp:")) and _norm(k2).startswith(first)][:6]
    else:
        host = top.split(":", 1)[1].split("/")[0]
        keys += [k2 for k2 in sorted(set(names.values())) if k2 not in keys and k2.startswith("webapp:" + host)][:6]
    ev = evidence(rag, keys, question, k)
    ov = overview(rag, keys[:1])
    usable = [e for e in ev if e["overlap"] >= 0.25 or e["kind"] == "hotkey"]
    conf = round(min(1.0, (sum(e["overlap"] for e in usable[:4]) / 2.0) + (0.2 if any(e["trust"] == "verified" for e in usable) else 0)), 2)
    head = {"app": found[0][0], "rag_key": keys[0], "known": ov.get(keys[0], {}), "confidence": conf}
    if not usable:
        known = ov.get(keys[0], {})
        return {**head, "answer": (f"I know {found[0][0]} ({known.get('documents', 0)} documents, {known.get('procedures', 0)} procedures, {known.get('hotkeys', 0)} shortcuts) but nothing in it answers this. "
                                   f"To learn it: reverse engineer the program (rea_sweep) or scan it live; a vendor help page for it would also help."), "evidence": [], "used_llm": False}
    numbered = "\n".join(f"[{i}] ({e['kind']}, {TRUST_NOTE.get(e['trust'], e['trust'] or 'unrated')}) {e['text']}" for i, e in enumerate(usable, 1))
    prompt = f"Application: {found[0][0]}\nQuestion: {question}\n\nEvidence:\n{numbered}\n\nAnswer using only the evidence, citing [n]."
    text = (llm or ask_llm)(prompt, SYSTEM)
    used = bool(text)
    note = ""
    if text:
        ok, why = grounded(text, len(usable))
        if not ok:
            used = False
            if why == "not_in_evidence":
                known = ov.get(keys[0], {})
                return {**head, "confidence": min(conf, 0.3), "used_llm": True, "not_found": True, "evidence": [{"n": i, **e} for i, e in enumerate(usable, 1)],
                        "answer": f"I could not find that in what I learned about {found[0][0]} ({known.get('documents', 0)} documents, {known.get('procedures', 0)} procedures, {known.get('hotkeys', 0)} shortcuts). "
                                  f"{text.split(':', 1)[-1].strip()} Reverse engineering or scanning it more would fill this in."}
            note = f"(the model's answer was not used because it {'said nothing' if why == 'empty_answer' else ('cited nothing' if why == 'no_citation' else 'cited evidence that does not exist')}) "
            text = None
    if not text:
        text = note + "Here is what I know (this is the evidence itself):\n" + "\n".join(f"- [{i}] {e['text'][:300]}" for i, e in enumerate(usable[:5], 1))
    return {**head, "answer": text, "evidence": [{"n": i, **e} for i, e in enumerate(usable, 1)], "used_llm": used}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["ask", "apps"])
    ap.add_argument("question", nargs="?", default="")
    ap.add_argument("--app", default="")
    a = ap.parse_args(argv)
    from core_organs import rag as R
    rag = R.get_rag()
    if a.cmd == "apps":
        names = app_names(rag)
        keys = sorted(set(names.values()))
        print(len(keys), "app keys")
        for key in keys[:400]:
            ov = overview(rag, [key])[key]
            if ov["documents"] or ov["procedures"] or ov["hotkeys"]:
                print(f"{key}: {ov}")
        return 0
    r = answer(a.question, a.app, rag)
    print(json.dumps({k: v for k, v in r.items() if k != "evidence"}, indent=1, ensure_ascii=False))
    for e in r.get("evidence", [])[:6]:
        print(f"  [{e['n']}] {e['kind']} / {e['trust']} / {e['source']}: {e['text'][:160]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
