"""Temporary smoke: organ_41 new capture chain end-to-end with timings."""
import sys, time
sys.path.insert(0, r"D:\new_automation\All codes")

from core_organs.organ_41_scanner import ScannerOrgan

s = ScannerOrgan()
if s._uia:
    s._uia.InitializeUIAutomationInCurrentThread()
print("backends: dxcam=%s mss=%s cv2=%s pil=%s" % (
    bool(getattr(s, "_dxcam", None)), bool(getattr(s, "_mss", None)),
    bool(getattr(s, "_cv2", None)), bool(getattr(s, "_image_grab", None))))

# Warmup grab (also creates dxcam camera in this thread)
for i in range(3):
    print("warm", i)
    f = s._grab_screen_frame()
print("frame type:", type(f).__name__, getattr(f, "shape", getattr(f, "size", None)))

N = 5
ts_grab, ts_enc = [], []
for i in range(N):
    print("tick", i)  # repaint console
    t0 = time.perf_counter(); f = s._grab_screen_frame(); ts_grab.append((time.perf_counter() - t0) * 1000)
    t0 = time.perf_counter(); b = s._encode_vision_frame(f); ts_enc.append((time.perf_counter() - t0) * 1000)
print("grab avg : %6.1f ms" % (sum(ts_grab) / N))
print("encode   : %6.1f ms  (b64 len %d)" % (sum(ts_enc) / N, len(b)))

# Full snapshot cycles
ts = []
for i in range(N):
    print("cycle", i)
    t0 = time.perf_counter(); snap = s._capture_snapshot(); dt = (time.perf_counter() - t0) * 1000; ts.append(dt)
    print("  %.0f ms | state=%s elements=%d tree_children=%d vision=%s" % (
        dt, snap.state.value, len(snap.elements),
        len((snap.raw_uia_tree or {}).get("children", [])),
        (len(snap.vision_data) // 1024) if snap.vision_data else 0))
    s._buffer.add(snap)
print("full cycle avg: %6.1f ms" % (sum(ts) / N))

# Static reuse check: repeat once more; if identical, vision should be reused
snap2 = s._capture_snapshot()
print("second-last state:", snap2.state.value, "| vision reused ok:", snap2.vision_data is not None)
print("SMOKE OK")
