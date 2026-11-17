"""
hojaiga_run -- ONE command that boots what is needed and does a task, however it is worded.

    hojaiga.bat "go to the Pricing page on todoist.com"
    hojaiga.bat "what is the shortcut for bold in Google Docs?"
    hojaiga.bat "write a LinkedIn post about launching our app; then reply to Priya's email"
    hojaiga.bat --boot-only            health of every service and the knowledge it will use
    hojaiga.bat --yes "<task>"         the person approves the risky controls named in this task (pay / send / delete ...); without it the task stops and asks

The pipeline (each stage is a module that can be tested alone; nothing here names an app):
  1 BOOT      Ollama (the local language model) up, the RAG opens, REA ready, the machine ledger read; what is missing is said, a missing Ollama is started
  2 INTAKE    task_intake: secrets removed, the task split into tickets, each ticket's domain (web / desktop), impossible things refused at the door, ONE question when nothing is named
  3 ROUTE     each ticket becomes one of: QUESTION (answered from what was learned about the app), WRITE (a draft in the right language / register / length for the reader), WEB (done on the site),
              DESKTOP (done in the app, hidden window), and tickets that are follow-ups on the same site share ONE browser session
  4 THINK     mind.brain: is the plan itself risky (delete all, send, pay)? then it stops and asks BEFORE anything runs. --resume continues the last run's unfinished tickets (finished ones are not redone)
  5 DO        the executor for that route (web_executor / task_lifecycle / app_qa / writer) with the RAG knowledge (stored procedures, shortcuts, REA findings); independent web / question / write tickets
              run side by side, desktop tickets one after the other
  6 PROVE     a ticket is DONE only when the executor checked it on the page / file / window; weak evidence is UNVERIFIED; nothing is claimed that was not checked
  7 LEARN     what worked is filed back into the RAG (a path that worked becomes a stored procedure); the whole run is written to data/hojaiga_runs/<id>/report.json
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import contextlib
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

DATA = os.environ.get("HOJAIGA_DATA", os.path.join("D:" + os.sep, "new_automation", "data"))
RUNS = os.path.join(DATA, "hojaiga_runs")
OLLAMA = os.environ.get("HOJAIGA_OLLAMA", "http://127.0.0.1:11434")
QA_MODEL = os.environ.get("HOJAIGA_QA_MODEL", os.environ.get("HOJAIGA_JUDGE_MODEL", "qwen2.5:7b"))


# ---- 1 boot ----------------------------------------------------------------------------------------------------------------------------------------------------
def _get(url: str, timeout: float = 2.5) -> Optional[Dict[str, Any]]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except Exception:
        return None


def boot(start_missing: bool = True, say=print) -> Dict[str, Any]:
    """One honest line per service: ready / degraded / absent. A missing Ollama is started (hidden); GPU services are only reported, never started unasked."""
    h: Dict[str, Any] = {}
    tags = _get(OLLAMA + "/api/tags")
    if tags is None and start_missing:
        with contextlib.suppress(Exception):
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
            for _ in range(20):
                time.sleep(1)
                tags = _get(OLLAMA + "/api/tags")
                if tags is not None:
                    break
    models = [m.get("name", "") for m in (tags or {}).get("models", [])]
    have = any(m.startswith(QA_MODEL.split(":")[0]) for m in models)
    h["ollama"] = {"status": "ready" if tags is not None and have else ("degraded" if tags is not None else "absent"), "models": models[:8], "wants": QA_MODEL}
    try:
        from core_organs import rag as R
        from core_organs.rag import lt
        rag = R.get_rag()
        h["rag"] = {"status": "ready", "documents": int(rag.proc.st.count("knowledge_chunks")), "procedures": int(rag.proc.st.count("procedures")), "hotkeys": int(rag.fast.st.count("fast_paths"))}
    except Exception as e:
        h["rag"] = {"status": "absent", "error": f"{type(e).__name__}: {str(e)[:100]}"}
    try:
        from core_organs import rea_bridge as RB
        h["rea"] = {"status": "ready" if RB.available() else "absent"}
    except Exception:
        h["rea"] = {"status": "absent"}
    try:
        from core_organs.harvest import machine_sweep as MS
        led = MS.load()
        ent = led.get("entries", {})
        h["machine_ledger"] = {"status": "ready" if ent else "absent", "apps": sum(1 for e in ent.values() if e.get("kind") == "app" and e.get("state") != "merged"),
                               "reverse_engineered": sum(1 for e in ent.values() if (e.get("rea") or {}).get("kinds"))}
    except Exception:
        h["machine_ledger"] = {"status": "absent"}
    h["vision_server"] = {"status": "ready" if _get("http://127.0.0.1:8081/health") is not None else "not started (optional; GPU)"}
    h["picker_adapter"] = {"status": "ready" if _get(os.environ.get("HOJAIGA_PICKER_URL", "http://127.0.0.1:11500") + "/health") is not None else "not started (optional; GPU)"}
    try:
        import playwright  # noqa: F401
        h["browser"] = {"status": "ready"}
    except Exception:
        h["browser"] = {"status": "absent"}
    for k, v in h.items():
        say(f"  [{v['status'].split(' ')[0].upper():<8}] {k}: " + ", ".join(f"{a}={b}" for a, b in v.items() if a != "status" and b not in ("", None, []))[:150])
    h["ok"] = all(h[k]["status"] == "ready" for k in ("ollama", "rag", "browser"))
    return h


_CMD_START = re.compile(r"^(open|click|press|go|navigate|type|enter|fill|search|select|add|create|draw|save|close|run|launch|start|delete|remove|send|submit|book|buy|order|download|upload|post|publish|write|draft|compose|"
                        r"prepare|reply|respond|find|show|what|how|where|which|who|why|when|can|could|does|do|is|are|explain|tell|teach|list|give|take|make|set|change|rename|copy|paste|move|check|read|summari[sz]e|"
                        r"translate|schedule|call|email|mail|message|text|play|stop|pause|turn|switch|log|sign|visit|use|apply|install|update|export|import|print|scroll|zoom|rotate|scan|learn|reverse|in|on|at|from|"
                        r"please|then|also|and)\b", re.I)


def split_parts(text: str) -> List[str]:
    """A task with several parts becomes several tickets: ';', a new line, 'then', 'and then', 'after that', 'next', 'finally'. The intake's own splitting only handles lists, and a part that is not split
    off is a part that is silently never done. A piece that does not start like a command ('helps people use it') is the rest of the previous sentence, not a new task."""
    pieces = re.split(r"(\s*(?:;|\n|\band then\b|\bthen\b|\bafter that\b|\bnext\b,?|\bfinally\b,?|\balso\b,?)\s*)", text or "", flags=re.I)
    parts: List[str] = []
    glue = ""
    for i, piece in enumerate(pieces):
        if i % 2 == 1:
            glue = piece
            continue
        pc = piece.strip(" ,.")
        if len(pc) <= 2:
            continue
        if parts and not _CMD_START.match(pc):
            parts[-1] = parts[-1] + (glue if glue.strip() else " ") + pc
        else:
            parts.append(pc)
    return parts or ([text.strip()] if (text or "").strip() else [])


# ---- 3 route -----------------------------------------------------------------------------------------------------------------------------------------------
_Q = re.compile(r"^\s*(what|how|where|which|who|why|when|can|could|does|do|is|are|explain|tell me|show me how|teach me|list|give me the shortcut)\b|\?\s*$", re.I)
_DO = re.compile(r"\b(open|click|press|go to|navigate|type|enter|fill|search for|select|add|create|draw|save|close|run|launch|start|delete|remove|send|submit|book|buy|order|download|upload|post|publish)\b", re.I)
_WRITE = re.compile(r"^\s*(?:please\s+)?(write|draft|compose|prepare|reply to|respond to|word)\b.*\b(email|e-mail|mail|message|post|linkedin|tweet|letter|summary|report|cover letter|blog|caption|reply|note)\b", re.I)
_CHANNEL = [(r"linkedin", "linkedin_post"), (r"tweet|twitter", "tweet"), (r"cover letter", "cover_letter"), (r"blog", "blog_post"), (r"reply|respond", "email_reply"), (r"e-?mail|mail", "email"),
            (r"whatsapp|sms|text message", "chat"), (r"slack|teams|chat|message", "team_chat"), (r"report|document|summary|letter", "document")]
_REL = [(r"boss|manager|supervisor", "boss"), (r"client|customer", "client"), (r"recruiter|hiring", "recruiter"), (r"professor|teacher|lecturer", "professor"), (r"friend|buddy|bro", "friend"),
        (r"team|colleague|coworker", "colleague"), (r"investor", "investor"), (r"public|followers|audience|network", "public")]


_BUILD = re.compile(r"\b(build|make|create|model|construct|add)\b.*\b(blender|in 3d|3d scene|3d world)\b", re.I)


ROUTES = ("question", "write", "web", "desktop", "build", "code", "video")
ACTS = ("web", "desktop", "build")                                                                    # the parts that touch a screen or a document; a failed one is never repeated by another acting part
# what each executor CAN do -- the model decides which one a ticket needs; this says nothing about any particular task
ROUTE_SYSTEM = ("You route one task to the part of an automation system that can do it. The parts:\n"
                "question = the person wants to KNOW something: how to do it, where a button is, what a shortcut is. Naming an app does not make it an action; nothing is done on the screen\n"
                "write = produce a text for a person (email, reply, post, letter, report, summary, quiz, caption ...) as a draft; nothing is sent\n"
                "web = the person wants it DONE on a website in a browser (open a page, click, fill, search, find something across pages)\n"
                "desktop = the person wants it DONE in an installed desktop app (open it, type, click, draw, save, export)\n"
                "build = build a 3D object or scene in Blender\n"
                "code = write the source code of a program, script, app or website as files; nothing is run\n"
                "video = edit video files: cut, trim, join, remove silences, captions, titles, music, highlights, reels\n"
                "Answer with exactly one word: question, write, web, desktop, build, code or video.")
# asked first, on its own: a 7B model that sees 'how do I make a pivot table in Excel' among six parts picks 'desktop' (the app's name pulls it); asked only this, it gets 19/20 (Oct-27 set)
WHO_SYSTEM = ("Is the person asking how THEY can do something (they will do it themselves), or asking for it to be done or made FOR them? Answer with one word: self or forme.")
ROUTE_LOG: Dict[str, str] = {}                                                                         # ticket -> who decided its route (memory / model / rules), carried into the report
_PAST: Dict[str, Any] = {"mtime": None, "rows": []}


def past_routes(ticket: str, k: int = 6, runs_dir: str = "") -> List[Dict[str, Any]]:
    """The closest earlier tickets that FINISHED well, with the route they took (newest 400 runs). These are the examples the model decides by, and an identical one is reused outright."""
    d = runs_dir or RUNS
    try:
        mt = os.path.getmtime(d)
    except OSError:
        return []
    if _PAST["mtime"] != (d, mt):
        rows = []
        runs = sorted((e for e in os.scandir(d) if e.is_dir()), key=lambda e: e.stat().st_mtime, reverse=True)[:400]
        for e in runs:
            with contextlib.suppress(Exception):
                for t in json.load(open(os.path.join(e.path, "report.json"), encoding="utf-8")).get("tickets", []):
                    if (t.get("result") or {}).get("status") in GOOD and t.get("kind") in ROUTES and t.get("text"):
                        rows.append({"text": t["text"], "kind": t["kind"], "words": set(re.findall(r"[a-z0-9]+", t["text"].lower()))})
        _PAST.update(mtime=(d, mt), rows=rows)
    w = set(re.findall(r"[a-z0-9]+", ticket.lower()))
    if not w:
        return []
    rows, seen = [], set()
    for r in _PAST["rows"]:
        if r["text"].lower() not in seen:
            seen.add(r["text"].lower())
            rows.append(r)
    vecs = _embed([ticket] + [r["text"] for r in rows if r["text"] not in _VEC]) if rows else None    # by meaning: 'remind me how blender exports to fbx' is the same job as 'how do you export a blender scene as fbx'
    scored = []
    for r in rows:
        s = len(w & r["words"]) / max(1, len(w | r["words"]))
        if r["text"].lower() == ticket.strip().lower():
            s, sim = 1.0, 1.0
        elif vecs is not None and r["text"] in _VEC:
            sim = _cos(vecs, _VEC[r["text"]])
        else:
            sim = None
        if sim is not None or s > 0:
            scored.append({"text": r["text"], "kind": r["kind"], "score": round(s, 3), "meaning": None if sim is None else round(sim, 3)})
    return sorted(scored, key=lambda x: -(x["meaning"] if x["meaning"] is not None else x["score"]))[:k]


_VEC: Dict[str, List[float]] = {}


def _embed(texts: List[str]) -> Optional[List[float]]:
    """Vectors from the local embedding model (HOJAIGA_EMBED_MODEL, '' turns it off), stored per text; returns the FIRST text's vector, None when there is no model (word overlap is used then)."""
    model = os.environ.get("HOJAIGA_EMBED_MODEL", "nomic-embed-text")
    if not model or not texts:
        return None
    try:
        body = {"model": model, "input": ["search_query: " + t for t in texts]}
        req = urllib.request.Request(OLLAMA + "/api/embed", data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            vs = json.loads(r.read().decode("utf-8")).get("embeddings") or []
    except Exception:
        return None
    if len(vs) != len(texts):
        return None
    for t, v in zip(texts[1:], vs[1:]):
        _VEC[t] = v
    return vs[0]


def _cos(a: Sequence[float], b: Sequence[float]) -> float:
    na, nb = sum(x * x for x in a) ** 0.5, sum(x * x for x in b) ** 0.5
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


def _ask_route_model(system: str, prompt: str) -> Optional[str]:
    """HOJAIGA_ROUTE_BRAIN=local (default: the warm local model, ~0.1 s, no rate limit) or cloud (a hosted model, local when it has no budget)."""
    if (os.environ.get("HOJAIGA_ROUTE_BRAIN") or "local").lower() == "cloud":
        with contextlib.suppress(Exception):
            from core_organs import organ_37_llm_gateway as GW
            out = GW.cloud_chat(system, prompt, temperature=0.0, timeout=30)                          # no max_tokens: reasoning models (gpt-oss) spend them thinking and return nothing
            if out:
                return out
    body = {"model": os.environ.get("HOJAIGA_ROUTE_MODEL", QA_MODEL), "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}], "stream": False,
            "options": {"temperature": 0.0, "num_predict": 6}}
    try:
        req = urllib.request.Request(OLLAMA + "/api/chat", data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            return (json.loads(r.read().decode("utf-8")).get("message") or {}).get("content")
    except Exception:
        return None


def decide_route(ticket: str, domain: str, rag: Any = None, names: Optional[Dict[str, str]] = None, ask: Optional[Any] = None) -> Tuple[str, str]:
    """(route, who decided). An identical ticket that finished well before -> its route (memory, no model call). Otherwise the model decides from what each part can do and the
    closest past tickets. The word rules only answer when the model does not (Ollama down, no valid word) or HOJAIGA_ROUTE_BRAIN=rules."""
    if (os.environ.get("HOJAIGA_ROUTE_BRAIN") or "local").lower() == "rules":
        return _rules_route(ticket, domain, rag, names), "rules"
    past = past_routes(ticket)
    if past and past[0]["score"] >= 0.999:
        return past[0]["kind"], "memory"
    same = float(os.environ.get("HOJAIGA_ROUTE_SAME", "0.82"))                                       # measured Oct-27 (nomic-embed-text): rewordings of one job 0.70-0.95, different jobs at most 0.69
    if past and (past[0].get("meaning") or 0) >= same:
        rival = max((p["meaning"] or 0 for p in past[1:] if p["kind"] != past[0]["kind"]), default=0.0)
        if past[0]["meaning"] - rival >= 0.05:                                                        # a close neighbour with a different part means the wording alone cannot decide
            return past[0]["kind"], f"memory (same meaning {past[0]['meaning']})"
    who = ((ask or _ask_route_model)(WHO_SYSTEM, f"Request: \"{ticket.strip()}\"\nAnswer:") or "").lower()
    if re.search(r"\bself\b", who):
        return "question", "model (they asked how to do it themselves)"
    past = [p for p in past if (p["meaning"] if p.get("meaning") is not None else p["score"] * 2) >= 0.5]   # only examples that are about the same kind of job; unrelated ones pulled routes off
    ex = "\n".join(f"- \"{p['text'][:140]}\" -> {p['kind']}" for p in past)
    prompt = (f"Earlier tasks that were done well, and their part:\n{ex}\n\n" if ex else "") + f"Task: \"{ticket.strip()}\"\n" + (f"(the task names a {domain} thing)\n" if domain in ("web", "desktop") else "") + "Part:"
    ans = (ask or _ask_route_model)(ROUTE_SYSTEM, prompt) or ""
    m = re.search(r"\b(" + "|".join(ROUTES) + r")\b", ans.lower())
    if m:
        return m.group(1), "model"
    return _rules_route(ticket, domain, rag, names), "rules (the model gave no route)"


def reroute(ticket: str, tried: Sequence[str], why: str, ask: Optional[Any] = None) -> Optional[str]:
    """After a part that does NOT act (question / write / code) could not do a ticket: the model's next choice, or None. A failed acting part is never handed on: the person wanted it done
    on the screen, and a draft or an answer instead is not that (live Oct-27: 'save it as plan.docx in Word' came back as a text draft reported DONE)."""
    if tried and tried[-1] in ACTS:
        return None
    allowed = [k for k in ROUTES if k not in tried]
    if not allowed:
        return None
    prompt = (f"Task: \"{ticket.strip()}\"\nThe {' and '.join(tried)} part could not do it: {why[:300]}\n"
              f"Which other part fits the task? Choose from: {', '.join(allowed)}, or none if no part fits.\nPart:")
    ans = ((ask or _ask_route_model)(ROUTE_SYSTEM, prompt) or "").lower()
    m = re.search(r"\b(" + "|".join(allowed + ["none"]) + r")\b", ans)
    return m.group(1) if m and m.group(1) != "none" else None


def classify(ticket: str, domain: str, rag: Any = None, names: Optional[Dict[str, str]] = None) -> str:
    kind, by = decide_route(ticket, domain, rag, names)
    ROUTE_LOG[ticket] = by
    return kind


def _rules_route(ticket: str, domain: str, rag: Any = None, names: Optional[Dict[str, str]] = None) -> str:
    t = ticket.strip()
    if _WRITE.search(t):
        return "write"
    if _BUILD.search(t):
        return "build"                                                                                 # a 3D build in Blender: the app_teaching_automation section (object knowledge -> parts -> the app's own commands -> measured)
    from core_organs import web_executor as WE
    site = WE.resolve_site(t, rag, names) if (domain == "web" or re.search(r"https?://|\.html?\b|\b[a-z0-9\-]+\.(com|org|net|io|gov|in|dev|app|ai)\b", t, re.I)) else {}
    if _Q.search(t) and not (re.match(r"^\s*(open|click|press|go to|navigate|type|enter|fill|search)", t, re.I)):
        return "question"
    if domain == "web" or site:
        return "web"
    if domain in ("desktop", "mixed", "system"):
        return "desktop"
    return "question" if not _DO.search(t) else "desktop"


# ---- executors ---------------------------------------------------------------------------------------------------------------------------------------------
WRITER_SYSTEM = ("You write messages for a person, exactly as briefed: the language, register, length and shape given. Use ONLY the facts supplied; do not invent names, dates, numbers or claims. "
                 "Write the message itself with no preface and no explanation. If something essential is missing, write one line starting 'NEED:' saying what.")


CONTENT_SYSTEM = ("You write exactly the thing that is asked for (a quiz, a list, a story, notes, a summary, a plan ...), complete and ready to use, in the language of the request. "
                  "Write the thing itself: not a message asking someone else for it, no preface, no explanation.")
READ_SYSTEM = ("You read one writing request and reply with JSON only: {\"form\": \"message\" or \"content\", \"channel\": one of CHANNELS, \"relationship\": one of RELS, "
               "\"facts\": [every fact the request itself gives, short, in its words], \"missing\": \"\" or the one essential fact that is not given}. "
               "form=message when it is sent to someone (email, reply, post, letter, chat); content when it is a thing to use (quiz, list, story, notes). "
               "A message whose point is in the request is not missing anything.")


def read_request(ticket: str) -> Optional[Dict[str, Any]]:
    """The model reads what kind of text is wanted, for whom, and which facts the request carries. None when it does not answer (the word rules are used then)."""
    from core_organs.mind import app_qa as QA, persona as P
    sys_ = READ_SYSTEM.replace("CHANNELS", "[" + ", ".join(P.CHANNELS) + "]").replace("RELS", "[" + ", ".join(sorted(set(P._REL_REGISTER) | {"public"})) + "]")
    out = QA.ask_llm(f"Request: \"{ticket.strip()}\"\nJSON:", sys_, timeout=90)
    m = re.search(r"\{.*\}", out or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return None
    return {"form": "content" if str(d.get("form", "")).lower() == "content" else "message",
            "channel": d.get("channel") if d.get("channel") in P.CHANNELS else "", "relationship": str(d.get("relationship") or "").lower(),
            "facts": [str(f).strip() for f in (d.get("facts") or []) if str(f).strip()][:12], "missing": str(d.get("missing") or "").strip()}


def do_write(ticket: str) -> Dict[str, Any]:
    from core_organs.mind import app_qa as QA, persona as P
    low = ticket.lower()
    inc = ""
    mm = re.search(r"(?:^|\n)\s*(?:their message|incoming|they wrote)\s*[:\-]\s*(.+)", ticket, re.I | re.S)
    if mm:
        inc = mm.group(1).strip()
    ask_text = ticket[:mm.start()] if mm else ticket
    rd = read_request(ask_text) or {}                                                                  # the request is read by the model; the word rules below only fill what it did not give
    if rd.get("form") == "content" and not inc:
        body = QA.ask_llm(ask_text.strip(), CONTENT_SYSTEM, timeout=180)
        if not body:
            return {"status": "FAILED", "evidence": "the language model did not answer (is Ollama running with the model?)"}
        return {"status": "DRAFTED", "draft": body, "form": "content", "read": rd, "note": "a draft only: nothing was sent or posted"}
    channel = rd.get("channel") or next((c for rx, c in _CHANNEL if re.search(rx, low)), "email")
    rel = rd.get("relationship") or next((r for rx, r in _REL if re.search(rx, low)), "public" if channel in ("linkedin_post", "tweet", "blog_post") else "unknown")
    facts = [f for f in rd.get("facts", []) if f != inc]
    if not rd:
        m = re.search(r"\b(?:about|saying|that|regarding|on|telling|to say|announcing|announce|mentioning)\b\s+(.+)$", ask_text, re.I)
        quoted = re.findall(r"[\"“']([^\"”']{3,300})[\"”']", ask_text)
        facts = [f.strip() for f in (quoted or ([m.group(1)] if m else [])) if f.strip()]
    brief = P.style_brief(inc, channel, rel, intent=ask_text)
    if not facts and not inc:
        return {"status": "NEEDS_INPUT", "question": f"I can write it in the right voice, but I need {rd.get('missing') or 'the facts to put in it (what happened, dates, numbers)'}. I will not invent them.", "brief": brief}
    prompt = P.compose_prompt(brief, facts, inc)
    draft = QA.ask_llm(prompt, WRITER_SYSTEM, timeout=180, private=bool(inc))                                          # a reply to someone's message stays on this machine
    if not draft:
        return {"status": "FAILED", "evidence": "the local language model did not answer (is Ollama running with the model?)", "brief": brief, "prompt": prompt}
    chk = P.check_draft(draft, brief)
    tries = 1
    if not chk["fits"] and not draft.strip().upper().startswith("NEED:"):
        retry = QA.ask_llm(prompt + "\n\nYour previous draft had these problems, fix them and write the message again:\n- " + "\n- ".join(chk["problems"]) + "\n\nPrevious draft:\n" + draft, WRITER_SYSTEM, timeout=180, private=bool(inc))
        if retry:
            draft, chk, tries = retry, P.check_draft(retry, brief), 2
    status = "NEEDS_INPUT" if draft.strip().upper().startswith("NEED:") else ("DRAFTED" if chk["fits"] else "DRAFTED_WITH_ISSUES")
    return {"status": status, "draft": draft, "fits_brief": chk["fits"], "problems": chk["problems"], "brief": {k: brief[k] for k in ("channel", "relationship", "language_name", "register", "max_words")}, "tries": tries,
            "note": "a draft only: nothing was sent or posted"}


CODE_MODEL = os.environ.get("HOJAIGA_CODE_MODEL", "qwen2.5-coder:7b")
CODE_SYSTEM = ("You write complete, working source code for the request. Give every file as a line 'FILE: <relative path>' followed by the file in one fenced code block. "
               "No placeholders, no 'rest of the code here'. End with one line 'RUN: <how to open or run it>'. Nothing else.")


def parse_files(text: str) -> List[Tuple[str, str]]:
    """[(relative path, content)] from 'FILE: path' + a fenced block. A path that leaves the folder (absolute, '..') is dropped."""
    out = []
    for m in re.finditer(r"FILE:\s*`?([^\s`]+)`?\s*\n+```[^\n]*\n(.*?)```", text or "", re.S):
        p = m.group(1).strip().replace("\\", "/")
        if p.startswith("/") or re.match(r"^[A-Za-z]:", p) or ".." in p.split("/"):
            continue
        out.append((p, m.group(2)))
    return out


def check_file(path: str, content: str) -> str:
    """'' when the file reads as what its name says (it is never run), else the problem."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".py":
            compile(content, path, "exec")
        elif ext == ".json":
            json.loads(content)
        elif ext in (".html", ".htm"):
            if not re.search(r"<(html|body|div|main|section|h1)\b", content, re.I):
                return "no page body"
        elif ext in (".js", ".mjs") and shutil.which("node"):
            with tempfile.NamedTemporaryFile("w", suffix=ext, delete=False, encoding="utf-8") as f:
                f.write(content)
            r = subprocess.run(["node", "--check", f.name], capture_output=True, text=True, timeout=20, creationflags=0x08000000)
            os.unlink(f.name)
            if r.returncode:
                return (r.stderr or "syntax error").strip().splitlines()[-1][:200]
    except SyntaxError as e:
        return f"line {e.lineno}: {e.msg}"
    except ValueError as e:
        return str(e)[:200]
    except Exception:
        return ""
    return "" if content.strip() else "empty"


_MEDIA = re.compile(r"((?:[A-Za-z]:[\\/]|[\\/])[^\n\"'<>|?*]*?\.(?:mp4|mov|mkv|avi|webm|m4v|mp3|wav|m4a|aac|flac|ogg))\b", re.I)


def do_video(ticket: str, out_dir: str) -> Dict[str, Any]:
    """An edit of the video files the ticket names (harvest.video_pipeline.edit_video: understand -> the model keeps lines -> FFmpeg render -> Shotcut project -> the render read
    back). Audio files the ticket names are the music. 'save it as X.mp4' places the result there. Nothing is uploaded or played on the screen."""
    import shutil
    from core_organs.harvest import video_pipeline as VP
    named = [m.group(1).strip() for m in _MEDIA.finditer(ticket)]
    save = re.search(r"\b(?:save|export|render)\w*\s+(?:it\s+|the\s+\w+\s+)?(?:as|to)\s+((?:[A-Za-z]:[\\/]|[\\/])\S+\.(?:mp4|mov|mkv|webm))", ticket, re.I)
    target = save.group(1) if save else ""
    videos = [p for p in named if p.lower().endswith(VP.VIDEO_EXT) and p != target and os.path.isfile(p)]
    music = next((p for p in named if not p.lower().endswith(VP.VIDEO_EXT) and os.path.isfile(p)), "")
    if not videos:
        return {"status": "NEEDS_INPUT", "question": "Which video file should I edit? Give its full path."}
    r = VP.edit_video(ticket, videos, os.path.join(out_dir, "video_" + uuid.uuid4().hex[:5]), music=music)
    if r.get("video") and target:
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        shutil.copy2(r["video"], target)
        r["video"] = target
    return {k: r.get(k) for k in ("status", "evidence", "video", "project", "captions", "check", "seconds") if r.get(k) is not None}


def do_code(ticket: str, out_dir: str) -> Dict[str, Any]:
    """The local coder model writes the files into the run folder; each is checked for what its name says (syntax, page body), one repair round with the problems; nothing is executed."""
    from core_organs.mind import app_qa as QA
    problems: List[str] = []
    files: List[Tuple[str, str]] = []
    text = ""
    prompt = ticket.strip()
    for _attempt in range(2):
        text = QA.ask_llm(prompt, CODE_SYSTEM, timeout=300, model=CODE_MODEL, max_tokens=3000) or ""
        files = parse_files(text)
        problems = [f"{p}: {e}" for p, c in files for e in [check_file(p, c)] if e] if files else ["no FILE: blocks in the answer"]
        if not problems:
            break
        prompt = ticket.strip() + "\n\nYour previous answer had these problems, fix them and give all files again:\n- " + "\n- ".join(problems) + "\n\nPrevious answer:\n" + text[:6000]
    if not files:
        return {"status": "FAILED", "evidence": "the code model gave no files" + (f": {text[:200]}" if text else " (is Ollama running with " + CODE_MODEL + "?)")}
    folder = os.path.join(out_dir, "code_" + uuid.uuid4().hex[:5])
    for p, c in files:
        fp = os.path.join(folder, *p.split("/"))
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(c)
    run_hint = (re.search(r"RUN:\s*(.+)", text) or [None, ""])[1].strip()
    return {"status": "DONE" if not problems else "DRAFTED_WITH_ISSUES", "folder": folder, "files": [p for p, _ in files], "problems": problems, "run": run_hint,
            "evidence": f"{len(files)} file(s) in {folder}" + (f"; problems: {'; '.join(problems)}" if problems else "; every file checks"), "note": "written only: nothing was run"}


def do_question(ticket: str, rag: Any, names: Optional[Dict[str, str]]) -> Dict[str, Any]:
    from core_organs.mind import app_qa as QA
    r = QA.answer(ticket, "", rag, names=names)
    if not r.get("app"):
        return {"status": "NEEDS_INPUT", "question": r["answer"]}
    # 'I could not find that' is not an answer the memory should learn from (ANSWERED_WEAK)
    return {"status": "ANSWERED" if r.get("confidence", 0) >= 0.3 and not r.get("not_found") else "ANSWERED_WEAK",
            "answer": r["answer"], "app": r["app"], "confidence": r["confidence"], "known": r.get("known"),
            "sources": [f"[{e['n']}] {e['kind']}/{e['trust']}/{e['source'][:40]}" for e in r.get("evidence", [])[:4]]}


def do_web(ticket: str, rag: Any, yes: bool, names: Optional[Dict[str, str]], out_dir: str, session: str = "") -> Dict[str, Any]:
    from core_organs import web_executor as WE
    reads = re.search(r"\b(read|copy|take|get|extract|grab|collect|fetch|pull)\b", ticket, re.I)
    acts = re.search(r"\b(click|type|fill|search|submit|log ?in|sign ?in|book|buy|order|post|send|press|select|scroll|download)\b", ticket, re.I)
    if reads and not acts and re.search(r"https?://", ticket):                                        # only data is wanted from a named page: read it, no browser steps (live Oct-28: the table
        kept = keep_from_web(ticket)                                                                  # was kept but the ticket FAILED because there was nothing to click)
        return {"status": "DONE" if kept.startswith("kept") else "FAILED", "evidence": kept, "kept": kept}
    r = WE.run_web_task(rag, ticket, yes=yes, names=names, out_dir=os.path.join(out_dir, "web_" + uuid.uuid4().hex[:5]), session=session)
    out = {k: r.get(k) for k in ("status", "evidence", "steps", "screenshot", "question", "site", "learned", "used_stored_procedure", "seconds", "session") if r.get(k) is not None}
    if out.get("status") == "DONE" and out.get("screenshot") and os.path.isfile(out["screenshot"]):
        # the browser's own 'it moved and carries the words' is checked a second way: the eye looks at the final page blind and the judge compares it with the ticket
        # (live Oct-28: 'open the early life section' was DONE on a BBC page). A page the eye says is not what was asked is FAILED_CHECK, never DONE.
        v = judge_picture(ticket, out["screenshot"], screen=True)
        out["proof"] = [{"screenshot": out["screenshot"], **v}]
        if v.get("ok") is False:
            out["status"] = "FAILED_CHECK"
    if re.search(r"\b(read|copy|take|get|extract|grab|collect|fetch|pull)\b", ticket, re.I):
        out["kept"] = keep_from_web(ticket, (r.get("site") or {}).get("url", ""))
    return out


def keep_from_web(ticket: str, site_url: str = "") -> str:
    """A web ticket that READS data for a later app (Chrome -> Excel) leaves the page's table and text on the shared blackboard (loop_first), where the
    next app's planner sees it. The page named in the ticket is read, else the site the web step used; no browser window."""
    from core_organs import loop_first as LF
    from core_organs import web_executor as WE
    m = re.search(r"https?://[^\s'\"<>]*[^\s'\"<>.,;:!?)]", ticket)
    url = m.group(0) if m else site_url
    if not url:
        return ""
    page = WE.read_page(url)
    if not page.get("ok"):
        return f"not kept: {page.get('why')}"
    if page["tables"]:
        rows = [[re.sub(r"\s*\[(?:\d{1,3}|[a-z]{1,2}|note \d+|citation needed)\]", "", str(c)).strip() for c in r] for r in WE.best_table(page["tables"], ticket)]   # 'City[a]', '41,913,860[12]': the page's footnote marks are not data
        LF.keep("web table", {"kind": "table", "rows": rows, "from": url})
    LF.keep("web text", {"kind": "text", "text": page["text"], "from": url})
    return f"kept {'a ' + str(len(rows)) + '-row table and ' if page['tables'] else ''}the page text from {url}"


def do_build(ticket: str, state: Dict[str, Any]) -> Dict[str, Any]:
    """One 3D build step through the section that already knows how (object knowledge -> parts -> Blender's own commands -> measured). The pieces of one run share ONE document: each step continues in the file
    the step before saved, so 'build a terrain; add a mountain; add a cabin' makes one scene."""
    from core_organs import app_teaching_automation as ATA
    sec = state.get("section")
    if sec is None:
        sec = state["section"] = ATA.AppTeachingAutomationSection(log=lambda *a, **k: None)
    rep = sec.handle(ticket, app="Blender", mode="delegate", file=state.get("file", ""), learn="never", recall=False, vlm=True, refine=1)   # the picture reader judges the shape and one re-plan round may follow
    sv, q = rep.get("saved") or {}, rep.get("quality") or {}
    if sv.get("ok"):
        state["file"] = sv["path"]
    built, wanted = q.get("parts_built"), q.get("parts_wanted")
    pic = rep.get("vlm") or {}
    if not (pic.get("ok") and pic.get("score") is not None) and rep.get("picture"):
        pic = judge_picture(ticket, rep["picture"])                                                    # no score from the section's reader: the front door's eye looks at the render
        pic = {"ok": pic.get("ok") is not None, "score": None if pic.get("ok") is None else (5 if pic["ok"] else 1), "sees": pic.get("sees", ""), "wrong": pic.get("why", "")}
    score = pic.get("score") if pic.get("ok") else None
    try:
        score = float(score) if score is not None else None
    except (TypeError, ValueError):
        score = None
    if rep.get("error"):
        status = "FAILED"
    elif not (sv.get("ok") and built and built == wanted):
        status = "PARTIAL" if built else "FAILED"
    else:
        if score is not None and score < 4 and rep.get("picture"):                                    # the section's reader marked a correct pine 3 ('no bark texture', Oct-27) and a correct lumberjack scene 2 ('perspective', Oct-28)
            second = judge_picture(ticket, rep["picture"])                                             # the blind describe-then-judge eye decides
            if second.get("ok") is not None:
                score = 4.0 if second["ok"] else 2.0
                pic = {**pic, "second_opinion": second.get("why", ""), "sees": second.get("sees", pic.get("sees", ""))}
        status = "UNVERIFIED" if score is None else ("DONE" if score >= 4 else "FAILED_CHECK")          # geometry 100 is not 'looks like a tree': the picture decides
    return {"status": status, "evidence": rep.get("error") or f"{built}/{wanted} parts built, geometry score {q.get('score')}, picture score {score} ({pic.get('sees', '')[:80]}; {pic.get('wrong', '')[:80]}), saved {sv.get('path')}",
            "picture": rep.get("picture"), "saved": sv.get("path"), "planner": (rep.get("planner") or {}).get("source"), "seconds": rep.get("seconds")}


# 'the app should show 12' / 'it should display ...' is what the RESULT must look like: it is checked by prove(), never planned as steps
# (live Nov-02: Calculator's '..., the app should show 12' was planned as type "12" after the sum)
_CHECK_CLAUSE = re.compile(r"[,;.]?\s*(?:and\s+|so\s+|then\s+)?(?:the\s+(?:app|screen|display|window|result)|it)\s+should\s+(?:show|display|read|say)\b.*$", re.I | re.S)


def without_check(ticket: str) -> str:
    """The ticket without its 'the app should show ...' clause; a clause inside quotes is text to type ('type 'It should show results'') and stays."""
    for m in _CHECK_CLAUSE.finditer(ticket or ""):
        before = ticket[:m.start()]
        if before.count('"') % 2 == 0 and len(re.findall(r"(?<!\w)'|'(?!\w)", before)) % 2 == 0 and before.strip():
            return before.rstrip(" ,;.")
    return ticket


def do_desktop(ticket: str, yes: bool) -> Dict[str, Any]:
    from core_organs import task_lifecycle as TL
    t0 = time.time()
    r = TL.run_lifecycle(without_check(ticket), allow_destructive=yes, unattended=True)
    tk = (r.get("tickets") or [{}])[0]
    out = {"status": r.get("status"), "evidence": (tk.get("evidence") or tk.get("note") or r.get("reason") or r.get("question") or "")[:600], "question": r.get("question"),
           "checkpoints": [f"{c['id']}:{c['status']}" for c in (r.get("checkpoints") or [])][:14], "escalations": tk.get("escalations"), "seconds": r.get("elapsed_s")}
    if out["status"] in GOOD or out["status"] == "PARTIAL":                                           # PARTIAL = every step passed, some only by 'the UI changed': the result itself decides (live Oct-27: Word's bold title was right but PARTIAL)
        hw = re.findall(r"hwnd=(\d+)", str(tk.get("evidence") or ""))
        pr = prove(ticket, t0, int(hw[-1]) if hw else 0)
        out = {**out, "proof": pr["proof"]} if (pr["status"] == "UNVERIFIED" and out["status"] == "PARTIAL") else {**out, **pr}
    return out


# ---- proof: a step's own verifier said PASS while the file held the text twice, a 'saved' drawing was never saved and a pole scored 100 as a tree (live Oct-27).
# DONE now needs the RESULT itself: every file the ticket names is read back and judged against the ticket; with no file, the app's final window is judged by the eye.
_EXT = r"\.(?:txt|md|csv|json|py|html?|js|docx|xlsx|pptx|png|jpe?g|bmp|gif|pdf|blend)\b"
_FILE = re.compile(r"((?:[A-Za-z]:[\\/]|[\\/])[\w .\-\\/]*?[\w\-]+" + _EXT + r"|(?<![\w\\/.:])[\w\-]+" + _EXT + ")", re.I)   # spaces only inside a full path; a bare name is one word
# two calls, so the checklist never comes from the result: shown both, the 7B judge took 'centred, diameter equal' from a picture's description as things the task asked for
ITEMS_SYSTEM = ("A task names an app to open and then the content to put in it. List only that content: every text or value to type, every object to draw or build, "
                "with where it goes (a cell, a slide, a title...) and its formatting (bold...). Never list the app, opening it or saving. "
                "Reply JSON only: {\"items\": [{\"content\": \"...\", \"where\": \"\" or \"...\", \"format\": \"\" or \"...\"}]}.")
CHECK_SYSTEM = "You check one thing in a task's result. Answer with one word: yes or no."
PICTURE_ITEMS = ("List the objects a task asks to appear in a picture of its result, each as the thing itself with the colour or shape the task names ('a red circle', 'a low poly tree'), "
                 "not the steps to make it. Reply JSON only: {\"items\": [{\"content\": \"...\", \"where\": \"\", \"format\": \"\"}]}.")
DESCRIBE = "Describe exactly what is in this picture: every object, its shape, its colour, its size relative to the others. Plain facts only, no guessing what it is meant to be."
DESCRIBE_SCREEN = ("This is a screenshot of an app or web page. Read it: which app or site it is, the page or document title, the headings and section names you can read, "
                   "what the main area shows (text topic, table, form, picture) and any dialog or error. Quote the words you read. Plain facts only.")
SCREEN_ITEMS = ("List what a screen must show when a task on an app or web page is done, as things readable on that screen ('the Wikipedia article on Alan Turing', "
                "'the section heading Early life', 'cell B2 holding 40'), not the steps. Reply JSON only: {\"items\": [{\"content\": \"...\", \"where\": \"\", \"format\": \"\"}]}.")
EYE_MODEL = os.environ.get("HOJAIGA_EYE_MODEL", "qwen2.5vl:3b")


def read_back(path: str) -> Tuple[str, str]:
    """(kind, what the file holds as text) -- 'image' kind returns the path; ('', why) when it cannot be read."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".png", ".jpg", ".jpeg", ".bmp", ".gif"):
            return "image", path
        if ext == ".docx":
            import docx
            d = docx.Document(path)
            lines = []
            for p in d.paragraphs:
                if p.text.strip():
                    fmt = [w for w, on in (("bold", any(r.bold for r in p.runs if r.text.strip())), ("italic", any(r.italic for r in p.runs if r.text.strip()))) if on]
                    runs = [r for r in p.runs if r.text.strip()]                                     # live Nov-02: Cascadia Code Light 36 pt was in the file, the proof saw only the text
                    names = {r.font.name for r in runs if r.font.name}
                    sizes = {r.font.size.pt for r in runs if r.font.size}
                    fmt += [f"{n} font" for n in sorted(names)] + [f"{s:g} pt" for s in sorted(sizes)]
                    lines.append(f"[paragraph{' ' + ' '.join(fmt) if fmt else ''}] {p.text}")
            pics = len(d.inline_shapes)
            tables = [" | ".join(c.text for c in r.cells) for t in d.tables for r in t.rows]
            lines += ([f"[{pics} picture(s) in the document]"] if pics else []) + ([f"[table row] {r}" for r in tables[:60]])
            return "text", "\n".join(lines) or "(the document is empty)"
        if ext == ".xlsx":
            import openpyxl
            wb = openpyxl.load_workbook(path, data_only=True)
            base_font = ("", 0.0)
            with contextlib.suppress(Exception):
                nf = next(st.font for st in wb._named_styles if st.name == "Normal")
                base_font = (nf.name or "", float(nf.sz or 0))
            def _fmt(c):                                                                              # live Oct-28: bold A1:B1 was in the file, but the proof never saw it and failed the run
                f, on = c.font, []
                on += ["bold"] if f and f.b else []
                on += ["italic"] if f and f.i else []
                on += ["underline"] if f and f.u else []
                on += [f"{f.name} font"] if f and f.name and f.name != base_font[0] else []  # the workbook's own default font is not something a task set
                on += [f"{float(f.sz):g} pt"] if f and f.sz and float(f.sz) != base_font[1] else []
                rgb =getattr(getattr(f, "color", None), "rgb", None) if f else None
                on += [f"font colour #{rgb[-6:]}"] if isinstance(rgb, str) and rgb[-6:] not in ("000000",) else []
                fill = getattr(getattr(c.fill, "fgColor", None), "rgb", None) if c.fill is not None and c.fill.fill_type else None
                on += [f"fill #{fill[-6:]}"] if isinstance(fill, str) and fill[-6:] not in ("000000", "FFFFFF") else []
                return f" [{', '.join(on)}]" if on else ""
            cells = [f"{ws.title}!{c.coordinate} = {c.value!r}{_fmt(c)}" for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.value is not None]
            return "text", "\n".join(cells[:200]) or "(every cell is empty)"
        if ext == ".pptx":
            import pptx
            pr = pptx.Presentation(path)
            def _slide(sl):
                parts = [s.text_frame.text for s in sl.shapes if s.has_text_frame and s.text_frame.text.strip()]
                parts += [" / ".join(" | ".join(c.text for c in r.cells) for r in s.table.rows) for s in sl.shapes if getattr(s, "has_table", False) and s.has_table]
                n_pic = sum(1 for s in sl.shapes if s.shape_type == 13)                               # 13 = picture
                return " | ".join(parts) + (f" [{n_pic} picture(s)]" if n_pic else "")
            return "text", "\n".join(f"slide {i}: " + _slide(sl) for i, sl in enumerate(pr.slides, 1)) or "(no slides)"
        if ext in (".pdf", ".blend"):
            return "exists", ""
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return "text", f.read(6000) or "(the file is empty)"
    except Exception as e:
        return "", f"{type(e).__name__}: {str(e)[:120]}"


def _json_ask(ask: Optional[Any], system: str, prompt: str, key: str) -> Dict[str, Any]:
    from core_organs.mind import app_qa as QA
    for _ in range(2):
        raw = (ask or (lambda s, p: QA.ask_llm(p, s, timeout=120, max_tokens=700)))(system, prompt) or ""
        m = re.search(r"\{.*\}", raw, re.S)
        with contextlib.suppress(ValueError):
            d = json.loads(m.group(0)) if m else {}
            if isinstance(d.get(key), list) and d[key]:
                return d
    return {}


def kept_in_file(what: str, sample: int = 40) -> Optional[Dict[str, Any]]:
    """When an earlier app's TABLE was handed over (the blackboard), the proof is exact: its cells are in the file (commas and spaces ignored: Excel stores
    '41,913,860' as 41913860). None when nothing was handed over (the judge decides then). Live Oct-28: the judge could not tie 'put the table in A1' to the cells."""
    with contextlib.suppress(Exception):
        from core_organs import loop_first as LF
        tables = [v for v in LF.BLACKBOARD.values() if v.get("kind") == "table" and v.get("rows")]
        if not tables:
            return None
        norm = lambda s: re.sub(r"[,\s ]|\.0\b", "", str(s)).lower()
        hay = norm(what)
        cells = [str(c) for r in tables[-1]["rows"][:8] for c in r if len(str(c).strip()) >= 3][:sample]
        if not cells:
            return None
        found = sum(1 for c in cells if norm(c) in hay)
        ok = found >= 0.9 * len(cells)
        return {"ok": ok, "why": f"{found} of {len(cells)} sampled cells of the table kept from {tables[-1].get('from', 'an earlier app')} are in the file"}
    return None


def judge_text(ticket: str, what: str, ask: Optional[Any] = None, doubles: bool = True, lister: str = "") -> Dict[str, Any]:
    """The model lists what the ticket asks for (from the ticket alone), then quotes each item from the result; the verdict is computed here, never asked for
    (asked for a verdict, the 7B judge failed good files over 'missing save action' and passed nothing it should)."""
    ticket = re.sub(r"\s*(?:,?\s*and\s+)?(?:save|export|store)\w*\s+(?:it|this|that|the \w+)?\s*(?:as|to|in)\s+" + _FILE.pattern, " ", ticket, flags=re.I)
    ticket = _FILE.sub("the file", ticket)                                                            # where it was saved is proven by the code; the judge sees only what should be IN it
    from core_organs.mind import app_qa as QA
    opened = {a.strip().lower() for a in re.findall(r"\bopen\s+([\w .\-]+?)(?=\s*(?:,|\band\b|$))", ticket, re.I)}
    items = []
    for i in _json_ask(ask, lister or ITEMS_SYSTEM, f"Task: \"{ticket.strip()}\"\nJSON:", "items").get("items", []):
        it = i if isinstance(i, dict) else {"content": str(i)}
        c = str(it.get("content") or "").strip()
        if c and c.lower() not in opened:                                                              # the app the ticket opens is not content (the 7B lister kept adding it)
            items.append({"content": c[:200], "where": str(it.get("where") or "").strip()[:60], "format": str(it.get("format") or "").strip()[:40]})
    if not items:
        return {"ok": None, "why": "the judge gave no list"}
    low = what.lower()
    yes_no = ask or (lambda s, p: QA.ask_llm(p, s, timeout=60, max_tokens=4))
    for it in items[:10]:
        if it["content"].lower() in low and not it["where"] and not it["format"]:
            it["found"] = True                                                                         # the exact text is there and nothing more is asked of it
            continue
        if lister == PICTURE_ITEMS:                                                                   # a picture: 'a low poly tree' is shown by 'a Christmas tree with three tiers'; 'exactly that' failed it (live Oct-27)
            q = f"does it show {it['content']!r}? A simple, stylised or low-detail version counts; a different kind of thing does not."
            it["found"] = bool(re.match(r"\s*yes\b", (yes_no(CHECK_SYSTEM, f"The result:\n\"\"\"\n{what[:4000]}\n\"\"\"\nQuestion: {q}\nAnswer:") or "").lower()))
            continue
        q = f"does it contain {it['content']!r}" + (f" at/in {it['where']}" if it["where"] else "") + (f", formatted {it['format']}" if it["format"] else "") + \
            ", exactly that and in that place?"
        it["found"] = bool(re.match(r"\s*yes\b", (yes_no(CHECK_SYSTEM, f"The result:\n\"\"\"\n{what[:4000]}\n\"\"\"\nQuestion: {q}\nAnswer:") or "").lower()))
    missing = [f"{it['content'][:40]}" + (f" ({it['where']})" if it["where"] else "") + (f" [{it['format']}]" if it["format"] else "") for it in items[:10] if not it["found"]]
    twice = [it["content"][:40] for it in items if doubles and len(it["content"]) >= 4 and low.count(it["content"].lower()[:max(4, min(16, len(it["content"]) // 2))]) > 1]
    why = "; ".join(([f"missing or wrong: {', '.join(missing)}"] if missing else []) + ([f"appears more than once: {', '.join(twice)}"] if twice else []))
    return {"ok": not why, "why": why or f"all {len(items)} asked item(s) found", "items": items[:8]}


def describe_picture(image: Any, screen: bool = False) -> str:
    """What the eye sees, asked WITHOUT the task: told 'the job was a tree', the 3B eye called a pole with a ball 'a low poly tree with branches'; asked blind, it said 'a vertical shaft with a sphere'."""
    import base64
    import io
    try:
        if isinstance(image, str):
            data = open(image, "rb").read()
        else:
            buf = io.BytesIO()
            im = image.convert("RGB")
            im.thumbnail((1280, 1280))
            im.save(buf, "PNG")
            data = buf.getvalue()
        b64 = base64.b64encode(data).decode()
    except Exception:
        return ""
    big = big_eye_url()
    if big:                                                                                           # the 7-8B vision server (start_hojaiga.bat, :8081) when it is up: a stronger eye than the 3B
        with contextlib.suppress(Exception):
            body = {"messages": [{"role": "user", "content": [{"type": "text", "text": DESCRIBE_SCREEN if screen else DESCRIBE}, {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}}]}],
                    "temperature": 0.0, "max_tokens": 220}
            req = urllib.request.Request(big + "/v1/chat/completions", data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=300) as r:
                txt = ((json.loads(r.read().decode("utf-8")).get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            if txt.strip():
                return txt.strip()
    try:
        body = {"model": EYE_MODEL, "stream": False, "prompt": DESCRIBE_SCREEN if screen else DESCRIBE, "images": [b64], "options": {"temperature": 0.0, "num_predict": 200, "num_ctx": 4096,
                                                                                                   **({"num_gpu": 0} if _HEAT["hot"] else {})}}    # hot GPU: the small eye on the CPU
        req = urllib.request.Request(OLLAMA + "/api/generate", data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=600) as r:
            return (json.loads(r.read().decode("utf-8")).get("response") or "").strip()
    except Exception:
        return ""


_HEAT = {"hot": False, "t": 0.0, "c": None}


def gpu_hot() -> bool:
    """The GPU is too hot for the big eye: above HOJAIGA_GPU_HOT (83 C) it stands aside until it is back under HOJAIGA_GPU_COOL (75 C); read at most every 20 s."""
    if time.time() - _HEAT["t"] > 20:
        _HEAT["t"] = time.time()
        with contextlib.suppress(Exception):
            out = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            _HEAT["c"] = c = float(out.split()[0])
            _HEAT["hot"] = c >= float(os.environ.get("HOJAIGA_GPU_HOT", "83")) or (_HEAT["hot"] and c > float(os.environ.get("HOJAIGA_GPU_COOL", "75")))
    return bool(_HEAT["hot"])


def big_eye_url() -> str:
    """The vision server's address when it answers its health check ('' otherwise, when HOJAIGA_BIG_EYE=0, or while the GPU is too hot: the small eye then runs on the CPU)."""
    url = os.environ.get("HOJAIGA_BIG_EYE_URL", "http://127.0.0.1:8081")
    if os.environ.get("HOJAIGA_BIG_EYE", "1") == "0" or gpu_hot():
        return ""
    return url if _get(url + "/health", timeout=1.5) is not None else ""


def judge_picture(ticket: str, image: Any, look: Optional[Any] = None, ask: Optional[Any] = None, screen: bool = False) -> Dict[str, Any]:
    """The eye describes the picture blind, then the judge compares that description with the ticket. look(image) -> description replaces the eye (tests)."""
    sees = look(image) if look else describe_picture(image, screen)                                  # a screen is READ (title, headings); a render is described as shapes
    if not sees:
        return {"ok": None, "why": "the eye could not look"}
    v = judge_text(ticket, ("The screen at the end shows: " if screen else "A picture of the result shows: ") + sees, ask, doubles=False, lister=SCREEN_ITEMS if screen else PICTURE_ITEMS)          # the eye repeats itself; a drawing drawn twice is not what this check is for
    return {**v, "sees": sees[:300]}


def prove(ticket: str, since: float, hwnd: int = 0, ask: Optional[Any] = None, look: Optional[Any] = None) -> Dict[str, Any]:
    """{'status': DONE | FAILED_CHECK | UNVERIFIED, 'proof': [...]}. Files the ticket names must exist, be written by this run and hold what the ticket asked;
    with no file named, the app's window is captured and judged. Nothing provable -> UNVERIFIED (never learned from as a success)."""
    proof: List[Dict[str, Any]] = []
    made = [m.group(1).strip() for m in _FILE.finditer(ticket) if re.search(r"\b(?:save|saved|export|store|render|write \w+ to)\w*\b(?:\s+\w+){0,4}\s*$", ticket[:m.start()], re.I)]
    files = list(dict.fromkeys(made or [m.group(1).strip() for m in _FILE.finditer(ticket) if not re.search(r"\b(?:open|read|from|insert|load)\b(?:\s+\w+){0,3}\s*$", ticket[:m.start()], re.I)]))
    # only a file the ticket MAKES must be new and hold the result; a file it opens / reads only has to exist (live Oct-28: a read of cities.xlsx was failed as 'older than this run')
    for f in [m.group(1).strip() for m in _FILE.finditer(ticket)]:
        if f not in files and os.path.isabs(f) and not os.path.isfile(f):
            proof.append({"file": f, "ok": False, "why": "a file the task uses does not exist"})
    for f in files:
        if not os.path.isabs(f):
            proof.append({"file": f, "ok": None, "why": "no folder was named, so where it was saved is not known"})
            continue
        if not os.path.isfile(f):
            proof.append({"file": f, "ok": False, "why": "the file was not saved"})
            continue
        if os.path.getmtime(f) < since - 1 or os.path.getsize(f) == 0:
            proof.append({"file": f, "ok": False, "why": "the file is empty or older than this run"})
            continue
        kind, what = read_back(f)
        if kind == "image":
            proof.append({"file": f, **judge_picture(ticket, what, look, ask)})
        elif kind == "text":
            kept = kept_in_file(what)
            proof.append({"file": f, "holds": what[:300], **(kept if kept else judge_text(ticket, what, ask))})
        elif kind == "exists":
            proof.append({"file": f, "ok": None, "why": "saved, but this kind of file cannot be read back here"})
        else:
            proof.append({"file": f, "ok": False, "why": f"the file cannot be opened: {what}"})
    # a ticket that only READS a file is proven by what it kept: the kept table's cells are in that file (live Oct-28: Excel's read half of Excel->PowerPoint had
    # 'nothing to check' and held the whole chain at PARTIAL)
    if not files and re.search(r"\b(?:read|copy|take|get|extract)\b", ticket, re.I):
        for f in [m.group(1).strip() for m in _FILE.finditer(ticket)]:
            if os.path.isabs(f) and os.path.isfile(f):
                kind, what = read_back(f)
                kept = kept_in_file(what) if kind == "text" else None
                if kept:
                    proof.append({"file": f, "read": True, **kept})
    if hwnd and all(p["ok"] is None for p in proof):
        img = None
        with contextlib.suppress(Exception):
            from core_organs import headless_input as HI
            img = HI.capture_window_robust(hwnd)[0]
        proof.append({"window": hwnd, **(judge_picture(ticket, img, look, ask, screen=True) if img is not None else {"ok": None, "why": "the window could not be captured"})})
    if any(p["ok"] is False for p in proof):
        return {"status": "FAILED_CHECK", "proof": proof}
    if proof and all(p["ok"] for p in proof):
        return {"status": "DONE", "proof": proof}
    return {"status": "UNVERIFIED", "proof": proof or [{"ok": None, "why": "nothing to check: no file named and no window"}]}


# ---- run --------------------------------------------------------------------------------------------------------------------------------------------------
GOOD = {"DONE", "ANSWERED", "DRAFTED"}


def unfinished_from_last(runs_dir: str = "") -> Tuple[str, List[str]]:
    """(the last run's id, the texts of its tickets that did not finish): a job left half done is continued, not started again."""
    folder = runs_dir or RUNS
    try:
        last = json.load(open(os.path.join(folder, "last_run.json"), encoding="utf-8"))
    except Exception:
        return "", []
    return last.get("run_id", ""), [t["text"] for t in last.get("tickets", []) if (t.get("result") or {}).get("status") not in GOOD]


def run(task: str, yes: bool = False, dry: bool = False, say=print, rag: Any = None, boot_first: bool = True, executors: Optional[Dict[str, Any]] = None, resume: bool = False, session: str = "") -> Dict[str, Any]:
    """`executors` replaces any of the four routes (tests); a missing key means the real one."""
    from core_organs import task_intake as TI
    from core_organs.mind import brain as BR
    t0 = time.time()
    run_id = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]
    out_dir = os.path.join(RUNS, run_id)
    os.makedirs(out_dir, exist_ok=True)
    ex = executors or {}
    with contextlib.suppress(Exception):                                                              # one blackboard for every ticket of this run: a web read feeds the desktop ticket after it
        from core_organs import loop_first as LF0
        LF0.BLACKBOARD.clear()
        LF0.KEEP_BOARD["on"] = True
    if resume:
        prev, left = unfinished_from_last()
        if not left:
            say("RESUME: the last run has nothing unfinished" if prev else "RESUME: there is no earlier run")
            return {"run_id": run_id, "task": task, "status": "NOTHING_TO_RESUME", "tickets": [], "resumed_from": prev}
        task = "; ".join(left)
        say(f"RESUME: continuing run {prev}: {len(left)} unfinished ticket(s)")
    rep: Dict[str, Any] = {"run_id": run_id, "task": task, "status": "FAILED", "tickets": []}
    if boot_first:
        say("BOOT")
        rep["boot"] = boot(say=say)
    if rag is None and "rag" not in ex:
        with contextlib.suppress(Exception):
            from core_organs import rag as R
            rag = R.get_rag()
    names = None
    with contextlib.suppress(Exception):
        from core_organs.mind import app_qa as QA
        names = QA.app_names(rag)
    say("INTAKE")
    intake = TI.analyse(task)
    rep["intake"] = {"tickets": intake.tickets, "domains": intake.ticket_domains, "secrets_removed": len(intake.secrets_found), "impossible": intake.impossible}
    say(f"  {len(intake.tickets)} ticket(s) by the intake, domains {intake.ticket_domains}" + (f", {len(intake.secrets_found)} secret(s) removed" if intake.secrets_found else ""))
    if intake.refused:
        rep.update(status="IMPOSSIBLE", reason="; ".join(intake.impossible))
        return _finish(rep, t0, out_dir, say)
    parts = split_parts(intake.clean_text)
    if len(parts) > len(intake.tickets):
        tickets = parts
        domains = []
        for pt in parts:
            domains.append(TI.classify_domain(pt, TI.detect_apps(pt, TI.installed_app_names()))[0])
    else:
        tickets, domains = intake.tickets, intake.ticket_domains
    # 'open paint, draw a heart, then fill it with grey and save as ...': the part after 'then' names no app and no site; it is the next step in the SAME app,
    # not a new task (live Nov-02: every such Paint task stopped at 'Which application should I use?')
    merged_t: List[str] = []
    merged_d: List[str] = []
    for i, tk in enumerate(tickets):
        dom = domains[i] if i < len(domains) else "unknown"
        if merged_t and merged_d[-1] == "desktop" and dom == "unknown" and not TI._URL_RE.search(tk):
            merged_t[-1] += ", then " + tk
            continue
        merged_t.append(tk)
        merged_d.append(dom)
    tickets, domains = merged_t, merged_d
    rep["intake"]["parts"] = tickets
    # group follow-up web tickets into one browser session
    routed: List[Dict[str, Any]] = []
    for i, tk in enumerate(tickets):
        dom = domains[i] if i < len(domains) else "unknown"
        kind = classify(tk, dom, rag, names)
        if kind != "web" and routed and routed[-1]["kind"] == "web" and kind in ("desktop", "question") and _DO.search(tk) and not [a for a, _p in TI.detect_apps(tk, TI.installed_app_names()) if a.lower() in tk.lower()]:   # the intake's fuzzy match took 'click' for the app 'Click to Do': an app counts only when its whole name is in the words
            from core_organs import web_executor as WE0
            if not WE0.resolve_site(tk, rag, names):
                kind = "web"                                                                           # 'click Features' right after a web step names no app and no site: it is the next step on the same page
        if kind == "web" and routed and routed[-1]["kind"] == "web":
            from core_organs import web_executor as WE
            if not WE.resolve_site(tk, rag, names) or WE.resolve_site(tk, rag, names).get("host") == routed[-1].get("host"):
                routed[-1]["text"] += "; " + tk
                routed[-1]["tickets"] += 1
                continue
        host = ""
        if kind == "web":
            from core_organs import web_executor as WE
            host = (WE.resolve_site(tk, rag, names) or {}).get("host", "")
        routed.append({"kind": kind, "text": tk, "domain": dom, "tickets": 1, "host": host, "route_by": ROUTE_LOG.get(tk, "rules")})
    if intake.question and not routed:
        rep.update(status="NEEDS_INPUT", question=intake.question)
        return _finish(rep, t0, out_dir, say)
    say("ROUTE")
    for r_ in routed:
        say(f"  {r_['kind'].upper():<8} {r_['text'][:90]}")
    # think: plan-level risk gate, before anything runs
    jobs: List[Dict[str, Any]] = []
    for r_ in routed:
        gate_text = r_["text"]
        if r_["kind"] == "write" and not re.search(r"\b(?:send|publish|post|tweet|share|email)\s+(?:it|this|that|them|the\s+(?:email|message|post|draft))\b|\band\s+(?:send|publish|post)\s+it\b", r_["text"], re.I):
            gate_text = "draft a text"                                                                # drafting is not publishing: the draft is shown, nothing is sent
        th = BR.think(gate_text, app=r_.get("host", ""))
        r_["think"] = {"decision": th["decision"], "kind": th["kind"], "severity": th["consequence"]["severity"], "say": th["say"] if th["decision"] != "proceed" else ""}
        if th["decision"] == "ask_first" and not yes:
            jobs.append({**r_, "result": {"status": "NEEDS_CONFIRM", "question": th["consequence"].get("heads_up", th["say"])}})
        else:
            jobs.append(r_)
    if dry:
        for j in jobs:
            j.setdefault("result", {"status": "DRY_RUN", "would": j["kind"]})
    # do: independent web / question / write tickets side by side, desktop tickets one at a time
    say("DO")
    build_state: Dict[str, Any] = {}

    def execute(j: Dict[str, Any]) -> Dict[str, Any]:
        k = j["kind"]
        if k in ex:
            return ex[k](j["text"])
        if k == "question":
            return do_question(j["text"], rag, names)
        if k == "write":
            return do_write(j["text"])
        if k == "web":
            return do_web(j["text"], rag, yes, names, out_dir, session)
        if k == "build":
            return do_build(j["text"], build_state)
        if k == "video":
            return do_video(j["text"], out_dir)
        if k == "code":
            return do_code(j["text"], out_dir)
        return do_desktop(j["text"], yes)
    todo = [j for j in jobs if "result" not in j]
    parallel = [j for j in todo if j["kind"] in ("web", "question", "write", "code")]
    serial = [j for j in todo if j["kind"] not in ("web", "question", "write", "code")]
    if parallel:
        with cf.ThreadPoolExecutor(max_workers=min(3, len(parallel))) as pool:
            futs = {pool.submit(lambda jj=j: _safe(execute, jj)): j for j in parallel}
            for fu in cf.as_completed(futs):
                futs[fu]["result"] = fu.result()
    for j in serial:
        j["result"] = _safe(execute, j)
    # a part that could not do its ticket hands it to the model's next choice; the route that WORKED is what the report (and so the memory) keeps
    for j in todo:
        tried = [j["kind"]]
        first = j["result"]
        while j["result"].get("status") in ("FAILED", "NEEDS_INPUT") and len(tried) < 3:
            why = str(j["result"].get("evidence") or j["result"].get("question") or j["result"].get("status"))
            nxt = None
            with contextlib.suppress(Exception):
                nxt = reroute(j["text"], tried, why)
            if not nxt:
                break
            if nxt in ACTS:                                                                            # the risk gate saw this ticket as a draft or a question: an acting part needs its own look first
                th = BR.think(j["text"], app=j.get("host", ""))
                if th["decision"] == "ask_first" and not yes:
                    j.update(kind=nxt, result={"status": "NEEDS_CONFIRM", "question": th["consequence"].get("heads_up", th["say"])}, route_by=f"retry after {', '.join(tried)} could not")
                    tried.append(nxt)
                    break
            res = _safe(execute, {**j, "kind": nxt})
            tried.append(nxt)
            if res.get("status") in GOOD or res.get("status") in ("ANSWERED_WEAK", "DRAFTED_WITH_ISSUES", "PARTIAL", "UNVERIFIED"):
                j.update(kind=nxt, result=res, route_by=f"retry after {', '.join(tried[:-1])} could not")
                break
        if len(tried) > 1:
            j["tried"] = tried
            if j["result"] is not first:
                j["result"]["first_try"] = {"kind": tried[0], "status": first.get("status")}
    for j in jobs:
        res = j["result"]
        say(f"  {res.get('status', '?'):<14} {j['kind']:<8} {j['text'][:70]}")
        rep["tickets"].append({"kind": j["kind"], "text": j["text"], "route_by": j.get("route_by"), "tried": j.get("tried"), "think": j.get("think"), "result": res})
    sts = [t["result"].get("status") for t in rep["tickets"]]
    good = {"DONE", "ANSWERED", "DRAFTED"}
    if sts and all(s in good for s in sts):
        rep["status"] = "DONE"
    elif any(s == "NEEDS_CONFIRM" for s in sts):
        rep["status"] = "NEEDS_CONFIRM"
    elif any(s == "NEEDS_INPUT" for s in sts):
        rep["status"] = "NEEDS_INPUT"
    elif any(s in good or s in ("UNVERIFIED", "ANSWERED_WEAK", "DRAFTED_WITH_ISSUES", "PARTIAL") for s in sts):
        rep["status"] = "PARTIAL"
    else:
        rep["status"] = "FAILED"
    return _finish(rep, t0, out_dir, say)


def _safe(fn, j) -> Dict[str, Any]:
    try:
        return fn(j)
    except Exception as e:
        return {"status": "FAILED", "evidence": f"{type(e).__name__}: {str(e)[:200]}"}


def _finish(rep: Dict[str, Any], t0: float, out_dir: str, say) -> Dict[str, Any]:
    rep["seconds"] = round(time.time() - t0, 1)
    with contextlib.suppress(Exception):
        from core_organs import loop_first as LF0
        rep["blackboard"] = {k: {kk: (vv if kk != "rows" else f"{len(vv)} rows") for kk, vv in v.items() if kk != "text"} for k, v in LF0.BLACKBOARD.items()}
        LF0.KEEP_BOARD["on"] = False                                                                  # the board is this run's only
    with contextlib.suppress(Exception):
        json.dump(rep, open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=str)
        if rep.get("tickets"):
            json.dump(rep, open(os.path.join(os.path.dirname(out_dir), "last_run.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=str)
    say(f"RESULT {rep['status']}  ({rep['seconds']} s)  report: {os.path.join(out_dir, 'report.json')}")
    for t in rep.get("tickets", []):
        r = t["result"]
        body = r.get("answer") or r.get("draft") or r.get("evidence") or r.get("question") or ""
        if body:
            say(f"  - [{t['kind']}] {str(body)[:900]}")
    if rep.get("question"):
        say(f"  ? {rep['question']}")
    return rep


# ---- learn an app: read it, map it, practise on it, prove it, keep what worked -------------------------------------------------------------------------
PRACTICE_SYSTEM = ("You write practice tasks for an automation system that is learning one desktop app. Write N different tasks a person would really type, in "
                   "plain words, each describing the RESULT they want (the content, and which of the app's features to use), never a list of menu clicks and never "
                   "'>' paths. Each task starts from a new empty document (never open an existing file), says the exact text or numbers it puts in, makes something with the "
                   "app and ends SAVE_RULE Any result you state must be correct (work arithmetic out yourself). Start each with 'open APP,'. Never delete, send, share, upload, pay, buy, "
                   "install, sign in or change settings. Mix easy and harder tasks. Reply JSON only: {\"tasks\": [\"...\"]}.")
_LEVEL_RULE = ("SIZE: each task uses exactly ONE of the app's features and at most two actions (one short text, one shape, one calculation), then the end.",
               "SIZE: each task uses two or three of the app's features together.",
               "SIZE: each task is a realistic piece of work using four or more of the app's features.")
_SAVE_RULE_FILE = "by saving it as a NEW file in the given folder (a new file name with the app's usual extension)."
_SAVE_RULE_SCREEN = "with the exact result that should then be visible in the app, written as 'the app should show ...' (this app does not save files)."
_RISKY_TASK = re.compile(r"\b(delete|remove|erase|send|e-?mail|share|upload|pay|buy|purchase|install|uninstall|sign ?in|log ?in|password|registry|settings|empty|format (?:the )?(?:disk|drive))\b", re.I)
FLYWHEEL = os.path.join(os.path.dirname(RUNS), "ai_root", "harvest", "training", "flywheel", "proven_plans.jsonl")


def _running(exe: str) -> bool:
    """Is a program with this file name already running (the person's own window: never touched)?"""
    if not exe:
        return False
    with contextlib.suppress(Exception):
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {os.path.basename(exe)}", "/NH"], capture_output=True, text=True, timeout=15,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        return os.path.basename(exe).lower() in out.lower()
    return False


def _pids(exe: str) -> set:
    """Process ids running this program file name."""
    with contextlib.suppress(Exception):
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {os.path.basename(exe)}", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=15,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        return {int(r[1]) for r in csv.reader(out.splitlines()) if len(r) > 1 and r[1].isdigit()}
    return set()


def _close_own(exe: str, before: set, say=print) -> List[int]:
    """Close the copies of the app THIS learning run started (by pid; the ones running before it began are never touched). Live Nov-02: each practice run left
    its Paint / Calculator / Excel window open, and the next app's run then saw 'already open' and skipped its live phases."""
    shut = []
    for pid in sorted(_pids(exe) - set(before)) if exe else []:
        with contextlib.suppress(Exception):
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            shut.append(pid)
    if shut:
        say(f"[learn] closed the {len(shut)} window(s) this run opened (pids {shut})")
    return shut


def _app_commands(key: str, limit: int = 60) -> List[str]:
    """Names of the commands the knowledge holds for this app (menus, ribbon, scanned controls), most corroborated first."""
    with contextlib.suppress(Exception):
        from core_organs import organ_48_app_behavior_model as bm
        # what is ON SCREEN (scanned / learned), most used first; programming-interface strings (preload:api-strings: 'Add Foreign Key Field') are not features a person picks
        rows = bm.get_model()._conn.execute("SELECT name, menu_path FROM bm_commands WHERE app_key=? AND (risk IS NULL OR risk!='E2') AND coalesce(origin,'') NOT LIKE 'preload:%' "
                                            "ORDER BY (source='learned') DESC, coalesce(successes,0) DESC LIMIT 2000", (key,)).fetchall()
        names = [(r[1] or r[0] or "").strip() for r in rows]
        names = [n for n in names if len(n.split(">")[-1].split()) <= 5 and not re.search(r"[.,]\s*\w", n.split(">")[-1])]   # a sentence ('There's nothing saved…', 'Arial, select to download') is status text, not a feature
        # a feature has a word in its name: zoom levels / cell refs / bare numbers and UIA class names ('ButtonControl') say nothing a person would ask for
        names = [n for n in dict.fromkeys(names) if 2 < len(n) < 80 and re.search(r"[A-Za-z]{3,}", n.split(">")[-1])
                 and not re.fullmatch(r"[A-Z][a-z]+(?:Control|Viewer|Item|Pane)", n.split(">")[-1].strip())]
        if len(names) > limit:                                                    # spread across the whole app, not the first letters of the alphabet
            step = len(names) / limit
            names = [names[int(i * step)] for i in range(limit)]
        return names
    return []


def _saves_files(key: str, d: Dict[str, Any]) -> bool:
    """Can this app save a file (so a practice task is proven from the file), or is its result only on screen (calculator)?"""
    if d.get("opens_files"):
        return True
    with contextlib.suppress(Exception):
        from core_organs import organ_48_app_behavior_model as bm
        names = bm.get_model()._conn.execute("SELECT name FROM bm_commands WHERE app_key=? AND lower(name) LIKE '%save%'", (key,)).fetchall()
        return any(re.match(r"\s*save(?: as| a copy)?\b", r[0] or "", re.I) for r in names)   # a Save command, not a sentence that says 'saved'
    return True


def learn_app(app: str, minutes: float = 10.0, practice: int = 5, questions: int = 4, live: bool = True, say=print, rag: Any = None) -> Dict[str, Any]:
    """Learn one app from first contact, then show what was learned by USING it. Phases, each measured:
       1 READ      the program itself without opening it: REA / type library / the Store package's own UI words, filed in the knowledge
       2 MAP       the live app: control tree, menus, ribbon, dialogs, state and a frontier explored one surface at a time (organ_63), invisible
       3 ASK       questions about the app answered from what was just learned (grounded: cited, or 'not found')
       4 PRACTISE  tasks it writes for itself from the app's own commands, done end to end and PROVEN from the saved files
       5 KEEP      every proven run's step plan becomes a training row (verified_by file_readback): the model is retrained on what really worked
       6 REPORT    readiness: what is known, what was proven, what failed and why
    The person's own running copy of the app is never touched: then only phase 1 and 3 run, and the report says so."""
    from core_organs import loop_first as LF
    from core_organs import organ_63_app_mastery as M63
    from core_organs import rea_native as RN
    from core_organs.mind import app_qa as QA
    t0 = time.time()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    if rag is None:
        from core_organs import rag as R
        rag = R.get_rag()
    rep: Dict[str, Any] = {"app": app, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "phases": {}}
    # 1 READ
    t = time.time()
    read: Dict[str, Any] = {}
    with contextlib.suppress(Exception):
        store = RN.learn_store_apps(rag, [app], say=lambda s: None) if RN.store_apps([app]) else {}
        if store:
            read["store"] = store
    if not read:
        with contextlib.suppress(Exception):
            low = app.lower().replace(" ", "")
            prog = next((p for p in RN.find_programs() if low in (p.get("name", "") + os.path.basename(p.get("exe", ""))).lower().replace(" ", "")), None)
            if prog:
                dg = RN.digest(prog)
                read["program"] = {"exe": prog["exe"], "mb": prog.get("mb"), "filed": RN.file_into_rag(rag, dg, f"learn_{stamp}"), "how_to_drive": RN.how_to_drive(dg)}
    d0 = {}
    with contextlib.suppress(Exception):
        d0 = M63.know(app, live=False)
    key = d0.get("app_key") or re.sub(r"[^a-z0-9]+", "_", app.lower()).strip("_")
    exe = (d0.get("identity") or {}).get("exe") or (read.get("program") or {}).get("exe", "")
    rep["app_key"], rep["exe"] = key, exe
    rep["phases"]["read"] = {**read, "seconds": round(time.time() - t, 1), "level": d0.get("knowledge_level")}
    say(f"[learn] {app}: read the program in {rep['phases']['read']['seconds']} s (level {d0.get('knowledge_level')})")
    busy = _running(exe)
    before = _pids(exe)
    if busy:
        say(f"[learn] {app} is already open on this computer: the live phases are skipped so your own window is never touched")
    # 2 MAP
    t = time.time()
    d = d0
    if live and not busy:
        with contextlib.suppress(Exception):
            d = M63.know(app, live=True, budget_s=max(30.0, minutes * 60 * 0.4))
    m = d.get("measure") or {}
    _close_own(exe, before, say)
    rep["phases"]["map"] = {"ran": bool(live and not busy), "seconds": round(time.time() - t, 1), "level": d.get("knowledge_level"),
                            "commands": m.get("commands"), "with_shortcut": m.get("commands_with_shortcut"), "dialogs": m.get("dialogs"),
                            "layout_controls": m.get("layout_controls"), "state_variables": m.get("statevars"), "frontier": m.get("frontier")}
    say(f"[learn] map: {m.get('commands')} commands, {m.get('dialogs')} dialogs, {m.get('layout_controls')} controls in {rep['phases']['map']['seconds']} s")
    cmds = _app_commands(key)
    # 3 ASK
    t = time.time()
    asked = []
    for c in cmds[: max(0, questions)]:
        q = f"In {app}, how do I use {c.split('>')[-1].strip()}?"
        with contextlib.suppress(Exception):
            r = do_question(q, rag, None)
            asked.append({"q": q, "status": r.get("status"), "answer": str(r.get("answer") or "")[:240]})
    rep["phases"]["ask"] = {"asked": len(asked), "answered": sum(1 for a in asked if a["status"] == "ANSWERED"), "items": asked, "seconds": round(time.time() - t, 1)}
    # 4 PRACTISE + 5 KEEP
    t = time.time()
    tasks: List[str] = []
    folder = os.path.join(os.path.dirname(RUNS), "practice", key)
    os.makedirs(folder, exist_ok=True)
    saves = _saves_files(key, d)
    feats = "\n- ".join(c.split(">")[-1].strip() for c in cmds[:40] or ["(none found yet)"])

    def write_tasks(level: int, n: int) -> List[str]:
        """n tasks at one difficulty level, from the app's own features. Level 1 = one feature, so the first thing proven is small; harder levels only after it."""
        system = PRACTICE_SYSTEM.replace("SAVE_RULE", _SAVE_RULE_FILE if saves else _SAVE_RULE_SCREEN).replace("APP", app) + " " + _LEVEL_RULE[min(level, len(_LEVEL_RULE)) - 1]
        prompt = ((f"N = {n}\nAPP = {app}\n" + (f"Folder for the saved files: {folder}\n" if saves else ""))
                  + "Some of the app's own features (from scanning it; use their names in plain sentences):\n- " + feats
                  + (f"\nIt opens these file types: {', '.join(map(str, (d.get('opens_files') or [])[:12]))}" if d.get("opens_files") else "")
                  + (f"\nAlready practised (write different ones): {'; '.join(x['task'][:80] for x in results[-6:])}" if results else "") + "\nJSON:")
        out: List[str] = []
        for _ in range(2):                                                        # one retry, told what was wrong with the first answer
            with contextlib.suppress(Exception):
                raw = QA.ask_llm(prompt, system, timeout=180, max_tokens=900, json_mode=True) or ""
                mm = re.search(r"\{.*\}", raw, re.S)
                out = [str(x).strip() for x in (json.loads(mm.group(0)).get("tasks") or []) if str(x).strip()] if mm else []
            bad = [x for x in out if ">" in x or len(x.split()) < 5]
            if out and len(bad) * 2 < len(out):
                break
            prompt += "\nYour last answer listed menu clicks or fragments. Write whole sentences a person would type, each describing the finished result.\nJSON:"
        return out[:n]

    kept_rows, results = 0, []
    level, levels_done = 1, []
    while practice and live and not busy and len(results) < practice:
        batch = write_tasks(level, min(2, practice - len(results)))
        tasks += batch
        if not batch:
            break
        proven_here = 0
        for task in batch:
            ends_ok = (folder.lower() in task.lower()) if saves else bool(re.search(r"\bshould show\b", task, re.I))
            if _RISKY_TASK.search(task) or ">" in task or not ends_ok:
                results.append({"task": task, "level": level, "status": "SKIPPED", "why": "risky words, a menu-click list, or no checkable end (" + ("not saved in the practice folder" if saves else "no 'should show'") + ")"})
                continue
            r: Dict[str, Any] = {}
            tt = time.time()
            with contextlib.suppress(Exception):
                r = run(task, yes=False, say=lambda s: None, rag=rag, boot_first=False)
            _close_own(exe, before, say)
            tk = (r.get("tickets") or [{}])[-1].get("result") or {}
            st = r.get("status", "FAILED")
            results.append({"task": task, "level": level, "status": st, "seconds": round(time.time() - tt, 1), "proof": str(tk.get("proof") or tk.get("evidence") or "")[:300]})
            if st == "DONE" and LF.LAST_PLANS:
                os.makedirs(os.path.dirname(FLYWHEEL), exist_ok=True)
                with open(FLYWHEEL, "a", encoding="utf-8") as fh:
                    for p in LF.LAST_PLANS:
                        if not p.get("steps"):
                            continue
                        text = " ; ".join(p["clauses"])
                        shown, paths = text, {}
                        for i, pth in enumerate(dict.fromkeys(LF._PATH_RE.findall(text))):
                            paths[pth] = f"PATH{i + 1}"
                            shown = shown.replace(pth, paths[pth])
                        steps = [{**s, "text": paths.get(s.get("text", ""), s.get("text", ""))} for s in p["steps"]]
                        fh.write(json.dumps({"messages": [{"role": "system", "content": [{"type": "text", "text": LF.STEP_SYSTEM.replace("APP", p["app"])}]},
                                                          {"role": "user", "content": [{"type": "text", "text": f"Instruction: \"{shown}\"\nJSON:"}]},
                                                          {"role": "assistant", "content": [{"type": "text", "text": json.dumps({"steps": steps}, ensure_ascii=False)}]}],
                                             "meta": {"job": "plan", "source": "practice", "verified_by": "file_readback", "app_key": key, "split_group": f"practice::{key}::{stamp}",
                                                      "ui_frames": True, "lang": "en"}}, ensure_ascii=False) + "\n")
                        kept_rows += 1
            say(f"[learn] practice: {st} in {results[-1]['seconds']} s -- {task[:90]}")
            proven_here += st == "DONE"
        levels_done.append({"level": level, "proven": proven_here, "of": len(batch)})
        if proven_here * 2 >= max(1, len(batch)):
            level += 1                                                            # proven at this size: the next tasks are bigger
    done = sum(1 for x in results if x["status"] == "DONE")
    tried = sum(1 for x in results if x["status"] != "SKIPPED")
    rep["phases"]["practice"] = {"written": len(tasks), "levels": levels_done, "highest_level_proven": max([x["level"] for x in levels_done if x["proven"]] or [0]), "tried": tried, "proven_done": done, "kept_training_rows": kept_rows, "results": results, "seconds": round(time.time() - t, 1)}
    # 6 REPORT
    ready = {"knows_commands": bool(m.get("commands")), "answers_questions": f"{rep['phases']['ask']['answered']}/{rep['phases']['ask']['asked']}",
             "proven_tasks": f"{done}/{tried}", "verdict": ("ready for supervised automation" if tried and done / tried >= 0.8 else
                                                            "partly ready: it does some tasks, check the failures" if done else
                                                            "not ready: nothing proven yet" if tried else "not tested live (app busy or live off)")}
    rep["readiness"] = ready
    rep["seconds"] = round(time.time() - t0, 1)
    out_dir = os.path.join(os.path.dirname(RUNS), "..", "reports", "learn")
    out_dir = os.path.normpath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{key}_{stamp}.json")
    json.dump(rep, open(path, "w", encoding="utf-8"), indent=1, default=str)
    rep["report"] = path
    say(f"[learn] {app}: {ready['verdict']} | commands {m.get('commands')} | questions {ready['answers_questions']} | proven {ready['proven_tasks']} | {rep['seconds']} s | {path}")
    return rep


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="hojaiga")
    ap.add_argument("task", nargs="*", help="the task in plain words")
    ap.add_argument("--yes", action="store_true", help="approve the risky controls this task names (pay / send / delete ...)")
    ap.add_argument("--boot-only", action="store_true")
    ap.add_argument("--resume", action="store_true", help="continue the last run: only its unfinished tickets are done again")
    ap.add_argument("--session", default="", help="a site whose saved login (session vault) the web parts start with, e.g. linkedin.com; you created it yourself with: python -m core_organs.session_vault capture <site>")
    ap.add_argument("--dry", action="store_true", help="intake, routing and the risk check only; nothing is executed")
    ap.add_argument("--learn", default="", help="learn these apps (comma-separated): read, map, ask, practise, prove, keep; a report per app in reports/learn")
    ap.add_argument("--minutes", type=float, default=10.0, help="--learn: time budget per app for the live map")
    ap.add_argument("--practice", type=int, default=5, help="--learn: practice tasks per app")
    a = ap.parse_args(argv)
    if a.learn:
        reps = [learn_app(x.strip(), minutes=a.minutes, practice=a.practice) for x in a.learn.split(",") if x.strip()]
        return 0 if reps else 1
    if a.boot_only:
        h = boot()
        return 0 if h["ok"] else 1
    task = " ".join(a.task).strip()
    if not task and not a.resume:
        task = input("Task > ").strip()
    r = run(task, yes=a.yes, dry=a.dry, resume=a.resume, session=a.session)
    return 0 if r["status"] in ("DONE", "PARTIAL", "NEEDS_CONFIRM", "NEEDS_INPUT", "NOTHING_TO_RESUME") else 1


if __name__ == "__main__":
    sys.exit(main())
