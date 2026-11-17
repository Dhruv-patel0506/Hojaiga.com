import ast
import io


def patch(path, edits):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in edits:
        assert old in s, old[:80]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


B = "D:/new_automation/All codes/core_organs/professor/"
patch(B + "sweeper.py", [
    ("    cancel: Optional[Callable[[], bool]] = None   # background upgrades stop naming as soon as a question is waiting\n",
     "    cancel: Optional[Callable[[], bool]] = None   # background upgrades stop naming as soon as a question is waiting\n"
     "    yolo: bool = field(default_factory=lambda: os.environ.get(\"HOJAIGA_PROF_YOLO_DEFAULT\", \"0\") == \"1\")   # optional icon-detector rung (professor.icon_detector): only where the tree is sparse\n"),
    ("""    sm.timings["candidates"] = round(time.time() - ts, 2)
    sm.timings.update({f"cv.{k}": v for k, v in cs.timings.items() if k != "total"})
""", """    if opt.yolo and len(uia_els) < 15:                                    # a tree names the controls itself; the detector is for UIA-blind applications
        try:
            from . import icon_detector as ID
            info = ID.augment(cs, img, scale, None, budget_s=left())
            if info.get("added"):
                sm.tiers_used.append(f"yolo:+{info['added']}")
            elif info.get("skipped"):
                sm.tiers_skipped.append("yolo:" + str(info["skipped"])[:80])
            sm.timings["yolo"] = info.get("seconds", 0.0)
        except Exception as exc:
            sm.tiers_skipped.append(f"yolo:{type(exc).__name__}")
    sm.timings["candidates"] = round(time.time() - ts, 2)
    sm.timings.update({f"cv.{k}": v for k, v in cs.timings.items() if k != "total"})
"""),
])
patch(B + "session.py", [
    ("                opt = sweeper.ScanOptions.for_mode(self.upgrade_mode)\n", "                opt = sweeper.ScanOptions.for_mode(self.upgrade_mode)\n                opt.yolo = True                              # the background upgrade may use the icon detector where the app has no tree\n"),
])
print("yolo rung wired")
