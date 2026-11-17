"""
autonomous_installer_engine -- JIT ephemeral app acquisition for Phase-2 testing.

Part of Hojaiga PART-2 (Dynamic Live Validation). It acquires ONE anchor app at a
time so the machine never accumulates 6,000 installs: install -> (the live
trajectory executor tests it) -> uninstall + state reset -> next.

Two acquisition rungs, in order:
  1. WINGET_SILENT : native `winget install --id <PID> --silent --accept-*`
  2. GUI_WIZARD    : only if silent fails / the installer is interactive. It walks
                     the wizard with the SAME headless organs the executor uses
                     (fast_uia scan + posted/UIA actuation, never the physical
                     cursor), clicking Next/I Agree/Install and -- importantly --
                     UNCHECKING pre-ticked adware/telemetry/bundle boxes.

Safety (this repo bans destructive surprises):
  * Default is PLAN-ONLY. Nothing installs unless --execute is passed. `winget --version`
    and `winget show` (read-only) are the only calls made in plan mode.
  * Every install caches its Quiet/UninstallString from the registry so cleanup is
    deterministic, and results append to trajectories/installs.jsonl (honest statuses).

Usage
-----
  python autonomous_installer_engine.py --plan "Notepad++.Notepad++"        # read-only
  python autonomous_installer_engine.py --execute "Some.App" --install-root D:\\AutoApps
  python autonomous_installer_engine.py --uninstall-cached "Some.App"       # clean up
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

_ORGANS = Path(__file__).resolve().parent / "All codes"
if str(_ORGANS) not in sys.path:
    sys.path.insert(0, str(_ORGANS))

INSTALL_LOG = Path("trajectories") / "installs.jsonl"

# Boxes we NEVER want ticked (third-party junk / telemetry / default hijacks).
ADWARE_RE = re.compile(
    r"(install (?:toolbar|partner|extra|more)|opt[- ]?in|send (?:diagnostics|usage|feedback)|"
    r"agreed to (?:send|share)|set (?:default|as my default)|make .{0,20}(?:default browser|default search|home ?page)|"
    r"try .{0,20}(?:toolbar|offer|deal)|sponsor|bundl(?:e|ed)|partner offer|newsletter|promo)",
    re.I,
)
# Buttons in install wizards, in preference order (semantic matcher resolves the live label).
WIZARD_ADVANCE = ["next", "install", "i agree", "agree", "accept", "finish", "complete", "yes", "continue"]


def log(m: str) -> None:
    print(f"[installer] {m}", flush=True)


def _run(cmd: list, timeout: int = 60) -> subprocess.CompletedProcess:
    # winget emits UTF-8; text=True would default to the cp1252 locale and raise
    # UnicodeDecodeError on smart-quote bytes -> decode explicitly, never crash.
    return subprocess.run(cmd, shell=False, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


# ---------------------------------------------------------------------------
# rung 1: native winget
# ---------------------------------------------------------------------------

def winget_available() -> bool:
    try:
        r = _run(["winget", "--version"], timeout=20)
        return r.returncode == 0
    except Exception:
        return False


def winget_search(query: str, execute: bool) -> dict:
    """Resolve a package id/name. PLAN mode uses read-only `winget show` (installs nothing);
    EXECUTE mode validates with `winget install` agreement dry run."""
    try:
        if not execute:
            r = _run(["winget", "show", "--id", query, "--exact", "--accept-source-agreements"], timeout=90)
        else:
            r = _run(["winget", "install", "--id", query, "--exact", "--accept-package-agreements",
                      "--accept-source-agreements"], timeout=90)
        text = (r.stdout or "") + (r.stderr or "")
        resolved = ("found this package" in text.lower() or "\u2117" in text or r.returncode == 0)
        return {"resolved": bool(resolved), "winget_rc": r.returncode, "note": text.strip()[-200:]}
    except Exception as exc:
        return {"resolved": False, "note": f"{type(exc).__name__}: {str(exc)[:120]}"}


# ---------------------------------------------------------------------------
# registry: cache uninstall string after install
# ---------------------------------------------------------------------------

def cache_uninstall_string(name_hint: str) -> dict:
    out = {}
    try:
        import winreg
    except Exception:
        return {"cached": False, "note": "winreg unavailable"}
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    key = (name_hint or "").lower()
    for hive, path in roots:
        try:
            with winreg.OpenKey(hive, path) as base:
                for i in range(winreg.QueryInfoKey(base)[0]):
                    try:
                        sub = winreg.OpenKey(base, winreg.EnumKey(base, i))
                        vals = {}
                        for prop in ("DisplayName", "QuietUninstallString", "UninstallString"):
                            try:
                                vals[prop] = winreg.QueryValueEx(sub, prop)[0]
                            except OSError:
                                pass
                        winreg.CloseKey(sub)
                        dn = (vals.get("DisplayName") or "").lower()
                        # A winget id like 'Notepad++.Notepad++' rarely substring-matches the
                        # registry DisplayName 'Notepad++ (x64)'; fall back to token overlap so
                        # MSI anchors (which register under a product-code key) are still found.
                        if dn and ((key in dn) or (dn in key) or (_norm_tokens(dn) & _norm_tokens(key))):
                            out = {"cached": True, "display": vals.get("DisplayName"),
                                   "quiet": vals.get("QuietUninstallString"),
                                   "uninstall": vals.get("UninstallString")}
                            return out
                    except Exception:
                        continue
        except OSError:
            continue
    return {"cached": False, "note": "uninstall key not found"}


def _is_safe_uninstall_cmd(cmd: str) -> bool:
    """Registry-sourced uninstall strings need shell semantics, but refuse anything
    carrying command-chaining / substitution metacharacters (defence in depth)."""
    if not cmd:
        return False
    if re.search(r"[;&|`<>]|\$\(|%[A-Z_]+%", cmd):
        return False
    return True


def _norm_tokens(s: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]{2,}", (s or "").lower())}


def _msi_quiet(cmd: str) -> str:
    """Registry MSI UninstallStrings often carry '/I{code}' (repair UI). For an unattended
    ephemeral reset we need '/X{code} /qn' (silent remove). Leave non-MSI commands alone."""
    m = re.search(r"\{[0-9A-Fa-f-]{36}\}", cmd or "")
    if m and "msiexec" in (cmd or "").lower():
        return f"msiexec.exe /X{m.group(0)} /qn /norestart"
    return cmd


def uninstall_cached(name_hint: str, execute: bool) -> dict:
    rec = cache_uninstall_string(name_hint)
    cmd = _msi_quiet(rec.get("quiet") or rec.get("uninstall") or "")
    if not cmd:
        return {**rec, "status": "NO_UNINSTALL_COMMAND"}
    if not _is_safe_uninstall_cmd(cmd):
        return {**rec, "status": "REFUSED_UNSAFE_COMMAND",
                "note": "uninstall string contains shell metacharacters; run it manually after review"}
    if not execute:
        return {**rec, "status": "PLAN", "would_run": cmd}
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300)
        return {**rec, "status": "UNINSTALLED" if r.returncode == 0 else "UNINSTALL_FAILED",
                "rc": r.returncode}
    except Exception as exc:
        return {**rec, "status": "UNINSTALL_ERROR", "note": str(exc)[:120]}


# ---------------------------------------------------------------------------
# rung 2: interactive wizard traversal (headless; uses the same organs)
# ---------------------------------------------------------------------------

def _wizard_windows():
    try:
        from core_organs import headless_input as hin
    except Exception:
        return []
    titles = hin.top_level_titles(visible_only=False)
    hits = []
    rx = re.compile(r"(setup|install|wizard|installer|installation|configuration)", re.I)
    for hwnd, t in titles:
        if rx.search(t or ""):
            hits.append((hwnd, t))
    return hits


def traverse_wizard(max_steps: int = 15, execute: bool = False) -> dict:
    """Walk a visible installer to completion with posted/UIA clicks; reject adware boxes.

    Plan mode reports the buttons/checkboxes it FINDS (via the live UIA tree) without
    acting, so the traversal logic is verifiable without mutating the machine."""
    import semantic_match as SM
    try:
        from core_organs import fast_uia, headless_input as hin
    except Exception as exc:
        return {"status": "ORGANS_UNAVAILABLE", "note": str(exc)[:120]}

    wins = _wizard_windows()
    if not wins:
        return {"status": "NO_WIZARD_WINDOW", "note": "no installer window currently open"}
    hwnd, title = wins[0]
    log(f"wizard target hwnd={hwnd} '{title}'")

    path = []
    for _ in range(max_steps):
        nodes = fast_uia.snapshot(hwnd, max_nodes=8000) or []
        # 1) neutralize any ticked adware/telemetry checkbox first
        if execute:
            for n in nodes:
                label = f"{getattr(n, 'name', '')} {getattr(n, 'aid', '')}"
                role = str(getattr(n, "role", "")).lower()
                toggle = getattr(n, "toggle_state", -1)
                if role == "checkbox" and ADWARE_RE.search(label) and toggle == 1:
                    _toggle_off(n)
                    path.append({"uncheck": label[:60]})
        # 2) find an advance button via the semantic matcher
        adv = _pick_advance(nodes, SM)
        if adv is None:
            break
        node, how, score = adv
        path.append({"click": (getattr(node, "name", "") or getattr(node, "aid", ""))[:60],
                     "how": how, "score": round(score, 2)})
        if not execute:
            break  # plan: show the first planned move, don't loop
        _press(node, hwnd)
        time.sleep(1.0)
        if any(re.search(r"(finish|complete|close)", (getattr(n, "name", "") or "").lower()) for n in nodes):
            break
    return {"status": "PLANNED" if not execute else "TRAVERSED", "wizard": title, "moves": path}


def _pick_advance(nodes, SM):
    best = None
    for kw in WIZARD_ADVANCE:
        m = SM.resolve({"element_name": kw, "element_type": "Button"}, nodes, use_embeddings=False)
        if m.node is not None and m.how in ("lexical", "embedding") and m.score >= SM.LEX_STRONG:
            role = str(getattr(m.node, "role", "")).lower()
            if role in ("button",):
                return m.node, m.how, m.score
        if best is None and m.node is not None:
            best = (m.node, m.how, m.score)
    return best if best and best[2] >= 0.6 else (best if best else None)


def _press(node, hwnd):
    try:
        from core_organs import headless_input as hin
    except Exception:
        return
    if getattr(node, "rect", (0, 0, 0, 0)) != (0, 0, 0, 0):
        l, t, r, b = node.rect
        hin.post_click(hwnd, (l + r) // 2, (t + b) // 2)
    try:
        ctrl = node.ctrl
        pat = ctrl.GetPattern(10000)  # Invoke
        if pat is not None:
            pat.Invoke()
    except Exception:
        pass


def _toggle_off(node):
    try:
        pat = node.ctrl.GetPattern(10015)  # Toggle
        if pat is not None and getattr(node, "toggle_state", 0) == 1:
            pat.Toggle()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------

def resolve_and_install(package: str, execute: bool, install_root: str = "") -> dict:
    result: dict = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "package": package,
              "mode": "EXECUTE" if execute else "PLAN", "winget": winget_available()}
    if not result["winget"]:
        result["status"] = "NO_WINGET"
        return _record(result)

    res = winget_search(package, execute)
    result["resolve"] = res
    if not execute:
        result["status"] = "PLAN_OK"
        result["next"] = "pass --execute to install, then run live_trajectory_executor for Phase-2 validation"
        return _record(result)

    silent = _run(["winget", "install", "--id", package, "--exact", "--silent",
                   "--accept-package-agreements", "--accept-source-agreements"]
                  + (["--override", f"/DIR={install_root}"] if install_root else []), timeout=900)
    if silent.returncode == 0:
        result["status"] = "SUCCESS"
        result["method"] = "WINGET_SILENT"
    else:
        result["status"] = "FALLBACK_GUI"
        result["gui"] = traverse_wizard(execute=True)
    result["uninstall_cache"] = cache_uninstall_string(package)
    return _record(result)


def _record(result: dict) -> dict:
    INSTALL_LOG.parent.mkdir(parents=True, exist_ok=True)
    with INSTALL_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(result, ensure_ascii=False) + "\n")
    log(json.dumps({k: result[k] for k in result if k in
                    ("status", "package", "mode", "method")}, ensure_ascii=False))
    return result


def main():
    p = argparse.ArgumentParser(description="JIT ephemeral installer for Phase-2 anchor testing (plan-only by default).")
    p.add_argument("--plan", metavar="PACKAGE", help="resolve via winget and report; install nothing")
    p.add_argument("--execute", metavar="PACKAGE", help="actually install (destructive; explicit opt-in)")
    p.add_argument("--traverse-wizard", action="store_true", help="plan the GUI wizard traversal for a currently-open installer")
    p.add_argument("--uninstall-cached", metavar="PACKAGE", help="run the cached uninstall string")
    p.add_argument("--install-root", default="", help="deterministic install dir (e.g. D:\\AutoApps)")
    p.add_argument("--yes", action="store_true", help="required alongside --execute to confirm a real install")
    args = p.parse_args()

    if args.traverse_wizard:
        print(json.dumps(traverse_wizard(execute=False), indent=3)); return
    if args.uninstall_cached:
        print(json.dumps(uninstall_cached(args.uninstall_cached, execute=args.yes), indent=3)); return
    if args.plan:
        print(json.dumps(resolve_and_install(args.plan, execute=False), indent=3)); return
    if args.execute:
        if not args.yes:
            log("--execute requires --yes (this installs software). Aborted. Nothing changed.")
            sys.exit(1)
        print(json.dumps(resolve_and_install(args.execute, True, args.install_root), indent=3)); return
    p.error("give --plan, --execute (+--yes), --traverse-wizard, or --uninstall-cached")


if __name__ == "__main__":
    main()
