"""
professor.checkpoints -- THE MANUAL RUN: a checklist of applications, scanned one after the other, with pictures saved into ONE folder you can attach.

    python -m core_organs.professor.checkpoints                    # tier 1, picks up at the first application that is not done yet
    python -m core_organs.professor.checkpoints --apps notepad     # only these applications
    python -m core_organs.professor.checkpoints --tier 2           # another tier (nothing outside the tier you name is touched)
    python -m core_organs.professor.checkpoints --list             # show the checklist and stop
    python -m core_organs.professor.checkpoints --again            # run applications again even if their checkpoint says done
    options: --no-guide (scan only) --no-vision --tasks N --attempts N --out DIR --no-zip

For every application the normal job is done (launch an owned instance, deep tree + vision scan, open every menu / submenu / dialog / page behind a button, run the user guide's procedures,
record everything in the database) and, on top of it, the pictures are kept:
    <out>/<app>/scan_*.png          the annotated scans (who found each control) and the accessibility tree level by level
    <out>/<app>/flyout_*.png        every menu and submenu that was opened
    <out>/<app>/option_*.png        every dialog / page a clicked option opened
    <out>/<app>/checkpoints/cp_*.png   plain pictures of the application at named points (launched, after the scan, after every guide procedure, end)
    <out>/<app>/evidence/*.png      what the screen looked like when something failed
    <out>/<app>/report.html|json    the full report
    <out>/INDEX.html  CHECKLIST.md  SUMMARY.md  run.log  and  <out>.zip    (one folder / one zip to attach)
The checklist is saved after EVERY application (data/professor/scan_checkpoints.json), so a stopped or crashed run resumes where it left off.
"""

from __future__ import annotations

import html
import json
import os
import shutil
import sys
import time
import traceback
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import config as CFG

STATE_PATH = os.path.join(CFG.DATA_DIR, "scan_checkpoints.json")
CHECKLIST_COPY = os.path.join(CFG.DATA_DIR, "SCAN_CHECKLIST.md")
DEFAULT_OUT = os.path.join(os.path.dirname(os.path.dirname(CFG.DATA_DIR)), "scan_output")                      # <project>/scan_output/<timestamp>
STAGES: List[Tuple[str, str]] = [("launched", "launched hidden"), ("tree_scan", "deep tree"), ("vision_scan", "vision scan"), ("catalog", "controls catalogued"), ("menus", "menus & submenus"),
                                 ("options", "options clicked"), ("guide", "guide procedures"), ("pictures", "pictures saved"), ("closed_clean", "closed & state restored")]
GLYPH = {"ok": "✔", "partial": "◐", "fail": "✖", "skipped": "–", "pending": "·"}


# ----------------------------------------------------------------------------------------------------------- stages from a report
def stage_states(rep: Dict[str, Any], run_dir: str = "", expect_vision: bool = True) -> Dict[str, Dict[str, str]]:
    """What the finished run of one application achieved, stage by stage: {stage: {state: ok|partial|fail|skipped, note}}."""
    ph = rep.get("phases", {}) or {}
    out: Dict[str, Dict[str, str]] = {}

    def put(k: str, state: str, note: str = "") -> None:
        out[k] = {"state": state, "note": note}

    launched = bool((ph.get("launch") or {}).get("launched")) and rep.get("result") != "launch_failed"
    put("launched", "ok" if launched else "fail", "" if launched else str((ph.get("launch") or {}).get("notes", "could not start an owned instance"))[:100])
    ds = ph.get("deep_scan") or {}
    put("tree_scan", "ok" if int(ds.get("nodes", 0) or 0) > 3 else "fail", f"{ds.get('nodes', 0)} nodes · depth {ds.get('depth', '?')} · {ds.get('state', '')}")
    vs = ph.get("vision_scan") or {}
    if vs.get("elements"):
        put("vision_scan", "ok" if vs.get("vision_model") else ("partial" if expect_vision else "skipped"), f"{vs.get('elements')} controls" + ("" if vs.get("vision_model") else " (vision model not used: tree + text only)"))
    else:
        put("vision_scan", "fail", "no scan")
    cat = ph.get("catalog_after_options") or ph.get("catalog_after_menus") or ph.get("catalog") or {}
    put("catalog", "ok" if int(cat.get("verbs", 0) or 0) >= 10 else ("partial" if cat.get("verbs") else "fail"), f"{cat.get('verbs', 0)} verbs")
    mn = ph.get("menus")
    if mn is None:
        put("menus", "skipped", "no menus phase")
    elif mn.get("error"):
        put("menus", "fail", mn["error"][:100])
    else:
        full = int(mn.get("opened", 0)) >= max(1, int(mn.get("openers", 0)))
        put("menus", "ok" if full else "partial", f"{mn.get('opened', 0)}/{mn.get('openers', 0)} openers · {mn.get('items', 0)} items · {mn.get('submenus', 0)} submenus")
    op = ph.get("options")
    if op is None:
        put("options", "skipped", "browser (read through DevTools) or switched off")
    elif op.get("error"):
        put("options", "fail", op["error"][:100])
    else:
        bad = op.get("tainted") or op.get("stopped")
        put("options", "partial" if bad else "ok", f"{op.get('opened', 0)}/{op.get('tried', 0)} opened more · {op.get('dialogs', 0)} dialogs · {op.get('pages', 0)} pages" + (f" · {str(op.get('stopped'))[:80]}" if bad else ""))
    if "guide" not in ph:
        put("guide", "skipped", "scan only")
    else:
        lc = rep.get("ledger_counts", {}) or {}
        failed = int(lc.get("failed", 0))
        put("guide", "ok" if failed == 0 and (lc.get("ok", 0) or lc.get("blocked", 0) or lc.get("skipped", 0)) else ("partial" if lc.get("ok", 0) else "fail"),
            ", ".join(f"{v} {k}" for k, v in sorted(lc.items())) or "nothing ran")
    n_pics = 0
    if run_dir and os.path.isdir(run_dir):
        for root, _d, files in os.walk(run_dir):
            n_pics += sum(1 for f in files if f.lower().endswith(".png"))
    put("pictures", "ok" if n_pics >= 4 else ("partial" if n_pics else "fail"), f"{n_pics} pictures")
    cl, sa = ph.get("close") or {}, ph.get("state_after") or {}
    put("closed_clean", "fail" if (cl.get("error") or sa.get("error")) else "ok", str(cl.get("error") or sa.get("error") or "")[:100])
    return out


def app_status(stages: Dict[str, Dict[str, str]], rep: Dict[str, Any], guide_expected: bool = True) -> str:
    """done | scanned (everything fine, but the guide was not run: a later full run still has work to do) | partial | failed"""
    if stages.get("launched", {}).get("state") == "fail" or rep.get("error"):
        return "failed"
    if all(s["state"] in ("ok", "skipped") for s in stages.values()):
        return "done" if guide_expected else "scanned"
    return "partial"


# ----------------------------------------------------------------------------------------------------------- checklist state
def load_state(path: Optional[str] = None) -> Dict[str, Any]:
    try:
        with open(path or STATE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"apps": {}}


def save_state(st: Dict[str, Any], path: Optional[str] = None) -> None:
    path = path or STATE_PATH
    st["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(st, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def checklist_rows(specs: Sequence[Any], st: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for sp in specs:
        a = (st.get("apps") or {}).get(sp.key, {})
        rows.append({"key": sp.key, "name": sp.name, "tier": sp.tier, "status": a.get("status", "pending"), "stages": a.get("stages", {}), "counts": a.get("counts", {}), "last_run": a.get("last_run", ""),
                     "runs": a.get("runs", 0), "report": a.get("report", ""), "note": a.get("note", "")})
    return rows


def checklist_markdown(rows: Sequence[Dict[str, Any]], title: str = "Application scan checklist") -> str:
    head = "| app | tier | status | " + " | ".join(lbl for _k, lbl in STAGES) + " | last run |"
    sep = "|" + "---|" * (4 + len(STAGES))
    lines = [f"# {title}", "", f"_updated {time.strftime('%Y-%m-%d %H:%M:%S')}_", "", head, sep]
    for r in rows:
        cells = []
        for k, _l in STAGES:
            s = (r["stages"] or {}).get(k)
            cells.append(GLYPH["pending" if not s else s["state"]])
        lines.append(f"| {r['key']} | {r['tier']} | **{r['status']}** | " + " | ".join(cells) + f" | {r['last_run'] or '-'} |")
    lines += ["", "✔ done · ◐ partly (see the report) · ✖ failed · – not applicable · · not run yet.   status 'scanned' = scan-only run, the guide still has to be run", ""]
    notes = [r for r in rows if r["status"] in ("partial", "failed")]
    if notes:
        lines.append("## What is still open")
        for r in notes:
            bad = [f"{lbl}: {r['stages'][k]['note']}" for k, lbl in STAGES if r["stages"].get(k, {}).get("state") in ("fail", "partial") and r["stages"][k].get("note")]
            lines.append(f"- **{r['key']}** ({r['status']}): " + ("; ".join(bad) if bad else "see report.html") + (f" — report: {r['report']}" if r["report"] else ""))
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------------------------------------- the bundle (INDEX.html)
def _pngs(app_dir: str) -> List[str]:
    out: List[str] = []
    for root, _d, files in os.walk(app_dir):
        for f in sorted(files):
            if f.lower().endswith(".png"):
                out.append(os.path.relpath(os.path.join(root, f), os.path.dirname(app_dir)).replace(os.sep, "/"))

    def order(p: str) -> Tuple[int, str]:
        b = os.path.basename(p)
        return (0 if b.startswith("scan_") else 1 if b.startswith("flyout_") else 2 if b.startswith("option_") else 3 if "/checkpoints/" in p else 4, p)
    return sorted(out, key=order)


def write_index(out_dir: str, rows: Sequence[Dict[str, Any]], ran: Sequence[str], seconds: float) -> str:
    badge = {"done": "#1b7f3a", "partial": "#a86a00", "failed": "#b3261e", "pending": "#5f6368"}
    cards = []
    for r in rows:
        if r["key"] not in ran:
            continue
        app_dir = os.path.join(out_dir, r["key"])
        pics = _pngs(app_dir) if os.path.isdir(app_dir) else []
        thumbs = "".join(f"<figure><a href='{html.escape(p)}'><img loading=lazy src='{html.escape(p)}'></a><figcaption>{html.escape(os.path.basename(p))}</figcaption></figure>" for p in pics)
        stg = "".join(f"<li><b>{GLYPH.get((r['stages'].get(k) or {}).get('state', 'pending'), '·')}</b> {html.escape(lbl)} <span class=m>{html.escape((r['stages'].get(k) or {}).get('note', ''))}</span></li>" for k, lbl in STAGES)
        cards.append(f"<section><h2>{html.escape(r['key'])} <span class=b style='background:{badge.get(r['status'], '#5f6368')}'>{r['status']}</span> <span class=m>tier {r['tier']} · "
                     f"<a href='{html.escape(r['key'])}/report.html'>full report</a> · <a href='{html.escape(r['key'])}/report.json'>json</a> · {len(pics)} pictures</span></h2><ul class=st>{stg}</ul><div class=grid>{thumbs}</div></section>")
    md = checklist_markdown(rows)
    doc = f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Scan checkpoints</title><style>
:root{{--bg:#fafaf8;--fg:#1f1f1f;--mut:#666;--card:#fff;--line:#e3e1dc}}@media (prefers-color-scheme:dark){{:root{{--bg:#16161a;--fg:#ececec;--mut:#9a9aa3;--card:#202026;--line:#34343c}}}}
body{{margin:0;padding:24px 16px 60px;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,Segoe UI,sans-serif}}main{{max-width:1240px;margin:auto}}h1{{font-size:26px;margin:0 0 6px}}
h2{{font-size:19px;margin:34px 0 8px;border-bottom:1px solid var(--line);padding-bottom:6px}}.m{{color:var(--mut);font-size:13px;font-weight:400}}.b{{color:#fff;border-radius:99px;padding:2px 10px;font-size:12px}}
pre{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;overflow:auto;font-size:12.5px}}ul.st{{list-style:none;padding:0;columns:2;font-size:13.5px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}}figure{{margin:0}}img{{width:100%;border:1px solid var(--line);border-radius:6px;background:#222}}figcaption{{font-size:11.5px;color:var(--mut);word-break:break-all}}
a{{color:#2f6fdd}}</style></head><body><main><h1>Scan checkpoints</h1><div class=m>{time.strftime('%Y-%m-%d %H:%M:%S')} · {round(seconds / 60, 1)} min · applications in this run: {html.escape(', '.join(ran))}</div>
<h2>Checklist</h2><pre>{html.escape(md)}</pre>{''.join(cards)}</main></body></html>"""
    p = os.path.join(out_dir, "INDEX.html")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return p


# ----------------------------------------------------------------------------------------------------------- the run
class _Tee:
    def __init__(self, stream: Any, fh: Any):
        self.stream, self.fh = stream, fh

    def write(self, s: str) -> int:
        try:
            self.stream.write(s)
        except Exception:
            pass
        try:
            self.fh.write(s)
            self.fh.flush()
        except Exception:
            pass
        return len(s)

    def flush(self) -> None:
        for x in (self.stream, self.fh):
            try:
                x.flush()
            except Exception:
                pass

    def __getattr__(self, name: str) -> Any:
        return getattr(self.stream, name)


def _vision_ready(say: Any) -> bool:
    try:
        from . import vision_server as VS
        r = VS.ensure(wait_s=240.0)
        say(f"vision model: {'ready' if r.get('ok') else 'NOT available (' + str(r.get('error', ''))[:80] + ')'}{' (started it)' if r.get('started') else ''}")
        return bool(r.get("ok"))
    except Exception as exc:
        say(f"vision model: not available ({type(exc).__name__})")
        return False


def ensure_guide(sp: Any, say: Any = print, min_docs: int = 3) -> int:
    """An application with no (or almost no) guide in the corpus gets its guide looked for BEFORE the scan: install folder, the vendor's own pages, winget's documentation links, then web search -
    the finder's own policy (official sources first, robots.txt kept, no aggregators, no challenge bypass). Returns the number of guide documents the application has afterwards."""
    try:
        from .knowledge import guide_finder as GF, manual_rag as MR, guide_corpus as GCP
        from . import launcher as LN
        key = sp.guide_key or sp.key
        ix = MR.ManualIndex()
        try:
            have = GF.indexed_docs(ix, key)
            if have >= min_docs:
                return have
            say(f"guide: '{sp.name}' has {have} document(s) - looking for its user guide (official sources first)")
            exe, company, seeds = "", "", []
            try:
                exe = LN.resolve(sp.name).exe or ""
            except Exception:
                pass
            for a in GCP.load_catalog():
                if a.get("key") == key:
                    company, seeds = a.get("company", ""), a.get("seeds", [])
                    break
            ident = GF.AppIdentity(app_key=key, product=sp.name, company=company, exe=exe)
            rep_ = GF.discover(ident, ix, web=True, budget_s=240.0, force=bool(have), seeds=seeds, want_docs=min_docs * 4, sources_wanted=4)
            n = GF.indexed_docs(ix, key)
            say(f"guide: {n} document(s) now ({rep_.get('coverage', '')[:90]})")
            return n
        finally:
            ix.close()
    except Exception as exc:
        say(f"guide lookup failed ({type(exc).__name__}): the scan goes on without one")
        return 0


def run(apps: Sequence[str] = (), tier: int = 1, again: bool = False, guide: bool = True, vision: bool = True, tasks: int = 0, attempts: int = 3, out: str = "", zip_it: bool = True,
        only_list: bool = False, fetch_guides: bool = True) -> Dict[str, Any]:
    from . import apprun as AR
    specs_all = [AR.SPECS[k] for k in AR.SPECS]
    want = [AR.spec_for(k) for k in apps] if apps else [sp for sp in specs_all if sp.tier == tier]
    specs_all += [sp for sp in want if sp.key not in AR.SPECS]                      # an application named on the command line joins the checklist
    st = load_state()
    rows_all = checklist_rows(specs_all, st)
    if only_list:
        print(checklist_markdown(rows_all))
        return {"listed": True}
    todo = [sp for sp in want if again or (st.get("apps", {}).get(sp.key, {}).get("status") != "done")]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.abspath(out or os.path.join(DEFAULT_OUT, stamp))
    os.makedirs(out_dir, exist_ok=True)
    log_fh = open(os.path.join(out_dir, "run.log"), "w", encoding="utf-8")
    old_out = sys.stdout
    sys.stdout = _Tee(sys.stdout, log_fh)
    t0 = time.time()
    ran: List[str] = []
    try:
        print(f"scan checkpoints · {time.strftime('%Y-%m-%d %H:%M:%S')} · folder {out_dir}")
        print(f"applications: {[sp.key for sp in want]} · to do now: {[sp.key for sp in todo]}" + (" · (the rest are already done: --again to repeat them)" if len(todo) < len(want) else ""))
        if not todo:
            print("nothing to do.")
        use_vision = vision and (_vision_ready(print) if todo else False)
        for sp in todo:
            app_dir = os.path.join(out_dir, sp.key)
            if tasks:
                sp.max_tasks = tasks
            rep: Dict[str, Any] = {}
            if guide and fetch_guides:
                ensure_guide(sp, print)
            try:
                rep = AR.AppRun(sp, max_attempts=attempts, vision=use_vision, phases=("guide",) if guide else (), out_dir=app_dir).run()
            except Exception as exc:
                rep = {"error": f"{type(exc).__name__}: {str(exc)[:200]}", "trace": traceback.format_exc()[-800:], "phases": {}}
                print("ERROR in", sp.key, rep["error"])
                try:                                                                # the folder of a crashed application still holds what is known about it
                    os.makedirs(app_dir, exist_ok=True)
                    with open(os.path.join(app_dir, "report.json"), "w", encoding="utf-8") as fh:
                        json.dump(rep, fh, indent=1, ensure_ascii=False)
                    with open(os.path.join(app_dir, "report.html"), "w", encoding="utf-8") as fh:
                        fh.write(f"<!doctype html><meta charset=utf-8><title>{html.escape(sp.key)}</title><h1>{html.escape(sp.key)}: the run stopped</h1><pre>{html.escape(rep['error'] + chr(10) + rep['trace'])}</pre>")
                except Exception:
                    pass
            if not guide:
                (rep.get("phases") or {}).pop("guide", None)
            stages = stage_states(rep, app_dir, expect_vision=vision)
            status = app_status(stages, rep, guide_expected=guide)
            prev = st.setdefault("apps", {}).get(sp.key, {})
            st["apps"][sp.key] = {"status": status, "tier": sp.tier, "stages": stages, "counts": rep.get("counts", {}), "ledger": rep.get("ledger_counts", {}), "last_run": stamp,
                                  "runs": int(prev.get("runs", 0)) + 1, "report": os.path.join(app_dir, "report.html"), "bundle": out_dir, "note": rep.get("error", "")}
            save_state(st)                                                          # a stopped run resumes after the last application that finished
            ran.append(sp.key)
            rows = checklist_rows(specs_all, st)
            with open(os.path.join(out_dir, "CHECKLIST.md"), "w", encoding="utf-8") as fh:
                fh.write(checklist_markdown(rows))
            write_index(out_dir, rows, ran, time.time() - t0)
            print(f"checkpoint saved: {sp.key} -> {status}")
        rows = checklist_rows(specs_all, st)
        md = checklist_markdown(rows)
        with open(os.path.join(out_dir, "CHECKLIST.md"), "w", encoding="utf-8") as fh:
            fh.write(md)
        try:
            with open(CHECKLIST_COPY, "w", encoding="utf-8") as fh:
                fh.write(md)
        except Exception:
            pass
        index = write_index(out_dir, rows, ran, time.time() - t0)
        zpath = ""
        print("\n" + md)
        print(f"folder : {out_dir}\nindex  : {index}")
        sys.stdout = old_out
        log_fh.close()
        if zip_it and ran:
            zpath = shutil.make_archive(out_dir, "zip", out_dir)
            print(f"zip    : {zpath}  ({os.path.getsize(zpath) // 1024} KB) - attach this file or the folder")
        return {"folder": out_dir, "index": index, "zip": zpath, "ran": ran, "seconds": round(time.time() - t0, 1)}
    finally:
        if sys.stdout is not old_out:
            sys.stdout = old_out
        try:
            log_fh.close()
        except Exception:
            pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    from . import apprun as AR
    ap = argparse.ArgumentParser(description="Scan applications one by one, keep pictures of every checkpoint in one folder, keep a resumable checklist")
    ap.add_argument("--apps", default="", help="comma list of applications - a key of the plan or ANY application name (default: every application of --tier)")
    ap.add_argument("--tier", type=int, default=1)
    ap.add_argument("--again", action="store_true", help="run applications whose checkpoint already says done")
    ap.add_argument("--list", action="store_true", help="show the checklist and stop")
    ap.add_argument("--no-guide", action="store_true", help="scan only: do not run the guide's procedures")
    ap.add_argument("--no-vision", action="store_true")
    ap.add_argument("--tasks", type=int, default=0, help="at most N guide procedures per application")
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--out", default="", help="folder for the pictures and reports (default: scan_output/<timestamp> next to data/)")
    ap.add_argument("--no-zip", action="store_true")
    ap.add_argument("--no-guide-fetch", action="store_true", help="do not look for a guide when the application has none in the corpus")
    a = ap.parse_args(argv)
    keys = [k.strip() for k in a.apps.split(",") if k.strip()]                  # any application: a listed key, or any name the machine can resolve (e.g. --apps "visual studio code,calculator")
    run(keys, a.tier, a.again, not a.no_guide, not a.no_vision, a.tasks, a.attempts, a.out, not a.no_zip, a.list, not a.no_guide_fetch)
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    raise SystemExit(main())
