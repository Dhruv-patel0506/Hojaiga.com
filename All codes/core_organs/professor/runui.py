"""
professor.runui -- the way a run LOOKS: a readable console log while it works, and one self-contained HTML page when it is done.

The page shows what the Professor saw (the annotated scans: boxes by who found each control, the accessibility tree drawn level by level, every flyout it opened), every procedure of the guide with
its outcome and the reason, what it learnt (ML numbers), and the database rows it left behind. Plain files: no server, nothing is uploaded.
"""

from __future__ import annotations

import base64
import html
import io
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

_C = {"ok": "\033[32m", "blocked": "\033[33m", "failed": "\033[31m", "skipped": "\033[90m", "dim": "\033[90m", "bold": "\033[1m", "cyan": "\033[36m", "end": "\033[0m"}
_GLYPH = {"ok": "✔", "blocked": "⏸", "failed": "✖", "skipped": "·", "pending": "…"}


def _color_on() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("HOJAIGA_COLOR") == "1":
        return True
    return sys.stdout.isatty()


class ConsoleUI:
    def __init__(self, app: str, tier: int, echo: bool = True):
        self.app, self.tier, self.echo = app, tier, echo
        for stream in (sys.stdout, sys.stderr):                                  # a redirected Windows console is cp1252: the box-drawing characters must not crash a run
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
        self.color = _color_on()
        self.t0 = time.time()
        self.lines: List[str] = []

    def _p(self, s: str) -> None:
        self.lines.append(s)
        if self.echo:
            print(s, flush=True)

    def c(self, key: str, text: str) -> str:
        return f"{_C[key]}{text}{_C['end']}" if self.color else text

    def banner(self, title: str, detail: str = "") -> None:
        bar = "═" * 78
        self._p(self.c("cyan", bar))
        self._p(self.c("bold", f"  {title}") + (self.c("dim", f"   {detail}") if detail else ""))
        self._p(self.c("cyan", bar))

    def phase(self, name: str, detail: str = "") -> None:
        self._p(f"{self.c('dim', f'{time.time() - self.t0:6.1f}s')}  {self.c('bold', f'{name:<10}')} {detail}")

    def note(self, text: str) -> None:
        self._p(f"{'':8}  {self.c('dim', text)}")

    def task_start(self, i: int, n: int, goal: str, steps: int, grounded: float) -> None:
        self._p(f"{self.c('dim', f'{time.time() - self.t0:6.1f}s')}  {self.c('bold', f'[{i:>2}/{n}]')} {goal[:62]}  {self.c('dim', f'({steps} steps, {grounded:.0%} grounded)')}")

    def attempt(self, n: int, status: str, done: int, steps: int, why: str = "") -> None:
        key = "ok" if status == "ok" else ("blocked" if status == "blocked" else "failed")
        self._p(f"{'':8}  {self.c(key, _GLYPH[key] + ' ' + status.upper()):<24} attempt {n}: {done}/{steps} steps" + (self.c("dim", f"  - {why[:110]}") if why else ""))

    def remedy(self, text: str) -> None:
        self._p(f"{'':8}  {self.c('dim', '↳ remedy: ' + text)}")

    def summary(self, counts: Dict[str, int], ledger: Dict[str, int], seconds: float, path: str) -> None:
        bar = "─" * 78
        self._p(self.c("dim", bar))
        parts = [self.c(k, f"{_GLYPH[k]} {counts.get(k, 0)} {k}") for k in ("ok", "blocked", "failed")]
        self._p(f"  {self.c('bold', self.app)} (tier {self.tier}):  " + "   ".join(parts) + self.c("dim", f"   skipped with a reason: {ledger.get('skipped', 0)}   {seconds:.0f}s"))
        self._p(self.c("dim", f"  report: {path}"))
        self._p(self.c("dim", bar))


def _img_tag(path: str, max_w: int = 1100) -> str:
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        if im.width > max_w:
            im = im.resize((max_w, int(im.height * max_w / im.width)))
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
        return f'<img src="data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}">'
    except Exception:
        return ""


_BADGE = {"ok": ("#1b7f3a", "passed"), "blocked": ("#a86a00", "blocked on purpose"), "failed": ("#b3261e", "failed"), "skipped": ("#5f6368", "skipped")}


def write_html(report: Dict[str, Any], run_dir: str) -> str:
    app = report.get("app", "?")
    pics = sorted((f for f in os.listdir(run_dir) if f.lower().endswith(".png")), key=lambda f: (0 if f.startswith("scan_") else (1 if f.startswith("flyout_") else 2), f))        # the scans first, then every flyout, then every dialog / page a clicked option opened
    ev_dir = os.path.join(run_dir, "evidence")
    evid = sorted(f for f in os.listdir(ev_dir) if f.lower().endswith(".png")) if os.path.isdir(ev_dir) else []
    ph = report.get("phases", {})
    ds = ph.get("deep_scan", {}) or {}
    vs = ph.get("vision_scan", {}) or {}
    cat = ph.get("catalog_after_options") or ph.get("catalog_after_menus") or ph.get("catalog") or {}
    opt = ph.get("options", {}) or {}
    mn = ph.get("menus", {}) or {}
    ml = report.get("ml", {}) or {}
    o = ml.get("outcome", {}) or {}
    cnd = ml.get("candidates", {}) or {}
    rows = []
    for r in report.get("ledger", []):
        col, label = _BADGE.get(r["disposition"], ("#5f6368", r["disposition"]))
        rows.append(f"<tr><td><span class=b style='background:{col}'>{label}</span></td><td>{html.escape(r['goal'][:90])}</td><td class=n>{r['steps']}</td><td class=n>{int(round(float(r.get('grounded', 0)) * 100))}%</td>"
                    f"<td class=why>{html.escape(str(r.get('reason', ''))[:260])}</td></tr>")
    detail = []
    for t in report.get("tasks", []):
        steps = []
        for a in t["attempts"]:
            for x in a["results"]:
                if "verb" in x:
                    steps.append(f"<li><b>{html.escape(str(x['verb']))}</b> — {x['status']} <span class=m>via {html.escape(str(x.get('route', '')))} · {html.escape(str(x.get('effect', '')))} · vision {x.get('vision_ok')}</span><br><span class=m>{html.escape(str(x.get('summary', ''))[:200])}</span></li>")
            steps.append(f"<li class=att>attempt {a['n']}: <b>{a['status']}</b> {html.escape(a.get('why', '')[:160])} {('— remedy: ' + html.escape(a['remedy'][:160])) if a.get('remedy') else ''}</li>")
        detail.append(f"<details><summary>{_GLYPH.get(t['final'], '')} {html.escape(t['goal'][:90])} <span class=m>[{html.escape(t['cite'][:70])}]</span></summary><ol>{''.join(steps)}</ol></details>")
    clicked = []
    for sfc in opt.get("surfaces", []):
        col = {"dialog": "#1b5fb3", "page": "#6b3fa0", "inline": "#0b7a75", "none": "#5f6368", "unreachable": "#b3261e", "error": "#b3261e"}.get(sfc.get("kind"), "#5f6368")
        clicked.append(f"<tr><td><span class=b style='background:{col}'>{html.escape(str(sfc.get('kind')))}</span></td><td>{html.escape(sfc['path'])}</td><td class=n>{len(sfc.get('controls', []))}</td>"
                       f"<td class=why>{html.escape(', '.join(sfc.get('controls', [])[:10]))}</td><td class=why>left by {html.escape(str(sfc.get('left_by', '')))} · "
                       f"{'application verified back' if sfc.get('restored') else 'NOT proved back: ' + html.escape(str(sfc.get('still_differs', ''))[:100])}</td></tr>")
    refused = "".join(f"<tr><td>{html.escape(x['path'])}</td><td class=why>{html.escape(x['why'])}</td></tr>" for x in (opt.get("skipped", []) + mn.get("skipped", [])))
    umap = "".join(f"<tr><td style='padding-left:{8 + 16 * (int(r.get('depth', 1)) - 1)}px'>{html.escape(r['path'])}</td><td>{html.escape(r['kind'])}</td><td class=n>{r['count']}</td><td class=why>{html.escape(', '.join(r['items'][:12]))}</td></tr>"
                   for r in ph.get("ui_map", []))
    hidden = ""
    if umap or clicked:
        hidden = (f"<h2>Hidden options it found by clicking</h2><div class=m>Every menu, submenu, dialog and page behind a button: opened once, read, drawn, closed again - and the application compared with its "
                  f"starting state each time. {mn.get('submenus', 0)} submenus entered · {opt.get('opened', 0)} of {opt.get('tried', 0)} clicked options opened something "
                  f"({opt.get('dialogs', 0)} dialogs, {opt.get('pages', 0)} pages) · {opt.get('controls', 0)} new controls.</div>"
                  + (f"<h3>Options that were clicked</h3><table><tr><th>opened</th><th>option</th><th>controls</th><th>first controls found</th><th>afterwards</th></tr>{''.join(clicked)}</table>" if clicked else "")
                  + (f"<h3>Map: what is behind what</h3><table><tr><th>path</th><th>kind</th><th>items</th><th>found there</th></tr>{umap}</table>" if umap else "")
                  + (f"<h3>Deliberately not opened</h3><table><tr><th>option</th><th>why</th></tr>{refused}</table>" if refused else ""))
    imgs = "".join(f"<figure>{_img_tag(os.path.join(run_dir, p))}<figcaption>{html.escape(p)}</figcaption></figure>" for p in pics)
    ev = "".join(f"<figure>{_img_tag(os.path.join(ev_dir, p), 760)}<figcaption>{html.escape(p)}</figcaption></figure>" for p in evid[:18])
    counts = report.get("counts", {})
    doc = f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>{html.escape(app)} guide run</title>
<style>
:root{{--bg:#fafaf8;--fg:#1f1f1f;--mut:#666;--card:#fff;--line:#e3e1dc}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16161a;--fg:#ececec;--mut:#9a9aa3;--card:#202026;--line:#34343c}}}}
body{{margin:0;padding:24px 16px 60px;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,Segoe UI,sans-serif}}
main{{max-width:1180px;margin:auto}}h1{{margin:0 0 4px;font-size:26px}}h2{{margin:34px 0 10px;font-size:19px;border-bottom:1px solid var(--line);padding-bottom:6px}}h3{{margin:22px 0 8px;font-size:15px}}
.m{{color:var(--mut);font-size:13px}}.kpi{{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}}.kpi div{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 16px;min-width:110px}}
.kpi b{{display:block;font-size:24px}}table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}}
td,th{{padding:6px 9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;font-size:13.5px}}th{{background:var(--bg);font-weight:600}}td.n{{text-align:right;white-space:nowrap}}td.why{{color:var(--mut);font-size:12.5px}}
.b{{color:#fff;border-radius:99px;padding:2px 9px;font-size:12px;white-space:nowrap}}figure{{margin:14px 0}}img{{max-width:100%;border:1px solid var(--line);border-radius:6px}}figcaption{{color:var(--mut);font-size:12.5px}}
details{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px 12px;margin:6px 0}}summary{{cursor:pointer}}li{{margin:4px 0}}li.att{{list-style:none;margin-left:-18px;color:var(--mut)}}
</style></head><body><main>
<h1>{html.escape(app)} — guide run</h1><div class=m>tier {report.get('tier')} · {html.escape(str(report.get('started', '')))} · {report.get('seconds', 0)} s · toolkit <b>{html.escape(str((ds.get('profile') or {}).get('family', '?')))}</b> ({html.escape(str(ds.get('state', '?')))} accessibility tree)</div>
<div class=kpi><div><b style=color:#1b7f3a>{counts.get('ok', 0)}</b>passed</div><div><b style=color:#a86a00>{counts.get('blocked', 0)}</b>blocked on purpose</div><div><b style=color:#b3261e>{counts.get('failed', 0)}</b>failed</div>
<div><b>{report.get('ledger_counts', {}).get('skipped', 0)}</b>skipped (reason given)</div><div><b>{ds.get('nodes', '?')}</b>tree nodes · depth {ds.get('depth', '?')}</div><div><b>{vs.get('elements', '?')}</b>controls in the vision scan</div>
<div><b>{cat.get('verbs', '?')}</b>verbs in the catalog</div></div>
<h2>What it saw</h2><div class=m>Boxes: green = accessibility tree, blue = printed text, orange = shape, purple = vision model, teal = remembered icon, red = nobody could name it. The depth picture draws the accessibility tree level by level.</div>{imgs}
{hidden}
<h2>The guide, procedure by procedure</h2><table><tr><th>outcome</th><th>procedure</th><th>steps</th><th>grounded</th><th>why</th></tr>{''.join(rows)}</table>
<h2>Step by step</h2>{''.join(detail)}
<h2>What it learnt</h2><div class=kpi><div><b>{o.get('seen', '?')}</b>actions seen by the outcome model</div><div><b>{o.get('ok_accuracy', '?')}</b>accuracy predicting success (baseline {o.get('ok_baseline', '?')})</div>
<div><b>{o.get('effect_accuracy', '?')}</b>accuracy predicting the effect (baseline {o.get('effect_baseline', '?')})</div><div><b>{cnd.get('seen', '?')}</b>vision candidates seen · AUC {cnd.get('prequential_auc', '?')}</div></div>
<div class=m>History database rows for this app: {html.escape(json.dumps(report.get('history', {}), default=str)[:300])}</div>
{('<h2>When something failed</h2>' + ev) if ev else ''}
</main></body></html>"""
    path = os.path.join(run_dir, "report.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return path
