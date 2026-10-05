"""
si_tests_knowledge.py -- suite tests for the app-knowledge engine (pe_resources, static_knowledge, knowledge_store,
command_registry, knowledge_bridge, organ_63_app_mastery) and the backlog items it closes (1.1 pure input, 3.1 template-first,
3.3 transitions, 3.6 launch honesty, 6.4 two-success rule).

Offline tests need no desktop. Live tests drive REAL apps in fresh windows that this module opens and closes itself, never reuse
or touch a window the user already had, and report ENV-BLOCKED (never a fake pass) when the app is not available.
Every function receives the suite's TestOutcome dataclass.
"""

import ast
import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import shutil
import struct
import sys
import tempfile
import time
import uuid
from typing import Any, Dict, List

os.environ.setdefault("HOJAIGA_WEBAPP_WATCH", "0")


def _tmpdb() -> str:
    return os.path.join(tempfile.gettempdir(), "hj_kn_" + uuid.uuid4().hex[:8] + ".db")


def _rm_db(path: str) -> None:
    for suf in ("", "-wal", "-shm"):
        try:
            os.remove(path + suf)
        except Exception:
            pass


def _model():
    from core_organs import organ_48_app_behavior_model as bm
    p = _tmpdb()
    return bm.BehaviorModel(p), p


def _verdict(TestOutcome, checks: Dict[str, bool], extra: str = "", metrics: Dict[str, Any] = None, env: bool = False):
    ok = all(checks.values())
    ev = "; ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in checks.items()) + (f" | {extra}" if extra else "")
    m = {"checks": f"{sum(1 for v in checks.values() if v)}/{len(checks)}"}
    m.update(metrics or {})
    return TestOutcome(passed=ok, evidence=ev, metrics=m)


# ============================================================================================================== KP1

def run_kp1(TestOutcome):
    """KP1: the PE resource reader agrees with WINDOWS' OWN menu loader on every menu resource, and static knowledge of a real
    classic program is complete and honest (command IDs, accelerators, context menus, toolkit, no false help text)"""
    from core_organs import pe_resources as pr
    from core_organs import static_knowledge as sk
    reg = r"C:\Windows\regedit.exe"
    mmc = r"C:\Windows\System32\mmc.exe"
    tm = r"C:\Windows\System32\taskmgr.exe"
    nps = r"C:\Windows\System32\notepad.exe"
    cands = [p for p in (reg, mmc, tm) if os.path.isfile(p)]
    if not cands:
        return TestOutcome(passed=False, env_blocked=True, evidence="no classic resource-bearing system programs on this host")
    u32 = ctypes.WinDLL("user32", use_last_error=True)         # private handle: never mutate the shared windll prototypes
    u32.LoadMenuIndirectW.restype = ctypes.c_void_p
    u32.LoadMenuIndirectW.argtypes = [ctypes.c_void_p]
    u32.GetSubMenu.restype = ctypes.c_void_p
    u32.GetSubMenu.argtypes = [ctypes.c_void_p, ctypes.c_int]
    u32.GetMenuItemCount.argtypes = [ctypes.c_void_p]
    u32.GetMenuItemID.argtypes = [ctypes.c_void_p, ctypes.c_int]
    u32.GetMenuStringW.argtypes = [ctypes.c_void_p, wt.UINT, ctypes.c_wchar_p, ctypes.c_int, wt.UINT]
    u32.DestroyMenu.argtypes = [ctypes.c_void_p]

    def live_walk(hm):
        out = []
        for i in range(u32.GetMenuItemCount(hm)):
            buf = ctypes.create_unicode_buffer(300)
            u32.GetMenuStringW(hm, i, buf, 299, 0x400)
            sub = u32.GetSubMenu(hm, i)
            mid = u32.GetMenuItemID(hm, i)
            out.append({"text": buf.value, "id": 0 if sub else (mid & 0xFFFFFFFF if mid != 0xFFFFFFFF else 0),
                        "children": live_walk(sub) if sub else []})
        return out

    def norm(items):
        o = []
        for it in items:
            sep = (not it["text"]) and not it["children"]
            o.append(("-" if sep else it["text"], 0 if (sep or it["children"]) else it["id"], norm(it["children"])))
        return o
    total = bad = 0
    for exe in cands:
        for src in [exe] + pr._mui_candidates(exe):
            mod = pr._Module(src)
            if not mod.h:
                continue
            try:
                for name in mod.names(pr.RT_MENU):
                    raw = mod.data(pr.RT_MENU, name)
                    buf = ctypes.create_string_buffer(raw, len(raw))
                    hm = u32.LoadMenuIndirectW(ctypes.addressof(buf))
                    if not hm:
                        continue
                    total += 1
                    if norm(pr.parse_menu(raw)) != norm(live_walk(hm)):
                        bad += 1
                    u32.DestroyMenu(hm)
            finally:
                mod.close()
    checks: Dict[str, bool] = {f"windows-oracle({total} menus, {bad} mismatches)": total >= 10 and bad == 0}
    t0 = time.perf_counter()
    d = sk.harvest(reg) if os.path.isfile(reg) else {"ok": False, "commands": []}
    ms = (time.perf_counter() - t0) * 1000
    cmds = d.get("commands", [])
    if d.get("ok"):
        withid = [c for c in cmds if c["menu_id"]]
        checks[f"regedit commands>=20 ({len(cmds)})"] = len(cmds) >= 20
        checks["every wm_command has its numeric ID"] = all(c["menu_id"] for c in cmds if c["verb"] == "wm_command") and len(withid) >= 15
        checks["accelerators joined by command ID"] = any(c["shortcut"] for c in cmds)
        helps = sum(1 for c in cmds if c.get("help"))
        checks[f"MFC-style prompts joined ({helps}/{len(cmds)})"] = helps / max(len(cmds), 1) >= 0.6
        checks["context menus found statically"] = d["menu_structure"]["contexts"] >= 1
        checks["toolkit: native Win32, not a sibling-file false positive"] = bool(d["frameworks"]) and d["frameworks"][0]["id"] == "win32_native" \
            and not any(f["id"] in ("chromium", "electron", "mfc") for f in d["frameworks"])
        checks["shared system dir is not scanned for siblings"] = d.get("shared_install_dir") is True
        checks["elevation request known (HITL)"] = d["requires_elevation"] == (d["manifest"].get("execution_level") in ("highestAvailable", "requireAdministrator"))
        checks[f"static harvest fast ({ms:.0f} ms < 1500)"] = ms < 1500
    if os.path.isfile(nps):
        dn = sk.harvest(nps)
        checks["no false help text where string IDs merely collide with command IDs"] = not any("%" in (c.get("help") or "") for c in dn.get("commands", []))
    big = r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE"
    if os.path.isfile(big):
        t0 = time.perf_counter()
        info = pr.pe_info(big)
        checks[f"pe_info seeks (a {info.get('size', 0) // 2**20} MB exe in {(time.perf_counter() - t0) * 1000:.0f} ms, {len(info.get('imports', []))} imports)"] = \
            info.get("ok") and len(info.get("imports", [])) > 10 and (time.perf_counter() - t0) < 1.0
    return _verdict(TestOutcome, checks, metrics={"menus_compared": total, "static_ms": round(ms)})


# ============================================================================================================== KP2

def _make_asar(path: str, files: Dict[str, bytes]) -> None:
    meta, off, blob = {"files": {}}, 0, b""
    for name, data in files.items():
        meta["files"][name] = {"size": len(data), "offset": str(off)}
        blob += data
        off += len(data)
    js = json.dumps(meta).encode()
    padded = js + b"\0" * ((4 - len(js) % 4) % 4)
    payload = struct.pack("<I", len(js)) + padded
    header_pickle = struct.pack("<I", len(payload)) + payload
    with open(path, "wb") as fh:
        fh.write(struct.pack("<I", 4) + struct.pack("<I", len(header_pickle)) + header_pickle + blob)


def run_kp2(TestOutcome):
    """KP2: shipped data sources are found by SHAPE (toolkit files, Electron asar package.json, keymap / manifest-'contributes' /
    settings files) in a synthetic install that uses no real app name, and ingested at catalog trust only"""
    from core_organs import static_knowledge as sk
    src_exe = r"C:\Windows\System32\notepad.exe"
    if not os.path.isfile(src_exe):
        return TestOutcome(passed=False, env_blocked=True, evidence="no stub exe to build the synthetic install from")
    tmp = tempfile.mkdtemp(prefix="hj_kp2_")
    mdl, dbp = _model()
    try:
        exe = os.path.join(tmp, "Zorblax.exe")
        shutil.copy(src_exe, exe)
        os.makedirs(os.path.join(tmp, "resources"))
        _make_asar(os.path.join(tmp, "resources", "app.asar"),
                   {"package.json": json.dumps({"name": "zorblax", "productName": "Zorblax", "main": "main.js", "version": "9.9",
                                               "dependencies": {"left-pad": "1", "electron-store": "2"}}).encode()})
        open(os.path.join(tmp, "chrome_100_percent.pak"), "wb").close()
        open(os.path.join(tmp, "Qt6Core.dll"), "wb").close()
        os.makedirs(os.path.join(tmp, "extensions", "ext-a"))
        with open(os.path.join(tmp, "extensions", "ext-a", "package.json"), "w", encoding="utf-8") as fh:
            json.dump({"name": "ext-a", "contributes": {
                "commands": [{"command": "zb.frobnicate", "title": "Frobnicate", "category": "Zorb"},
                             {"command": "zb.splat", "title": "Splat the Widget"}],
                "keybindings": [{"command": "zb.frobnicate", "key": "ctrl+alt+f"}]}}, fh)
        with open(os.path.join(tmp, "keybindings.json"), "w", encoding="utf-8") as fh:
            json.dump([{"key": "ctrl+shift+z", "command": "zb.redoThing"}, {"key": "f7", "command": "zb.checkSpelling"}], fh)
        with open(os.path.join(tmp, "settings.json"), "w", encoding="utf-8") as fh:
            json.dump({"editor": {"wordWrap": True, "minimap": False}, "name": "x"}, fh)
        d = sk.harvest(exe)
        ids = [f["id"] for f in d.get("frameworks", [])]
        names = {c["name"] for c in d.get("commands", [])}
        by = {c["name"]: c for c in d.get("commands", [])}
        src = d.get("install_sources", {})
        rep = sk.ingest(mdl, "zorblax", d)
        rows = [dict(r) for r in mdl._conn.execute("SELECT source, origin FROM bm_commands WHERE app_key='zorblax'")]
        from core_organs import knowledge_store as ks
        checks = {
            "toolkits by file shape (electron+chromium+qt)": {"electron", "chromium", "qt"} <= set(ids),
            "electron package.json read out of app.asar": (src.get("electron_package") or {}).get("name") == "zorblax",
            "manifest 'contributes' commands + category": "Zorb: Frobnicate" in names and "Splat the Widget" in names,
            "contributes keybinding joined to its command": by.get("Zorb: Frobnicate", {}).get("shortcut") == "ctrl+alt+f",
            "keybindings.json parsed": {"zb.redoThing", "zb.checkSpelling"} <= names,
            "settings toggles found (2 booleans, no values stored)": src.get("settings_toggles") == 2,
            "shipped command lists are DEMOTED hints (archetype trust, origin preload:*), never learned or catalog (P2-J)":
                bool(rows) and all(r["source"] == "archetype" and (r["origin"] or "").startswith("preload:") for r in rows),
            "facts stored with a source": bool(ks.get_fact(mdl, "zorblax", "frameworks")) and bool(ks.get_fact(mdl, "zorblax", "strategy")),
            "toolkit strategy says UIA after-wake": (d.get("strategy") or {}).get("uia") == "after-wake",
        }
        return _verdict(TestOutcome, checks, extra=f"toolkits={ids[:4]}, commands={len(names)}, ingested={rep['commands']}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        mdl.close()
        _rm_db(dbp)


# ============================================================================================================== KS1

def run_ks1(TestOutcome):
    """KS1: one command map per app: rows from independent sources merge and corroborate, E2 stays out of lookups, routes follow how
    the app accepts input, the frontier persists across versions, and the dossier names its own gaps"""
    from core_organs import command_registry as cr
    from core_organs import knowledge_store as ks
    mdl, dbp = _model()
    try:
        k = "kpad"
        # the SAME command described by three independent sources
        mdl.upsert_command(k, {"name": "Save As...", "menu_path": "File > Save As...", "menu_id": 4, "shortcut": "ctrl+shift+s", "verb": "wm_command"},
                           source="catalog", origin="static:pe-menu-resource", evidence="help=Saves the document under a new name; alt=fa")
        mdl.upsert_command(k, {"name": "Save as", "menu_path": "File > Save as", "shortcut": "ctrl+shift+s", "verb": "invoke"},
                           source="catalog", origin="e0:uia-expandcollapse")
        mdl.upsert_command(k, {"name": "Save As", "verb": "invoke"}, source="catalog", origin="layout:menubar")
        mdl.upsert_command(k, {"name": "Delete", "menu_path": "Edit > Delete", "verb": "invoke"}, source="catalog", origin="e0:uia-expandcollapse")
        mdl.upsert_command(k, {"name": "Bold (Ctrl+B)", "verb": "invoke"}, source="catalog", origin="layout:toolbar")
        mdl.upsert_command(k, {"name": "Open...", "menu_path": "File > Open...", "menu_id": 2, "verb": "wm_command"}, source="catalog", origin="static:pe-menu-resource",
                           evidence="help=Opens a file; alt=fo")
        # the SAME row described by a second source (identical name/path/shortcut): provenance must keep BOTH, evidence must not be wiped
        mdl.upsert_command(k, {"name": "Open...", "menu_path": "File > Open...", "menu_id": 2, "verb": "wm_command"}, source="catalog", origin="e0:win32-hmenu")
        reg = cr.build(mdl, k)
        sa = [c for c in reg if cr.canon(c["name"]) == "save as" and c["kind"] == "menu"]
        hit = cr.lookup(mdl, k, "save as", registry=reg)
        hit_del = cr.lookup(mdl, k, "save the file", registry=reg)
        ks.put_fact(mdl, k, "strategy", {"native_menus": True, "uia": "good"}, source="static")
        r_native = cr.routes_for(mdl, k, sa[0])
        ks.put_fact(mdl, k, "key_delivery", {"status": "not-delivered"}, source="live")
        r_nokey = cr.routes_for(mdl, k, sa[0])
        ks.put_fact(mdl, k, "key_delivery", {"status": "works"}, source="live")
        r_key = cr.routes_for(mdl, k, sa[0])
        # frontier persistence
        f1 = ks.frontier_add(mdl, k, "tab", "Insert", "Ribbon > Insert", version_hash="v1")
        ks.frontier_done(mdl, f1, "explored", {"x": 1}, "r1")
        again = ks.frontier_add(mdl, k, "tab", "Insert", "Ribbon > Insert", version_hash="v1")
        st1 = ks.frontier_stats(mdl, k)
        ks.frontier_add(mdl, k, "tab", "Insert", "Ribbon > Insert", version_hash="v2")      # app updated: everything reopens
        st2 = ks.frontier_stats(mdl, k)
        ks.put_statevar(mdl, k, "v1", "Word wrap", "toggle", ["on"])
        ks.put_statevar(mdl, k, "v1", "Word wrap", "toggle", ["off"])
        sv = ks.statevars(mdl, k)
        dos = cr.dossier(mdl, k)
        bold = [c for c in reg if "bold" in cr.canon(c["name"])]
        opn = [c for c in reg if cr.canon(c["name"]) == "open"]
        checks = {
            "three sources of one command merge into ONE entry": len(sa) == 1 and sa[0]["corroborated"] >= 2,
            "sources listed": set(sa[0]["sources"]) >= {"static", "menus_live"} if sa else False,
            "shortcut agreement counted": sa[0]["shortcut"] == "ctrl+shift+s" and sa[0]["shortcut_agreement"] >= 2 if sa else False,
            "help text + mnemonic chain kept from the static row": "new name" in sa[0]["help"] and sa[0]["access_chain"] == "fa" if sa else False,
            "lookup ranks it first": bool(hit) and cr.canon(hit[0]["name"]) == "save as" and hit[0]["coverage"] == 1.0,
            "destructive command never offered for a save goal": not any(cr.canon(h["name"]) == "delete" for h in hit_del),
            "chord embedded in a label is extracted": bold and bold[0]["shortcut"] == "ctrl+b",
            "same-row sources are both kept (provenance) and earlier help survives": bool(opn) and {"static", "menus_live"} <= set(opn[0]["sources"])
            and opn[0]["corroborated"] >= 2 and "opens a file" in opn[0]["help"].lower(),
            "native toolkit: WM_COMMAND id is route #1": r_native and r_native[0]["effector"] == "wm_command",
            "keys proven not delivered: no key route": not any(r["effector"] == "key" for r in r_nokey),
            "keys proven delivered: key route first": r_key and r_key[0]["effector"] == "key",
            "explored frontier node stays closed on a re-scan": again == f1 and st1["by_status"].get("explored") == 1,
            "a new app version reopens the frontier": st2["by_status"].get("open") == 1,
            "state variable values accumulate": sv and sorted(sv[0]["values"]) == ["off", "on"],
            "dossier lists its own gaps": any("not explored yet" in g or "no dialog schema" in g for g in dos["gaps"]),
        }
        return _verdict(TestOutcome, checks, extra=f"{len(reg)} unified from 6 rows; gaps={len(dos['gaps'])}")
    finally:
        mdl.close()
        _rm_db(dbp)


# ============================================================================================================== KB1

def run_kb1(TestOutcome):
    """KB1: scan knowledge reaches the loop only through gates: direct control needs >= 2 verified successes (6.4: one lucky trace
    never enables muscle memory), a postcondition, full goal coverage, a non-destructive class; organ_47's step memory obeys the same rule"""
    from core_organs import knowledge_bridge as kb
    from core_organs import command_registry as cr
    from core_organs import desktop_grounding as dg
    from core_organs.organ_47_app_intelligence import AppIntelligence
    mdl, dbp = _model()
    idb = _tmpdb()
    old_db = _tmpdb()
    try:
        br = kb.KnowledgeBridge(mdl)
        k = "gatepad"
        post = [{"kind": "window_opened", "title_contains": "save"}]
        mdl.upsert_command(k, {"name": "Find", "goal": "find", "menu_path": "Edit > Find", "verb": "invoke", "risk": "E1", "post": post, "menu_id": 20},
                           source="catalog", origin="e0:uia")
        c = mdl.commands(k)[0]["cmd_id"]
        ks_ = __import__("core_organs.knowledge_store", fromlist=["x"])
        ks_.put_fact(mdl, k, "strategy", {"native_menus": True}, source="static")

        def case(successes: int, failures: int = 0, risk: str = "E1", has_post: bool = True, goal: str = "find"):
            mdl._conn.execute("UPDATE bm_commands SET successes=?, failures=?, risk=?, post_json=?, opaque=?, source=?, confidence=0.85 WHERE cmd_id=?",
                              (successes, failures, risk, json.dumps(post if has_post else []), 0 if has_post else 1,
                               "learned" if successes else "catalog", c))
            mdl._conn.commit()
            br._bust(k)
            got = br.consult(k, goal)
            return (br.direct_ok(got, goal) if got else (False, "no consult")), got
        (one, _w1), g1 = case(1)
        (two, _w2), g2 = case(2)
        (e2, _w3), _ = case(3, risk="E2")
        (nop, _w4), _ = case(3, has_post=False)
        (cov, _w5), _ = case(3, goal="find the word in the document")
        (fail, _w6), _ = case(2, failures=2)
        typing, _ = br.consult(k, "type hello", wants_text=True), None
        # 4.2: a keyboard accelerator DECLARED by two sources + proven delivery is a verified attempt; one source is not
        ks_.put_fact(mdl, k, "key_delivery", {"status": "works"}, source="live")
        mdl._conn.execute("UPDATE bm_commands SET shortcut='ctrl+f', successes=0, failures=0, source='catalog', risk='E1' WHERE cmd_id=?", (c,))
        mdl.upsert_command(k, {"name": "Find", "goal": "find", "menu_path": "Edit > Find", "shortcut": "ctrl+f", "verb": "wm_command", "menu_id": 20},
                           source="catalog", origin="static:pe-menu-resource")
        mdl._conn.commit()
        br._bust(k)
        acc_two = br.consult(k, "find")
        acc_ok = br.accelerator_ok(acc_two, "find") if acc_two else (False, "no consult")
        mdl._conn.execute("DELETE FROM bm_commands WHERE app_key=? AND origin='static:pe-menu-resource'", (k,))
        mdl._conn.commit()
        br._bust(k)
        acc_one = br.consult(k, "find")
        acc_no = br.accelerator_ok(acc_one, "find") if acc_one else (False, "no consult")
        ks_.put_fact(mdl, k, "key_delivery", {"status": "not-delivered"}, source="live")
        br._bust(k)
        acc_nokey = br.accelerator_ok(br.consult(k, "find"), "find")
        # organ_47: successes counter + migration
        intel = AppIntelligence(db_path=idb)
        intel.record_step("gatepad", "save", "key", shortcut="ctrl+s", element_role="shortcut", outcome="PASS", source="learned")
        s1 = intel.playbook("gatepad", "save", allow_llm_briefing=False).hints[0]
        intel.record_step("gatepad", "save", "key", shortcut="ctrl+s", element_role="shortcut", outcome="PASS", source="learned")
        s2 = intel.playbook("gatepad", "save", allow_llm_briefing=False).hints[0]
        intel.record_step("gatepad", "save", "key", shortcut="ctrl+s", element_role="shortcut", outcome="FAIL", source="learned")
        s3 = intel.playbook("gatepad", "save", allow_llm_briefing=False).hints[0]
        loop = dg.DesktopAutonomyLoop()
        loop.intel = intel
        cons1 = None
        for _ in range(1):
            # one verified success: hint, never a direct shortcut
            fresh = AppIntelligence(db_path=_tmpdb())
            fresh.record_step("gatepad2", "print", "key", shortcut="ctrl+p", element_role="shortcut", outcome="PASS", source="learned")
            loop.intel = fresh
            cons1 = loop._consult_intel("gatepad2", "print")
            fresh.record_step("gatepad2", "print", "key", shortcut="ctrl+p", element_role="shortcut", outcome="PASS", source="learned")
            loop.intel = fresh
            cons2 = loop._consult_intel("gatepad2", "print")
            fresh.close()
        # a database from BEFORE the counter existed: a PASS row keeps exactly one verification
        import sqlite3
        raw = sqlite3.connect(old_db)
        raw.executescript("""CREATE TABLE steps (step_id TEXT PRIMARY KEY, app_key TEXT, goal TEXT, verb TEXT, element_name TEXT, element_role TEXT,
            shortcut TEXT, menu_path TEXT, fingerprint TEXT, outcome TEXT, source TEXT, confidence REAL DEFAULT 0.5, hits INTEGER DEFAULT 0, ts REAL);
            CREATE TABLE apps (app_key TEXT PRIMARY KEY, display_name TEXT, exe_path TEXT, version TEXT, archetype TEXT, source TEXT, confidence REAL DEFAULT 0.5,
            successes INTEGER DEFAULT 0, failures INTEGER DEFAULT 0, first_seen REAL, last_seen REAL, meta_json TEXT DEFAULT '{}');
            CREATE TABLE briefings (app_key TEXT PRIMARY KEY, briefing_json TEXT, source TEXT, ts REAL);
            INSERT INTO steps VALUES ('a:1','a','new','key','','','ctrl+n','','fp','PASS','learned',0.85,3,0);""")
        raw.commit()
        raw.close()
        mig = AppIntelligence(db_path=old_db)
        mrow = mig._conn.execute("SELECT successes FROM steps WHERE step_id='a:1'").fetchone()
        mig.close()
        checks = {
            "bridge: 1 verified success is NOT direct control": one is False,
            "bridge: 2 verified successes + postcondition + full coverage IS": two is True,
            "bridge: destructive class (E2) is never direct": e2 is False,
            "bridge: no machine-checkable postcondition is never direct": nop is False,
            "bridge: label covering only part of the goal is not direct": cov is False,
            "bridge: failures outweighing successes revoke it": fail is False,
            "bridge: a typing goal is not a command goal": typing is None,
            "4.2: accelerator declared by 2 sources + proven key delivery = a verified ATTEMPT": acc_ok[0] is True,
            "4.2: an accelerator from one source only is not": acc_no[0] is False,
            "4.2: keys not delivered on this app: no accelerator rung": acc_nokey[0] is False,
            "organ_47: successes counts verified PASSes (1 then 2)": s1.successes == 1 and s2.successes == 2,
            "organ_47: a failure takes one verification away": s3.successes == 1,
            "loop: ONE pass of a learned shortcut stays a judge hint": cons1 is not None and cons1["kind"] == "element",
            "loop: TWO passes allow the direct shortcut": cons2 is not None and cons2["kind"] == "shortcut",
            "migration: an old PASS row keeps one verification, not two": mrow is not None and mrow["successes"] == 1,
        }
        return _verdict(TestOutcome, checks)
    finally:
        mdl.close()
        for p in (dbp, idb, old_db):
            _rm_db(p)


# ============================================================================================================== INF1

def run_inf1(TestOutcome):
    """INF1: what an app IS is inferred from evidence (file types it opens + the vocabulary of its own labels), not from its name:
    right on clear evidence, honestly 'unclassified' on thin or single-keyword evidence (a calculator is not a media player because
    its converter lists 'Volume')"""
    from core_organs import static_knowledge as sk
    editor = sk.infer_profile(labels=["File > New", "File > Open...", "File > Save", "File > Save As...", "Edit > Find...", "Edit > Replace...",
                                      "Edit > Undo", "Format > Word Wrap", "Format > Font..."], exts=[".txt", ".log", ".ini", ".md"])
    calc = sk.infer_profile(labels=["Memory add", "Clear entry", "Open Navigation", "Open history flyout", "Scientific Calculator",
                                    "Standard Calculator", "Programmer Calculator", "Volume Converter", "Length Converter"], exts=[])
    browser = sk.infer_profile(labels=["New tab", "Bookmarks", "Downloads", "Address bar"], exts=[".html", ".htm", ".mhtml", ".pdf"])
    player = sk.infer_profile(labels=["Play", "Pause", "Playlist", "Next track"], exts=[".mp3", ".flac", ".mp4", ".mkv"])
    paint = sk.infer_profile(labels=["Brush", "Eraser", "Layers", "Filters", "Crop", "Resize"], exts=[".png", ".jpg", ".bmp"])
    thin = sk.infer_profile(labels=["Play"], exts=[])
    bare = sk.infer_profile(labels=[], exts=[])
    sheet = sk.infer_profile(labels=["Formulas", "Chart", "Pivot", "Sort"], exts=[".xlsx", ".xls", ".csv"])
    viewer = sk.infer_profile(labels=["File > Open...", "File > Save...", "File > Print...", "File > Exit", "Edit > Copy", "Edit > Select All",
                                      "Edit > Find", "View > Refresh"], exts=[".nfo"])
    checks = {
        "text editor from labels + .txt/.log": editor["archetype"] == "text_editor",
        "calculator is not a media player": calc["archetype"] != "media_player" and "media_transport" not in calc["capabilities"],
        "browser from .html + tabs/bookmarks": browser["archetype"] == "browser",
        "media player from audio/video types + transport words": player["archetype"] == "media_player",
        "raster editor from image types + tools": paint["archetype"] == "raster_editor",
        "spreadsheet-like labels + types -> office": sheet["archetype"] == "office_doc",
        "one keyword is not enough": thin["archetype"] == "unclassified",
        "no evidence stays unclassified": bare["archetype"] == "unclassified",
        "shared file verbs + one .nfo type is not a text editor": viewer["archetype"] == "unclassified",
        "'Open Navigation' is not 'open a file'": "open" not in calc["capabilities"],
        "an embedded chord is not part of the label": "save" in sk.infer_profile(labels=["Save (Ctrl+S)"], exts=[])["capabilities"],
    }
    return _verdict(TestOutcome, checks, extra=f"editor={editor['archetype']} calc={calc['archetype']} browser={browser['archetype']} player={player['archetype']}")


# ============================================================================================================== B2N

def run_b2n(TestOutcome):
    """B2N: an invented app name fails at launch with a reason: the fuzzy resolver may never map it onto a real app and start THAT
    (it once launched Excel), and a crash-relaunch checks the executable first"""
    from core_organs import desktop_grounding as dg
    from core_organs import organ_40_app_launcher as o40
    called: List[str] = []
    real = o40.resolve_and_launch
    o40.resolve_and_launch = lambda *a, **k: (called.append(str(a)), {"launched": True})[1]
    try:
        class _G:
            def find_window(self, name):
                return 0

        class _Loop:
            grounding = _G()
            _launch_note = ""
        lp = _Loop()
        invented = "zzqx frobnicator pro " + uuid.uuid4().hex[:6]
        t0 = time.perf_counter()
        launched = dg._launch_if_missing(lp, invented)
        dt = time.perf_counter() - t0
        ok_res, why = dg._fallback_resolution_ok(invented)
        real_ok, _ = dg._fallback_resolution_ok("notepad")
    finally:
        o40.resolve_and_launch = real
    checks = {
        "invented name: nothing launched": launched is False,
        "invented name: the fuzzy resolver was never invoked": called == [],
        "reported with a reason": "no installed app resolves" in lp._launch_note,
        "no retry storm (answered in < 20 s)": dt < 20.0,
        "a real app still resolves": bool(real_ok),
    }
    return _verdict(TestOutcome, checks, extra=f"{dt:.1f}s; note={lp._launch_note[:90]!r}")


# ============================================================================================================== PURE1

_PHYS_ATTRS = {"SetCursorPos", "mouse_event", "keybd_event", "SendInput"}
_PAG_CALLS = {"click", "moveTo", "press", "hotkey", "write", "typewrite", "keyDown", "keyUp", "mouseDown", "mouseUp", "drag", "dragTo", "scroll",
              "doubleClick", "rightClick", "moveRel", "tripleClick", "middleClick", "hscroll", "vscroll"}


def run_pure1(TestOutcome):
    """PURE1: no first-party source file reaches for a physical-input API (SetCursorPos / mouse_event / keybd_event / SendInput /
    pyautogui actions). Read from the AST, so comments and docstrings cannot hide or fake it; the only exceptions are the test files
    that call those APIs on purpose to prove the process-wide guard REFUSES them. 1.1: the code paths were deleted, not skipped"""
    from core_organs import headless_input as hin
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    hits: Dict[str, List[str]] = {}
    scanned = 0
    for dp, dn, fn in os.walk(os.path.join(root, "All codes")):
        dn[:] = [d for d in dn if d not in ("__pycache__", "_archive", ".git", "node_modules")]
        for f in fn:
            if not f.endswith(".py") or f.startswith(("si_test", "run_system_intelligence", "debug_", "test_")):
                continue
            p = os.path.join(dp, f)
            if "core_organs" not in dp:
                continue
            try:
                tree = ast.parse(open(p, encoding="utf-8", errors="replace").read())
            except SyntaxError:
                continue                            # an unparsable file is reported by the import-health test, not here
            scanned += 1
            for n in ast.walk(tree):
                if isinstance(n, ast.Attribute):
                    if n.attr in _PHYS_ATTRS or (n.attr in _PAG_CALLS and isinstance(n.value, ast.Name) and n.value.id in ("pyautogui", "pag", "pg")):
                        hits.setdefault(f, []).append(f"{n.lineno}:{n.attr}")
    n0 = len(hin.VIOLATIONS)
    try:
        ctypes.windll.user32.SetCursorPos(5, 5)                 # a third-party-style call: the guard must refuse it
    except Exception:
        pass
    refused = len(hin.VIOLATIONS) == n0 + 1
    env_escape = "HOJAIGA_ALLOW_PHYSICAL_INPUT" in open(os.path.join(here, "headless_input.py"), encoding="utf-8").read().replace("no opt-out", "")
    checks = {
        f"no physical-input API in {scanned} first-party source files": not hits,
        "the process-wide guard still refuses a physical call": refused,
        "no environment opt-out exists any more": not env_escape or "os.environ.get(\"HOJAIGA_ALLOW_PHYSICAL_INPUT\")" not in open(os.path.join(here, "headless_input.py"), encoding="utf-8").read(),
    }
    return _verdict(TestOutcome, checks, extra=("offenders: " + json.dumps(hits)[:300]) if hits else "", metrics={"files_scanned": scanned})


# ============================================================================================================== live helpers

def _top_titles(sub: str) -> List[int]:
    from core_organs import headless_input as hin
    return [h for h, t in hin.top_level_titles(False) if sub in (t or "").lower() or sub in hin._class_name(h).lower()]


def _user_has(app_sub: str) -> str:
    """The title of a window of this app the USER already has open ('' when none)."""
    from core_organs import headless_input as hin
    for h, t in hin.top_level_titles(False):
        if app_sub in (t or "").lower():
            return t
    return ""


# ============================================================================================================== KM1

def run_km1(TestOutcome):
    """KM1: mastery learns an app across runs, invisibly, and the knowledge is TRUE: run 1 builds the command map + state transitions,
    run 2 continues from the persisted frontier and adds more, an independent UIA walk of the live window finds (almost) every named
    control already known, the physical pointer is untouched and the app is closed afterwards"""
    from core_organs import organ_63_app_mastery as am
    from core_organs import organ_48_app_behavior_model as bm
    from core_organs import universal_scan as us
    from core_organs import command_registry as cr
    from core_organs import desktop_grounding as dg
    from core_organs import headless_input as hin
    from core_organs import background_window as bw
    import knowledge_bench as kbn
    if _user_has("calculator"):
        return TestOutcome(passed=False, env_blocked=True, evidence="ENV-BLOCKED: the user's Calculator window is open; not touched")
    mdl, dbp = _model()
    v0 = len(hin.VIOLATIONS)
    p0 = ctypes.wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(p0))
    try:
        t0 = time.time()
        r1 = am.master("calculator", model=mdl, budget_s=40, runs=1, close_if_launched=False, conventions=False)
        run1 = r1["runs"][0]
        if run1.get("error"):
            return TestOutcome(passed=False, env_blocked=True, evidence=f"ENV-BLOCKED: Calculator could not be driven here ({run1['error']})")
        hwnd = dg.DesktopGrounding().find_window("calculator") or 0
        key = bm._app_key("calculator")
        recall, gt_n, missed = None, 0, []
        if hwnd:
            from core_organs import background_window as bw2
            with bw2.BackgroundSession(hwnd):
                time.sleep(0.8)
                gt = kbn.ground_truth(hwnd)
            lay = [dict(r) for r in mdl._conn.execute("SELECT name FROM bm_layout WHERE app_key=?", (key,))] if am._count(mdl._conn, "bm_layout", key) else []
            known = {(r["name"] or "").strip().lower() for r in lay if r["name"]}
            for c in cr.build(mdl, key):
                for n in c["names"]:
                    known.add(n.strip().lower())
            hit = [n for n in gt if n in known]
            gt_n = len(gt)
            recall = len(hit) / gt_n if gt_n else None
            missed = [n for n in gt if n not in known][:5]
            us.close_window(hwnd, discard_unsaved=True, timeout_s=8)
        r2 = am.master("calculator", model=mdl, budget_s=40, runs=1, conventions=False)
        run2 = r2["runs"][0] if r2["runs"] else {}
        k1, k2 = run1.get("known", {}), run2.get("known", {})
        fr1, fr2 = (k1.get("frontier") or {}), (k2.get("frontier") or {})
        left = _top_titles("calculator")
        p1 = ctypes.wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(p1))
        gain2 = sum(max(0, v) for kk, v in (run2.get("gain") or {}).items() if kk in ("commands", "dialogs", "regions", "statevars", "transitions"))
        checks = {
            "static facts before launch (toolkit + strategy)": bool(k1.get("facts", 0) >= 8),
            f"run 1 built a command map ({k1.get('commands')} commands)": (k1.get("commands") or 0) >= 25,
            f"run 1 recorded state transitions ({k1.get('transitions')})": (k1.get("transitions") or 0) >= 1,
            f"run 1 explored something ({fr1.get('by_status', {})})": (fr1.get("by_status") or {}).get("explored", 0) >= 1,
            f"run 2 continued and learned more (+{gain2}, explored {fr1.get('explored_n')} -> {fr2.get('explored_n')})": gain2 >= 1 and (fr2.get("explored_n") or 0) >= (fr1.get("explored_n") or 0),
            f"independent UIA walk: {gt_n} named controls, recall {recall if recall is None else round(recall, 2)}": recall is not None and recall >= 0.85,
            "no physical input reached the OS (guard violations)": len(hin.VIOLATIONS) == v0,
            "the user's pointer did not move": (p0.x, p0.y) == (p1.x, p1.y),
            "the app was closed afterwards": not left,
        }
        return _verdict(TestOutcome, checks, extra=f"missed={missed}; {time.time() - t0:.0f}s",
                        metrics={"run1_commands": k1.get("commands"), "run2_commands": k2.get("commands"), "transitions": k2.get("transitions"),
                                 "recall": None if recall is None else round(recall, 3)})
    finally:
        try:
            h = dg.DesktopGrounding().find_window("calculator") or 0
            if h:
                us.close_window(h, discard_unsaved=True, timeout_s=6)
        except Exception:
            pass
        mdl.close()
        _rm_db(dbp)


# ============================================================================================================== KC1

def run_kc1(TestOutcome):
    """KC1: a context menu is discovered headless (posted WM_CONTEXTMENU to the child window under the target; measured ~0.4 s on a
    XAML host), its items become commands, and it is CLOSED again (WM_CLOSE: a posted Escape is not delivered to XAML) with the app
    left exactly as found; a dropdown is expanded, read and collapsed the same way"""
    from core_organs import universal_scan as us
    from core_organs import background_window as bw
    from core_organs import organ_63_app_mastery as am
    from core_organs import organ_48_app_behavior_model as bm
    from core_organs import knowledge_store as ks
    from core_organs import fast_uia
    if _user_has("notepad"):
        return TestOutcome(passed=False, env_blocked=True, evidence="ENV-BLOCKED: the user's Notepad window is open; not touched")
    mdl, dbp = _model()
    li = us.launch_hidden("notepad")
    hwnd = li.get("hwnd", 0)
    if not hwnd:
        _rm_db(dbp)
        return TestOutcome(passed=False, env_blocked=True, evidence="ENV-BLOCKED: Notepad could not be launched hidden")
    try:
        key = "notepad"
        with bw.BackgroundSession(hwnd):
            time.sleep(1.0)
            us.wake_accessibility(hwnd)
            fast_uia.wait_ready(hwnd, 12)
            main, extra = am._snap_all(hwnd)
            before_ops = am._op_names(main + extra)
            pop0 = list(bm._open_popups(hwnd))
            am.populate_frontier(mdl, key, hwnd, main, "t")
            ctx = [r for r in ks.frontier_open(mdl, key, limit=50) if r["kind"] == "context"]
            exp = [r for r in ks.frontier_open(mdl, key, limit=50) if r["kind"] == "expander"]
            pr = am.Prober(mdl, key, hwnd, pristine=False)
            res_ctx = pr.run(ctx[0]) if ctx else None
            res_exp = pr.run(exp[0]) if exp else None
            main2, extra2 = am._snap_all(hwnd)
            restored = am._op_names(main2 + extra2) == before_ops and bm._open_popups(hwnd) == pop0
            cmds = [dict(r) for r in mdl._conn.execute("SELECT name, origin, evidence FROM bm_commands WHERE app_key=?", (key,))]
        ctx_items = [c for c in cmds if c["origin"] == "e1:context-menu"]
        checks = {
            "a context-menu target was found in the live tree": bool(ctx),
            f"context menu opened headless with items ({res_ctx.items if res_ctx else 0})": bool(res_ctx and res_ctx.status == "explored" and res_ctx.items >= 3),
            "its items are stored as context commands": len(ctx_items) >= 3,
            "context menu closed again (unwound)": bool(res_ctx and res_ctx.unwound),
            "dropdown expanded + read + collapsed (or none on this build)": (res_exp is None) or (res_exp.status in ("explored", "no_effect") and res_exp.unwound),
            "app left exactly as found (structure + popups)": restored,
        }
        return _verdict(TestOutcome, checks, extra=f"ctx via {res_ctx.effector if res_ctx else '-'}: {[c['name'] for c in ctx_items][:5]}; expander={res_exp.label if res_exp else 'n/a'}")
    finally:
        us.close_window(hwnd, discard_unsaved=True, timeout_s=8)
        mdl.close()
        _rm_db(dbp)


# ============================================================================================================== KT1

def run_kt1(TestOutcome):
    """KT1: the free-form loop USES and FEEDS the knowledge: a VERIFIED command (>= 2 successes) runs as a direct route with the
    verifier judging it (trace tagged knowledge:direct); the verified step becomes a (state, action, effector) -> (state', evidence)
    transition and reinforces the command (3.3); an unverified command only ranks the judge's shortlist"""
    from core_organs import desktop_grounding as dg
    from core_organs import universal_scan as us
    from core_organs import knowledge_bridge as kb
    from core_organs import organ_48_app_behavior_model as bm
    if _user_has("calculator"):
        return TestOutcome(passed=False, env_blocked=True, evidence="ENV-BLOCKED: the user's Calculator window is open; not touched")
    mdl, dbp = _model()
    key = "calculator"
    post = [{"kind": "ui_changed"}]
    mdl.upsert_command(key, {"name": "Seven", "goal": "seven", "verb": "invoke", "risk": "E1", "post": post}, source="catalog", origin="e1:mastery")
    cid = mdl.commands(key)[0]["cmd_id"]
    for _ in range(2):
        mdl.command_outcome(cid, "PASS", "seeded for KT1", promote=True)
    prep = dg.prepare_app("calculator")
    hwnd = prep.get("hwnd", 0)
    if not hwnd:
        mdl.close()
        _rm_db(dbp)
        return TestOutcome(passed=False, env_blocked=True, evidence=f"ENV-BLOCKED: Calculator not ready ({prep.get('ready_reason')})")
    loop = dg.get_loop()
    saved = loop.bridge
    loop.bridge = kb.KnowledgeBridge(mdl)
    try:
        loop._goal_fails = {}
        r = loop.step("Seven", "calculator")
        trace = loop.trace[-1] if loop.trace else None
        c_after = mdl.commands(key)[0]
        trans = mdl._conn.execute("SELECT COUNT(*) c FROM bm_transitions WHERE app_key=?", (key,)).fetchone()["c"]
        eff = mdl.effector_coverage(key)
        # an UNverified command must only be a hint
        mdl2, p2 = _model()
        mdl2.upsert_command(key, {"name": "Seven", "goal": "seven", "verb": "invoke", "risk": "E1", "post": post}, source="catalog", origin="e1:mastery")
        loop.bridge = kb.KnowledgeBridge(mdl2)
        loop._goal_fails = {}
        r2 = loop.step("Seven", "calculator")
        trace2 = loop.trace[-1] if loop.trace else None
        direct2 = bool(trace2 and "knowledge:direct" in (trace2.evidence or ""))
        mdl2.close()
        _rm_db(p2)
        checks = {
            "a verified command ran as a DIRECT route (knowledge:direct)": bool(trace and "knowledge:direct" in (trace.evidence or "")),
            "the verifier judged it PASS": bool(trace and trace.verdict == "PASS"),
            "the command was reinforced (successes 2 -> 3)": c_after["successes"] >= 3,
            f"a transition was recorded ({trans})": trans >= 1,
            "the effector outcome was recorded": bool(eff),
            "an UNverified command did not take direct control": not direct2,
        }
        return _verdict(TestOutcome, checks, extra=f"route={trace.method if trace else '-'}; effectors={eff}")
    finally:
        loop.bridge = saved
        try:
            us.close_window(hwnd, discard_unsaved=True, timeout_s=6)
        except Exception:
            pass
        mdl.close()
        _rm_db(dbp)


# ============================================================================================================== KM2

def run_km2(TestOutcome):
    """KM2: a command that needs a MODE is never fired in the wrong one (3.2): the bridge evaluates the learned precondition, walks the
    learned mode graph (Tab -> edit mode) to repair it, fires nothing when no path exists, and costs nothing for commands without one.
    Logic-level on a scripted app (no 3D application is installed: TG1 stays ENV-BLOCKED)"""
    from core_organs import knowledge_bridge as kb
    from core_organs import organ_48_app_behavior_model as bm
    mdl, dbp = _model()
    fake = {"mode": "object"}
    performed: List[str] = []
    real_observe, real_perform = bm.observe, bm.EffectorLadder.perform

    def fake_observe(hwnd, **kw):
        names = ["add cube", "object"] if fake["mode"] == "object" else ["vertex select", "edit"]
        return bm.ObservedState(title="fakecad", names=names, hwnd=hwnd)

    def fake_perform(self, app_key, hwnd, action, avoid=None):
        performed.append(action.get("keys") or action.get("name") or "?")
        if action.get("keys") == "tab":
            fake["mode"] = "edit" if fake["mode"] == "object" else "object"
        return True, "key", "scripted"
    bm.observe, bm.EffectorLadder.perform = fake_observe, fake_perform
    try:
        pack = {"schema": bm.PACK_SCHEMA, "app": "fakecad", "trust": "catalog",
                "modes": [{"name": "object", "indicator": [{"kind": "element_present", "name": "add cube"}]},
                          {"name": "edit", "indicator": [{"kind": "element_present", "name": "vertex select"}]}],
                "commands": [{"name": "Toggle Edit Mode", "shortcut": "tab", "verb": "key", "risk": "E1",
                              "pre": [{"kind": "mode_is", "mode": "object"}], "post": [{"kind": "mode_is", "mode": "edit"}]},
                             {"name": "Toggle Object Mode", "shortcut": "tab", "verb": "key", "risk": "E1",
                              "pre": [{"kind": "mode_is", "mode": "edit"}], "post": [{"kind": "mode_is", "mode": "object"}]},
                             {"name": "Extrude", "shortcut": "e", "verb": "key", "risk": "E1",
                              "pre": [{"kind": "mode_is", "mode": "edit"}], "post": [{"kind": "ocr_number_increase"}]},
                             {"name": "Add Cube", "verb": "invoke", "risk": "E1", "post": [{"kind": "ui_changed"}]}]}
        loaded = mdl.load_pack(pack)
        br = kb.KnowledgeBridge(mdl)
        g_wrong = br.precheck("fakecad", "Extrude", 0)                  # object mode: must repair via Tab
        mode_after = fake["mode"]
        n_repair = len(performed)
        g_right = br.precheck("fakecad", "Extrude", 0)                  # already in edit mode: nothing to repair
        no_extra = len(performed) == n_repair
        g_none = br.precheck("fakecad", "Add Cube", 0)                  # no precondition: None, no observation cost
        # without the learned path the command must be REFUSED and nothing fired
        mdl._conn.execute("DELETE FROM bm_commands WHERE app_key='fakecad' AND name LIKE 'Toggle%'")
        mdl._conn.commit()
        fake["mode"] = "object"
        before = len(performed)
        g_nopath = br.precheck("fakecad", "Extrude", 0)
        checks = {
            "pack with modes + pre/post loaded": bool(loaded.get("loaded")),
            "wrong mode: repaired through the learned graph (Tab)": bool(g_wrong and g_wrong["ok"] and g_wrong["repaired"] == ["Toggle Edit Mode"]),
            "the app really ended in the required mode": mode_after == "edit",
            "right mode: nothing fired": bool(g_right and g_right["ok"]) and no_extra,
            "a command without preconditions costs nothing (None)": g_none is None,
            "no path to the mode: REFUSED, nothing fired": bool(g_nopath and not g_nopath["ok"]) and len(performed) == before and "no learned path" in g_nopath["why"],
        }
        return _verdict(TestOutcome, checks, extra=f"performed={performed}")
    finally:
        bm.observe, bm.EffectorLadder.perform = real_observe, real_perform
        mdl.close()
        _rm_db(dbp)


# ============================================================================================================== TF1

def run_tf1(TestOutcome):
    """TF1: the FREE-FORM path (execute_task's loop-first preamble) tries a learned template BEFORE any goal planning (3.1): with a
    matching template the app run completes via the template (chain: 'no LLM planning') and run_loop_first is never called; with none,
    the verified loop runs as before"""
    from core_organs import task_lifecycle as tl
    from core_organs import loop_first as lf
    from core_organs import desktop_grounding as dg
    from core_organs import organ_48_app_behavior_model as bm
    mdl, dbp = _model()
    run_calls: List[str] = []
    real_rlf, real_prep, real_run, real_gm = lf.run_loop_first, dg.prepare_app, bm.TemplateRunner.run, bm.get_model
    try:
        tpl = {"name": "type text and save as file", "aliases": ["type and save", "write text then save"],
               "steps": [{"id": "t", "goal": "type {text}", "do": [{"verb": "type", "text": "{text}"}], "post": [{"kind": "ui_changed"}]},
                         {"id": "s", "goal": "save as {path}", "do": [{"verb": "key", "keys": "ctrl+shift+s"}], "post": [{"kind": "ui_changed"}]}]}
        mdl.upsert_template("zpad", tpl, source="learned")
        lf.run_loop_first = lambda *a, **k: (run_calls.append("loop"), lf.LoopFirstResult(ran=True, reason="loop"))[1]
        dg.prepare_app = lambda app, **k: {"ready": True, "hwnd": 0, "launched": False}
        bm.TemplateRunner.run = lambda self, app, task, params=None, **k: {"matched": True, "completed": True, "leaves": [{"step_id": "t"}, {"step_id": "s"}],
                                                                       "template": "type text and save as file"}
        bm.get_model = lambda: mdl
        cmd = "open zpad, type hello world and save it as D:/tmp/out.txt"
        ch = tl.Chain()
        res = tl.try_template_first(cmd, [("zpad", cmd.index("zpad"))], mdl, "run_tf1", ch)
        tf = [i for i in ch.items if i["id"] == "A3.template"]
        # a ticket nothing covers falls through to the verified loop
        ch2 = tl.Chain()
        c2 = "open zpad and press the big red button"
        res2 = tl.try_template_first(c2, [("zpad", c2.index("zpad"))], mdl, "run_tf1b", ch2)
        # two apps: templates cover one app only
        c3 = "open zpad and zbar, type hi"
        res3 = tl.try_template_first(c3, [("zpad", c3.index("zpad")), ("zbar", c3.index("zbar"))], mdl, "run_tf1c", tl.Chain())
        checks = {
            "template-first completed the app run": bool(res is not None and res.runs and res.runs[0].status == "COMPLETED" and res.all_completed),
            "the run is tagged as the template path": bool(res is not None and res.runs[0].result.get("via") == "template"),
            "the chain says: no LLM planning": any("no LLM planning" in i["evidence"] for i in tf if i["status"] == "PASS"),
            "the free-form loop was NOT consulted": run_calls == [],
            "every goal of the plan counts as verified": bool(res is not None and all(v == "PASS" for v in res.runs[0].goal_verdicts)),
            "a ticket no template covers returns None (loop runs)": res2 is None,
            "two-app tickets are not template-run": res3 is None,
        }
        return _verdict(TestOutcome, checks, extra=(tf[-1]["evidence"][:120] if tf else ""))
    finally:
        lf.run_loop_first, dg.prepare_app, bm.TemplateRunner.run, bm.get_model = real_rlf, real_prep, real_run, real_gm
        mdl.close()
        _rm_db(dbp)


# ============================================================================================================== DAY2

def run_day2(TestOutcome):
    """DAY2: the unattended day survives a KILLED process: tickets already done are never redone, the cut-off ticket is retried once, a
    destructive ticket waits for a human, a hung ticket times out, a raising ticket fails, a false 'DONE' is caught by the independent
    check - and the report equals the ground truth of what actually executed (6.1 / 6.2 / 6.3)"""
    import subprocess
    from core_organs import day_runner as dr
    from core_organs import organ_48_app_behavior_model as bm
    tmp = tempfile.mkdtemp(prefix="hj_day2_")
    dbp = os.path.join(tmp, "day.db")
    counter = os.path.join(tmp, "executed.txt")
    tasks = [{"id": "a", "task": "write the weekly report"}, {"id": "b", "task": "open the spreadsheet and add a column"},
             {"id": "c", "task": "press the totals button"}, {"id": "d", "task": "delete all files in the downloads folder"},
             {"id": "e", "task": "summarize the notes"}, {"id": "f", "task": "send the invoice to the customer"},
             {"id": "g", "task": "export the chart"}, {"id": "h", "task": "rename the heading"}]
    tfile = os.path.join(tmp, "tasks.json")
    json.dump(tasks, open(tfile, "w", encoding="utf-8"))
    here = os.path.dirname(os.path.abspath(__file__))
    py = sys.executable
    env = dict(os.environ, HJ_DAY_COUNTER=counter, PYTHONPATH=os.pathsep.join([os.path.dirname(os.path.dirname(here)), os.path.dirname(here)]),
               PYTHONUTF8="1")
    cmd = [py, "-X", "utf8", os.path.join(here, "day_runner.py"), "run", tfile, "--run-id", "day2", "--budget", "3", "--db", dbp,
           "--executor", "core_organs.si_day_stub:executor", "--verify", "core_organs.si_day_stub:verify"]
    try:
        p1 = subprocess.run(cmd, env=dict(env, HJ_DAY_KILL_AT="b"), capture_output=True, text=True, timeout=120)
        m1 = bm.BehaviorModel(dbp)
        dr._ensure(m1)
        mid = {r["task_id"]: r["status"] for r in m1._conn.execute("SELECT task_id, status FROM bm_day_tickets WHERE run_id='day2'")}
        mid_counts = dr._counts(m1, "day2")
        m1.close()
        p2 = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
        m2 = bm.BehaviorModel(dbp)
        rep = dr.day_report(m2, "day2")
        row = {r["task_id"]: dict(r) for r in m2._conn.execute("SELECT * FROM bm_day_tickets WHERE run_id='day2'")}
        m2.close()
        ran: Dict[str, int] = {}
        for line in open(counter, encoding="utf-8"):
            if line.strip():
                ran[line.strip()] = ran.get(line.strip(), 0) + 1
        st = {k: v["status"] for k, v in row.items()}
        report_file = os.path.join(dr.REPORT_DIR, "day2.md")
        checks = {
            "run 1 really died mid-ticket (exit 9)": p1.returncode == 9,
            "at the kill: 'a' finished, 'b' was left RUNNING": mid.get("a") == "DONE" and mid.get("b") == "RUNNING",
            "run 2 completed the whole day": rep["complete"] and p2.returncode == 0,
            "finished tickets were NOT redone ('a' ran once)": ran.get("a") == 1,
            "the cut-off ticket was retried once ('b' ran twice) and finished": ran.get("b") == 2 and st.get("b") == "DONE" and row["b"]["attempts"] == 2,
            "destructive tickets never executed (d, f) and wait for a human": "d" not in ran and "f" not in ran and st.get("d") == "ESCALATED" and st.get("f") == "ESCALATED",
            "a raising ticket failed and the queue went on (c, then h)": st.get("c") == "FAILED" and st.get("h") == "DONE",
            "a hung ticket hit the watchdog (e)": st.get("e") == "TIMEOUT",
            "a false DONE was caught by the independent check (g)": st.get("g") == "FAILED" and "independent check failed" in row["g"]["reason"],
            "every executed ticket ran at most the allowed times": all(n <= 2 for n in ran.values()) and sorted(ran) == ["a", "b", "c", "e", "g", "h"],
            "report == ground truth: 3 done / 3 failed / 2 waiting": rep["capsule"] == "3 done / 3 failed / 2 waiting for you"
            and sorted(i["id"] for i in rep["done"]) == ["a", "b", "h"],
            "the report file was written": os.path.isfile(report_file),
        }
        return _verdict(TestOutcome, checks, extra=f"capsule={rep['capsule']!r}; executed={ran}; mid-kill={mid_counts}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ============================================================================================================== ORG1

_APP_NAME_RX = re.compile(r"""["'](notepad|calculator|calc|mspaint|paint|excel|winword|word|chrome|blender|vscode|visual studio|photoshop|steam|"""
                          r"""discord|whatsapp|obs|spotify|vlc|powerpoint|outlook|firefox|edge|gimp|krita|wordpad|antigravity)["']""", re.I)
ORGAN01_APP_NAME_LITERALS_MAX = 173          # the ratchet: measured 265 before backlog 2.3, 182 after the first two refactor steps. Only goes DOWN.


def run_org1(TestOutcome):
    """ORG1: the per-app hard-coding in organ_01 (backlog 2.3) only shrinks: a ratchet on quoted app-name literals, plus the structural
    facts of the refactor (one 'infrastructure window' helper replaced the copies of the IDE/browser/terminal title list; the per-app
    window matchers and the clean-slate reset go through the one window resolver)"""
    here = os.path.dirname(os.path.abspath(__file__))
    src = open(os.path.join(here, "organ_01_crewai_engine.py"), encoding="utf-8").read()
    n = len(_APP_NAME_RX.findall(src))
    host_lists = len(re.findall(r"for bad in \[\s*[\"']antigravity", src))
    checks = {
        f"app-name literals in organ_01 ({n}) <= ratchet {ORGAN01_APP_NAME_LITERALS_MAX}": n <= ORGAN01_APP_NAME_LITERALS_MAX,
        "no copy of the hard-coded IDE/browser/terminal title list is left": host_lists == 0,
        "one generic infrastructure-window helper exists": "def _is_infra_window(" in src and src.count("_is_infra_window(") >= 10,
        "clean-slate hygiene resets nothing per app (closes only windows the harness launched)": "def _clean_slate_app_hygiene" in src
        and "is_ours" in src.split("def _clean_slate_app_hygiene")[1].split("def _math_expr_to_button_sequence")[0]
        and "SetValue" not in src.split("def _clean_slate_app_hygiene")[1].split("def _math_expr_to_button_sequence")[0],
    }
    return _verdict(TestOutcome, checks, metrics={"app_name_literals": n, "ratchet": ORGAN01_APP_NAME_LITERALS_MAX})


# ============================================================================================================== DAY3

def run_day3(TestOutcome):
    """DAY3 (live, opt-in --day-live): the 'I'm gone all day' acceptance. 8 real tickets across 4 apps through the REAL lifecycle with no
    human: a destructive ticket waits for a human and is NOT executed, an invented app does not stall the queue, nothing is reported DONE
    that an independent read of the disk / the app does not confirm, every ticket ends with a status, and the capsule reads the truth (6.1)"""
    from core_organs import day_runner as dr
    from core_organs import organ_48_app_behavior_model as bm
    from core_organs import loop_first as lf
    from core_organs import universal_scan as us
    from core_organs import headless_input as hin
    for app in ("notepad", "calculator", "paint", "excel"):
        owned = _user_has(app)
        if owned:
            return TestOutcome(passed=False, env_blocked=True, evidence=f"ENV-BLOCKED: the user's {app} window is open ({owned[:30]!r}); not touched")
    tmp = os.path.join(r"D:\new_automation", "_day3_tmp_" + uuid.uuid4().hex[:5])
    os.makedirs(tmp, exist_ok=True)
    n1, n2 = os.path.join(tmp, "n1.txt"), os.path.join(tmp, "n2.txt")
    pp, xx = os.path.join(tmp, "p1.png"), os.path.join(tmp, "e1.xlsx")
    tasks = [
        {"id": "t1", "app": "notepad", "task": f"open notepad, type day one note and save it as {n1}"},
        {"id": "t2", "app": "calculator", "task": "open calculator and compute 6 * 7"},
        {"id": "t3", "app": "paint", "task": f"open paint and save the image as {pp}"},
        {"id": "t4", "app": "notepad", "task": f"delete the file {n1}"},
        {"id": "t5", "app": "frobnitz", "task": "open frobnitz studio and type hi"},
        {"id": "t6", "app": "excel", "task": f"open excel, type 42 in cell A1 and save it as {xx}"},
        {"id": "t7", "app": "notepad", "task": f"open notepad, type second note and save it as {n2}"},
        {"id": "t8", "app": "outlook", "task": "send the report to my boss by email"},
    ]

    def truth(tid: str) -> bool:
        """Independent ground truth: is the work really there?"""
        try:
            if tid == "t1":
                return os.path.exists(n1) and "day one note" in open(n1, errors="replace").read().lower()
            if tid == "t7":
                return os.path.exists(n2) and "second note" in open(n2, errors="replace").read().lower()
            if tid == "t3":
                return os.path.exists(pp) and open(pp, "rb").read(8) == b"\x89PNG\r\n\x1a\n"
            if tid == "t6":
                import zipfile
                if not os.path.exists(xx):
                    return False
                z = zipfile.ZipFile(xx)
                return any("42" in z.read(n).decode("utf-8", "replace") for n in z.namelist() if n.startswith("xl/worksheets/"))
            if tid == "t2":
                h = lf.handle_for("calculator")
                from core_organs import si_tests_fixes as sf
                return bool(h and "42" in " ".join(sf._names_in(h)))
        except Exception:
            return False
        return False

    vlog: Dict[str, bool] = {}

    def verify(task, res):
        ok = truth(task["id"])
        vlog[task["id"]] = ok                                   # t2 (the calculator display) can only be read while the app is open
        return ok, ("independent read confirms the work" if ok else "independent read does NOT confirm the work")

    mdl, dbp = _model()
    caps: List[str] = []
    before_wins = set(h for h, _t in hin.top_level_titles(False))
    try:
        t0 = time.time()
        rep = dr.run_day(tasks, run_id="day3_" + uuid.uuid4().hex[:4], model=mdl, verify=verify, per_task_budget_s=420,
                         capsule_cb=lambda s, t: caps.append(t))
        elapsed = time.time() - t0
        st = {i["id"]: i["status"] for k in ("done", "failed", "waiting_for_you", "pending", "running") for i in rep[k]}
        reported_done = {k for k, v in st.items() if v == "DONE"}
        truly_done = {t["id"] for t in tasks if t["id"] not in ("t2",) and truth(t["id"])}
        t4_untouched = os.path.exists(n1) or "t1" not in reported_done        # the delete never ran (t1's file is still there when t1 made it)
        checks = {
            "every ticket ended with a status (none pending/running)": rep["complete"] and set(st) == {t["id"] for t in tasks},
            "nothing is reported DONE that the independent read does not confirm": all((truth(i) if i != "t2" else vlog.get("t2", False)) for i in reported_done),
            "the destructive ticket (t4) was queued for a human, not executed": st.get("t4") == "ESCALATED" and t4_untouched,
            "the outward-facing ticket (t8) waits for a human": st.get("t8") in ("ESCALATED",),
            "the invented app (t5) did not stall the day": st.get("t5") in ("FAILED", "ESCALATED") and "t7" in st,
            "the capsule text equals the report counts": rep["capsule"] == dr.capsule_text(mdl, rep["run_id"]) and bool(caps) and caps[-1] == rep["capsule"],
            "the report file exists": os.path.isfile(rep.get("report_file", "")),
            f"at least 3 tickets really completed ({sorted(reported_done)})": len(reported_done) >= 3,
        }
        return _verdict(TestOutcome, checks, extra=f"{elapsed:.0f}s; statuses={st}; capsule={rep['capsule']!r}",
                        metrics={"done": len(reported_done), "seconds": round(elapsed)})
    finally:
        try:
            for h, t in hin.top_level_titles(False):
                if h not in before_wins and any(s in (t or "").lower() for s in ("notepad", "calculator", "paint", "excel", "book")):
                    us.close_window(h, discard_unsaved=True, timeout_s=6)
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)
        mdl.close()
        _rm_db(dbp)


# ============================================================================================================== PRIV1

def run_priv1(TestOutcome):
    """PRIV1: the knowledge database is synced to a repository, so a UI label that names a PERSON ('Signed in as <name>') is stored
    without the person in every sink (commands, dialogs, regions, layout, frontier); the label is never pressed"""
    from core_organs import knowledge_store as ks
    from core_organs import organ_63_app_mastery as am
    mdl, dbp = _model()
    secret = "Zork Quimby"
    try:
        k = "privapp"
        mdl.upsert_command(k, {"name": f"Signed in as {secret}", "menu_path": f"Toolbar > Signed in as {secret}", "verb": "invoke"}, source="catalog", origin="e1:test")
        ks.put_dialog(mdl, k, f"Welcome back, {secret}", [{"kind": "button", "name": f"Signed in as {secret}"}, {"kind": "button", "name": "OK"}], source="live:test")
        mdl.record_region(k, f"Profile of {secret}", [{"name": f"Account: {secret}@mail.example", "type": "button"}], via="test")

        class N:                                                 # a minimal stand-in for a fast_uia node
            def __init__(self, i, name, ctype="ButtonControl", parent=-1):
                self.idx, self.name, self.ctype, self.parent = i, name, ctype, parent
                self.enabled, self.pats, self.rect, self.aid, self.cls = True, ["invoke"], (0, 0, 100, 30), "", ""
                self.toggle_state, self.selected, self.expand_state = -1, None, -1
        nodes = [N(0, "Window", "WindowControl"), N(1, f"Signed in as {secret}", parent=0), N(2, "Open settings", parent=0)]
        am.populate_frontier(mdl, k, 0, nodes, "v1")
        fr = [dict(r) for r in mdl._conn.execute("SELECT label, path, status FROM bm_frontier WHERE app_key=?", (k,))]
        blob = " | ".join(str(dict(r)) for t in ("bm_commands", "bm_dialogs", "bm_ui_regions", "bm_frontier")
                          for r in mdl._conn.execute(f"SELECT * FROM {t} WHERE app_key=?", (k,)))
        who = [f for f in fr if f["label"].startswith("Signed in as")]
        checks = {
            "redact keeps the phrase, drops the person": ks.redact(f"Signed in as {secret}") == "Signed in as <redacted>",
            "an ordinary label is untouched": ks.redact("Open settings") == "Open settings" and ks.redact("Sign in") == "Sign in",
            "no sink stored the name (commands, dialogs, regions, frontier)": secret not in blob and "Quimby" not in blob,
            "the account label is on the frontier as UNSAFE (never pressed)": bool(who) and who[0]["status"] == "unsafe",
            "an ordinary control is still explorable": any(f["label"] == "Open settings" and f["status"] == "open" for f in fr),
        }
        return _verdict(TestOutcome, checks)
    finally:
        mdl.close()
        _rm_db(dbp)


# ============================================================================================================== PTR1

def run_ptr1(TestOutcome):
    """PTR1: the pointer sentinel names WHO moved the mouse - a human hand or another process is ABORTED-ENV, this code is a FAIL, and a
    pointer failure that coincides with a real failure is never hidden (P0-C)"""
    from core_organs import pointer_sentinel as ps
    base = {"p0": (10, 10), "p1": (10, 10), "drift_px": 0, "moved": False, "guard_violations": 0, "hardware_events": 0,
            "injected_events": 0, "max_step_px": 0, "max_speed_px_ms": 0.0, "hook_ok": True}
    def rep(**kw):
        r = dict(base, **kw)
        r["cause"] = ps.classify(r)
        return r
    hand = rep(moved=True, drift_px=648, p1=(658, 10), max_step_px=648, hardware_events=37, max_speed_px_ms=64.8)
    foreign = rep(moved=True, drift_px=50, injected_events=3)
    ghost = rep(moved=True, drift_px=50)
    ours = rep(moved=True, drift_px=50, guard_violations=1, injected_events=1)
    ev_ptr_only = ("a=OK(x); physical-pointer-untouched-and-no-guard-violations=FAIL(pointer (409, 610)->(1031, 537), guard violations+=0, "
                   "largest 10 ms step=648px); total 108s")
    ev_km1 = "recall=OK; the user's pointer did not move=FAIL; the app was closed afterwards=OK | missed=[]"
    ev_mixed = "file-saved=FAIL(not on disk); physical-pointer-untouched=FAIL(moved)"
    # the real watcher: quiet for half a second in a test process (nobody is asked to touch the mouse for this check)
    live = ps.Sentinel().start()
    time.sleep(0.5)
    live.stop()
    lr = live.report()
    checks = {
        "no movement is classified 'still'": base and ps.classify(dict(base)) == "still",
        "hardware events = human-hand": hand["cause"] == "human-hand",
        "injected events from another process = foreign": foreign["cause"] == "foreign",
        "a move with no event and no guard call = unattributed": ghost["cause"] == "unattributed",
        "a guard-recorded physical call = ours-guard": ours["cause"] == "ours-guard",
        "pointer-only failure + human hand -> ABORTED-ENV": bool(ps.abort_if_env_only(ev_ptr_only, hand)),
        "KM1-style evidence (no parentheses) is recognised": bool(ps.abort_if_env_only(ev_km1, hand)),
        "pointer failure + injected foreign mover -> ABORTED-ENV": bool(ps.abort_if_env_only(ev_ptr_only, foreign)),
        "a pointer failure caused by THIS code stays a FAIL": ps.abort_if_env_only(ev_ptr_only, ours) is None,
        "a pointer failure next to a real failure is never hidden": ps.abort_if_env_only(ev_mixed, hand) is None,
        "the live low-level hook installed": bool(lr["hook_ok"]),
        "an unmoved pointer in the live probe reports no guard call": lr["guard_violations"] == 0,
    }
    return _verdict(TestOutcome, checks, extra=f"live probe: {ps.describe(lr)}")


# ============================================================================================================== ES2

def run_es2(TestOutcome):
    """ES2: every need-human record carries a REAL screenshot of what the agent saw: the D3 gate's queued irreversible step gets a PNG
    (decodes, non-zero, not one flat colour) attached to its queue row, for a visible window AND for a minimized one (P2-L / 4.1)"""
    from core_organs import task_lifecycle as tl
    from core_organs import loop_first as lf
    from core_organs import si_test_support as sup
    from core_organs import headless_input as hin
    mdl, dbp = _model()
    win = sup.NativeButtonWindow(title="HJ-ES2-App", button_text="Delete everything").start()
    made: List[str] = []
    try:
        if not win.hwnd:
            return TestOutcome(passed=False, env_blocked=True, evidence="could not create the fixture window")
        run_id = "es2_" + uuid.uuid4().hex[:6]
        plan = lf.AppPlan(app="hj-es2-app", goals=["open the file", "delete C:/hj_es2/keep.txt"], strength=["weak", "weak"])
        chain = tl.Chain()
        tl.gate_plans([plan], model=mdl, run_id=run_id, task="clean up", allow_destructive=False, unattended=True, chain=chain)
        queued_n = len(tl._QUEUED.get(run_id, []))
        done = tl.attach_queue_evidence(mdl, run_id, ["hj-es2-app"])
        row = (mdl.pending_queue() or [{}])[-1]
        ctx = json.loads(row.get("context_json") or "{}")
        p1 = ctx.get("screenshot", "")
        made.append(p1)

        def _png_ok(p):
            if not p or not os.path.exists(p) or os.path.getsize(p) < 1500:
                return False
            with open(p, "rb") as fh:
                if fh.read(8) != b"\x89PNG\r\n\x1a\n":
                    return False
            from PIL import Image
            with Image.open(p) as im:
                im.load()
                lo, hi = im.convert("L").getextrema()
            return hi > lo
        # the same window minimized (how Hojaiga holds an app): parked off-screen for the grab, then put back
        hin._u32.ShowWindow(win.hwnd, 7)
        time.sleep(0.6)
        shot2 = tl.capture_evidence("hj-es2-app", "minimized window")
        made.append(shot2.get("path", ""))
        still_min = bool(hin.is_minimized(win.hwnd))
        gone = tl.capture_evidence("no-such-app-hj-es2", "app gone")
        checks = {
            "the gate queued the irreversible step and kept the safe one": queued_n == 1 and plan.goals == ["open the file"],  # noqa
            "the queue row carries a screenshot path": bool(p1),
            "that file is a real PNG (decodes, non-zero, not one flat colour)": _png_ok(p1),
            "the row also records its size and what was captured": ctx.get("screenshot_bytes", 0) > 1500 and ctx.get("screenshot_title", "") != "",
            "a MINIMIZED window is captured too": _png_ok(shot2.get("path", "")),
            "the minimized window went back to minimized": still_min,
            "an app that is gone gives an honest empty record, never a fake file": gone.get("path", "") == "" and bool(gone.get("note")),
        }
        return _verdict(TestOutcome, checks, extra=f"shot={os.path.basename(p1)} {ctx.get('screenshot_bytes')} bytes; minimized={shot2.get('note')} {shot2.get('bytes')} bytes; gone={gone.get('note')!r}",
                        metrics={"png_bytes": ctx.get("screenshot_bytes")})
    finally:
        win.stop()
        mdl.close()
        _rm_db(dbp)
        for p in made:
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass


# ============================================================================================================== PRE1

def run_pre1(TestOutcome):
    """PRE1: the command lists an app ships (keymaps, plugin manifests, Python operator registries, request lists, a plugin's request-name
    table) are preloaded as DEMOTED hints (archetype trust, opaque, origin preload:*) and promoted ONLY when a live probe corroborates them
    (P2-J). Real install: the VS Code manifests; format fixtures: operator registry, protocol JSON, API string table"""
    from core_organs import preload_sources as pre
    from core_organs import organ_48_app_behavior_model as bm
    mdl, dbp = _model()
    root = tempfile.mkdtemp(prefix="hj_pre1_")
    try:
        # ---- format fixtures (no app names: just the formats)
        ops = "\n".join(f'class OT_{i}(Operator):\n    bl_idname = "grp{i % 7}.act_{i}"\n    bl_label = "Do Thing {i}"\n    bl_options = {{"REGISTER"}}\n' for i in range(60))
        os.makedirs(os.path.join(root, "scripts", "operators"))
        open(os.path.join(root, "scripts", "operators", "ops.py"), "w", encoding="utf-8").write(ops)
        proto = {"requests": [{"requestType": f"{v}Thing{i}", "description": f"does {v} on thing {i}"}
                              for i in range(12) for v in ("Get", "Set", "Start", "Stop", "Toggle")]}
        os.makedirs(os.path.join(root, "data"))
        open(os.path.join(root, "data", "protocol.json"), "w", encoding="utf-8").write(json.dumps(proto))
        names = [f"{v}Stream{k}" for k in ("Status", "Settings", "Service", "Output") for v in ("Get", "Set", "Start", "Stop", "Toggle", "Trigger", "Save", "Open")]
        os.makedirs(os.path.join(root, "plugins"))
        open(os.path.join(root, "plugins", "remote-control-plugin.dll"), "wb").write(b"MZ\x00\x00" + b"\x00".join(n.encode() for n in names) + b"\x00lonelyIdentifier\x00")
        rep = pre.scan(root)
        fmts = {s["format"]: s["found"] for s in rep["sources"]}
        n_total = len(rep["commands"])
        r = pre.ingest_preload(mdl, "fixtureapp", rep["commands"])
        rows = [dict(x) for x in mdl._conn.execute("SELECT * FROM bm_commands WHERE app_key=?", (bm._app_key("fixtureapp"),))]
        all_demoted = bool(rows) and all(x["source"] == "archetype" and x["opaque"] == 1 and (x["origin"] or "").startswith("preload:") for x in rows)
        # a preloaded command is never direct control; a live verified probe promotes exactly the corresponding one
        key = bm._app_key("fixtureapp")
        before_src = mdl.command_by_name(key, "Do Thing 3")["source"]
        promoted = pre.promote_if_probed(mdl, "fixtureapp", ["Do Thing 3", "Some Other Menu"], evidence="e1 probe: menu entry seen and effect verified")
        after = mdl.command_by_name(key, "Do Thing 3")
        untouched = mdl.command_by_name(key, "Do Thing 4")
        # ---- the real install (VS Code ships its manifests and keymap)
        real = r"C:\Users\dhruv\AppData\Local\Programs\Microsoft VS Code"
        real_n, real_demoted, real_note = None, None, "not installed on this machine"
        if os.path.isdir(real):
            m2, p2 = _model()
            try:
                rr = pre.preload_for(m2, "vscode-fixture", real, budget_s=8.0)
                rows2 = [dict(x) for x in m2._conn.execute("SELECT source, origin, opaque FROM bm_commands WHERE app_key=?", (bm._app_key("vscode-fixture"),))]
                real_n = len(rows2)
                real_demoted = bool(rows2) and all(x["source"] == "archetype" for x in rows2)
                real_note = f"{real_n} preloaded from {len(rr['sources'])} source file(s) in {rr['elapsed_s']}s"
            finally:
                m2.close()
                _rm_db(p2)
        checks = {
            "operator registry read (60 operators)": fmts.get("operator-registry") == 60,
            "request-list JSON read (60 requests)": fmts.get("protocol-json") == 60,
            "plugin request-name table read (32 names; the lone identifier is not an API)": fmts.get("api-strings") == 32,
            ">= 50 commands preloaded from shipped sources": n_total >= 50 and r["preloaded"] >= 50,
            "EVERY preloaded command is demoted (archetype, opaque, origin preload:*)": all_demoted,
            "a preloaded command is hint-only before evidence": before_src == "archetype",
            "a verified probe promotes exactly the matching command to learned": promoted == ["Do Thing 3"] and after["source"] == "learned",
            "a command nobody probed stays demoted": untouched["source"] == "archetype",
            "words of a request name read as a label ('StartRecord' -> 'Start Record')": pre.humanize("StartRecord") == "Start Record" and pre.humanize("object.mode_set") == "Object: Mode Set",
        }
        if real_n is not None:
            checks[f"the real install's shipped manifests give >= 50 demoted commands ({real_note})"] = bool(real_n >= 50 and real_demoted)
        return _verdict(TestOutcome, checks, extra=f"formats={fmts}; real={real_note}", metrics={"fixture_commands": n_total, "real_commands": real_n})
    finally:
        mdl.close()
        _rm_db(dbp)
        shutil.rmtree(root, ignore_errors=True)


# ============================================================================================================== CAP1

def run_cap1(TestOutcome):
    """CAP1: 'what is this app and how do I use it fully' is written from DATA in about a second: capabilities, how to drive it, every
    surface with what lives there and ONE task a live probe verified on it - and a surface with no verified task says so (P1-H)"""
    from core_organs import command_registry as cr
    from core_organs import knowledge_store as ks
    from core_organs import organ_48_app_behavior_model as bm
    mdl, dbp = _model()
    try:
        key = "capapp"
        ks.ensure(mdl)
        ks.put_fact(mdl, key, "version_info", {"FileDescription": "Capability fixture", "CompanyName": "Test"}, source="static", confidence=0.9)
        ks.put_fact(mdl, key, "profile", {"capabilities": ["edit_text", "save_file"], "ext_categories": {"text": 3}, "archetype": "text_editor"}, source="static", confidence=0.9)
        ks.put_fact(mdl, key, "strategy", {"native_menus": True, "posted_keys": "works"}, source="static", confidence=0.9)
        rows = [("Save", "File > Save", "ctrl+s"), ("Open", "File > Open", "ctrl+o"), ("Copy", "Edit > Copy", "ctrl+c"), ("Paste", "Edit > Paste", "ctrl+v"),
                ("Word wrap", "Format > Word wrap", ""), ("Zoom in", "View > Zoom in", "ctrl++")]
        ids = {}
        for name, path, sc in rows:
            ids[name] = mdl.upsert_command(key, {"name": name, "menu_path": path, "shortcut": sc, "verb": "menu"}, source="catalog", origin="e0:menu")
        for nm in ("Save", "Copy"):                                       # two surfaces get a verified (probe-promoted) task
            mdl.command_outcome(ids[nm], "PASS", evidence="e1 probe verified", promote=True)
        ks.put_dialog(mdl, key, "Save As", [{"kind": "edit", "name": "File name"}, {"kind": "button", "name": "Save"}], source="live:probe", via="File > Save as")
        t0 = time.time()
        d = cr.dossier(mdl, key)
        dt = time.time() - t0
        s = d.get("summary") or {}
        surf = {x["surface"]: x for x in s.get("surfaces", [])}
        checks = {
            "the summary was produced from data in under a second": dt < 1.0 and "error" not in s,
            "it says what the app is (description + archetype)": s.get("what_it_is") == "Capability fixture" and s.get("archetype") == "text_editor",
            "it lists the capabilities": s.get("capabilities") == ["edit_text", "save_file"],
            "every menu is a surface with its command count": surf.get("menu: File", {}).get("commands") == 2 and surf.get("menu: Edit", {}).get("commands") == 2,
            "a surface with a probe-verified task names it": (surf.get("menu: File", {}).get("verified_task") or {}).get("command") == "Save"
                                                          and (surf.get("menu: Edit", {}).get("verified_task") or {}).get("command") == "Copy",
            "a dialog seen open live is a verified surface": (surf.get("dialog: Save As", {}).get("verified_task") or {}).get("command") == "open 'Save As'",
            "a surface nobody exercised says so (no invented task)": surf.get("menu: Format", {}).get("verified_task") is None and surf.get("menu: View", {}).get("verified_task") is None,
            "coverage is reported honestly (3 of 5 surfaces verified)": s.get("coverage", {}).get("surfaces") == 5 and s.get("coverage", {}).get("with_verified_task") == 3,
            "how to drive it comes from the stored strategy": any("menu bar" in h for h in s.get("how_to_use", [])),
        }
        return _verdict(TestOutcome, checks, extra=f"{dt * 1000:.0f} ms; coverage={s.get('coverage')}")
    finally:
        mdl.close()
        _rm_db(dbp)


# ============================================================================================================== PV1

def run_pv1(TestOutcome):
    """PV1: a popup that exposes NOTHING (custom-drawn, no controls, no UIA children) is read through the DAP perception pipeline (capture
    + OCR with word boxes) and answered through the unchanged role policy: the safe button is pressed with a POSTED click, an elevation
    prompt in the same disguise is escalated and never pressed, zero physical input, zero per-dialog hardcodes (P2-M)"""
    from core_organs import si_test_support as sup
    from core_organs import popup_policy as pp
    from core_organs import headless_input as hin
    from core_organs import organ_24_dap as dap
    try:
        import pytesseract  # noqa: F401
    except Exception:
        return TestOutcome(passed=False, env_blocked=True, evidence="OCR backend (pytesseract / Tesseract) is not installed (environment)")
    v0 = len(hin.VIOLATIONS)
    novel = sup.PaintedDialog("Heads up", ["Try the new dashboard today.", "It only takes a minute."],
                              [("Allow access", (40, 150, 250, 205)), ("Not now", (290, 150, 500, 205))], sysmenu=False).start()
    uac = sup.PaintedDialog("Security", ["Do you want to allow this app", "to make changes to your device?"],
                            [("Yes", (40, 150, 250, 205)), ("No", (290, 150, 500, 205))], x=480, y=320).start()
    try:
        if not (novel.hwnd and uac.hwnd):
            return TestOutcome(passed=False, env_blocked=True, evidence="could not create the painted fixture windows")
        native_btns, _t = hin.native_dialog_parts(novel.hwnd)
        info = pp.inspect_dialog(novel.hwnd)
        names = [b[0].lower() for b in info.buttons]
        # DAP selector: ocr:'Not now' must come back with a BOX inside that button
        core = dap.DAPRuntimeCore()
        node = dap.Win32Provider().build_node(novel.hwnd, None)
        ocr_hits = dap.OCREngine().query(node, "Not now", dap.CaptureEngine())
        r = hin.wt.RECT()
        hin._u32.GetWindowRect(novel.hwnd, hin.ctypes.byref(r))
        bb = ocr_hits[0].bounds if ocr_hits else dap.Rect()
        l, t, rr, b = bb.left, bb.top, bb.right, bb.bottom
        in_btn = bool(ocr_hits) and (r.left + 290 <= (l + rr) // 2 <= r.left + 500 + 8) and (r.top + 150 <= (t + b) // 2 <= r.top + 205 + 40)
        d = pp.resolve_view(pp.PopupView(hwnd=novel.hwnd, title="Heads up", class_name=hin._class_name(novel.hwnd), kind="modal_window"),
                            db=False, key_sender=lambda *_a, **_k: False, mode="inflight", budget_s=8.0)
        time.sleep(0.6)
        d2 = pp.resolve_view(pp.PopupView(hwnd=uac.hwnd, title="Security", class_name=hin._class_name(uac.hwnd), kind="modal_window"),
                             db=False, key_sender=lambda *_a, **_k: False, mode="inflight", budget_s=8.0)
        time.sleep(0.6)
        checks = {
            "the dialog really exposes nothing (no Win32 push buttons)": not native_btns,
            "OCR through the DAP reader found both painted buttons by their captions": "not now" in names and "allow access" in names,
            "the message was read too (so escalation cues work)": "dashboard" in info.message.lower(),
            "the DAP 'ocr' selector returns a BOX on the 'Not now' button, not the whole window": in_btn,
            "the safe button was pressed (Not now), through the role policy": novel.result == "Not now" and d.handled and not d.need_human,
            "the 'Allow access' button was never pressed": novel.result != "Allow access" and novel.clicks == 1,
            "the answer was a POSTED click read by OCR (no pointer, no keyboard)": "ocr-click" in d.action and len(hin.VIOLATIONS) == v0,
            "the same disguise around an elevation prompt is ESCALATED, not answered": d2.need_human and not d2.handled and uac.clicks == 0 and uac.alive(),
        }
        return _verdict(TestOutcome, checks, extra=f"novel: action={d.action} tier={d.tier} {d.ms:.0f} ms buttons={names}; uac: action={d2.action} tier={d2.tier} note={d2.note!r}",
                        metrics={"novel_ms": d.ms})
    finally:
        novel.stop()
        uac.stop()


# ============================================================================================================== ACT1

def run_act1(TestOutcome):
    """ACT1: every action leaves through the DAP actuation backbone: the loop's _act_on_element routes into dap_actuator, the app FAMILY picks the
    ordered providers, the first that delivers wins and the per-provider trace is kept, a new app family is supported by REGISTERING a provider
    (never by a physical rung), and an action nothing can deliver is reported UNDELIVERABLE (P0 backbone)"""
    from core_organs import dap_actuator as da
    from core_organs import desktop_grounding as dg
    from core_organs import si_test_support as sup
    from core_organs import si_tests_fixes as sf
    from core_organs import headless_input as hin
    act = da.get_actuator()
    v0 = len(hin.VIOLATIONS)
    btn = sup.NativeButtonWindow(title="HJ-ACT1-Btn").start()
    ed = sf.EditorWindow("HJ-ACT1-Edit").start()
    created: List[Any] = []
    try:
        if not (btn.hwnd and ed.hwnd):
            return TestOutcome(passed=False, env_blocked=True, evidence="could not create the fixture windows")
        r = hin.wt.RECT()
        hin._u32.GetWindowRect(btn.btn_hwnd, hin.ctypes.byref(r))
        el_btn = dg.GroundedElement(id="b", name="ProbeBtn", role="button", bbox=(r.left, r.top, r.right, r.bottom), tier="win32", hwnd=btn.btn_hwnd)
        el_edit = dg.GroundedElement(id="e", name="edit", role="edit", bbox=(0, 0, 10, 10), tier="win32", hwnd=ed.edit)
        # 1. the loop's entry point goes THROUGH the actuator (counted by wrapping it)
        calls = []
        orig_act = act.act
        act.act = lambda elem, verb, text="": (calls.append((elem.name, verb)), orig_act(elem, verb, text))[1]
        try:
            c0 = btn.clicks
            ok, note = dg._act_on_element(el_btn, "click")
            time.sleep(0.4)
        finally:
            act.act = orig_act
        trace_click = [t["provider"] for t in act.last_trace]
        # 2. typing appends through the text provider
        ok2, note2 = act.act(el_edit, "type", "hello ")
        ok3, note3 = act.act(el_edit, "type", "world")
        time.sleep(0.3)
        text = ed.read_text()
        trace_type = [t["provider"] for t in act.last_trace]
        # 3. families are decided from what the window IS
        class _ChromeLike:
            """a top-level window whose CLASS is Chromium's: no tree, nothing else - the family must still be 'chromium'"""
        ch = _make_class_window("Chrome_WidgetWin_1", "HJ-ACT1-Chrome")
        created.append(ch)
        fam = {"classic": da.family_of(btn.hwnd), "chromium": da.family_of(ch)}
        el_ch = dg.GroundedElement(id="c", name="field", role="edit", bbox=(0, 0, 10, 10), tier="uia", hwnd=ch)
        ok4, note4 = act.act(el_ch, "type", "x")
        trace_ch = [t["provider"] for t in act.last_trace]
        note_ch = act.last_trace[0]["note"] if act.last_trace else ""
        # 4. a new family's way in is a REGISTERED provider, asked first
        class _Probe(da.Provider):
            name = "act1-probe"
            def applies(self, ctx):
                return ctx.verb == "click" and ctx.elem.name == "ProbeBtn"
            def act(self, ctx):
                return True, "act1-probe-delivered"
        act.register(_Probe(), families=["win32"], before="key")
        try:
            ok5, note5 = act.act(el_btn, "click")
        finally:
            da.LADDERS["win32"].remove("act1-probe")
            act.providers.pop("act1-probe", None)
        # 5. nothing can deliver -> honest, no physical fallback
        ghost = dg.GroundedElement(id="g", name="ghost", role="button", bbox=(0, 0, 4, 4), tier="win32", hwnd=0)
        ok6, note6 = act.act(ghost, "click")
        checks = {
            "_act_on_element routed into the DAP actuator": calls == [("ProbeBtn", "click")],
            "a classic button click was delivered (BN_CLICKED arrived)": ok and btn.clicks == c0 + 1,
            "the winning provider is recorded in the trace": trace_click[-1:] == ["message-click"] and all(t for t in trace_click),
            "typing appends through the text provider (two goals, one document)": ok2 and ok3 and text == "hello world" and trace_type[:1] == ["text-append"],
            "family is decided from the window class: classic vs chromium": fam == {"classic": "win32", "chromium": "chromium"},
            "a Chromium page control with no pattern is reported INEFFECTIVE by its provider (not a silent success)": trace_ch[:1] == ["chromium"] and "INEFFECTIVE" in note_ch,
            "a registered provider is asked first for its family": ok5 and note5 == "act1-probe-delivered",
            "an action nothing can deliver is UNDELIVERABLE": (not ok6) and hin.UNDELIVERABLE in note6,
            "there is no physical-input provider and the guard saw nothing": not [n for n in act.providers if any(w in n for w in ("physical", "sendinput", "cursor"))] and len(hin.VIOLATIONS) == v0,
        }
        return _verdict(TestOutcome, checks, extra=f"click trace={trace_click} type trace={trace_type} chromium trace={trace_ch} stats={act.stats}")
    finally:
        for h in created:
            hin._u32.PostMessageW(h, 0x0010, 0, 0)
        btn.stop()
        ed.stop()


def _make_class_window(class_name: str, title: str) -> int:
    """A top-level window of a given window CLASS (own thread + message loop), for family-detection checks. Returns its hwnd."""
    import threading
    from core_organs import si_test_support as sup
    out = {}
    ready = threading.Event()

    def _run():
        proc = sup.WNDPROC(lambda h, m, w, l: (sup.user32.PostQuitMessage(0) or 0) if m == sup.WM_DESTROY else sup.user32.DefWindowProcW(h, m, w, l))
        hinst = sup.kernel32.GetModuleHandleW(None)
        wc = sup._WNDCLASSW()
        wc.lpfnWndProc = proc
        wc.hInstance = hinst
        wc.lpszClassName = class_name
        wc.hbrBackground = 6
        sup.user32.RegisterClassW(ctypes.byref(wc))
        out["h"] = sup.user32.CreateWindowExW(0x08000000, class_name, title, sup.WS_OVERLAPPEDWINDOW, 700, 500, 300, 200, None, None, hinst, None) or 0
        ready.set()
        msg = wt.MSG()
        while sup.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            sup.user32.TranslateMessage(ctypes.byref(msg))
            sup.user32.DispatchMessageW(ctypes.byref(msg))
    threading.Thread(target=_run, daemon=True).start()
    ready.wait(5)
    return int(out.get("h", 0))


# ============================================================================================================== RANK1

def run_rank1(TestOutcome):
    """RANK1: the loop's element ranking encodes what a person would do, measured on synthetic screens: window chrome and account controls are
    never a step, 'save ... as <path>' goes File -> Save As -> Browse, an off-screen command is behind its conventional menu, 'paste the image'
    is a command (not typing), 'no' does not match 'notepad', and a control already pressed twice without progress is not offered again"""
    from core_organs import desktop_grounding as dg
    J = dg.ConstrainedJudge
    E = lambda name, role, y=100: dg.GroundedElement(id=f"{role}:{name}", name=name, role=role, bbox=(10, y, 90, y + 20), tier="uia", hwnd=1)
    goal = r"save it as D:\data\out.xlsx"
    screen = [E("Minimize", "button", 5), E("Restore", "button", 5), E("File Tab", "button", 40), E("Save", "button", 60), E("AutoSave", "button", 80),
              E("Save As", "listitem", 120), E("Browse", "button", 150), E("Signed in as Some Person", "button", 20), E("Patel, Dhruv", "menuitem", 21), E("Home", "listitem", 200)]
    top = lambda g, els: [(e.name, round(sc, 1)) for sc, _i, e in J.rank_scored(g, els)][:4]
    r1 = top(goal, screen)
    names1 = [n for n, _ in J.rank_candidates(goal, screen)[:0]] or [e.name for _i, e in J.rank_candidates(goal, screen)]
    paste_screen = [E("File", "menuitem", 10), E("Edit", "menuitem", 12), E("Zoom", "edit", 300), E("Image", "group", 60), E("Cut", "button", 400)]
    r2 = top("paste the image from the clipboard", [e for e in paste_screen if e.name != "Cut"])
    r3 = top("zoom in", [E("Zoom", "edit", 300), E("Edit", "menuitem", 12), E("View", "menuitem", 14)])
    g = dg.DesktopGrounding()
    checks = {
        "window chrome (Minimize / Restore) ranks below every real control": names1.index("Minimize") > names1.index("Browse") and names1.index("Restore") > names1.index("Save As"),
        "'Save As' and 'File Tab' outrank the in-place Save / AutoSave for a path goal": names1.index("Save As") < names1.index("Save") and names1.index("File Tab") < names1.index("AutoSave"),
        "'Browse...' (the real file picker) is promoted for a goal that names a path": names1.index("Browse") < names1.index("Home"),
        "an account control is recognised ('Signed in as', 'Last, First', 'Sign out') unless the goal is about accounts":
            dg.is_account_control("Signed in as Some Person", goal) and dg.is_account_control("Patel, Dhruv", goal) and dg.is_account_control("Sign out of this account", goal)
            and not dg.is_account_control("Sign out", "sign out of the account") and not dg.is_account_control("Save As", goal),
        "an off-screen command ('paste') is behind its conventional menu: Edit ranks first": r2[0][0] == "Edit",
        "'paste the image' is a command, 'paste \"hello\"' is typing": (not J._wants_text("paste the image from the clipboard")) and J._wants_text("paste 'hello' into the box") and J._wants_text("type hello"),
        "the conventional menu is DECISIVE (no model call) for a command that is not on screen": (J.decisive(J(), "paste the image from the clipboard", [e for e in paste_screen if e.name != "Cut"]) or {}).get("decisive") is True,
        "a command already on screen keeps its own control (Zoom edit is not displaced by View)": r3[0][0] in ("Zoom",),
        "a 2-letter hint token matches whole words only ('no-such-app' is not Notepad)": g.find_window("no-such-app-hj-rank1") is None,
    }
    return _verdict(TestOutcome, checks, extra=f"order for the save goal: {names1}; paste top: {r2[:3]}")


# ============================================================================================================== PAINT1

def run_paint1(TestOutcome):
    """PAINT1: a drawing described as DATA (several primitives, not a canned shape) is drawn in WinUI Paint with zero physical input - rendered
    off-screen, placed on the clipboard, pasted through the actuation backbone, saved, and every part proven from the saved PNG's pixels (P1-F).
    The clipboard is only overwritten when HOJAIGA_TEST_CLIPBOARD=1 (the user said yes once); plain-text clipboards are always fine and restored"""
    import shutil
    import psutil
    from core_organs import canvas_paste as cp
    from core_organs import headless_input as hin
    from PIL import Image
    if any((p.info["name"] or "").lower() == "mspaint.exe" for p in psutil.process_iter(["name"])):
        return TestOutcome(passed=False, env_blocked=True, evidence="Paint is already open and is the USER'S: PAINT1 will not drive or close it")
    fmts, _why = cp.clipboard_formats()
    allow = os.environ.get("HOJAIGA_TEST_CLIPBOARD") == "1"
    if fmts and not set(fmts) <= cp._SAFE_PLAIN and not allow:
        return TestOutcome(passed=False, env_blocked=True, evidence=f"the clipboard holds the user's rich data (formats {fmts[:5]}); set HOJAIGA_TEST_CLIPBOARD=1 to let the test overwrite it")
    tmp = os.path.join(r"D:\new_automation", "_paint1_tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    out = os.path.join(tmp, "p1.png")
    spec = {"size": (300, 220), "background": (255, 255, 255), "items": [
        {"type": "rectangle", "box": (40, 90, 220, 200), "color": (30, 30, 30), "fill": (222, 184, 135), "width": 3},
        {"type": "polygon", "points": [(30, 90), (130, 20), (230, 90)], "color": (140, 20, 20), "fill": (200, 40, 40), "width": 3},
        {"type": "ellipse", "box": (240, 10, 290, 60), "color": (230, 160, 0), "fill": (255, 215, 0), "width": 2}]}
    v0 = len(hin.VIOLATIONS)
    p0 = hin._u32.GetCursorPos
    try:
        r = cp.draw("paint", spec, out, allow_clipboard_overwrite=allow)
        parts = {}
        if os.path.exists(out):
            im = Image.open(out).convert("RGB")
            px = im.load()
            w, h = im.size
            def count(col, tol=30):
                return sum(1 for y in range(0, min(h, 230), 2) for x in range(0, min(w, 310), 2) if all(abs(px[x, y][i] - col[i]) <= tol for i in range(3)))
            parts = {"roof": count((200, 40, 40)), "walls": count((222, 184, 135)), "sun": count((255, 215, 0))}
        checks = {
            "the loop completed both goals (paste, then save)": bool(r.get("completed")),
            "the saved file exists and is a real PNG": os.path.exists(out) and Image.open(out).format == "PNG",
            "every part of the drawing is in the saved pixels (roof, walls, sun)": bool(parts) and all(n > 15 for n in parts.values()),
            "zero physical input (input guard saw nothing)": len(hin.VIOLATIONS) == v0,
            "the user's clipboard text was put back": (lambda f: (not f) or set(f) <= cp._SAFE_PLAIN)(cp.clipboard_formats()[0] or []),
        }
        return _verdict(TestOutcome, checks, extra=f"parts={parts}; {r.get('steps')} steps in {r.get('elapsed_s')}s; reason={r.get('reason')}")
    finally:
        for p in psutil.process_iter(["name"]):
            if (p.info["name"] or "").lower() == "mspaint.exe":
                try:
                    p.kill()
                except Exception:  # noqa: BLE001
                    pass
        shutil.rmtree(tmp, ignore_errors=True)


# ============================================================================================================== PAR1

def run_par1(TestOutcome):
    """PAR1: two independent apps run AT THE SAME TIME, one child virtual cursor each (own loop, own sprite id, own cursor path), and each is
    verified independently on disk; the run is shorter than the two sequential runs would be (P1-I). Word + Excel save-to-path"""
    import shutil
    import zipfile
    import psutil
    from core_organs import task_lifecycle as tl
    names = {"winword.exe", "excel.exe"}
    pids0 = {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() in names}
    if pids0:
        return TestOutcome(passed=False, env_blocked=True, evidence=f"the user's Word/Excel is running (pids {sorted(pids0)}): PAR1 will not drive or close it")
    tmp = os.path.join(r"D:\new_automation", "_par1_tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    fw, fx = os.path.join(tmp, "w.docx"), os.path.join(tmp, "x.xlsx")
    try:
        t0 = time.time()
        r = tl.run_lifecycle(f"open word and save it as {fw}, then open excel and save it as {fx}", parallel=True)
        dt = time.time() - t0
        loop = (r.get("tickets") or [{}])[0].get("loop") or {}
        apps = {a["app"]: a for a in loop.get("apps", [])}
        def valid(p):
            try:
                return os.path.exists(p) and "[Content_Types].xml" in zipfile.ZipFile(p).namelist()
            except Exception:
                return False
        w, x = apps.get("word", {}), apps.get("excel", {})
        seq_est = sum(a.get("elapsed_s", 0) for a in apps.values())
        checks = {
            "the plans were independent and ran in parallel": bool((loop.get("parallel") or {}).get("used")),
            "each app got its OWN child cursor id": bool(w.get("cursor")) and bool(x.get("cursor")) and w.get("cursor") != x.get("cursor"),
            "each child cursor recorded its own path": (w.get("cursor_points") or 0) >= 1 and (x.get("cursor_points") or 0) >= 1,
            "Word: completed and the .docx is a real OOXML file": w.get("status") == "COMPLETED" and valid(fw),
            "Excel: completed and the .xlsx is a real OOXML file": x.get("status") == "COMPLETED" and valid(fx),
            "wall time is shorter than the sum of the two runs": dt < seq_est * 0.95,
        }
        return _verdict(TestOutcome, checks, extra=f"wall {dt:.0f}s vs sum of app times {seq_est:.0f}s; word {w.get('elapsed_s')}s excel {x.get('elapsed_s')}s; parallel={loop.get('parallel')}")
    finally:
        time.sleep(3)
        for p in psutil.process_iter(["name"]):
            if (p.info["name"] or "").lower() in names and p.pid not in pids0:
                try:
                    p.kill()
                except Exception:  # noqa: BLE001
                    pass
        shutil.rmtree(tmp, ignore_errors=True)
