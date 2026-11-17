import ast
import io


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:90]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


patch("D:/new_automation/All codes/core_organs/professor/capture.py", [
    (r'''def exclude_from_capture(hwnd: int) -> bool:''', r'''def grab_composite(hwnd: int, pops: Sequence[int]) -> Optional[Frame]:
    """The window PLUS its open pop-ups / dialogs, each rendered from its own surface (so it works for windows parked off-screen) and placed where it sits relative to the window: the picture
    a person would see. A pop-up that cannot be rendered (blank) is left out."""
    main = grab_window(hwnd, isolated=True)
    if main is None:
        return None
    if not pops:
        return main
    wb = window_info(hwnd).box
    parts: List[Tuple[Image.Image, Box]] = [(main.image, wb)]
    boxes = [wb]
    for p in pops:
        try:
            pb = window_info(p).box
            if not pb.valid or pb.w < 8 or pb.h < 8:
                continue
            im = _printwindow(p)
            if im is None or _is_blank(im):
                continue
            parts.append((im, pb))
            boxes.append(pb)
        except Exception:
            continue
    if len(parts) == 1:
        return main
    x1, y1 = min(b.x1 for b in boxes), min(b.y1 for b in boxes)
    x2, y2 = max(b.x2 for b in boxes), max(b.y2 for b in boxes)
    if (x2 - x1) > 6000 or (y2 - y1) > 6000:
        return main
    canvas = Image.new("RGB", (int(x2 - x1), int(y2 - y1)), (24, 24, 24))
    for im, b in parts:
        canvas.paste(im, (int(b.x1 - x1), int(b.y1 - y1)))
    return Frame(canvas, origin=(int(x1), int(y1)), kind="window", hwnd=hwnd, dpi_scale=main.dpi_scale, via=(main.via or "window") + f"+{len(parts) - 1}popups")


def exclude_from_capture(hwnd: int) -> bool:'''),
])

patch("D:/new_automation/All codes/core_organs/professor/sweeper.py", [
    (r'''    pops = popup_hwnds(hwnd) if include_popups else []
    if not pops or isolated:
        return grab_window(hwnd, isolated=isolated), hwnd, pops''', r'''    pops = popup_hwnds(hwnd) if include_popups else []
    if pops and not isolated:
        try:
            wb = window_info(hwnd).box
            if wb.overlap_frac(virtual_screen()) < 0.5:                       # parked off-screen: nothing to screen-grab; render each window from its own surface
                fr = grab_composite(hwnd, pops)
                if fr is not None:
                    return fr, hwnd, pops
        except Exception:
            pass
    if not pops or isolated:
        return grab_window(hwnd, isolated=isolated), hwnd, pops'''),
])

patch("D:/new_automation/All codes/core_organs/professor/probe.py", [
    (r'''        fr = grab_window(hwnd, isolated=True)
        img = fr.image.convert("RGB")''', r'''        try:
            fr = grab_composite(hwnd, hin.popup_windows(hwnd)[:6]) if popups else grab_window(hwnd, isolated=True)
        except Exception:
            fr = grab_window(hwnd, isolated=True)
        img = fr.image.convert("RGB")'''),
])
print("ok")
