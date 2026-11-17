"""
try_app_batch -- run the deep on-screen exploration + reverse engineering over a LIST of sites, one after another, and write one comparison table.

    D:\\new_automation\\hojaiga_env\\Scripts\\python.exe -X utf8 -m core_organs.try_app_batch                       the default list
    ... -m core_organs.try_app_batch linkedin.com github.com --clicks 60                                          your own list

Each site runs in its OWN process (one crash or one blocked site never stops the rest), with its own proof folder (report.json, UNDERSTANDING.md, page pictures) and log. At the end
reports/try_app/batch_<stamp>/SUMMARY.md has one row per site: did it load, what is in the way (login wall, bot check), controls found, how deep the clicking went, the stack, the traffic,
the shortcuts it taught itself, and what kind of app the pool thinks it is. Read-only and logged-out on every site: nothing is typed, nothing is submitted, no one is signed in.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Sequence

ROOT = os.environ.get("HOJAIGA_REPORTS", os.path.join("D:" + os.sep, "new_automation", "reports"))
DEFAULT = ["github.com", "youtube.com", "twitch.tv", "linkedin.com", "mail.google.com", "joinhandshake.com", "naukri.com", "reddit.com", "stackoverflow.com", "notion.so"]


def one(target: str, folder: str, extra: Sequence[str], timeout_s: float) -> Dict[str, Any]:
    log = os.path.join(folder, re.sub(r"[^a-z0-9.]+", "_", target.lower()) + ".log")
    cmd = [sys.executable, "-X", "utf8", "-m", "core_organs.try_app", "--show", target, *extra]
    env = dict(os.environ, PYTHONPATH=r"D:\new_automation;D:\new_automation\All codes", PYTHONUNBUFFERED="1")
    t0 = time.time()
    status = "ok"
    try:
        with open(log, "w", encoding="utf-8") as f:
            p = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=env, cwd=r"D:\new_automation\All codes", timeout=timeout_s)
            if p.returncode != 0:
                status = f"exit {p.returncode}"
    except subprocess.TimeoutExpired:
        status = f"timed out after {timeout_s:.0f} s"
    text = open(log, encoding="utf-8", errors="replace").read()
    m = re.search(r"proof folder: (\S.*)", text)
    rep: Dict[str, Any] = {}
    if m:
        with open(os.path.join(m.group(1).strip(), "report.json"), encoding="utf-8") as f:
            rep = json.load(f)
        rep["_folder"] = m.group(1).strip()
    return {"target": target, "status": status, "seconds": round(time.time() - t0), "log": log, "report": rep, "text": text}


def row(r: Dict[str, Any]) -> List[str]:
    rep = r["report"]
    if not rep:
        why = re.search(r"\[2 SCAN\] failed: (.*)", r["text"])
        return [r["target"], r["status"], "-", "-", "-", "-", "-", "-", (why.group(1)[:60] if why else "no report")]
    d, u, sc = rep.get("digest", {}), rep.get("understanding") or {}, rep.get("scan", {})
    ex = sc.get("explore") or {}
    st, net, au, sh = u.get("stack", {}), u.get("network", {}), u.get("auth", {}), u.get("shortcut_sheet", {})
    walls = "; ".join(d.get("walls", [])) or ("login wall" if au.get("login_wall") else "-")
    rec = rep.get("recognise", {})
    return [r["target"], f"{r['status']} / {r['seconds']} s", str(d.get("controls", "-")), f"{ex.get('clicks', '-')} clicks, {ex.get('max_depth', '-')} deep, {len(ex.get('pages', {}))} pages",
            ", ".join(st.get("frameworks", [])[:3]) or "-", f"{net.get('requests', '-')} req / {len(net.get('api_endpoints', []))} api", f"{len(sh.get('pairs', []))}",
            (rec.get("ranked") or [["-"]])[0][0] + f" ({rec.get('status', '')})" if rec.get("ranked") else "-", walls[:70]]


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("targets", nargs="*")
    ap.add_argument("--clicks", type=int, default=250)
    ap.add_argument("--depth", type=int, default=5)
    ap.add_argument("--pages", type=int, default=15)
    ap.add_argument("--explore-seconds", type=float, default=600.0)
    ap.add_argument("--pace", type=float, default=0.25)
    ap.add_argument("--hold", type=float, default=2.0)
    ap.add_argument("--timeout", type=float, default=1500.0, help="seconds allowed per site")
    a = ap.parse_args(argv)
    targets = a.targets or DEFAULT
    folder = os.path.join(ROOT, "try_app", "batch_" + time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(folder, exist_ok=True)
    extra = ["--clicks", str(a.clicks), "--depth", str(a.depth), "--pages", str(a.pages), "--explore-seconds", str(a.explore_seconds), "--pace", str(a.pace), "--hold", str(a.hold)]
    rows: List[List[str]] = []
    print(f"BATCH {len(targets)} sites -> {folder}", flush=True)
    for t in targets:
        print(f"SITESTART {t}", flush=True)
        r = one(t, folder, extra, a.timeout)
        rows.append(row(r))
        print(f"SITEDONE {t}: {rows[-1][1]}; controls {rows[-1][2]}; {rows[-1][3]}; walls: {rows[-1][8]}", flush=True)
        head = ["site", "status", "controls", "deep exploration", "stack", "traffic", "shortcuts read", "recognised as", "in the way"]
        md = ["# Batch: deep scan + reverse engineering", "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(x.replace("|", "/") for x in rw) + " |" for rw in rows]
        md += ["", "Per site: `UNDERSTANDING.md`, `report.json` and pictures in each site's proof folder (path is the last line of its .log)."]
        with open(os.path.join(folder, "SUMMARY.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(md))
    print(f"BATCHDONE {folder}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
