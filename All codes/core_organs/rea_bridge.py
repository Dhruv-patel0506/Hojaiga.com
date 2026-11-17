"""
rea_bridge -- REA (Reverse Engineer Anything, npm `rea-agents`) as one more TOOL of the Qwen + RAG system.

Where it sits.  The explorer (try_app) learns what a web app DOES by clicking it; REA reads what the app IS made of, with evidence: its scripts and the routes inside them, the API calls it makes (turned into
named tools), and, for an installed Electron / JavaScript desktop app, its modules, imports and the boundary between the page and the main process. This module runs REA as a subprocess (its own Node 22,
installed under D:\\new_automation\\tools, nothing global), turns its Evidence into short, source-cited facts, and files them in the RAG next to what the explorer learned:

    web_static()    REA's view of the live page (through the browser's debug port): scripts, resources, same-site URLs found in the DOM, storage KEY NAMES, route candidates from the code, page-declared WebMCP tools
    api_tools()     the API a recorded session used, as tools: method, path template, parameters, body shape, statuses (REA environment-build; the bundle is built in a temp folder, read, deleted)
    desktop_app()   an installed Electron / JS application: modules, imports, Electron boundaries (IPC channels, preload, window settings), routes
    file_into_rag() the digest as a retrievable document + one procedure per API tool + a command per route; every fact keeps REA's evidence id

Safety.  REA runs only what the caller names. HAR bodies can contain credentials: nothing from request / response BODIES or HEADERS is copied into the RAG, only names, templates, shapes and counts.
Write-type API tools (POST/PUT/PATCH/DELETE) are stored as KNOWLEDGE, never executed here. Static analysis never runs the application.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse

TOOLS = os.environ.get("HOJAIGA_TOOLS", os.path.join("D:" + os.sep, "new_automation", "tools"))
NODE = os.environ.get("HOJAIGA_REA_NODE", os.path.join(TOOLS, "node-v22.23.4-win-x64", "node.exe"))
REA_JS = os.environ.get("HOJAIGA_REA_JS", os.path.join(TOOLS, "rea", "node_modules", "rea-agents", "scripts", "rea.mjs"))
DATA = os.environ.get("HOJAIGA_DATA", os.path.join("D:" + os.sep, "new_automation", "data"))
OUT_DIR = os.path.join(DATA, "rea")
WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")


GHIDRA = os.environ.get("GHIDRA_INSTALL_DIR", os.path.join(TOOLS, "ghidra_12.1.4_PUBLIC"))
JDK_DIRS = [os.path.join(TOOLS, d) for d in sorted(os.listdir(TOOLS), reverse=True) if d.lower().startswith(("jdk-", "jdk25", "openjdk")) and os.path.isdir(os.path.join(TOOLS, d))] if os.path.isdir(TOOLS) else []


def native_env() -> Dict[str, str]:
    """Environment for REA's native-binary analysis: GHIDRA_INSTALL_DIR, and JAVA_HOME of the JDK kept next to it (Ghidra 12.2 needs Java 25 or newer; the system Java 17 is not enough)."""
    env = dict(os.environ)
    env.setdefault("REA_GHIDRA_STARTUP_TIMEOUT_MS", "1500000")                     # REA's default (330 s) is too short for a loaded machine (measured)
    if os.path.isdir(GHIDRA):
        env["GHIDRA_INSTALL_DIR"] = GHIDRA
    for d in JDK_DIRS:
        home = d if os.path.isfile(os.path.join(d, "bin", "java.exe")) else next((os.path.join(d, x) for x in os.listdir(d) if os.path.isfile(os.path.join(d, x, "bin", "java.exe"))), "")
        if home:
            env["JAVA_HOME"] = home
            env["PATH"] = os.path.join(home, "bin") + os.pathsep + env.get("PATH", "")
            break
    return env


def available() -> bool:
    return os.path.isfile(NODE) and os.path.isfile(REA_JS)


def run(cmd: str, *args: str, timeout: float = 180.0) -> Dict[str, Any]:
    """One REA command. Returns {ok, data (the parsed JSON object), error, seconds}. Progress lines go to stderr and are ignored."""
    if not available():
        return {"ok": False, "data": None, "error": "REA is not installed (see D:\\new_automation\\tools\\rea)", "seconds": 0.0}
    t0 = time.time()
    try:
        p = subprocess.run([NODE, REA_JS, cmd, *[str(a) for a in args], "--json"], capture_output=True, text=True, timeout=timeout, env=native_env(), cwd=os.path.dirname(os.path.dirname(os.path.dirname(REA_JS))), encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return {"ok": False, "data": None, "error": f"timed out after {timeout:.0f} s", "seconds": round(time.time() - t0, 1)}
    out = (p.stdout or "").strip()
    data = None
    with contextlib.suppress(Exception):
        a, b = out.find("{"), out.rfind("}")
        data = json.loads(out[a:b + 1]) if a >= 0 and b > a else None
    err = ""
    if p.returncode != 0 or (isinstance(data, dict) and data.get("error")):
        err = (data or {}).get("message") or (data or {}).get("error") or (p.stderr or "").strip()[-200:] or f"exit {p.returncode}"
    return {"ok": p.returncode == 0 and not err, "data": data, "error": err, "seconds": round(time.time() - t0, 1)}


def nr_of(res: Dict[str, Any]) -> Dict[str, Any]:
    d = res.get("data") or {}
    return d.get("normalized_result") or {}


def evidence_id(res: Dict[str, Any]) -> str:
    return (res.get("data") or {}).get("evidence_id", "")


# ------------------------------------------------------------------------------------------------------------------------------------ live web page
def digest_page(nr: Dict[str, Any], origin: str) -> Dict[str, Any]:
    scripts = (nr.get("scripts") or {}).get("items", [])
    resources = nr.get("resources") or []
    by_type: Dict[str, int] = {}
    for r in resources:
        by_type[r.get("type", "?")] = by_type.get(r.get("type", "?"), 0) + 1
    urls = []
    for d in ((nr.get("metadata") or {}).get("dom_urls") or []):
        u = d.get("url", "")
        pu = urlparse(u)
        if pu.scheme in ("http", "https") and (not origin or u.startswith(origin)):
            urls.append(pu.path or "/")
    st = nr.get("storage") or {}
    return {"scripts": len(scripts), "script_hosts": sorted({urlparse(s.get("url", "")).netloc for s in scripts if s.get("url")})[:8], "script_bytes": sum(int(s.get("length") or 0) for s in scripts),
            "source_maps": sum(1 for s in scripts if s.get("source_map_url")), "resources": by_type, "dom_nodes": (nr.get("dom") or {}).get("total_nodes"), "accessibility_nodes": (nr.get("accessibility") or {}).get("total_nodes"),
            "frames": len(nr.get("frames") or []), "same_site_paths": sorted(dict.fromkeys(urls))[:80], "local_storage_keys": (st.get("local_storage_keys") or [])[:20],
            "session_storage_keys": (st.get("session_storage_keys") or [])[:20], "indexed_db": (st.get("indexed_db_names") or [])[:10], "websockets": len((nr.get("network") or {}).get("websocket_connections") or [])}


def digest_bundle(nr: Dict[str, Any]) -> Dict[str, Any]:
    inv = nr.get("route_inventory") or {}
    routes = []
    for r in inv.get("routes", []):
        pat = r.get("pattern") or r.get("path") or r.get("route") or ""
        if pat:
            routes.append(pat)
    cov = inv.get("coverage") or {}
    return {"routes": sorted(dict.fromkeys(routes))[:120], "sources": (inv.get("statistics") or {}).get("sources_retained"), "coverage": cov.get("application_routes", "unknown"), "unknowns": len(nr.get("unknowns") or [])}


def web_static(endpoint: str, origin: str = "", observation_ms: int = 1500) -> Dict[str, Any]:
    """REA's static + passive reading of the page currently open in the browser at `endpoint` (a loopback debug address)."""
    out: Dict[str, Any] = {"ok": False, "evidence": {}}
    r = run("list-browser-targets", endpoint, timeout=60)
    targets = (nr_of(r).get("targets") or []) if r["ok"] else []
    pick = next((t for t in targets if t.get("type") == "page" and (not origin or str(t.get("url", "")).startswith(origin))), None) or next((t for t in targets if t.get("type") == "page"), None)
    if not pick:
        out["error"] = r.get("error") or "no page target"
        return out
    tid = pick["target_id"]
    pg = run("inspect-web-page", endpoint, tid, "--observation-ms", observation_ms, "--include-json-body-shapes", "--include-storage-keys", "--include-websocket-shapes", timeout=150)
    if pg["ok"]:
        out["page"] = digest_page(nr_of(pg), origin or pick.get("origin", ""))
        out["evidence"]["page"] = evidence_id(pg)
    bd = run("analyze-web-bundle", endpoint, tid, "--observation-ms", observation_ms, timeout=200)
    if bd["ok"]:
        out["bundle"] = digest_bundle(nr_of(bd))
        out["evidence"]["bundle"] = evidence_id(bd)
    wm = run("discover-webmcp-tools", endpoint, tid, timeout=60)
    if wm["ok"]:
        n = nr_of(wm)
        out["webmcp"] = {"status": n.get("status"), "tools": [t.get("name") for t in (n.get("tools") or {}).get("items", [])][:30]}
    out["ok"] = "page" in out or "bundle" in out
    out["seconds"] = round(sum(x["seconds"] for x in (r, pg, bd, wm)), 1)
    return out


# ------------------------------------------------------------------------------------------------------------------------------------ recorded session -> API tools
def sanitize_har(path: str) -> None:
    """HAR uses -1 for 'not applicable'; REA's HAR schema wants >= 0."""
    h = json.load(open(path, encoding="utf-8"))
    for e in h.get("log", {}).get("entries", []):
        for k, v in list((e.get("timings") or {}).items()):
            if isinstance(v, (int, float)) and v < 0:
                e["timings"][k] = 0
        if e.get("time", 0) < 0:
            e["time"] = 0
    json.dump(h, open(path, "w", encoding="utf-8"))


def api_tools(har_path: str, name: str = "site-env") -> Dict[str, Any]:
    """The API the recorded session used, as REA derives tools from it. The bundle REA writes (it holds recorded bodies) is built in a temporary folder, only the manifest is read, the folder is deleted."""
    if not os.path.isfile(har_path):
        return {"ok": False, "error": "no recording"}
    with contextlib.suppress(Exception):
        sanitize_har(har_path)
    name = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")[:40] or "site-env"
    tmp = os.path.join(tempfile.gettempdir(), "rea_env_" + str(int(time.time() * 1000)))
    try:
        r = run("environment-build", har_path, tmp, "--name", name, timeout=240)
        if not r["ok"]:
            return {"ok": False, "error": r["error"], "seconds": r["seconds"]}
        d = r["data"] or {}
        man = json.load(open(os.path.join(tmp, "envs", name, "manifest.json"), encoding="utf-8")).get("normalized_result", {})
        tools = []
        for t in man.get("tools", []):
            tools.append({"name": t.get("name"), "method": t.get("method"), "path": t.get("path_template"), "params": [p.get("name") for p in t.get("params", [])], "query": t.get("query_parameter_names", []),
                          "body_shape": t.get("body_shape"), "statuses": t.get("statuses"), "content_types": t.get("content_types"), "write": (t.get("method") or "").upper() in WRITE_METHODS})
        return {"ok": True, "origin": man.get("origin"), "tools": tools, "records": len(man.get("records", [])), "other_origin_groups": len(man.get("excluded", [])), "unknowns": [u.get("statement", "")[:160] for u in man.get("unknowns", [])][:4],
                "coverage": d.get("coverage"), "credential_like_members": len([w for w in d.get("warnings", []) if w.get("code") == "credential-named-members"]), "evidence_id": (d.get("manifest") or {}).get("evidence_id", ""),
                "seconds": r["seconds"]}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:120]}"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------------------------------------------------------------------------ knowledge
def knowledge_text(host: str, web: Optional[Dict[str, Any]] = None, api: Optional[Dict[str, Any]] = None) -> str:
    md = [f"# {host}: what it is made of (read with REA, with evidence)", ""]
    ev = (web or {}).get("evidence") or {}
    if web and web.get("page"):
        p = web["page"]
        md += ["## Page", "", f"- {p['scripts']} scripts from {', '.join(p['script_hosts']) or 'its own origin'} ({p['script_bytes']:,} bytes), {p['source_maps']} with source maps", f"- resources: {p['resources']}",
               f"- {p['dom_nodes']} DOM nodes, {p['accessibility_nodes']} accessibility nodes, {p['frames']} frames",
               f"- local-storage keys (names only): {', '.join(p['local_storage_keys']) or 'none'}; indexedDB: {', '.join(p['indexed_db']) or 'none'}", f"- evidence: {ev.get('page', '')}", ""]
        if p["same_site_paths"]:
            md += ["## Same-site URLs present in the page", ""] + [f"- {x}" for x in p["same_site_paths"][:40]] + [""]
    if web and web.get("bundle"):
        b = web["bundle"]
        md += ["## Routes found in the page's code", "", f"Static candidates ({b['sources']} source files; application routes: {b['coverage']}). Reachability is NOT established.", ""] + [f"- {r}" for r in b["routes"][:60]] + ["", f"evidence: {ev.get('bundle', '')}", ""]
    if web and web.get("webmcp"):
        md += ["## Tools the page declares itself (WebMCP)", "", f"status: {web['webmcp']['status']}; tools: {', '.join(web['webmcp']['tools']) or 'none'}", ""]
    if api and api.get("ok") and api.get("tools"):
        md += [f"## API used by the site (origin {api.get('origin')})", ""]
        for t in api["tools"]:
            md.append(f"- {t['method']} {t['path']}  (tool '{t['name']}'; parameters: {', '.join(t['params']) or 'none'}; query: {', '.join(t['query']) or 'none'}; statuses {t['statuses']}"
                      + ("; WRITE: recorded, not executed" if t["write"] else "") + ")")
        md += ["", f"evidence: {api.get('evidence_id', '')}", ""]
    return "\n".join(md)


def file_into_rag(rag: Any, key: str, host: str, web: Optional[Dict[str, Any]], api: Optional[Dict[str, Any]], run_id: str, write: bool = True) -> Dict[str, Any]:
    """Document + one procedure per read-only API tool (goal 'Read X from the API of host') + a command per route candidate. Deterministic ids: filing the same site twice changes nothing."""
    from core_organs.harvest import web_learn as WL
    import hashlib
    res = {"document_chunks": 0, "api_procedures": 0, "route_commands": 0}
    if not write or rag is None:
        return res
    text = knowledge_text(host, web, api)
    with WL.rag_lock():
        with contextlib.suppress(Exception):
            rep = rag.proc.ingest_document(key, text, f"rea:{run_id}", kind="web_doc", title=f"{host} (REA)", trust="web")
            res["document_chunks"] = int(getattr(rep, "inserted", 0) or 0) + int(getattr(rep, "updated", 0) or 0)
        for t in (api or {}).get("tools", []):
            goal = f"{'Call' if not t['write'] else 'Know the write call'} {t['method']} {t['path']} on {host} ({t['name']})"
            pid = hashlib.sha1(f"rea|{host}|{t['method']}|{t['path']}".encode()).hexdigest()[:20]
            steps = [{"text": f"Send {t['method']} {t['path']}" + (f" with {', '.join(t['params'])}" if t["params"] else "") + (f" and query {', '.join(t['query'])}" if t["query"] else ""), "target": t["name"] or t["path"],
                      "route_hint": "api", "expect": f"status {t['statuses']}, {', '.join(t['content_types'] or [])}", "write": t["write"]}]
            with contextlib.suppress(Exception):
                rag.proc.ingest_procedure(key, goal[:190], steps, f"rea:{run_id}", trust="web", procedure_id=pid)
                res["api_procedures"] += 1
        for r in ((web or {}).get("bundle") or {}).get("routes", [])[:80]:
            with contextlib.suppress(Exception):
                rag.lex.add_command(key, f"route {r}", archetype="web:route", source="rea_route", trust="web")
                res["route_commands"] += 1
    return res
