"""
rea_desktop -- REA on an INSTALLED JavaScript / Electron application (an ASAR or an extracted folder): static, the application is never run.

    python -m core_organs.rea_desktop check                                            is REA installed and answering?
    python -m core_organs.rea_desktop app "<path to app.asar or folder>" [--key NAME]   analyse it and file what it found in the RAG
    python -m core_organs.rea_desktop app <path> --from-evidence <saved REA result>      reuse an earlier saved result instead of analysing again

What comes back: size and parts (modules, import links, files in the archive), the Electron boundary (browser windows, preload entry points, IPC channels), native add-ons, worker threads, network
endpoint CANDIDATES (inferred, low confidence), integrity contradictions, and what REA says it could not establish. A big minified bundle can exceed REA's per-source deadline; the partial Evidence REA
keeps is then used and the result says 'partial'.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Sequence

from core_organs import rea_bridge as RB


def digest_js_app(nr: Dict[str, Any], partial: bool = False) -> Dict[str, Any]:
    """The facts worth remembering from REA's application graph."""
    g = nr.get("graph") or {}
    kinds: Dict[str, int] = {}
    for n in g.get("nodes", []):
        kinds[n.get("kind", "?")] = kinds.get(n.get("kind", "?"), 0) + 1

    def labels(kind: str, cap: int = 12) -> List[str]:
        out: List[str] = []
        for n in g.get("nodes", []):
            if n.get("kind") == kind:
                for o in n.get("observations", []):
                    if o.get("label") and str(o["label"])[:60] not in out:
                        out.append(str(o["label"])[:60])
        return out[:cap]
    st = nr.get("statistics") or {}
    sm = nr.get("summary") or {}
    ipc = sm.get("ipc") or {}
    sk: Dict[str, int] = {}
    for n in (nr.get("semantic_graph") or {}).get("nodes", []):
        sk[n.get("kind", "?")] = sk.get(n.get("kind", "?"), 0) + 1
    return {"partial": partial, "format": nr.get("format"), "files": st.get("relevant_files"), "parsed_js_files": st.get("parsed_javascript_files"), "skipped_js_files": st.get("skipped_javascript_files"),
            "modules": st.get("modules") or kinds.get("javascript-module"), "text_bytes_read": st.get("text_bytes_read"), "node_kinds": dict(sorted(kinds.items(), key=lambda kv: -kv[1])[:10]),
            "imports": sum(1 for e in g.get("edges", []) if e.get("relation") == "imports"), "native_addons": labels("native-addon"), "asar_entries": labels("asar-entry", 14), "workers": kinds.get("worker", 0),
            "endpoints_inferred": labels("endpoint", 10), "browser_windows": sm.get("browser_windows"), "preload_entrypoints": sm.get("preload_entrypoints"), "ipc_channels": ipc.get("literal_channels"),
            "ipc_operations": ipc.get("operations"), "listeners": sk.get("listener", 0), "functions": sk.get("function", 0), "call_sites": sk.get("call-site", 0),
            "integrity_contradictions": [c.get("logical_path") for c in nr.get("integrity_contradictions", [])][:5], "limitations": [x[:140] for x in (nr.get("limitations") or [])][:4]}


def desktop_app(path: str, analysis_timeout_ms: int = 900000, from_evidence: str = "") -> Dict[str, Any]:
    if from_evidence:
        raw = open(from_evidence, encoding="utf-8").read()
        res = {"ok": True, "data": json.loads(raw[raw.find("{"):raw.rfind("}") + 1]), "error": "", "seconds": 0.0}
    else:
        os.makedirs(RB.OUT_DIR, exist_ok=True)
        res = RB.run("analyze-javascript-application", path, "--integrity-policy", "record-and-continue", "--analysis-timeout-ms", analysis_timeout_ms, timeout=analysis_timeout_ms / 1000 + 120)
    d = res.get("data") or {}
    nr, partial = d.get("normalized_result") or {}, False
    po: Dict[str, Any] = {}
    if not nr and d.get("code") == "provider_timeout":
        po = (d.get("details") or {}).get("partial_observation") or (d.get("recovery") or {}).get("partial_observation") or {}
        nr, partial = po.get("normalized_result") or {}, True
    if not nr:
        return {"ok": False, "error": res.get("error") or d.get("message") or "no result", "seconds": res.get("seconds", 0)}
    out = digest_js_app(nr, partial)
    out.update(ok=True, path=path, evidence_id=d.get("evidence_id") or po.get("evidence_id", ""), seconds=res.get("seconds", 0))
    return out


def text_of(name: str, dg: Dict[str, Any]) -> str:
    md = [f"# {name}: what the installed application is made of (read with REA, static, never run)", "",
          f"- format {dg['format']}, {dg['files']} relevant files, {dg['modules']} JavaScript modules ({dg['imports']} import links), {dg['parsed_js_files']} parsed, {dg['skipped_js_files']} skipped"
          + (" - PARTIAL: REA reached its time limit, this is what had been read" if dg["partial"] else ""),
          f"- Electron boundary: {dg['browser_windows']} browser windows, {dg['preload_entrypoints']} preload entry points, {dg['ipc_channels']} literal IPC channels ({dg['ipc_operations']} IPC operations)",
          f"- {dg['workers']} worker threads, {dg['listeners']} event listeners, {dg['functions']} functions, {dg['call_sites']} call sites in the semantic graph",
          f"- native add-ons: {', '.join(dg['native_addons']) or 'none'}", f"- files packed in the archive: {', '.join(dg['asar_entries'][:10]) or '-'}"]
    if dg["endpoints_inferred"]:
        md.append(f"- network endpoint CANDIDATES (inferred, low confidence, may be event names rather than URLs): {', '.join(dg['endpoints_inferred'])}")
    if dg["integrity_contradictions"]:
        md.append(f"- integrity: the archive's declared hashes disagree with the bytes for {', '.join(dg['integrity_contradictions'])} (observed bytes treated as untrusted)")
    md += ["", "Limits stated by REA:"] + [f"- {x}" for x in dg["limitations"]] + ["", f"evidence: {dg.get('evidence_id', '')}"]
    return "\n".join(md)


def file_into_rag(rag: Any, key: str, name: str, dg: Dict[str, Any], run_id: str, write: bool = True) -> Dict[str, Any]:
    from core_organs.harvest import web_learn as WL
    res = {"document_chunks": 0}
    if write and rag is not None and dg.get("ok"):
        with WL.rag_lock():
            with contextlib.suppress(Exception):
                rep = rag.proc.ingest_document(key, text_of(name, dg), f"rea:{run_id}", kind="web_doc", title=f"{name} (REA, static)", trust="web")
                res["document_chunks"] = int(getattr(rep, "inserted", 0) or 0) + int(getattr(rep, "updated", 0) or 0)
    return res


def find_installed(max_mb: float = 40.0) -> List[Dict[str, Any]]:
    """Electron / JavaScript apps installed for this user: a folder with resources/app.asar or resources/app. Larger than `max_mb` is left out (a 140 MB bundle takes REA far longer than its deadline)."""
    roots = [os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"), os.environ.get("LOCALAPPDATA", ""), r"C:\Program Files", r"C:\Program Files (x86)"]
    out: List[Dict[str, Any]] = []
    seen = set()
    for r in roots:
        if not r or not os.path.isdir(r):
            continue
        for d in sorted(os.listdir(r)):
            base = os.path.join(r, d)
            for kind, rel in (("asar", os.path.join("resources", "app.asar")), ("dir", os.path.join("resources", "app"))):
                p = os.path.join(base, rel)
                if not os.path.exists(p) or p in seen:
                    continue
                seen.add(p)
                if kind == "asar":
                    mb = os.path.getsize(p) / 1e6
                else:
                    mb = sum(os.path.getsize(os.path.join(a, f)) for a, _, fs in os.walk(p) for f in fs) / 1e6
                out.append({"name": d, "path": p, "kind": kind, "mb": round(mb, 1), "too_big": mb > max_mb})
    return sorted(out, key=lambda x: x["mb"])


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="REA on an installed JavaScript / Electron application, filed in the RAG.")
    ap.add_argument("cmd", choices=["app", "check", "installed"])
    ap.add_argument("path", nargs="?", default="")
    ap.add_argument("--key", default="")
    ap.add_argument("--timeout-ms", type=int, default=900000)
    ap.add_argument("--from-evidence", default="")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--max-mb", type=float, default=40.0, help="installed: leave out archives larger than this")
    a = ap.parse_args(argv)
    if a.cmd == "check":
        r = RB.run("capabilities", timeout=60)
        print(json.dumps({"installed": RB.available(), "node": RB.NODE, "ok": r["ok"], "seconds": r["seconds"], "error": r["error"]}, indent=1))
        return 0
    if a.cmd == "installed":
        apps = find_installed(a.max_mb)
        print(json.dumps([{k: v for k, v in x.items() if k != "path"} | {"path": x["path"]} for x in apps], indent=1))
        if a.no_write and not a.path:
            return 0
        from core_organs import rag as R
        rag = R.get_rag()
        for x in [x for x in apps if not x["too_big"]]:
            dg = desktop_app(x["path"], a.timeout_ms)
            key = re.sub(r"[^a-z0-9]+", "_", x["name"].lower()).strip("_")
            print(f"{x['name']}: " + (f"{dg.get('modules')} modules{' (partial)' if dg.get('partial') else ''}, native add-ons {dg.get('native_addons')}" if dg.get("ok") else f"failed: {dg.get('error', '')[:100]}"), flush=True)
            if dg.get("ok") and not a.no_write:
                file_into_rag(rag, key, x["name"], dg, "installed_" + time.strftime("%Y%m%d_%H%M%S"))
        return 0
    p = a.path.replace("/", os.sep)
    name = os.path.basename(os.path.dirname(os.path.dirname(p))) if p.lower().endswith("app.asar") else os.path.basename(p.rstrip("\\/"))
    key = a.key or re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    dg = desktop_app(a.path, a.timeout_ms, a.from_evidence)
    print(json.dumps({k: v for k, v in dg.items() if k != "asar_entries"}, indent=1, default=str))
    if dg.get("ok") and not a.no_write:
        from core_organs import rag as R
        print(json.dumps(file_into_rag(R.get_rag(), key, name, dg, "app_" + time.strftime("%Y%m%d_%H%M%S"))))
    return 0 if dg.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
