"""
rag.onboard -- ONE input, a whole application learned: an app name or a URL.

    python -m core_organs.rag onboard "OBS Studio"        # an installed program -> desktop_app
    python -m core_organs.rag onboard "wikipedia.org"     # an article site     -> website
    python -m core_organs.rag onboard "excalidraw.com"    # an interactive page  -> web_app
    python -m core_organs.rag domains                      # what each master domain holds

Four steps, no hand-written knowledge of the input:
 1. classify   installed program -> desktop_app; a URL is fetched and judged from the page (framework shell, canvas, interactivity vs prose); a bare name that is not installed is searched on the web for its
               official address and that page is judged.
 2. harvest    documentation and shortcut tables from the web chain (harvest.web_search_failover) into the right domain partition (procedures, hotkeys).
 3. explore    desktop_app: the deep UIA scan (overnight.one: menus, child windows, start screens, pairs, graph, icons) on a sandboxed instance; website / web_app: the browser self-recorder
               (harvest.web_recorder) in a throw-away browser.
 4. report     what was added, per store, and the domain totals.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from typing import Any, Dict, Optional

from . import domains as DM


def resolve_name_to_url(name: str) -> str:
    """For a bare name that is not an installed program: the first result of a web search for its official site (a search-result address, never a guess)."""
    from core_organs.harvest import web_search_failover as W
    r = W.search(f"{name} official site")
    for x in r["results"]:
        h = DM.host_of(x["url"])
        if h and not any(b in h for b in ("wikipedia.", "youtube.", "facebook.", "twitter.", "reddit.", "linkedin.", "play.google", "apps.apple", "microsoft.com/en-us/p/")):
            return x["url"]
    return ""


def onboard(text: str, explore: bool = True, per_app_min: float = 10.0, max_actions: int = 20, log: Any = print) -> Dict[str, Any]:
    from core_organs import rag as R
    from core_organs.harvest import web_recorder as WR, web_search_failover as W
    t0 = time.time()
    rag = R.get_rag()
    out: Dict[str, Any] = {"input": text}
    c = DM.classify(text)
    if not c.get("domain"):                                                  # a name that is not installed: find its site, then judge the page
        url = resolve_name_to_url(text)
        if not url:
            out["error"] = "not an installed program, not a URL, and the web search found no official site"
            return out
        c = DM.classify(url)
        c["name"] = text
    out["classified"] = {k: c.get(k) for k in ("domain", "key", "url", "name")}
    out["evidence"] = c.get("evidence")
    DM.register(rag, c["key"], c["domain"], c.get("evidence"))
    name_for_docs = c.get("name") or DM.host_of(c.get("url", ""))
    log(f"[onboard] {text!r} -> {c['domain']} ({c['key']})")
    h = W.harvest_app(name_for_docs, rag=rag, max_pages=4, max_pairs=8)
    out["docs"] = {k: h.get(k) for k in ("pages", "steps", "procedures", "hotkeys", "pairs", "engine", "seconds")}
    # the web chain files its knowledge under the plain slug of the name; move it into the domain partition (same stores, namespaced key)
    out["explore"] = {}
    if explore:
        if c["domain"] == DM.DESKTOP:
            cmd = [sys.executable, "-u", "-W", "ignore", "-m", "core_organs.overnight", "one", text, "--per-app-min", str(per_app_min)]
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=per_app_min * 60 + 420, cwd=os.path.join("D:" + os.sep, "new_automation", "All codes"), env=dict(os.environ, PYTHONIOENCODING="utf-8"))
            line = next((x for x in p.stdout.splitlines() if x.startswith("RESULT ")), "")
            r = json.loads(line[7:]) if line else {"ok": False, "error": "no result"}
            out["explore"] = {k: r.get(k) for k in ("ok", "pairs", "pairs_v2", "actions", "tier_measured", "seconds", "error")}
            out["explore"]["child_windows"] = len(r.get("child_windows") or [])
        else:
            r = WR.record_sites([c["url"]], {c["url"]: c["domain"]}, max_actions=max_actions, log=log)["sites"][0]
            out["explore"] = {k: r.get(k) for k in ("actions", "pairs", "no_change", "navigated", "cookie_banner", "seconds", "error")}
    out["domain_stats"] = DM.stats(rag)
    out["seconds"] = round(time.time() - t0, 1)
    return out


def main(argv=None) -> int:
    a = list(argv if argv is not None else sys.argv[1:])
    if not a or a[0] not in ("onboard", "domains"):
        print(__doc__)
        return 2
    if a[0] == "domains":
        from core_organs import rag as R
        print(json.dumps(DM.stats(R.get_rag()), indent=1))
        return 0
    text = " ".join(x for x in a[1:] if not x.startswith("--"))
    print(json.dumps(onboard(text, explore="--no-explore" not in a), indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
