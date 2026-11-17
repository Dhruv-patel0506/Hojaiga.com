"""
atlas.scanner -- ONE orchestrator, four speed tiers, any application.

    instant   (seconds)  static developer harvest + the program-file command harvest + CACHED public knowledge. Never launches, never blocks on the network.
    fast      (~10-30 s) + live structure scan of the window (UIA tree, menus, ribbon, layout)  [+ OCR labels when the window gives UIA nothing]
    deep      (~1-3 min) + frontier exploration (open every dialog / tab / flyout, with verified unwind), universal-chord tests, the GESTURE ATLAS
                         (click / right-click / drag / wheel / hold / modifiers, on regions and on objects), blind-app hover + menu reading
    full      (minutes)  + independent recall, exhaustion proof, oracle coverage, a second exploration pass, the application model + report

The same code path serves a window we launched ourselves (invisible, disposable: mutating probes allowed) and a window someone else is using
(attach: read-only + view-only gestures with verified undo). Every phase is bounded; every failure is reported in the result, never raised.
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import os
import re
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import common as C
from . import coverage as COV
from . import devscan
from . import evolve

TIERS = ("instant", "fast", "deep", "full")
DEFAULT_BUDGET = {"instant": 4, "fast": 30, "deep": 150, "full": 1500}



FRAME_NAMES = {"system", "minimize", "maximize", "restore", "close", "help"}


def frame_only(nodes) -> bool:
    """True when the UIA tree is just the window frame (title bar, system menu, caption buttons): the application's own controls are not there (yet)."""
    if not nodes:
        return True
    for n in nodes:
        if n.ctype in ("WindowControl", "TitleBarControl", "MenuBarControl"):
            continue
        if n.ctype in ("ButtonControl", "MenuItemControl") and C.fold(n.name) in FRAME_NAMES:
            continue
        return False
    return True


def ensure_tree(h: int, bg=None, max_s: float = 6.0) -> Tuple[List[Any], float, bool]:
    """Snapshot the window, and if it is only the frame wait (bounded) for the application's controls to be realised: nudge a parked window so
    one pixel is on screen (the engine's own lay_out trick: lazily laid-out toolkits build their tree only then), re-reading until it grows.
    Returns (nodes, seconds waited, frame_only_at_the_end)."""
    from core_organs import fast_uia
    t0 = time.time()
    nodes = fast_uia.snapshot(h, timeout_ms=7000) or []
    if not frame_only(nodes):
        return nodes, 0.0, False
    if bg is not None and getattr(bg, "mode", "") == "parked":
        try:
            bg.lay_out(settle_s=0.6)
        except Exception:
            pass
    while time.time() - t0 < max_s:
        time.sleep(0.4)
        nodes = fast_uia.snapshot(h, timeout_ms=7000) or []
        if not frame_only(nodes):
            break
    return nodes, round(time.time() - t0, 2), frame_only(nodes)


def close_owned(h: int, timeout_s: float = 9.0) -> Dict[str, Any]:
    """Close a program window THIS scan launched (a disposable empty document), whatever it asks. Order: the engine's polite close; if a (possibly hidden, off-screen) save prompt
    holds it open, answer it with the non-saving button; if the process still refuses, end the process we started (nothing of the user's is in it). Reports what was needed."""
    import ctypes
    from core_organs import universal_scan as us
    from core_organs import fast_uia
    from core_organs import headless_input as hin
    u32 = ctypes.windll.user32
    rec: Dict[str, Any] = {"how": "close"}
    try:
        pid = hin.window_pid(h) if u32.IsWindow(h) else 0
    except Exception:
        pid = 0
    if us.close_window(h, timeout_s=timeout_s / 2, discard_unsaved=True):
        return rec
    # hidden save prompts are windows of the same process that the engine's popup listing does not show
    for _ in range(2):
        for w in hin.process_windows(h, include_hidden=True):
            if w == h:
                continue
            nodes = fast_uia.snapshot(w, timeout_ms=3000) or []
            if not any(re.search(r"save (your )?changes|do you want to save|want to save", n.name or "", re.I) for n in nodes):
                continue
            btn = next((n for n in nodes if n.ctype == "ButtonControl" and re.match(r"(don.t save|no|discard|close without saving)", (n.name or "").strip(), re.I) and "invoke" in n.pats), None)
            if btn is not None:
                try:
                    btn.ctrl.GetInvokePattern().Invoke()
                    rec["how"] = "answered the save prompt with the non-saving button"
                except Exception:
                    pass
        time.sleep(1.2)
        if not u32.IsWindow(h):
            return rec
    if u32.IsWindow(h) and pid:
        import subprocess
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, creationflags=0x08000000)
        rec["how"] = "process ended (it refused to close and holds only the scan's empty document)"
        time.sleep(0.8)
    rec["closed"] = not u32.IsWindow(h)
    return rec


def resolve_installed(name: str) -> str:
    """Installed-app name -> its exe (Start-menu shortcut targets, then PATH lookup). '' when the host has no such program."""
    try:
        from core_organs.organ_40_app_launcher import AppCatalog
        cat = AppCatalog()
        hit = cat.find(name)
        p = hit[1] if hit and hit[1] else ""
        if p and p.lower().endswith(".exe") and os.path.isfile(p):
            return p
        p = cat.path_lookup(name) or ""
        if p and os.path.isfile(p):
            return p
    except Exception:
        pass
    return ""


class Atlas:
    def __init__(self, store: Optional[C.AtlasStore] = None, model=None, log: Optional[Callable[[str], None]] = None):
        self.store = store or C.get_store()
        self._model = model
        self.log = log or (lambda s: None)

    @property
    def model(self):
        if self._model is None:
            from core_organs import organ_48_app_behavior_model as bm
            self._model = bm.get_model()
        return self._model

    # ------------------------------------------------------------------------------------------
    def learn(self, target: Any, *, tier: str = "fast", budget_s: Optional[float] = None, web: Optional[bool] = None, hwnd: int = 0,
              attach: str = "auto", pristine: Optional[bool] = None, oracle_json: str = "", report: bool = True) -> Dict[str, Any]:
        """Learn `target` (name | exe path | hwnd) at the given tier. Returns a summary; everything learned is in the store."""
        assert tier in TIERS, f"tier must be one of {TIERS}"
        t0 = time.time()
        budget = float(budget_s or DEFAULT_BUDGET[tier])
        run_id = f"atlas_{uuid.uuid4().hex[:8]}"
        from core_organs import static_knowledge as sk
        name = str(target) if not isinstance(target, int) else ""
        exe = sk.exe_for(hwnd or target)
        if not exe and name:                                 # "powerpoint" is not an exe name: ask the host's installed-app catalog (Start menu / App Paths)
            exe = resolve_installed(name)
        key =C.app_key_of(name or os.path.basename(exe))
        out: Dict[str, Any] = {"app_key": key, "target": name or hwnd, "tier": tier, "run_id": run_id, "exe": exe, "phases": {}, "errors": []}
        learner = evolve.Learner(self.store, key, run_id)

        # ---- phase 1: static (parallel with the web)
        web_on = (tier != "instant") if web is None else bool(web)
        pool = cf.ThreadPoolExecutor(max_workers=3)
        holder: Dict[str, Any] = {"static": None}

        def start_static() -> None:                     # CPU-heavy: started only AFTER the window is parked (GIL contention starved the park's timing loop)
            if holder["static"] is None:
                holder["static"] = pool.submit(self._phase_static, target, key, exe, budget)
        f_web = pool.submit(self._phase_web, key, name or os.path.splitext(os.path.basename(exe))[0], exe, web_on, tier == "instant") if (web_on or tier == "instant") else None

        live_info: Dict[str, Any] = {}
        if tier != "instant":
            try:
                live_info = self._phase_live(target, key, exe, tier, budget, hwnd=hwnd, attach=attach, pristine=pristine, learner=learner, oracle_json=oracle_json, run_id=run_id,
                                             on_parked=start_static)
            except Exception as exc:
                import traceback
                out["errors"].append(f"live: {type(exc).__name__}: {str(exc)[:160]}")
                live_info = {"error": traceback.format_exc()[-600:]}
        out["phases"]["live"] = live_info
        start_static()
        for nm_, fut in (("static", holder["static"]), ("web", f_web)):
            if fut is None:
                continue
            try:
                out["phases"][nm_] = fut.result(timeout=max(5.0, budget * 0.6))
            except Exception as exc:
                out["errors"].append(f"{nm_}: {type(exc).__name__}: {str(exc)[:120]}")
                out["phases"][nm_] = {"error": str(exc)[:200]}
        pool.shutdown(wait=False)

        # ---- phase: knowledge model + report
        if report:
            try:
                from . import architect
                am = architect.build(key, self.store, self.model, exe=exe)
                out["phases"]["model"] = {"kind": am.get("identity", {}).get("kind"), "confidence": am.get("identity", {}).get("kind_confidence"), "sections": list(am.keys())}
                paths = architect.write_report(key, am, self.store)
                out["report"] = paths
            except Exception as exc:
                import traceback
                out["errors"].append(f"architect: {type(exc).__name__}: {str(exc)[:160]}")
                out["architect_trace"] = traceback.format_exc()[-500:]
        counts = self.store.count_claims(key)
        out["claims_total"] = sum(counts.values())
        out["claims_by_kind"] = counts
        try:
            from core_organs import organ_63_app_mastery as m63
            m = m63.measure(self.model, key)
            out["commands"], out["dialogs"], out["transitions"], out["regions"] = m.get("commands"), m.get("dialogs"), m.get("transitions"), m.get("regions")
        except Exception:
            pass
        out["gestures"] = len(self.store.gestures(key))
        out["accuracy"] = learner.accuracy(key)
        out["seconds"] = round(time.time() - t0, 1)
        self.store.log_run(run_id, key, tier, t0, out["seconds"], {k: v for k, v in out.items() if k not in ("phases", "claims_by_kind")})
        return out

    # ------------------------------------------------------------------------------------------
    def _phase_static(self, target: Any, key: str, exe: str, budget: float) -> Dict[str, Any]:
        t0 = time.time()
        rep: Dict[str, Any] = {}
        try:
            d = devscan.scan(exe or target, budget_s=min(9.0, max(3.0, budget * 0.5)), app_key=key, store=self.store, persist=True)
            rep["devscan"] = {"ok": d.get("ok"), "claims": len(d.get("claims", [])), "seconds": d.get("seconds"), "why": d.get("why", ""), "scope": d.get("scope", ""),
                              "languages": list((d.get("languages") or {}).keys()), "areas": sorted((d.get("areas") or {}).keys()),
                              "com": (d.get("com") or {}).get("n_classes"), "cli_flags": len(d.get("cli_flags") or [])}
        except Exception as exc:
            rep["devscan"] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
        try:
            from . import introspect
            rep["introspect"] = introspect.learn(exe, key, self.store, budget_s=max(30.0, budget))
        except Exception as exc:
            rep["introspect"] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
        try:
            from core_organs import organ_63_app_mastery as m63
            rep["program_file"] =m63._static_phase(self.model, str(target) if not isinstance(target, int) else os.path.basename(exe), 0)
        except Exception as exc:
            rep["program_file"] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
        rep["seconds"] = round(time.time() - t0, 2)
        return rep

    def _phase_web(self, key: str, name: str, exe: str, enabled: bool, cache_only: bool) -> Dict[str, Any]:
        from . import webknow, distill, keymaps
        t0 = time.time()
        rep: Dict[str, Any] = {"enabled": enabled, "cache_only": cache_only}
        if not enabled and not cache_only:
            return rep
        webknow.CACHE_ONLY = cache_only
        try:
            vendor = product = ""
            if exe:
                from core_organs import pe_resources as pr
                v = pr.read_version(exe)
                vendor, product = (v.get("CompanyName") or ""), (v.get("ProductName") or "")
                if product.lower().startswith(("microsoft office", "microsoft® office")) or product.lower() in ("microsoft 365", "microsoft office"):
                    product = ""                                  # the suite name; the program's own name is better (WINWORD -> Word)
            q = name if not product else product
            web = webknow.knowledge_for(q if len(name) < 3 else name, vendor=vendor, product=product if product and C.fold(product) != C.fold(name) else "", app_key=key)
            rep.update(ok=web.get("ok"), sources=web.get("sources", []), seconds_fetch=web.get("seconds"), stats=web.get("stats"))
            if not web.get("ok"):
                rep["why"] = web.get("github_error") or "nothing found (offline, not cached, or not public)"
                return rep
            claims = webknow.structured_claims(key, web)
            gh = web.get("github") or {}
            binds: List[Dict[str, Any]] = []
            for f in gh.get("files", []):
                if f["tag"] == "keymap":
                    b = keymaps.extract(f["text"], f["path"])
                    binds += b
                    claims += keymaps.to_claims(key, b, f["url"], max_claims=120)
            rep["keymap_bindings"] = len(binds)
            rep["pointer_bindings"] = len(keymaps.gestures_of(binds))
            texts: List[Tuple[str, str]] = []
            wp = web.get("wikipedia") or {}
            if wp.get("text"):
                texts.append((wp["url"], wp["text"]))
            for f in gh.get("files", []):
                if f["tag"] in ("readme", "doc", "dev-doc") and f["text"]:
                    texts.append((f["url"], f["text"]))
            dstat = []
            for url, txt in texts[:3]:
                cl, meta = distill.distill(key, txt, url, use_model=(not cache_only))
                claims += cl
                dstat.append({"url": url[-60:], **{k: v for k, v in meta.items() if k != "model"}, "model": {k: v for k, v in (meta.get("model") or {}).items() if k in ("proposed", "kept", "dropped", "error")}})
            rep["distill"] = dstat
            self.store.delete_claims(key, source="atlas.webknow")
            self.store.delete_claims(key, source="atlas.keymaps")
            self.store.delete_claims(key, source="atlas.distill")
            n = 0
            for c in claims:
                try:
                    self.store.put_claim(c)
                    n += 1
                except C.EvidenceRequired:
                    continue
            rep["claims"] = n
        except Exception as exc:
            rep["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        finally:
            webknow.CACHE_ONLY = False
        rep["seconds"] = round(time.time() - t0, 2)
        return rep

    # ------------------------------------------------------------------------------------------
    def _acquire(self, target: Any, exe: str, hwnd: int, attach: str) -> Tuple[int, bool, Dict[str, Any]]:
        """(hwnd, owned, info). owned = a window WE launched (invisible, disposable)."""
        info: Dict[str, Any] = {}
        if hwnd:
            info["mode"] = "attached (given)"
            return hwnd, False, info
        from core_organs import universal_scan as us
        from core_organs import desktop_grounding as dg
        name = str(target) if not isinstance(target, int) else ""
        if attach in ("auto", "existing"):
            try:
                found = dg.DesktopGrounding().find_window(name or exe)
                if isinstance(found, int) and found:
                    info["mode"] = "attached (existing window)"
                    return found, False, info
            except Exception:
                pass
        if attach == "existing":
            return 0, False, {"mode": "none", "why": "no existing window"}
        try:
            lh = us.launch_hidden(name or exe, timeout_s=40.0, fast=True)
        except Exception as exc:
            return 0, False, {"mode": "launch-failed", "why": f"{type(exc).__name__}: {str(exc)[:120]}"}
        h = int(lh.get("hwnd") or 0)
        info.update(mode="launched hidden", launched=bool(lh.get("launched")), launch=lh.get("status") or lh.get("why"))
        return h, bool(h and lh.get("launched")), info

    def _phase_live(self, target: Any, key: str, exe: str, tier: str, budget: float, *, hwnd: int, attach: str, pristine: Optional[bool], learner: evolve.Learner,
                    oracle_json: str, run_id: str, on_parked: Optional[Callable[[], None]] = None) -> Dict[str, Any]:
        from core_organs import background_window as bw
        from core_organs import fast_uia
        from core_organs import universal_scan as us
        T = C.Timer()
        live: Dict[str, Any] = {}
        h, owned, info = self._acquire(target, exe, hwnd, attach)
        live["acquire"] = info
        live["owned"] = owned
        if not h:
            live["skipped"] = info.get("why") or "no window to learn from (not installed, not running, could not launch)"
            return live
        live["hwnd"] = h
        visible_to_user = False
        try:
            visible_to_user = bool(bw.user_can_see(h))
        except Exception:
            pass
        live["user_can_see"] = visible_to_user
        polite = visible_to_user and not owned
        pr_ok = owned if pristine is None else pristine
        gest_pristine = bool(pr_ok) and not polite
        try:
            with bw.BackgroundSession(h) as bg:
                if bg.mode == "failed":                 # a window that is still being created can refuse once: wait, retry (bounded)
                    for _ in range(2):
                        time.sleep(1.2)
                        bg.state = bw.enter(h)
                        if bg.mode != "failed":
                            break
                live["park"] = bg.mode
                if on_parked:
                    on_parked()
                time.sleep(0.4)
                nodes, waited, still_frame = ensure_tree(h, bg, max_s=3.5 if tier != "instant" else 2.0)
                live["tree_wait_s"] = waited
                live["frame_only"] = still_frame
                actionable = [n for n in nodes if (set(n.pats) & {"invoke", "toggle", "expand", "select"})]
                live["uia"] = {"nodes": len(nodes), "actionable": len(actionable)}
                uia_rich = len(actionable) >= 12
                live["uia_rich"] = uia_rich
                T.mark("snapshot")
                names = [n.name for n in actionable if n.name]

                # ---- fast: the engine's structure scan (deep / full: AFTER the cartographer, which first brings the program to a working document)
                def do_structure() -> None:
                    if still_frame:
                        live["structure"] = {"skipped": "the window exposes only its frame to UI Automation: the engine's structure scan has nothing to read and is not run on a window we do not own"}
                    elif not polite or tier != "instant":
                        try:
                            from core_organs import fast_scan
                            rep = fast_scan.deep_scan(str(target) if not isinstance(target, int) else os.path.basename(exe), self.model, budget_s=min(30.0, max(8.0, budget * 0.35)),
                                                      vision=False, target_hwnd=h, close_if_launched=False, force=False)
                            live["structure"] = {"seconds": rep.get("seconds"), "within_budget": rep.get("within_budget"), "tree": rep.get("tree"), "error": rep.get("error")}
                        except Exception as exc:
                            live["structure"] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
                        T.mark("structure")
                if tier not in ("deep", "full") or not uia_rich or polite:
                    do_structure()

                # ---- deep: exploration + conventions
                before_m = None
                app_name = str(target) if not isinstance(target, int) else os.path.basename(exe)
                if tier in ("deep", "full") and uia_rich and not polite:
                    try:
                        live["explore"] = self._explore(h, app_name, key, float(os.environ.get("HOJAIGA_ATLAS_EXPLORE_S") or (min(100.0, budget * 0.42) if tier == "deep" else budget * 0.6)), gest_pristine, learner, run_id)
                    except Exception as exc:
                        live["explore"] = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
                    T.mark("explore")
                    do_structure()
                    if tier == "full" and os.environ.get("HOJAIGA_ATLAS_ENGINE_EXPLORE") == "1":
                        # opt-in: the engine's explorer can leave a stuck UIA call behind on toolkits whose modal dialogs block the provider (measured)
                        try:
                            from core_organs import organ_63_app_mastery as m63
                            fin, val = m63._bounded(lambda: self._engine_explore(h, app_name, key, 25.0, gest_pristine, conventions=False), 60.0)
                            live["engine_explore"] = val if fin and not isinstance(val, BaseException) else {"error": "did not finish within 60 s (bounded)"}
                        except Exception as exc:
                            live["engine_explore"] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
                        T.mark("engine_explore")

                # ---- deep: gestures (+ blind-app perception)
                gres: List[Any] = []
                if tier in ("deep", "full") and h:
                    from . import gestures as G
                    gp = G.GestureProber(h, key, store=self.store, run_id=run_id, budget_s=min(70.0, budget * 0.35), pristine=gest_pristine,
                                         predictor=lambda k, f: learner.predict(k, f),
                                         observer=lambda k, f, pred, obs: learner.observe(k, f, pred, obs), log=self.log,
                                         evidence_dir=os.path.join(C.EVIDENCE_DIR, key, run_id))
                    nodes = fast_uia.snapshot(h, timeout_ms=7000) or nodes                   # the explorer may have changed the window (size, tab): regions come from the CURRENT tree
                    regions = G.discover_regions(h, nodes if nodes else None)
                    if not uia_rich and not [r for r in regions if r.kind in ("canvas", "blind")]:
                        regions = []
                    live["regions"] = [{"kind": r.kind, "name": r.name, "size": [r.w, r.h]} for r in regions][:20]
                    if polite:
                        live["gestures"] = {"skipped": "the window is in the user's view: read-only"}
                    else:
                        live["gestures"] = gp.run(regions, nodes)
                        gres = gp.results
                    T.mark("gestures")
                    chan = self._channels(key, gres, uia_rich, live, run_id)
                    live["channels"] = chan
                if not uia_rich and tier != "instant":
                    live["blind"] = self._blind(h, key, tier, budget, live.get("channels", {}), learner, run_id)
                    T.mark("blind")

                # ---- full: coverage proofs
                if tier == "full":
                    cov: Dict[str, Any] = {}
                    try:
                        cov["independent"] = COV.independent_recall(self.model, key, h)
                    except Exception as exc:
                        cov["independent"] = {"error": str(exc)[:100]}
                    oj = oracle_json or os.environ.get("HOJAIGA_ORACLE_JSON", "")
                    if oj and os.path.isfile(oj):
                        cov["oracle"] = COV.oracle_coverage(self.model, key, COV.TruthFileOracle(oj))
                    if uia_rich and not polite:
                        try:
                            from core_organs import organ_63_app_mastery as m63
                            from core_organs import knowledge_store as ks_
                            nb = COV.known_names(self.model, key)
                            db = {d["title"] for d in ks_.dialogs(self.model, key)}
                            b2 = m63.measure(self.model, key)
                            again = self._explore(h, app_name, key, min(60.0, budget * 0.2), gest_pristine, learner, run_id + "b", passes=("menus", "tabs", "openers"))
                            da = {d["title"] for d in ks_.dialogs(self.model, key)}
                            cov["exhaustion"] = COV.exhaustion(self.model, key, b2, m63.measure(self.model, key), names_before=nb, dialogs_before=db, dialogs_after=da)
                            cov["exhaustion"]["second_pass"] = {k: again.get(k) for k in ("menu_items", "dialogs", "pages", "controls", "seconds")}
                        except Exception as exc:
                            cov["exhaustion"] = {"error": str(exc)[:100]}
                    live["coverage"] = cov
                    T.mark("coverage")
                # ---- drift fingerprint (inside the session: the tree is complete)
                try:
                    nodes2 = fast_uia.snapshot(h, timeout_ms=5000) or []
                    nm2 = [n.name for n in nodes2 if n.name and (set(n.pats) & {"invoke", "toggle", "expand", "select"})]
                    live["drift"] = evolve.fingerprint(self.store, key, exe, nm2 or names, len(self.model.commands(key, limit=5000)))
                except Exception as exc:
                    live["drift"] = {"error": str(exc)[:100]}
        finally:
            if owned and h:
                try:
                    live["closed"] = close_owned(h)
                except Exception as exc:
                    live["closed"] = f"error: {str(exc)[:80]}"
        live["timings"] = T.marks
        return live

    # ------------------------------------------------------------------------------------------
    def _explore(self, hwnd: int, name: str, key: str, budget_s: float, pristine: bool, learner, run_id: str, passes=("ribbon", "menus", "tabs", "openers")) -> Dict[str, Any]:
        """Atlas's own explorer (menus, tabs, openers, the dialog protocol) + evidenced claims about what it found."""
        from . import explorer
        ex = explorer.Explorer(hwnd, name, key, self.model, store=self.store, pristine=pristine, budget_s=budget_s, learner=learner, run_id=run_id, log=self.log)
        st = ex.run(passes)
        if ex.uimap.get("surfaces"):
            from . import uimap as UM
            try:
                st["uimap"] = UM.to_knowledge(key, ex.uimap, self.store, self.model, run_id, st.get("uimap_file", ""))
            except Exception as exc:
                st["uimap"] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
        st["dialog_titles"] = sorted(ex.seen_dialogs.keys())
        for title, info in ex.seen_dialogs.items():
            bits = [f"{info.get('controls')} controls"]
            if info.get("master_detail"):
                bits.append(f"master/detail with {info.get('pages')} page(s)")
            if info.get("wizard"):
                bits.append(f"wizard of {info.get('pages', 0) + 1} page(s)")
            if info.get("commit"):
                bits.append(f"commit '{info['commit']}'")
            if info.get("cancel"):
                bits.append(f"cancel '{info['cancel']}'")
            self.store.claim(key, "ui.dialog", f"Dialog '{title}': " + ", ".join(bits), trust="measured", confidence=0.9,
                             evidence=[C.Evidence("probe", f"{run_id}:dialog:{title}", f"opened, read via {info.get('read_via')}, closed with a verified unwind")], value=info, source="atlas.explorer")
        by_menu: Dict[str, List[str]] = {}
        try:
            for r in self.model._conn.execute("SELECT menu_path FROM bm_commands WHERE app_key=? AND origin='atlas:menu'", (key,)):
                parts = [x.strip() for x in str(r[0]).split(">")]
                if len(parts) >= 2:
                    by_menu.setdefault(parts[0], []).append(parts[-1])
        except Exception:
            pass
        for menu, items in by_menu.items():
            self.store.claim(key, "ui.menu", f"Menu '{menu}' contains: " + "; ".join(sorted(set(items))), trust="measured", confidence=0.9,
                             evidence=[C.Evidence("probe", f"{run_id}:menu:{menu}", "read from the opened menu")], value={"menu": menu, "items": sorted(set(items))}, source="atlas.explorer")
        st["records"] = st.get("records", [])[:25]
        return st

    def _engine_explore(self, hwnd: int, name: str, key: str, budget_s: float, pristine: bool, conventions: bool = True) -> Dict[str, Any]:
        """The engine's own exploration (frontier, verified unwind, conventions) on a window that is ALREADY parked by our session."""
        from core_organs import organ_63_app_mastery as m63
        from core_organs import organ_48_app_behavior_model as bm
        out: Dict[str, Any] = {}
        main, extra = m63._snap_all(hwnd)
        state = m63.derive_state(main + extra)
        out["state_vars"] = m63.record_state_vars(self.model, key, state)
        pristine_ok, why = m63.is_pristine(hwnd, main)
        out["pristine"] = {"pristine": pristine_ok, "why": why}
        vh = bm.app_version_hash(bm._exe_of_hwnd(hwnd))
        out["frontier_added"] = m63.populate_frontier(self.model, key, hwnd, main + extra, vh)
        exe_live = bm._exe_of_hwnd(hwnd).lower()
        sysroot = (os.environ.get("SystemRoot") or r"C:\Windows").lower()
        hosted = os.path.basename(exe_live) == "applicationframehost.exe"
        kinds = None
        if exe_live and not hosted and (exe_live.startswith(sysroot + os.sep) or os.sep + "systemapps" + os.sep in exe_live):
            kinds = ["tab", "opener", "context", "expander"]
        res = m63.explore(self.model, name, hwnd, run_id=f"atlas_x_{int(time.time())}", budget_s=budget_s, pristine=pristine_ok and pristine, kinds=kinds)
        out["explore"] = {k: v for k, v in res.items() if k in ("probed", "explored", "new_commands", "new_dialogs", "new_transitions", "unsafe", "app_unresponsive", "stopped", "elapsed_s", "reason")} or {"raw_keys": list(res)[:12]}
        if conventions and not res.get("app_unresponsive"):
            try:
                skip = {c["shortcut"] for c in self.model.commands(key, limit=5000) if c["shortcut"] and c["source"] == "learned"}
                fin, val = m63._bounded(lambda: m63.test_conventions(self.model, key, hwnd, pristine=pristine_ok and pristine, run_id="atlas", skip_chords=skip), 90.0)
                out["conventions"] = ({"tested": len((val or {}).get("tested", []))} if fin and not isinstance(val, BaseException) else {"error": "did not finish"})
            except Exception as exc:
                out["conventions"] = {"error": str(exc)[:100]}
        try:
            from core_organs import command_registry as cr
            out["registry"] = {k: v for k, v in cr.refresh_profile(self.model, key).items() if k in ("archetype", "capabilities")}
        except Exception:
            pass
        main2, extra2 = m63._snap_all(hwnd)
        out["left_as_found"] = bool(m63.derive_state(main2 + extra2)["signature"] == state["signature"] and not bm._open_popups(hwnd))
        return out

    def _channels(self, key: str, gres: List[Any], uia_rich: bool, live: Dict[str, Any], run_id: str) -> Dict[str, Any]:
        """How can this application be DRIVEN without a physical pointer? Measured from the gesture run, stored as facts."""
        delivered = [g for g in gres if g.delivered and g.effect_class != "unobserved"]
        eff = [g for g in delivered if g.effective]
        mouse = "unknown"
        if delivered:
            mouse = "effective" if eff else ("ineffective" if len(delivered) >= 4 else "unknown")
        ch = {"posted_mouse": mouse, "gestures_tested": len(delivered), "gestures_effective": len(eff), "uia_tree": "rich" if uia_rich else "blind"}
        ev = [C.Evidence("gesture", f"{run_id}:channels", f"{len(eff)}/{len(delivered)} posted pointer gestures changed the picture or opened a surface")]
        if mouse == "ineffective":
            self.store.claim(key, "input.channel", f"Posted pointer input is IGNORED by this application ({len(delivered)} gestures delivered, none had an effect): it reads the physical pointer; "
                             f"drive it through its scripting/command-line/COM surface or a human", trust="measured", confidence=0.85, evidence=ev, value=ch, source="atlas.scanner")
        elif mouse == "effective":
            self.store.claim(key, "input.channel", f"Posted pointer input WORKS on this application ({len(eff)}/{len(delivered)} gestures had an effect)", trust="measured", confidence=0.9, evidence=ev, value=ch, source="atlas.scanner")
        return ch

    def _blind(self, hwnd: int, key: str, tier: str, budget: float, chan: Dict[str, Any], learner: evolve.Learner, run_id: str) -> Dict[str, Any]:
        from . import blind
        if not blind.available():
            return {"skipped": "OCR engine unavailable"}
        bp = blind.BlindProber(hwnd, key, store=self.store, run_id=run_id, budget_s=min(80.0, budget * 0.4), log=self.log,
                               observer=lambda k, f, pred, obs: learner.observe(k, f, pred, obs))
        mouse_ok = chan.get("posted_mouse") == "effective"
        per = bp.perceive()
        out: Dict[str, Any] = {"labels": len(per.get("labels", [])), "ocr_s": per.get("seconds")}
        cl = blind.menu_cluster(per.get("labels", []), bp.size[1]) if per.get("labels") else []
        out["menu_cluster"] = [l["text"] for l in cl]
        if per.get("labels"):
            for l in per["labels"][:160]:
                self.store.claim(key, "ui.label", f"Visible label '{l['text']}'", trust="measured", confidence=min(0.9, l["conf"] / 100.0),
                                 evidence=[C.Evidence("probe", f"{run_id}:ocr:{l['id']}", f"box={l['box']}")], value={"text": l["text"], "box": l["box"]}, source="atlas.blind")
        if tier in ("deep", "full") and mouse_ok:
            out.update(bp.run(hover_s=30.0, menu_s=20.0, open_menus=True))
        else:
            out["interaction"] = "skipped: " + ("posted pointer input is ineffective on this application" if chan.get("posted_mouse") == "ineffective" else "not requested at this tier")
        return out
