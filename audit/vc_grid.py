"""Which layout-signature grid separates 'same screen, another recording' from 'another screen of the same app'?"""
import sys, itertools
sys.path.insert(0, r"D:\new_automation\All codes")
import numpy as np, cv2
from core_organs import si_tests_consolidate as T
from core_organs.harvest import consolidate as C

STYLES = [dict(size=(854, 480), theme="dark", pad=(0, 0), webcam=False), dict(size=(1280, 720), theme="light", pad=(80, 0), webcam=True),
          dict(size=(640, 360), theme="dark", pad=(0, 18), webcam=True), dict(size=(1100, 620), theme="light", pad=(0, 0), webcam=False)]
STATES = ["home", "file_menu", "settings", "advanced", "export", "layers"]
imgs = {}
for st in STATES:
    for i, s in enumerate(STYLES):
        W, H = s["size"]
        im = T.frame_of(T.render(st, s["theme"], (300 + 40 * i, 200 + 30 * i)), W, H, s["pad"], s["webcam"])
        imgs[(st, i)] = C._to_gray(im)


def sig(g, grid, blur):
    box = C.crop_box(g)
    c = C._canvas(g, box)
    e = cv2.Canny(cv2.GaussianBlur(c, (blur, blur), 0), 50, 150).astype(np.float32) / 255.0
    cells = cv2.resize(e, grid, interpolation=cv2.INTER_AREA)
    v = np.sqrt(cells).ravel()
    return v / max(np.linalg.norm(v), 1e-6)


for grid in [(24, 14), (16, 9), (12, 7), (8, 5)]:
    for blur in (3, 7):
        S = {k: sig(g, grid, blur) for k, g in imgs.items()}
        same, diff = [], []
        for a, b in itertools.combinations(S, 2):
            c = C.cos(S[a], S[b])
            (same if a[0] == b[0] else diff).append(c)
        near = []     # states that differ only by a small region
        for st2 in ("file_menu", "layers", "export"):
            for i in range(len(STYLES)):
                for j in range(len(STYLES)):
                    near.append(C.cos(S[("home", i)], S[(st2, j)]))
        print(f"grid={grid} blur={blur}: same-state cos min={min(same):.3f} mean={np.mean(same):.3f} | different-state max={max(diff):.3f} mean={np.mean(diff):.3f} | home-vs-nearby-state max={max(near):.3f}")
