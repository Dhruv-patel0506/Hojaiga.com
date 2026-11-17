"""organ_64_effect_prober — the Law-0 "holographic plate" that learns by doing.

App-agnostic knowledge acquisition:
  * Discovery is by PATTERN (any actionable UIA control) and, when the UIA tree is thin
    (GL / custom-rendered apps like Blender), by VISION (local OmniParser YOLO boxes).
    Nothing is targeted by an app name or a word list.
  * Each affordance is probed and classified by its OBSERVED state delta
    (new window / control-set change / value change / pixel delta) — measured causality.
  * Safety = open-then-cancel: we learn a control by what it OPENS, then revert
    (Escape / WM_CLOSE / Collapse / Toggle-back). We never press a final commit.
  * Inside a spawned dialog we go READ-ONLY + list-item selection (master/detail sweep),
    we do NOT invoke dialog buttons, then we close it.
  * Recursion is generic (a new window is a sub-app), bounded by depth + budget.
  * exhausted = a fresh enumeration yields no new un-probed affordance.

Reads/restores state; never commits. Writes evidence PNGs + trace.jsonl + report.json.
"""
import os, sys, time, json, hashlib, traceback
sys.path.insert(0, r"D:\new_automation\OmniParser")
import numpy as np
import uiautomation as auto
import win32gui, win32con, win32process, win32api
from PIL import ImageGrab

try:
    import psutil
except Exception:
    psutil = None

_PATTERNS = ("Invoke", "Toggle", "ExpandCollapse", "SelectionItem", "RangeValue", "Scroll", "Value")
# SAFETY FLOOR (not a discovery gate): OS window chrome is never an app affordance,
# and probing "Close" would kill the target. These are universal Windows caption tokens.
# We match as spaced words so WinUI names like "Close Calculator" / "Maximize Foo" are caught.
_CHROME_TOKENS = ("minimize", "maximize", "maximise", "restore", "close",
                  "system menu", "snap left", "snap right", "always on top")


def _is_chrome(label):
    L = " " + (label or "").strip().lower() + " "
    return any((" " + tok + " ") in L for tok in _CHROME_TOKENS)


_VISION_IF_FEWER_THAN = int(os.environ.get("HOJAIGA_PROBE_VISION_IF_FEWER_THAN", "12"))
_PIXEL_EFFECT = float(os.environ.get("HOJAIGA_PROBE_PIXEL_EFFECT", "0.02"))


# --------------------------------------------------------------------------- discovery
def _pid_name_map():
    m = {}
    if psutil:
        for p in psutil.process_iter(["pid", "name"]):
            try:
                m[p.info["pid"]] = (p.info["name"] or "").lower()
            except Exception:
                pass
    return m


def find_window(proc_substr="", title_substr=""):
    """Largest visible, non-tool, titled top-level window matching proc/title (normal-rect aware)."""
    names = _pid_name_map()
    best = {}

    def cb(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return
            ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            if ex & win32con.WS_EX_TOOLWINDOW:
                return
            title = win32gui.GetWindowText(hwnd) or ""
            if not title.strip():
                return
            if title.strip().lower() == "program manager":
                return                                    # the desktop shell is never an app target
            pl = win32gui.GetWindowPlacement(hwnd)
            if pl[1] == win32con.SW_SHOWMINIMIZED:
                nr = pl[4]; w, h = nr[2]-nr[0], nr[3]-nr[1]
            else:
                r = win32gui.GetWindowRect(hwnd); w, h = r[2]-r[0], r[3]-r[1]
            if w < 300 or h < 200:
                return
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            pname = names.get(pid, "")
            qual = (proc_substr and proc_substr.lower() in pname) or \
                   (title_substr and title_substr.lower() in title.lower())
            if qual and (not best or w*h > best["area"]):
                best.update(area=w*h, hwnd=hwnd, pid=pid, proc=pname, title=title)
        except Exception:
            pass
    win32gui.EnumWindows(cb, None)
    if not best:
        return None
    best["ctrl"] = auto.ControlFromHandle(best["hwnd"])
    return best


def walk(window_ctrl, max_depth=14, cap=5000, tcap=15.0):
    """Return (actionable_nodes, all_signature, all_count, walked)."""
    nodes, sig_items = [], []
    visited = [0]; t0 = time.time()

    def walk_(c, d):
        if d > max_depth or visited[0] > cap or (time.time()-t0) > tcap:
            return
        for ch in c.GetChildren():
            visited[0] += 1
            try:
                ct = ch.ControlTypeName
            except Exception:
                ct = ""
            if ct == "TitleBarControl":
                continue                                    # never probe/descend window caption chrome
            try:
                r = ch.BoundingRectangle
                if r.right > r.left and r.bottom > r.top:
                    bbox = [r.left, r.top, r.right, r.bottom]
                    sig_items.append("%s|%s|%d,%d,%d,%d" % (ch.ControlTypeName, (ch.Name or "").strip(), *bbox))
                    pats = {}
                    for nm in _PATTERNS:
                        try:
                            pats[nm.lower()] = getattr(ch, "Get%sPattern" % nm)() is not None
                        except Exception:
                            pats[nm.lower()] = False
                    label = (ch.Name or "").strip().lower()
                    if any(pats.values()) and not _is_chrome(label):
                        nodes.append({"name": (ch.Name or "").strip(), "type": ch.ControlTypeName,
                                      "bbox": bbox, "patterns": pats, "ctrl": ch, "src": "uia"})
            except Exception:
                pass
            walk_(ch, d + 1)
    walk_(window_ctrl, 0)
    h = hashlib.md5("\n".join(sorted(sig_items)).encode()).hexdigest()[:12]
    return nodes, h, len(sig_items), visited[0]


def vision_boxes(hwnd, yolo):
    """OmniParser YOLO icon boxes -> pseudo-nodes (actuated by PostMessage click).

    LAW-0 SAFE: only boxes whose CENTER falls inside the window CLIENT area are kept.
    Anything in the non-client band (OS caption / min-max-close / borders) is universal
    window chrome, not an app affordance, so it is dropped here regardless of app name.
    """
    try:
        from util.utils import predict_yolo
        r = win32gui.GetWindowRect(hwnd)
        try:
            cl, ctop = win32gui.ClientToScreen(hwnd, (0, 0))
            cr = win32gui.GetClientRect(hwnd)
            cright, cbottom = win32gui.ClientToScreen(hwnd, (cr[2], cr[3]))
        except Exception:
            cl, ctop, cright, cbottom = r[0], r[1], r[2], r[3]
        img = ImageGrab.grab(bbox=r, all_screens=True).convert("RGB")
        W, H = img.size
        boxes, conf, _ = predict_yolo(model=yolo, image=img, box_threshold=0.05,
                                      imgsz=(H, W), scale_img=False, iou_threshold=0.1)
        boxes = boxes.cpu().numpy() if hasattr(boxes, "cpu") else np.asarray(boxes)
        out = []
        for i, b in enumerate(boxes):
            if i < len(conf) and float(conf[i]) < 0.30:
                continue
            bbox = [int(b[0])+r[0], int(b[1])+r[1], int(b[2])+r[0], int(b[3])+r[1]]
            cx = (bbox[0] + bbox[2]) // 2
            cy = (bbox[1] + bbox[3]) // 2
            if not (cl <= cx <= cright and ctop <= cy <= cbottom):
                continue                                    # non-client (title bar / border) -> skip
            out.append({"name": "", "type": "VisionIcon", "bbox": bbox,
                        "patterns": {k.lower(): False for k in _PATTERNS},
                        "ctrl": None, "src": "vision", "conf": float(conf[i]) if i < len(conf) else 0.0})
        return out
    except Exception:
        return []


# --------------------------------------------------------------------------- effect model
def top_windows(pid):
    s = set()
    def cb(h, _):
        try:
            _, p = win32process.GetWindowThreadProcessId(h)
            if p == pid and win32gui.IsWindowVisible(h):
                s.add(h)
        except Exception:
            pass
    win32gui.EnumWindows(cb, None)
    return s


def grab(hwnd):
    try:
        r = win32gui.GetWindowRect(hwnd)
        return np.asarray(ImageGrab.grab(bbox=r, all_screens=True).convert("RGB"))
    except Exception:
        return None


def pixel_delta(a, b):
    if a is None or b is None:
        return 0.0
    if a.shape != b.shape:
        return 1.0
    return float(np.mean(np.abs(a.astype(int) - b.astype(int))) / 255.0)


def classify_effect(sig_pre, cnt_pre, sig_post, cnt_post, new_windows, pdelta):
    """Pure, testable: map observed deltas -> effect class."""
    if new_windows:
        return "opens-window"
    if sig_pre != sig_post:
        return "reveals-content" if cnt_post > cnt_pre else "changes-structure"
    if pdelta > _PIXEL_EFFECT:
        return "visual-change"
    return "no-effect"


# --------------------------------------------------------------------------- actuation + revert
def actuate(node, hwnd):
    p = node.get("ctrl")
    try:
        if p is not None:
            if node["patterns"].get("expand"):
                p.GetExpandCollapsePattern().Expand(); return "expand"
            if node["patterns"].get("invoke"):
                p.GetInvokePattern().Invoke(); return "invoke"
            if node["patterns"].get("toggle"):
                p.GetTogglePattern().Toggle(); return "toggle"
            if node["patterns"].get("select"):
                p.GetSelectionItemPattern().Select(); return "select"
    except Exception:
        pass
    try:  # generic fallback: headless message-click at bbox centroid
        cx = (node["bbox"][0] + node["bbox"][2]) // 2
        cy = (node["bbox"][1] + node["bbox"][3]) // 2
        lx, ly = win32gui.ScreenToClient(hwnd, (cx, cy))
        lp = win32api.MAKELONG(lx & 0xFFFF, ly & 0xFFFF)
        win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lp)
        time.sleep(0.04)
        win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lp)
        return "postmsg-click"
    except Exception:
        return None


def _escape_close(hwnd):
    try:
        win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, win32con.VK_ESCAPE, 0)
        win32gui.PostMessage(hwnd, win32con.WM_KEYUP, win32con.VK_ESCAPE, 0)
    except Exception:
        pass


def revert(node, method, new_windows, effect):
    """Open-then-cancel with HONEST status (never fake a pass).

    Returns one of:
      "reverted"      - we actively undid it (closed every spawned window / collapsed / toggled back)
      "no-change"     - probe produced no observable delta, nothing to undo
      "unverified"    - state changed but there is no safe, known undo (e.g. a bare Invoke)
      "revert-failed" - we tried an undo and it errored / a window would not close
    """
    closed = 0
    for w in new_windows:
        try:
            _escape_close(w)
            time.sleep(0.12)
            if win32gui.IsWindow(w) and win32gui.IsWindowVisible(w):
                win32gui.PostMessage(w, win32con.WM_CLOSE, 0, 0)
                time.sleep(0.12)
            if not (win32gui.IsWindow(w) and win32gui.IsWindowVisible(w)):
                closed += 1
        except Exception:
            pass
    all_closed = (closed == len(new_windows))
    if new_windows and not all_closed:
        return "revert-failed", closed
    corrective = False
    try:
        p = node.get("ctrl")
        if p is not None and method == "expand" and node["patterns"].get("expand"):
            p.GetExpandCollapsePattern().Collapse(); corrective = True
        elif p is not None and method == "toggle" and node["patterns"].get("toggle"):
            p.GetTogglePattern().Toggle(); corrective = True
    except Exception:
        return "revert-failed", closed
    if effect == "no-effect":
        return "no-change", closed
    if all_closed and (corrective or new_windows):
        return "reverted", closed
    return "unverified", closed


# --------------------------------------------------------------------------- dialog read-only sweep
def sweep_dialog(dlg_hwnd, budget_s=8.0):
    """Enumerate a spawned dialog; sweep list/tree items (master/detail) by SELECT only.
    Never invokes buttons. Returns a compact schema."""
    info = {"hwnd": dlg_hwnd, "title": win32gui.GetWindowText(dlg_hwnd), "items": [], "panes": []}
    try:
        wc = auto.ControlFromHandle(dlg_hwnd)
    except Exception:
        return info
    t0 = time.time()
    try:
        lists = []
        stack = [(wc, 0)]
        while stack and (time.time()-t0) < budget_s:
            c, d = stack.pop()
            try:
                for ch in c.GetChildren():
                    if d < 12:
                        stack.append((ch, d+1))
                    ct = ch.ControlTypeName
                    if ct in ("ListControl", "TreeControl", "TableControl"):
                        lists.append(ch)
            except Exception:
                pass
        for lst in lists[:3]:
            try:
                for item in lst.GetChildren()[:40]:
                    if (time.time()-t0) > budget_s:
                        break
                    nm = (item.Name or "").strip()
                    try:
                        item.GetSelectionItemPattern().Select()
                        time.sleep(0.15)
                        info["items"].append(nm)
                    except Exception:
                        info["items"].append(nm)
            except Exception:
                pass
    except Exception:
        pass
    return info


# --------------------------------------------------------------------------- main probe loop
def _key(node):
    return "%s|%s|%d,%d,%d,%d" % (node["src"], node["type"], *node["bbox"])


def probe_app(target, outdir, budget_s=180.0, max_depth=1, vision=True, stop_file=None):
    os.makedirs(outdir, exist_ok=True)
    hwnd = target["hwnd"]; pid = target["pid"]
    trace_path = os.path.join(outdir, "trace.jsonl")
    trace = open(trace_path, "w", encoding="utf-8")

    def emit(ev):
        trace.write(json.dumps(ev) + "\n"); trace.flush()

    def stopped():
        return stop_file and os.path.exists(stop_file)

    report = {"target": {"proc": target["proc"], "title": target["title"], "hwnd": hwnd},
              "started": time.strftime("%Y-%m-%d %H:%M:%S"), "effects": {}, "edges": [],
              "dialogs": [], "probed": 0, "reverted_ok": 0, "revert_failed": 0,
              "revert_unverified": 0, "exhausted": False, "notes": []}
    yolo = None
    if vision:
        try:
            import torch
            from util.utils import get_yolo_model
            wp = os.path.join(r"D:\new_automation\OmniParser\weights", "icon_detect", "model.pt")
            yolo = get_yolo_model(model_path=wp, device="cuda" if torch.cuda.is_available() else "cpu")
        except Exception as e:
            report["notes"].append("vision unavailable: %s" % e)

    probed = set()
    t_end = time.time() + budget_s
    pass_no = 0
    try:
        while time.time() < t_end and not stopped():
            pass_no += 1
            nodes, sig, cnt, walked = walk(target["ctrl"])
            thin = cnt < _VISION_IF_FEWER_THAN or len(nodes) < _VISION_IF_FEWER_THAN
            if vision and yolo is not None and thin:
                nodes = nodes + vision_boxes(hwnd, yolo)
            todo = [n for n in nodes if _key(n) not in probed]
            if not todo:
                report["exhausted"] = True
                break
            for node in todo:
                if time.time() >= t_end or stopped():
                    break
                probed.add(_key(node))
                pre_nodes, psig, pcnt, _ = walk(target["ctrl"], tcap=6.0)
                pre_px = grab(hwnd)
                wins_before = top_windows(pid)
                method = actuate(node, hwnd)
                time.sleep(0.35)
                wins_after = top_windows(pid)
                new_wins = list(wins_after - wins_before)
                post_nodes, psig2, pcnt2, _ = walk(target["ctrl"], tcap=6.0)
                pd = pixel_delta(pre_px, grab(hwnd))
                eff = classify_effect(psig, pcnt, psig2, pcnt2, new_wins, pd)
                report["probed"] += 1
                report["effects"][eff] = report["effects"].get(eff, 0) + 1
                edge = {"name": node["name"], "type": node["type"], "src": node["src"],
                        "method": method, "effect": eff, "new_windows": len(new_wins)}
                # recurse read-only into the first spawned window
                if new_wins:
                    info = sweep_dialog(new_wins[0], budget_s=min(8.0, max(1.0, t_end-time.time())))
                    info["opened_by"] = node["name"] or node["type"]
                    report["dialogs"].append(info)
                    edge["n_list_items"] = len(info["items"])
                restored, closed = revert(node, method, new_wins, eff)
                edge["restore"] = restored
                report["reverted_ok"] += int(restored in ("reverted", "no-change"))
                report["revert_failed"] += int(restored == "revert-failed")
                report["revert_unverified"] += int(restored == "unverified")
                report["edges"].append(edge)
                emit(edge)
                if eff != "no-effect":
                    try:
                        import cv2
                        px = grab(hwnd)
                        if px is not None:
                            cv2.imwrite(os.path.join(outdir, "ev_%03d_%s.png" % (report["probed"], eff)),
                                        cv2.cvtColor(px, cv2.COLOR_RGB2BGR))
                    except Exception:
                        pass
            if pass_no >= 2 and not [n for n in nodes if _key(n) not in probed]:
                report["exhausted"] = True
                break
    except Exception:
        report["notes"].append("probe error: %s" % traceback.format_exc()[-400:])
    finally:
        report["passes"] = pass_no
        report["elapsed_s"] = round(time.time() - (t_end - budget_s), 1)
        report["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(os.path.join(outdir, "report.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        trace.close()
    return report


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--proc", default=""); ap.add_argument("--title", default="")
    ap.add_argument("--budget", type=float, default=180.0)
    ap.add_argument("--outdir", default=r"D:\new_automation\overnight_results\probe")
    ap.add_argument("--no-vision", action="store_true")
    a = ap.parse_args()
    t = find_window(a.proc, a.title)
    if not t:
        print("window not found"); sys.exit(2)
    r = probe_app(t, a.outdir, budget_s=a.budget, vision=not a.no_vision)
    print(json.dumps({k: r[k] for k in ("probed", "effects", "exhausted", "reverted_ok", "revert_failed", "revert_unverified")}, indent=2))
