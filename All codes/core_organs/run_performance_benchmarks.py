"""
Hojaiga Performance Benchmark Suite
====================================
Real, measured performance numbers -- no claims. Every section times the
actual code paths used by the automation pipeline and prints milliseconds.

Run:
    D:\\new_automation\\hojaiga_env\\Scripts\\python.exe "All codes\\core_organs\\run_performance_benchmarks.py"

Sections:
    1. Screen capture backends        (PIL ImageGrab vs mss vs dxcam)
    2. JPEG encoding                  (PIL vs cv2, full-res vs downscaled)
    3. Hash serialization             (json vs orjson)
    4. organ_41 full snapshot cycle   (capture + UIA walk + hash + encode)
    5. organ_30 UIA walkers           (manual vs native vs fixed wrapper)
    6. organ_30 deep scan end-to-end  (quiet mode, foreground window)
    7. VerbAliasEngine.resolve        (throughput over the task matrix)
    8. DB element batch store         (organ_24 store_elements_batch)
    9. Enhanced compiler              (compile_task latency)
"""

import os
import sys
import time
import json
import logging
import statistics

sys.path.insert(0, r"D:\new_automation\All codes")

# Organs log heavily via INFO; the benchmark prints its own report.
logging.disable(logging.INFO)

RESULTS = {}


def section(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def report(key, value):
    RESULTS[key] = value
    print(f"  {value}")


def ms(x):
    return f"{x:.1f} ms"


# --------------------------------------------------------------------------- #
# 1. Screen capture backends
# --------------------------------------------------------------------------- #
def bench_capture():
    section("1. SCREEN CAPTURE BACKENDS (full screen)")
    N = 8

    try:
        from PIL import ImageGrab
        # Warmup + paint a frame
        print("bench", end="", flush=True)
        ts = []
        for _ in range(N):
            t0 = time.perf_counter()
            img = ImageGrab.grab()
            ts.append((time.perf_counter() - t0) * 1000)
        report("pil_grab", f"PIL ImageGrab : {ms(statistics.mean(ts))} avg  (min {ms(min(ts))})")
    except Exception as e:
        report("pil_grab", f"PIL ImageGrab : SKIP ({e})")

    frame_pil = None
    try:
        from PIL import ImageGrab
        frame_pil = ImageGrab.grab()
    except Exception:
        pass

    try:
        import mss
        sct = mss.MSS()
        mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        sct.grab(mon)  # warmup
        ts = []
        for _ in range(N):
            t0 = time.perf_counter()
            raw = sct.grab(mon)
            ts.append((time.perf_counter() - t0) * 1000)
        report("mss_grab", f"mss           : {ms(statistics.mean(ts))} avg  (min {ms(min(ts))})")
        sct.close()
    except Exception as e:
        report("mss_grab", f"mss           : SKIP ({e})")

    try:
        import dxcam
        cam = dxcam.create(output_idx=0, output_color="BGR")
        for _ in range(3):
            print("", end="", flush=True)
            cam.grab(new_frame_only=False)
        ts, freshes = [], 0
        for _ in range(N):
            print("bench", end="", flush=True)  # force repaint
            t0 = time.perf_counter()
            f = cam.grab(new_frame_only=False)
            ts.append((time.perf_counter() - t0) * 1000)
            if f is not None:
                freshes += 1
        report("dxcam_grab", f"dxcam         : {ms(statistics.mean(ts))} avg  (min {ms(min(ts))}, fresh {freshes}/{N})")
        try:
            cam.release()
        except Exception:
            pass
    except Exception as e:
        report("dxcam_grab", f"dxcam         : SKIP ({e})")


# --------------------------------------------------------------------------- #
# 2. JPEG encoding
# --------------------------------------------------------------------------- #
def bench_encode():
    section("2. JPEG ENCODING (same frame, q85)")
    import io
    import numpy as np

    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
    except Exception as e:
        report("pil_encode", f"PIL q85       : SKIP ({e})")
        return

    frame_rgb = np.asarray(img)
    frame_bgr = frame_rgb[:, :, ::-1].copy()

    N = 6
    ts = []
    for _ in range(N):
        t0 = time.perf_counter()
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        ts.append((time.perf_counter() - t0) * 1000)
    pil_ms = statistics.mean(ts)
    report("pil_encode", f"PIL q85 full-res          : {ms(pil_ms)}  ({len(buf.getvalue()) // 1024} KB, {img.size[0]}x{img.size[1]})")

    try:
        import cv2
        ts = []
        for _ in range(N):
            t0 = time.perf_counter()
            ok, enc = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            ts.append((time.perf_counter() - t0) * 1000)
        cv_full = statistics.mean(ts)
        report("cv2_full", f"cv2 q85 full-res          : {ms(cv_full)}  ({enc.nbytes // 1024} KB)  [speedup {pil_ms / cv_full:.1f}x vs PIL]")

        small = cv2.resize(frame_bgr, (1280, 720), interpolation=cv2.INTER_AREA)
        ts = []
        for _ in range(N):
            t0 = time.perf_counter()
            ok, enc2 = cv2.imencode(".jpg", small, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            ts.append((time.perf_counter() - t0) * 1000)
        cv_small = statistics.mean(ts)
        report("cv2_720", f"cv2 q85 1280x720 (scanner): {ms(cv_small)}  ({enc2.nbytes // 1024} KB)  [speedup {pil_ms / cv_small:.1f}x vs PIL full]")
    except Exception as e:
        report("cv2_full", f"cv2           : SKIP ({e})")


# --------------------------------------------------------------------------- #
# 3. Hash serialization
# --------------------------------------------------------------------------- #
def bench_hash():
    section("3. HASH SERIALIZATION (elements payload)")
    import hashlib

    # Build a realistic payload from a real UIA walk if possible
    payload = {"elements": [{"control_id": f"c{i}", "name": f"Button {i}", "bounds": (0, 0, 100, 30)} for i in range(300)],
               "active_window": {"title": "bench", "class_name": "x", "handle": 1, "bounds": (0, 0, 1920, 1080)}}

    N = 50
    ts = []
    for _ in range(N):
        t0 = time.perf_counter()
        h1 = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        ts.append((time.perf_counter() - t0) * 1000)
    json_ms = statistics.mean(ts)
    report("hash_json", f"json.dumps + sha256 : {json_ms:.2f} ms / 300 elements")

    try:
        import orjson
        ts = []
        for _ in range(N):
            t0 = time.perf_counter()
            h2 = hashlib.sha256(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)).hexdigest()
            ts.append((time.perf_counter() - t0) * 1000)
        or_ms = statistics.mean(ts)
        report("hash_orjson", f"orjson   + sha256 : {or_ms:.2f} ms / 300 elements  [speedup {json_ms / or_ms:.1f}x]")
    except Exception as e:
        report("hash_orjson", f"orjson : SKIP ({e})")


# --------------------------------------------------------------------------- #
# 4. organ_41 full snapshot cycle
# --------------------------------------------------------------------------- #
def bench_snapshot_cycle():
    section("4. ORGAN_41 FULL SNAPSHOT CYCLE (capture+walk+hash+encode)")
    try:
        from core_organs.organ_41_scanner import ScannerOrgan
        scanner = ScannerOrgan()
        if scanner._uia:
            scanner._uia.InitializeUIAutomationInCurrentThread()

        ts, details = [], []
        for i in range(6):
            print(f"cycle {i}", flush=True)  # repaint
            t0 = time.perf_counter()
            snap = scanner._capture_snapshot()
            dt = (time.perf_counter() - t0) * 1000
            ts.append(dt)
            scanner._buffer.add(snap)
            details.append((dt, snap.state.value, len(snap.elements)))

        for dt, state, n_el in details:
            print(f"     {ms(dt):>10} | state={state:<8} elements={n_el}")
        report("cycle", f"avg {ms(statistics.mean(ts))}, min {ms(min(ts))}, max {ms(max(ts))}  (budget {scanner._walk_budget_ms} ms walk, {scanner._vision_max_width} px vision)")
    except Exception as e:
        report("cycle", f"SKIP ({e})")


# --------------------------------------------------------------------------- #
# 5. organ_30 UIA walkers
# --------------------------------------------------------------------------- #
def bench_walkers():
    section("5. ORGAN_30 UIA WALKERS (foreground window)")
    try:
        import uiautomation as auto
        import win32gui
        auto.SetGlobalSearchTimeout(1.0)
        auto.InitializeUIAutomationInCurrentThread()
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)[:48]
        ctrl = auto.ControlFromHandle(hwnd)
        report("walk_target", f"target: '{title}'")

        def manual(c, depth=0, max_d=32):
            if depth > max_d:
                return
            try:
                for ch in c.GetChildren():
                    yield (ch, depth)
                    yield from manual(ch, depth + 1, max_d)
            except Exception:
                return

        def run_walker(fn, label):
            t0 = time.perf_counter()
            n, d = 0, 0
            for _c, dd in fn(ctrl):
                n += 1
                if dd > d:
                    d = dd
            el = (time.perf_counter() - t0) * 1000
            report(label, f"{label:<18}: {n:5d} nodes, max depth {d:2d}, {ms(el)}")
            return n, d, el

        run_walker(lambda c: manual(c, 0, 32), "manual walk")
        run_walker(lambda c: auto.WalkControl(c, includeTop=False, maxDepth=32), "native WalkControl")
        from core_organs.organ_30_app_scanner import _safe_walk_control
        run_walker(lambda c: _safe_walk_control(c, includeTop=False, maxDepth=32), "fixed wrapper")
    except Exception as e:
        report("walkers", f"SKIP ({e})")


# --------------------------------------------------------------------------- #
# 6. organ_30 deep scan end-to-end
# --------------------------------------------------------------------------- #
def bench_deep_scan():
    section("6. ORGAN_30 DEEP SCAN END-TO-END (quiet, foreground window)")
    try:
        import uiautomation as auto
        import win32gui
        from core_organs.organ_30_app_scanner import EyeAndBrainOrchestrator

        auto.InitializeUIAutomationInCurrentThread()
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)

        # deep_scan_unknown_app lives on EyeAndBrainOrchestrator (the class used
        # everywhere in production: organ_01, organ_10, master engine).
        scanner = EyeAndBrainOrchestrator()
        t0 = time.perf_counter()
        data = scanner.deep_scan_unknown_app(app_name="", target_hwnd=hwnd, quiet=True)
        elapsed = time.perf_counter() - t0

        stats = data.get("tree_stats", {})
        report("deep_scan", f"'{title[:40]}': {elapsed:.2f}s, "
                            f"{stats.get('nodes_walked', '?')} nodes walked, "
                            f"{data.get('total_controls', '?')} actionable, "
                            f"{data.get('total_elements', '?')} elements, "
                            f"max depth {stats.get('max_depth_seen', '?')}/{stats.get('walk_max_depth', '?')}")
        with_rules = data.get("ui_elements", [])
        if with_rules:
            e0 = with_rules[0]
            report("deep_scan_sample", f"sample element keys: {sorted(e0.keys())[:12]}")
    except Exception as e:
        report("deep_scan", f"SKIP ({e})")


# --------------------------------------------------------------------------- #
# 7. VerbAliasEngine.resolve throughput
# --------------------------------------------------------------------------- #
def bench_resolve():
    section("7. VERBALIASENGINE.RESOLVE THROUGHPUT")
    try:
        from organ_40_app_launcher import VerbAliasEngine, AppCatalog
        engine = VerbAliasEngine(AppCatalog())
        tasks = ["gmail", "open mail", "jot down a note", "take a screenshot",
                 "do some math", "open a spreadsheet", "write a letter",
                 "cook me dinner", "check task manager", "record the session"]
        for t in tasks:  # warmup
            engine.resolve(t)
        N = 200
        t0 = time.perf_counter()
        for _ in range(N):
            for t in tasks:
                engine.resolve(t)
        total = (time.perf_counter() - t0) * 1000
        per = total / (N * len(tasks))
        report("resolve", f"{N * len(tasks)} resolutions in {ms(total)}  ->  {per * 1000:.0f} us per task")
    except Exception as e:
        report("resolve", f"SKIP ({e})")


# --------------------------------------------------------------------------- #
# 8. DB element batch store
# --------------------------------------------------------------------------- #
def bench_db_batch():
    section("8. DB ELEMENT BATCH STORE (organ_24, 200 elements)")
    try:
        from organ_24_dap import DAPBridge
        dap = DAPBridge()
        # Keys must match DatabaseManager.upsert_element_profiles_batch:
        # element_name is the row key; unnamed elements are skipped.
        elements = [{
            "element_name": f"bench_el_{i}",
            "element_type": "button",
            "control_type": "ButtonControl",
            "visual_description": "benchmark element",
            "region_x": i, "region_y": i, "region_w": 40, "region_h": 20,
            "tab_location": "", "group_location": "",
            "spatial_context": "run_performance_benchmarks",
        } for i in range(200)]
        t0 = time.perf_counter()
        written = dap.store_elements_batch("__benchmark__", elements)
        elapsed = (time.perf_counter() - t0) * 1000
        if written:
            report("db_batch", f"{written} profiles written in {ms(elapsed)}  ->  {elapsed / max(1, written):.2f} ms/element (single round trip)")
        else:
            report("db_batch", f"call returned 0 in {ms(elapsed)} (DB unavailable or rejected - no crash)")
    except Exception as e:
        report("db_batch", f"SKIP ({e})")


# --------------------------------------------------------------------------- #
# 9. Enhanced compiler latency
# --------------------------------------------------------------------------- #
def bench_compiler():
    section("9. ENHANCED COMPILER LATENCY (compile_task)")
    try:
        from enhanced_brain_compiler import get_enhanced_compiler
        compiler = get_enhanced_compiler()
        compiler.compile_task("open gmail")  # warmup
        N = 5
        ts = []
        for _ in range(N):
            t0 = time.perf_counter()
            plan = compiler.compile_task("open gmail")
            ts.append((time.perf_counter() - t0) * 1000)
        report("compiler", f"compile_task('open gmail'): {ms(statistics.mean(ts))} avg over {N} runs, {len(plan.checkpoints)} checkpoints")
    except Exception as e:
        report("compiler", f"SKIP ({e})")


def main():
    print("=" * 78)
    print("HOJAIGA PERFORMANCE BENCHMARKS  (all numbers measured on this machine)")
    print("=" * 78)
    print(f"Python {sys.version.split()[0]} | platform {sys.platform}")
    try:
        from PIL import ImageGrab
        print(f"Screen: {ImageGrab.grab().size}")
    except Exception:
        pass

    bench_capture()
    bench_encode()
    bench_hash()
    bench_snapshot_cycle()
    bench_walkers()
    bench_deep_scan()
    bench_resolve()
    bench_db_batch()
    bench_compiler()

    section("SUMMARY (machine-readable)")
    print(json.dumps(RESULTS, indent=2))
    print("\nBenchmark complete.")


if __name__ == "__main__":
    main()
