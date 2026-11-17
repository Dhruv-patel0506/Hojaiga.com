# =========================================================================================================== the optional icon-detector rung
def run_pr39() -> TestOutcome:
    """PR39: the optional icon-detector rung - it can RE-ADD a control the CV tier lost (end to end through the sweeper), but never adds a box that is already a candidate, an empty cell, a speck, a screen-sized box or a low-confidence guess; off switch and availability are honest"""
    from core_organs.professor import candidates as CD, icon_detector as ID, sweeper, synth
    from core_organs.professor.schema import Box
    img, truth, _ = synth.render_app("light", 1.0)
    cs = CD.detect(img, 1.0, ocr=True, budget_s=30)
    icons = [c for c in cs.candidates if c.kind == "icon" and 14 <= c.box.w <= 60]
    victim, victim2, keep = icons[len(icons) // 3], icons[len(icons) // 2], icons[-1]
    cs.candidates = [c for c in cs.candidates if c is not victim and c is not victim2]
    ink = CD.ink_mask(np.asarray(img.convert("L")), 1.0)
    blank = None
    for y in range(40, img.height - 60, 24):
        for x in range(40, img.width - 60, 24):
            b = Box(x, y, x + 22, y + 22)
            if CD.ink_density(ink, b) == 0 and not any(b.iou(c.box) > 0 for c in cs.candidates):
                blank = b
                break
        if blank:
            break
    boxes = [(victim.box, 0.9), (Box(keep.box.x1 + 1, keep.box.y1, keep.box.x2 + 1, keep.box.y2), 0.95), (blank, 0.8), (Box(5, 5, 9, 9), 0.9), (Box(0, 0, float(img.width), float(img.height)), 0.9), (victim2.box, 0.1)]
    n0 = len(cs.candidates)
    rep = ID.augment(cs, img, 1.0, ink, conf=0.3, detector=lambda im: boxes)
    new = cs.candidates[n0:]
    # end to end: the sweeper loses `victim` in its CV tier, the (stubbed) detector gives it back
    real_detect, real_det = CD.detect, ID.detect

    def lossy(im, scale=1.0, ocr=True, budget_s=25.0, roi=None):
        r = real_detect(im, scale, ocr, budget_s, roi)
        r.candidates = [c for c in r.candidates if not (c.kind == "icon" and c.box.iou(victim.box) > 0.5)]
        return r

    ID_available = ID.available()
    CD.detect = lossy                                                # type: ignore[assignment]
    ID.detect = lambda im, conf=0.3, imgsz=1280: [(victim.box, 0.9)]  # type: ignore[assignment]
    try:
        opt0 = sweeper.ScanOptions.for_mode("quick")
        opt0.use_uia = opt0.knowledge = opt0.learn = False
        opt0.yolo = False
        sm0, _f = sweeper.scan(image=img, options=opt0, app_key="synth")
        opt1 = sweeper.ScanOptions.for_mode("quick")
        opt1.use_uia = opt1.knowledge = opt1.learn = False
        opt1.yolo = True
        sm1, _f = sweeper.scan(image=img, options=opt1, app_key="synth")
    finally:
        CD.detect, ID.detect = real_detect, real_det
    tb = victim.box
    covers = lambda sm: any(max(e.bbox.overlap_frac(tb), tb.overlap_frac(e.bbox)) > 0.5 for e in sm.elements)
    old = os.environ.get("HOJAIGA_PROF_YOLO")
    os.environ["HOJAIGA_PROF_YOLO"] = "0"
    try:
        off = ID.augment(cs, img, 1.0, ink)
        avail_off = ID.available()
    finally:
        if old is None:
            os.environ.pop("HOJAIGA_PROF_YOLO", None)
        else:
            os.environ["HOJAIGA_PROF_YOLO"] = old
    checks = {"lost_control_re_added": rep["added"] == 1 and len(new) == 1 and new[0].box.iou(victim.box) > 0.9 and new[0].flags == ["yolo"], "overlap_empty_speck_huge_lowconf_all_rejected": rep["added"] == 1 and rep["seen"] == 6,
              "sweeper_without_it_misses_the_control": not covers(sm0) and not any(t.startswith("yolo") for t in sm0.tiers_used), "sweeper_with_it_finds_the_control": covers(sm1) and any(t == "yolo:+1" for t in sm1.tiers_used),
              "off_switch_reported": off.get("skipped", "").startswith("switched off") and avail_off[0] is False, "availability_is_honest": ID_available[0] or bool(ID_available[1]), "default_is_off_for_scans": not sweeper.ScanOptions().yolo or os.environ.get("HOJAIGA_PROF_YOLO_DEFAULT") == "1"}
    return _verdict(checks, f"augment {rep}; blank cell {blank.to_list() if blank else None}; sweeper tiers with it: {[t for t in sm1.tiers_used if t.startswith(('cv', 'yolo'))]}; available={ID_available}")


def run_pl11() -> TestOutcome:
    """PL11: the REAL OmniParser icon detector on a real UIA-blind editor (Blender capture) - it must add real controls the CV tier missed, quickly and on the CPU, and the sweeper must report the rung"""
    from core_organs.professor import candidates as CD, icon_detector as ID, sweeper
    shot = os.path.join("D:/new_automation", "scratch", "blender_cap_0.png")
    ok, why = ID.available()
    if not os.path.isfile(shot) or not ok:
        return TestOutcome(True, f"detector or capture unavailable: {why or 'no Blender capture'}", env_blocked=True)
    img = Image.open(shot).convert("RGB")
    t0 = time.time()
    cs = CD.detect(img, 1.0, ocr=True, budget_s=40)
    ink = CD.ink_mask(np.asarray(img.convert("L")), 1.0)
    n_cv = len(cs.candidates)
    t1 = time.time()
    rep = ID.augment(cs, img, 1.0, ink, conf=0.3, budget_s=120)
    dt = time.time() - t1
    rep2 = ID.augment(cs, img, 1.0, ink, conf=0.3, budget_s=120)                      # second call: the model is resident, nothing new to add
    t2 = time.time()
    ID.detect(img, 0.3)
    warm = time.time() - t2
    opt = sweeper.ScanOptions.for_mode("quick")
    opt.use_uia = opt.knowledge = opt.learn = False
    opt.yolo = True
    sm, _f = sweeper.scan(image=img, options=opt, app_key="blender")
    checks = {"adds_real_controls": rep["added"] >= 8, "all_new_boxes_control_sized_with_ink": all(8 <= c.box.w <= 140 and CD.ink_density(ink, c.box) >= 0.03 for c in cs.candidates[n_cv:]), "nothing_new_the_second_time": rep2["added"] == 0,
              "fast_once_loaded_on_cpu": warm < 5.0, "sweeper_reports_the_rung": any(t.startswith("yolo:+") for t in sm.tiers_used)}
    return _verdict(checks, f"CV candidates {n_cv}; detector added {rep['added']} of {rep['seen']} boxes (first call incl. model load {dt:.1f}s, warm {warm:.1f}s); sweeper tiers {[t for t in sm.tiers_used if t.startswith(('cv', 'yolo'))]}",
                    {"added": rep["added"], "warm_s": round(warm, 2)})


