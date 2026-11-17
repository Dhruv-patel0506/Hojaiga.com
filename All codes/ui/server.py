"""
ui.server -- the local companion backend (FastAPI + server-sent events). Binds to 127.0.0.1 only.

    GET  /                      the companion page
    GET  /api/state             session snapshot
    GET  /api/events            live event stream (SSE); resumes from Last-Event-ID
    GET  /api/apps              installed programs to pick from
    POST /api/start   {target}  open + scan the program visibly
    POST /api/chat    {text}    talk to HoJaiga (yes / questions / tasks)
    POST /api/control {action}  next | repeat | stop | voice | autoplay | close
    POST /api/new               end the session and start clean
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse  # noqa: E402

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app = FastAPI(title="HoJaiga companion")
_state: Dict[str, Any] = {"session": None, "apps": None}
_lock = threading.Lock()


def session() -> Any:
    with _lock:
        if _state["session"] is None:
            from core_organs.live_tutor import TutorSession
            _state["session"] = TutorSession()
        return _state["session"]


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/state")
def state() -> Dict[str, Any]:
    return session().snapshot()


@app.get("/api/apps")
def apps() -> List[str]:
    if _state["apps"] is None:
        from core_organs.harvest import catalogue as C
        import re
        out = []
        for a in C.installed():
            if not C.EXCLUDE.search(a["name"].lower()):
                out.append(a["name"])
        _state["apps"] = sorted(set(out), key=str.lower)
    return _state["apps"]


@app.post("/api/start")
async def start(req: Request) -> Dict[str, Any]:
    body = await req.json()
    target = str(body.get("target", "")).strip()
    if not target:
        return {"ok": False, "error": "say which program to open"}
    from core_organs.rag import domains as DM
    if DM.looks_like_url(target) or target.lower().startswith(("http://", "https://")):
        s = session()
        s.emit("error", text="Websites and web apps are taught through the command-line onboarding in this build (python -m core_organs.rag onboard <url>); the live on-screen tour covers installed programs.")
        return {"ok": False, "error": "websites: not in the live tour yet"}
    session().start(target)
    return {"ok": True}


@app.post("/api/chat")
async def chat(req: Request) -> Dict[str, Any]:
    body = await req.json()
    session().chat(str(body.get("text", "")))
    return {"ok": True}


@app.post("/api/control")
async def control(req: Request) -> Dict[str, Any]:
    body = await req.json()
    session().control(str(body.get("action", "")))
    return {"ok": True}


@app.get("/api/debug")
def debug() -> Dict[str, Any]:
    s = session()
    ov = s.overlay
    return {"overlay": getattr(ov, "kind", None), "overlay_error": getattr(ov, "error", ""), "actors": len(getattr(ov, "actors", []) or []), "window": s.window, "pos": s._pos, "events": len(s.events),
            "log": [e for e in s.events if e["kind"] in ("log",)][-5:]}


@app.post("/api/new")
def new() -> Dict[str, Any]:
    with _lock:
        s = _state["session"]
        _state["session"] = None
    if s is not None:
        threading.Thread(target=s.close, daemon=True).start()
    return {"ok": True}


@app.get("/api/events")
async def events(request: Request) -> StreamingResponse:
    last = request.headers.get("last-event-id")
    start_at = int(last) + 1 if (last and last.isdigit()) else 0

    async def gen():
        i = start_at
        sess = session()
        while True:
            if await request.is_disconnected():
                return
            if session() is not sess:                                   # a new session replaced this one
                sess, i = session(), 0
                yield "event: reset\ndata: {}\n\n"
            evs = sess.since(i)
            for ev in evs:
                yield f"id: {ev['id']}\nevent: {ev['kind']}\ndata: {json.dumps(ev, default=str)}\n\n"
                i = ev["id"] + 1
            if not evs:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.35)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
