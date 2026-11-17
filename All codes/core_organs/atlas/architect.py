"""
atlas.architect -- from evidence to the DEVELOPER-LEVEL model of an application, and a report a developer would trust.

`build()` reads everything the other modules stored (claims with trust + evidence, gestures, the engine's commands / dialogs / state variables /
conventions) and assembles:

    identity            what it is: product, vendor, version, and its KIND by evidence-voting against a taxonomy (public description,
                        file types, library areas, UI vocabulary, object-model type names) -- or 'unclassified' when the evidence does not
                        separate the candidates
    stack               language(s), toolkit/runtime, rendering, audio, video, network, storage, scripting, AI/compute, packages, versions
    process_model       helpers, services, plugin hosts
    ui_model            commands, menus, dialogs (schemas), regions, modes (state variables), labels seen
    interaction_grammar measured gestures per region kind + published (shipped) bindings + input-channel facts
    data_model          persisted configuration schema, database tables, COM object model, file formats
    extensibility       plugin folders, scripting runtimes, COM, command line, URL protocols
    behavior            transitions learned, reversibility, conventions tested
    gaps                what is NOT known and why (honest list)
    provenance          claim counts by trust class

`write_report()` renders it as Markdown with the evidence behind each statement, plus the JSON model.
"""

from __future__ import annotations

import collections
import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from . import common as C

_TAX: Dict[str, Any] = {}


def taxonomy() -> Dict[str, Any]:
    global _TAX
    if not _TAX:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "taxonomy.json"), "r", encoding="utf-8") as fh:
            _TAX = json.load(fh)
    return _TAX


def _words_in(text: str, words: List[str]) -> List[str]:
    t = " " + C.fold(text) + " "
    return [w for w in words if (" " + C.fold(w) + " ") in t]


def classify(claims: List[Dict[str, Any]], *, file_types: List[str], labels: List[str], com_types: List[str]) -> Dict[str, Any]:
    """Evidence voting. Each source adds weighted votes for kinds; the result lists the top candidates WITH the evidence behind them."""
    tax = taxonomy()["kinds"]
    web_text = " ".join(c["statement"] for c in claims if c["kind"].startswith("web.") or c["kind"] in ("arch.design", "model.published"))
    kind_claims = " ".join(c["statement"] for c in claims if c["kind"] in ("web.kind", "web.identity"))
    area_hits: Dict[str, List[str]] = collections.defaultdict(list)
    lib_labels: List[str] = []
    for c in claims:
        if c["kind"].startswith("stack.") and isinstance(c.get("value"), dict):
            v = c["value"]
            if v.get("area"):
                area_hits[v["area"]].append(v.get("label", ""))
            if v.get("label"):
                lib_labels.append(v["label"])
    label_text = " ".join(labels).lower()
    exts = {e.lower() for e in file_types}
    scores: Dict[str, float] = {}
    why: Dict[str, List[str]] = {}
    for k in tax:
        s, w = 0.0, []
        hit = _words_in(kind_claims, k["words"])
        if hit:
            s += 4.0 + 0.5 * (len(hit) - 1)
            w.append(f"public description says: {', '.join(hit[:3])}")
        hit2 = _words_in(web_text, k["words"])
        if hit2 and not hit:
            s += 1.5
            w.append(f"public text mentions: {', '.join(hit2[:3])}")
        eh = sorted(exts & set(k["ext"]))
        if eh:
            s += min(3.0, 0.8 * len(eh))
            w.append(f"opens/saves {', '.join(eh[:5])}")
        for area, wt in k.get("areas", {}).items():
            if area_hits.get(area):
                s += wt * min(1.0, 0.5 + 0.25 * len(area_hits[area]))
                w.append(f"{area} libraries: {', '.join(sorted(set(area_hits[area]))[:3])}")
        lh = [l for l in k["libs"] if l in lib_labels]
        if lh:
            s += min(3.0, 0.9 * len(lh))
            w.append(f"specific libraries: {', '.join(lh[:4])}")
        uh = [u for u in k["ui"] if re.search(r"\b" + re.escape(u) + r"\b", label_text)]
        if uh:
            s += min(3.0, 0.45 * len(uh))
            w.append(f"UI vocabulary: {', '.join(uh[:6])}")
        ch = [t for t in k.get("com", []) if t in com_types]
        if ch:
            s += min(3.5, 1.2 * len(ch))
            w.append(f"object model has: {', '.join(ch[:5])}")
        if s > 0:
            scores[k["id"]], why[k["id"]] = s, w
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    labels_of = {k["id"]: k["label"] for k in tax}
    top = [{"kind": i, "label": labels_of[i], "score": round(sc, 2), "evidence": why[i]} for i, sc in ranked[:3]]
    if not ranked:
        return {"kind": "unclassified", "confidence": 0.0, "candidates": [], "why": "no evidence matched any known kind"}
    best, second = ranked[0][1], (ranked[1][1] if len(ranked) > 1 else 0.0)
    ok = best >= 4.0 and best >= 1.25 * second
    return {"kind": ranked[0][0] if ok else "unclassified", "label": labels_of[ranked[0][0]] if ok else "", "confidence": round(min(0.97, best / (best + second + 3.0)), 2) if ok else round(best / (best + second + 6.0), 2),
            "candidates": top, "why": "" if ok else f"evidence does not separate '{top[0]['label']}' ({best:.1f}) from the runner-up ({second:.1f})"}


def build(app_key: str, store: C.AtlasStore, model, *, exe: str = "") -> Dict[str, Any]:
    from core_organs import knowledge_store as ks
    claims = store.claims(app_key)
    by_kind: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    for c in claims:
        by_kind[c["kind"]].append(c)
    pick = lambda prefix: [c for k, v in by_kind.items() if k.startswith(prefix) for c in v]
    facts: Dict[str, Any] = {}
    try:
        facts = ks.facts(model, app_key)
    except Exception:
        pass
    file_types = list(facts.get("file_types") or [])
    labels: List[str] = []
    try:
        for r in model._conn.execute("SELECT name, menu_path FROM bm_commands WHERE app_key=?", (app_key,)):
            labels.append(str(r[0]))
            if r[1]:
                labels += str(r[1]).split(">")
    except Exception:
        pass
    labels += [c["value"]["text"] for c in by_kind.get("ui.label", []) if isinstance(c.get("value"), dict) and c["value"].get("text")]
    com_types: List[str] = []
    for c in by_kind.get("ext.com.model", []):
        f = (c.get("value") or {}).get("file")
        if f and os.path.isfile(f):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    d = json.load(fh)
                for lib in d.get("typelibs", {}).values():
                    com_types += [t["name"].lstrip("_") for t in lib.get("top", [])]
                    com_types += list(lib.get("methods", {}).keys())
            except Exception:
                pass
    identity_c = (by_kind.get("arch.identity") or [None])[0]
    ident: Dict[str, Any] = {"summary": identity_c["statement"] if identity_c else "", "evidence": identity_c["evidence"] if identity_c else []}
    if identity_c and isinstance(identity_c.get("value"), dict):
        ident.update(identity_c["value"])
    wd = [c["statement"] for c in by_kind.get("web.identity", [])]
    ident["public_description"] = wd[0] if wd else ""
    cl = classify(claims, file_types=file_types, labels=labels, com_types=com_types)
    ident.update(kind=cl["kind"], kind_label=cl.get("label", ""), kind_confidence=cl["confidence"], kind_candidates=cl["candidates"], kind_note=cl.get("why", ""))

    stack: Dict[str, List[str]] = collections.defaultdict(list)
    for c in pick("stack."):
        area = c["kind"].split(".")[1]
        if c["statement"] not in stack[area]:
            stack[area].append(c["statement"])
    stack_out = {a: v for a, v in stack.items()}
    ui: Dict[str, Any] = {}
    try:
        from core_organs import command_registry as cr
        reg = cr.build(model, app_key)
        ui["commands"] = len(reg)
        ui["by_kind"] = dict(collections.Counter(r["kind"] for r in reg))
        ui["verified_commands"] = sum(1 for r in reg if r["verified"])
        ui["with_shortcut"] = sum(1 for r in reg if r["shortcut"])
        ui["menus"] = sorted({r["menu_path"].split(">")[0].strip() for r in reg if r["menu_path"]})[:40]
    except Exception as exc:
        ui["commands_error"] = str(exc)[:100]
    try:
        ui["dialogs"] = [{"title": d["title"], "controls": len(d.get("controls", [])) if d.get("controls") is not None else None} for d in ks.dialogs(model, app_key, with_controls=True)][:60]
        ui["state_variables"] = [{"name": v["name"], "kind": v["kind"], "values": v["values"][:8]} for v in ks.statevars(model, app_key)][:40]
        ui["conventions"] = [{k: c[k] for k in ("intent", "chord", "verdict")} for c in ks.conventions(model, app_key)][:30]
    except Exception:
        pass
    ui["labels_seen"] = len(by_kind.get("ui.label", []))
    ui["widgets_interactive"] = len(by_kind.get("ui.widget", []))
    ui["tooltips"] = [c["statement"] for c in by_kind.get("ui.tooltip", [])][:30]
    ui["blind_menus"] = [c["statement"] for c in by_kind.get("ui.menu", [])][:12]
    ui["published_shortcuts"] = len(by_kind.get("ui.shortcut.published", []))

    gest = store.gestures(app_key)
    measured: Dict[str, Dict[str, Any]] = {}
    for g in gest:
        k = f"{g['region_kind']}|{g['gesture']}"
        if g["effect_class"] in ("no_effect",) and k in measured:
            continue
        measured[k] = {"region_kind": g["region_kind"], "gesture": g["gesture"], "effect": g["effect_class"], "reversible": bool(g["reversible"]) if g["reversible"] is not None else None,
                       "delivered": bool(g["delivered"]), "effective": bool(g["effective"]) if g["effective"] is not None else None, "params": {k2: v for k2, v in (g["effect"] or {}).items() if k2 in ("zoom_factor", "deg_per_px", "pan_ratio_x", "kinds", "items")}}
    shipped = [c["statement"] for c in by_kind.get("gesture.shipped", [])]
    grammar = {"measured": sorted(measured.values(), key=lambda m: (m["region_kind"], m["gesture"])), "shipped_pointer_bindings": shipped[:80], "n_shipped": len(shipped),
               "input_channels": [c["statement"] for c in by_kind.get("input.channel", [])]}
    data_model = {"config_schema": [c["statement"] for c in by_kind.get("cfg.schema", [])][:10], "databases": [c["statement"] for c in by_kind.get("cfg.database", [])][:6],
                  "locations": [c["statement"] for c in by_kind.get("cfg.location", [])], "com_model": [c["statement"] for c in by_kind.get("ext.com.model", [])],
                  "file_types": file_types[:60], "registry": [c["statement"] for c in by_kind.get("cfg.registry", [])][:4]}
    ext = {"plugins": [c["statement"] for c in by_kind.get("ext.plugins", [])][:10], "scripting": [c["statement"] for c in pick("stack.scripting")], "com": [c["statement"] for c in by_kind.get("ext.com", [])],
           "command_line": [c["statement"] for c in by_kind.get("ext.cli", [])], "protocols": [c["statement"] for c in by_kind.get("ext.protocol", [])], "published": [c["statement"] for c in by_kind.get("ext.published", []) + by_kind.get("ext.scripting.published", [])][:8]}
    proc = [c["statement"] for c in by_kind.get("arch.process", [])] + [c["statement"] for c in by_kind.get("arch.install", [])]
    web = {"kind": [c["statement"] for c in by_kind.get("web.kind", [])], "language": [c["statement"] for c in by_kind.get("web.language", [])], "source": [c["statement"] for c in by_kind.get("web.source", [])],
           "layout": [c["statement"] for c in by_kind.get("web.layout", []) + by_kind.get("web.modules", [])], "design": [c["statement"] for c in by_kind.get("arch.design", [])],
           "features": [c["statement"] for c in by_kind.get("web.feature", [])][:10], "platform": [c["statement"] for c in by_kind.get("web.platform", [])]}
    behavior: Dict[str, Any] = {}
    try:
        tr = model.transitions(app_key)
        behavior["transitions"] = len(tr)
    except Exception:
        pass
    n_rev = sum(1 for m in measured.values() if m["reversible"])
    behavior["gestures_measured"] = len(measured)
    behavior["gestures_reversible"] = n_rev
    gaps: List[str] = []
    if not ui.get("commands"):
        gaps.append("no commands known yet (run the 'fast' tier or higher on a window of this program)")
    if not gest:
        gaps.append("no gestures measured (the 'deep' tier probes them; or the posted pointer is ignored by this program)")
    if any("IGNORED" in x for x in grammar["input_channels"]):
        gaps.append("this program ignores posted pointer input: its gestures could only be read from published keymaps, not verified live")
    if cl["kind"] == "unclassified":
        gaps.append("kind not classified: " + (cl.get("why") or "no evidence"))
    if not by_kind.get("web.source") and not by_kind.get("web.identity"):
        gaps.append("no public knowledge found (offline, not public, or the name is ambiguous)")
    if ui.get("dialogs") == [] or not ui.get("dialogs"):
        gaps.append("no dialog schema learned")
    prov = collections.Counter(c["trust_name"] for c in claims)
    return {"app_key": app_key, "built": time.time(), "identity": ident, "stack": stack_out, "process_model": proc, "ui_model": ui, "interaction_grammar": grammar, "data_model": data_model,
            "extensibility": ext, "public_knowledge": web, "behavior": behavior, "gaps": gaps, "provenance": dict(prov), "claims_total": len(claims)}


# --------------------------------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------------------------------

def _bul(items: List[str], limit: int = 12) -> str:
    return "\n".join(f"- {i}" for i in items[:limit]) + ("\n" if items else "_none learned_\n")


def render_markdown(am: Dict[str, Any]) -> str:
    i = am["identity"]
    L: List[str] = [f"# {i.get('product') or am['app_key']} -- how it works", ""]
    L.append(f"**Identity.** {i.get('summary') or am['app_key']}")
    if i.get("public_description"):
        L.append(f"\n**Public description.** {i['public_description']}")
    if i.get("kind") != "unclassified":
        L.append(f"\n**Kind.** {i['kind_label']} (confidence {i['kind_confidence']})")
    else:
        L.append(f"\n**Kind.** not classified ({i.get('kind_note', '')})")
    for cand in i.get("kind_candidates", [])[:3]:
        L.append(f"  - {cand['label']} score {cand['score']}: " + "; ".join(cand["evidence"][:3]))
    L += ["", "## Stack (what it is built from)"]
    for area, items in sorted(am["stack"].items()):
        if area.endswith("api") or not items:
            continue
        L.append(f"- **{area}**: " + " | ".join(items[:5]))
    L += ["", "## Process model", _bul(am["process_model"], 8)]
    ui = am["ui_model"]
    L += ["## User interface model", f"- commands: {ui.get('commands', 0)} ({ui.get('by_kind', {})}); verified by a probe: {ui.get('verified_commands', 0)}; with shortcut: {ui.get('with_shortcut', 0)}",
          f"- menus: {', '.join(ui.get('menus', [])[:20]) or 'n/a'}", f"- dialogs learned: {len(ui.get('dialogs', []))}: " + ", ".join(d['title'] for d in ui.get('dialogs', [])[:12]),
          f"- modes (state variables): " + ", ".join(f"{v['name']}={v['values'][:4]}" for v in ui.get('state_variables', [])[:8]),
          f"- on-screen labels read by OCR: {ui.get('labels_seen', 0)}; controls that react to the pointer: {ui.get('widgets_interactive', 0)}; published shortcuts: {ui.get('published_shortcuts', 0)}", ""]
    if ui.get("tooltips"):
        L += ["### Tooltips (the program describing its own controls)", _bul(ui["tooltips"], 10)]
    if ui.get("blind_menus"):
        L += ["### Menus read from the screen", _bul(ui["blind_menus"], 8)]
    g = am["interaction_grammar"]
    L += ["## Interaction grammar (how the pointer drives it)"]
    for ch in g["input_channels"]:
        L.append(f"- **input channel:** {ch}")
    for m in g["measured"]:
        extra = ", ".join(f"{k}={v}" for k, v in m["params"].items() if k not in ("items",))
        L.append(f"- measured: `{m['gesture']}` on a {m['region_kind']} -> **{m['effect']}**" + (f" ({extra})" if extra else "") + ("" if m["reversible"] in (True, None) else " [NOT reversible]"))
    if g["n_shipped"]:
        L.append(f"\nPublished (shipped) pointer bindings: {g['n_shipped']}; examples:")
        L.append(_bul(g["shipped_pointer_bindings"], 14))
    d = am["data_model"]
    L += ["", "## Data model and persistence", "### Where it keeps state", _bul(d["locations"], 5), "### Config schema (key names)", _bul(d["config_schema"], 5),
          "### Databases", _bul(d["databases"], 4), "### Object model (COM)", _bul(d["com_model"], 3), f"### File types\n{', '.join(d['file_types'][:40]) or '_unknown_'}", ""]
    e = am["extensibility"]
    L += ["## Extensibility", "### Plugins / modules", _bul(e["plugins"], 6), "### Scripting", _bul(e["scripting"], 6), "### COM automation", _bul(e["com"], 3), "### Command line", _bul(e["command_line"], 2), "### URL protocols", _bul(e["protocols"], 3)]
    p = am["public_knowledge"]
    if any(p.values()):
        L += ["## Public knowledge (published sources)", "- " + "\n- ".join((p["kind"] + p["language"] + p["platform"] + p["source"] + p["design"])[:12]), "", "### Source layout", _bul(p["layout"], 4)]
    L += ["## Behaviour", f"- transitions learned: {am['behavior'].get('transitions', 0)}; gestures measured: {am['behavior'].get('gestures_measured', 0)} (reversible: {am['behavior'].get('gestures_reversible', 0)})", "",
          "## What is NOT known (honest gaps)", _bul(am["gaps"], 20), "## Provenance", f"claims by trust class: {am['provenance']} (measured > static > published > inferred)"]
    return "\n".join(L)


def write_report(app_key: str, am: Dict[str, Any], store: Optional[C.AtlasStore] = None) -> Dict[str, str]:
    d = C.ensure_dir(os.path.join(C.REPORT_DIR, app_key))
    jp, mp = os.path.join(d, "model.json"), os.path.join(d, "report.md")
    with open(jp, "w", encoding="utf-8") as fh:
        json.dump(am, fh, indent=1, default=str)
    with open(mp, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(am))
    return {"json": jp, "markdown": mp}
