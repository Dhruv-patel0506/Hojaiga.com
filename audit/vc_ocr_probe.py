import sys, os
sys.path.insert(0, r"D:\new_automation\All codes")
import numpy as np, cv2, pytesseract
from core_organs.harvest import consolidate as C

g = C.AppGraph.load("webapp:excalidraw.com")
ids = [int(x) for x in sys.argv[1:]] or [92, 140, 91]
for eid in ids:
    e = g.edges[eid]
    print("== edge", eid, "support", g.support(e), "videos", e["videos"])
    for o in e["obs"][:8]:
        im = cv2.imdecode(np.fromfile(o["post"], dtype=np.uint8), cv2.IMREAD_COLOR)
        H, W = im.shape[:2]
        cx0, cy0, cx1, cy1 = o["crop_px"]
        p = o["primary"]
        x0, y0 = int(cx0 + p[0] * (cx1 - cx0)), int(cy0 + p[1] * (cy1 - cy0))
        x1, y1 = int(cx0 + p[2] * (cx1 - cx0)), int(cy0 + p[3] * (cy1 - cy0))
        crop = im[max(0, y0 - 2):y1 + 2, max(0, x0 - 2):x1 + 2]
        if crop.size == 0:
            continue
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        if gray.mean() < 110:
            gray = 255 - gray
        txt = pytesseract.image_to_string(gray, config="--psm 6").strip().replace("\n", " | ")
        print("  ", o["video"][:6], "t=%.0f" % o["t"], "crop", crop.shape[:2], "->", repr(txt[:90]))
