"""
harvest.catalogue -- WHICH applications to learn, found on the machine, classified, safety-filtered, balanced across categories and tiers.

Nothing here lists applications by hand: the Start menu is read (Get-StartApps), every entry is classified by what its NAME and program say (category), and a safety filter removes what must never be driven by a
background learner -- anything that holds the person's accounts, messages, files, photos, money or machine (shells, registry, disk tools, security, remote access), games and their launchers, installers,
uninstallers, documentation shortcuts and tools that need elevation. What remains is ordered tier by tier and category by category so a run that stops early still covers the world of software widely rather
than 40 flavours of one vendor's utility.

Tier here is a HINT from the category and program class; the TRUE tier is measured after the scan (controls found, depth, child windows) and written back to data/catalogue/tiers.json:
    tier 0  flat controls (a few dozen), no child windows
    tier 1  ribbons / toolbars / menus, some dialogs
    tier 2  deep: many controls, nested child windows, heavy start-up (3D, CAD / CAE, IDEs, media suites)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any, Dict, List, Optional

OUT_DIR = r"D:\new_automation\data\catalogue"

# never driven by a background learner (accounts / personal data / the machine / launchers / docs)
EXCLUDE = re.compile(
    r"uninstall|installer|setup|\bupdate\b|licen[cs]e|readme|read me|manual|help\b|documentation|dokumentation|\bfaq|website|homepage|donate|changelog|release notes|sample|tools for|feedback|get started|get help|offers|"
    r"promotion|video instructions|\bpdf\b|command prompt|powershell|terminal|console|\bbash\b|git cmd|\bcmd\b|\bwsl\b|ubuntu|registry|task manager|task scheduler|services|computer management|event viewer|component services|"
    r"disk cleanup|defragment|recovery|backup|security|defender|firewall|iscsi|odbc|memory diagnostic|system configuration|system information|remote desktop|quick assist|ultraviewer|etcher|wireshark|ip scanner|"
    r"discord|whatsapp|teams|skype|outlook|calendar|people|phone link|onedrive|dropbox|steam|epic games|riot|valorant|counter-strike|rainbow six|roblox|xbox|game bar|overwolf|medal|lagofast|aimlabs|netflix|booking|"
    r"duolingo|chatgpt|\bclaude\b|copilot|devin|opencode|cursor|antigravity|qoder|ollama|docker|ngrok|grammarly|zoom|lockdown|photos|file explorer|\bfiles\b|camera|sound recorder|voice access|live captions|narrator|"
    r"on-screen keyboard|click to do|screenshots|steps recorder|\bhp\b|omen|nvidia|intel|samsung|wooting|wootility|power automate|microsoft store|\bnews\b|microsoft to do|whiteboard|adobe express|crop images|edit photos|"
    r"remove background|rotate photos|view photos|add text|clipchamp|capcut|solitaire|\bdev home\b|windows tools|control panel|\brun\b|settings|reset |debuggable|application verifier|app cert|performance recorder|"
    r"gpuview|windows performance|sql server .*(configuration|installation|error|import)|database engine|profiler|telemetry|office language|spreadsheet compare|\bfamily\b|\bconsole\b|jupyter|anaconda prompt|"
    r"uninstall|reset keymapper|server|cluster|monitor$|scheduler|licensing|ansys help|\bhelp\b|pdf help|configuration manager|configuration 20|file association|"
    # MEASURED (Oct 18): file managers and notebooks show the person's own folders / notes in every screenshot (7-Zip showed C:\Users\<name>\Downloads); media / VM / IDE launchers list their personal libraries and projects
    r"github desktop|media player|visual studio 2022|ans_admin|onenote|virtualbox|publisher", re.I)       # 7-Zip is allowed again: it is started on the sandbox folder (harvest.sandbox)

# category by name / program keyword (first hit wins; order matters)
CATEGORIES = [
    ("browser", r"edge|chrome|firefox|brave|opera|vivaldi", 1),
    ("office", r"word|excel|powerpoint|access|publisher|onenote|acrobat", 1),
    ("editor", r"notepad|sticky|texworks|hxd|idle|spyder|visual studio code", 1),
    ("ide", r"visual studio|ssms|sql server management|git gui|github desktop|anaconda navigator", 2),
    ("3d", r"blender|roblox|unreal|maya|3ds|cinema", 2),
    ("video_audio", r"obs|audacity|vlc|media player|davinci|premiere|handbrake", 2),
    ("graphics", r"paint|gimp|inkscape|krita|photoshop|illustrator", 1),
    ("engineering", r"ansys|zemax|opticstudio|spaceclaim|fluent|mechanical|workbench|cfd|ensight|optislang|speos|workbench|polyflow|forte|chemkin|rocky|aqwa|turbogrid|discovery|motion", 2),
    ("virtualisation", r"virtualbox|vmware|hyper-v", 2),
    ("utility", r"calculator|clock|character map|magnifier|snipping|weather|resource monitor|performance monitor|gpu-z|dosbox|7-zip|media player legacy", 0),
]
CATEGORY_DEFAULT = ("other", 1)


def installed() -> List[Dict[str, str]]:
    """[{name, appid}] from the Start menu (what a person could search for and open)."""
    cmd = "Get-StartApps | Sort-Object Name | ConvertTo-Json -Compress"
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True, text=True, timeout=60)
        data = json.loads(r.stdout or "[]")
    except Exception:
        return []
    if isinstance(data, dict):
        data = [data]
    out, seen = [], set()
    for d in data:
        nm = (d.get("Name") or "").strip()
        if nm and nm.lower() not in seen:
            seen.add(nm.lower())
            out.append({"name": nm, "appid": d.get("AppID") or ""})
    return out


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40]


def classify(name: str) -> Dict[str, Any]:
    nm = name.lower()
    for cat, rx, tier in CATEGORIES:
        if re.search(rx, nm):
            return {"category": cat, "tier_hint": tier}
    return {"category": CATEGORY_DEFAULT[0], "tier_hint": CATEGORY_DEFAULT[1]}


def candidates() -> List[Dict[str, Any]]:
    out = []
    for a in installed():
        if EXCLUDE.search(a["name"]):
            continue
        c = classify(a["name"])
        out.append({"name": a["name"], "key": slug(a["name"]), "appid": a["appid"], **c})
    return out


def select(limit: int = 60, per_category: int = 8) -> List[Dict[str, Any]]:
    """Balanced and ordered: tier 0 first, then 1, then 2; within a tier, categories round-robin so a stopped run has covered as many kinds of software as possible."""
    cands = candidates()
    by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for c in cands:
        by_cat.setdefault(c["category"], []).append(c)
    for cat in by_cat:
        by_cat[cat] = by_cat[cat][:per_category]
    out: List[Dict[str, Any]] = []
    for tier in (0, 1, 2):
        pools = [[c for c in v if c["tier_hint"] == tier] for v in by_cat.values()]
        i = 0
        while any(pools) and len(out) < limit:
            for pool in pools:
                if i < len(pool) and len(out) < limit:
                    out.append(pool[i])
            i += 1
            if all(i >= len(p) for p in pools):
                break
    return out[:limit]


def save(entries: List[Dict[str, Any]], name: str = "apps.json") -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    p = os.path.join(OUT_DIR, name)
    json.dump(entries, open(p, "w", encoding="utf-8"), indent=1)
    return p


def measured_tier(n_controls: int, n_child_windows: int, menus_found: int = 0) -> int:
    """The tier a scan MEASURED: deep (many controls or nested child windows) = 2, ribbon / menu-rich = 1, flat = 0."""
    if n_controls > 150 or n_child_windows >= 4:
        return 2
    if n_controls > 45 or n_child_windows >= 1 or menus_found >= 3:
        return 1
    return 0


if __name__ == "__main__":
    es = select()
    print(len(es), "apps selected; written to", save(es))
    for e in es:
        print(f"  tier{e['tier_hint']} {e['category']:<14} {e['name']}")
