"""PV1's eyes, rung by rung: which capture method actually gets the pixels of a window that only paints WM_PAINT?

The fixture (si_test_support.PaintedDialog) draws its message and its two buttons with raw GDI in WM_PAINT and
exposes nothing else. PrintWindow(PW_RENDERFULLCONTENT) hands back the title bar and a BLANK client (measured:
the saved PNG is white with black margins), so OCR reads 0 words and PV1 has failed since it was written.

Four candidate rungs, all headless, judged by what Tesseract can read out of them.
"""
import ctypes
import sys
import time

sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")

from core_organs import si_test_support as sup          # noqa: E402
from core_organs import headless_input as hin           # noqa: E402
from core_organs import organ_24_dap as dap             # noqa: E402

_u32 = ctypes.windll.user32
_g32 = ctypes.windll.gdi32
SRCCOPY = 0x00CC0020


def _grab(hdc_src, x, y, w, h):
    """BitBlt a rectangle out of an arbitrary DC into a PIL image (RGB)."""
    from PIL import Image
    mdc = _g32.CreateCompatibleDC(hdc_src)
    bmp = _g32.CreateCompatibleBitmap(hdc_src, w, h)
    old = _g32.SelectObject(mdc, bmp)
    try:
        _g32.BitBlt(mdc, 0, 0, w, h, hdc_src, x, y, SRCCOPY)

        class BIH(ctypes.Structure):
            _fields_ = [("biSize", ctypes.c_uint), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                        ("biPlanes", ctypes.c_ushort), ("biBitCount", ctypes.c_ushort),
                        ("biCompression", ctypes.c_uint), ("biSizeImage", ctypes.c_uint),
                        ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
                        ("biClrUsed", ctypes.c_uint), ("biClrImportant", ctypes.c_uint)]
        bmi = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = (ctypes.c_ubyte * (w * h * 4))()
        if not _g32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bmi), 0):
            return None
        return Image.frombuffer("RGBA", (w, h), bytes(buf), "raw", "BGRA", 0, 1).convert("RGB")
    finally:
        _g32.SelectObject(mdc, old)
        _g32.DeleteObject(bmp)
        _g32.DeleteDC(mdc)


def printwindow(hwnd, flags):
    from PIL import Image
    r = hin.wt.RECT()
    _u32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    wdc = _u32.GetWindowDC(hwnd)
    mdc = _g32.CreateCompatibleDC(wdc)
    bmp = _g32.CreateCompatibleBitmap(wdc, w, h)
    old = _g32.SelectObject(mdc, bmp)
    try:
        ok = _u32.PrintWindow(hwnd, mdc, flags)
        img = _grab(mdc, 0, 0, w, h)
        return ok, img
    finally:
        _g32.SelectObject(mdc, old)
        _g32.DeleteObject(bmp)
        _g32.DeleteDC(mdc)
        _u32.ReleaseDC(hwnd, wdc)


def window_bitblt(hwnd):
    r = hin.wt.RECT()
    _u32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    wdc = _u32.GetWindowDC(hwnd)
    try:
        return _grab(wdc, 0, 0, w, h)
    finally:
        _u32.ReleaseDC(hwnd, wdc)


def screen_bitblt(hwnd):
    r = hin.wt.RECT()
    _u32.GetWindowRect(hwnd, ctypes.byref(r))
    sdc = _u32.GetDC(0)                                    # the screen
    try:
        return _grab(sdc, r.left, r.top, r.right - r.left, r.bottom - r.top)
    finally:
        _u32.ReleaseDC(0, sdc)


def report(tag, img):
    if img is None:
        print(f"  {tag:26} -> None")
        return
    px = list(img.convert("L").resize((60, 40)).getdata())
    mean = sum(px) / len(px)
    var = (sum((v - mean) ** 2 for v in px) / len(px)) ** 0.5
    import pytesseract
    big = img.resize((img.width * 2, img.height * 2)) if max(img.size) < 900 else img
    try:
        flat = (pytesseract.image_to_string(big) or "").lower()
        n_words = len([w for w in flat.split() if w.strip()])
    except Exception as exc:  # noqa: BLE001
        flat, n_words = f"<ocr-error {type(exc).__name__}>", -1
    print(f"  {tag:26} {img.size} mean={mean:.0f} sd={var:.0f} ocr_words={n_words} "
          f"has_text={'allow access' in flat and 'not now' in flat}")
    img.save(rf"D:\new_automation\scratch\_pv1_{tag.replace(' ', '_')}.png")


def main() -> int:
    d = sup.PaintedDialog("Heads up", ["Try the new dashboard today.", "It only takes a minute."],
                          [("Allow access", (40, 150, 250, 205)), ("Not now", (290, 150, 500, 205))],
                          sysmenu=False).start()
    try:
        if not d.hwnd:
            print("fixture window never appeared")
            return 1
        hin._u32.RedrawWindow(d.hwnd, None, None, 0x0001 | 0x0004 | 0x0100 | 0x0080)
        time.sleep(1.2)
        print(f"hwnd={d.hwnd:#x} visible={bool(_u32.IsWindowVisible(d.hwnd))} rect={_rect(d.hwnd)}")
        ok, img = printwindow(d.hwnd, 2)
        print(f"PrintWindow(RENDERFULLCONTENT) returned {ok}")
        report("printwindow_full", img)
        ok0, img0 = printwindow(d.hwnd, 0)
        print(f"PrintWindow(0) returned {ok0}")
        report("printwindow_classic", img0)
        report("windowdc_bitblt", window_bitblt(d.hwnd))
        report("screen_bitblt", screen_bitblt(d.hwnd))
        report("dap_print_rung2", hin._dap_print(d.hwnd)[0])
        report("capture_window", hin.capture_window(d.hwnd)[0])
        # the product path PV1 actually uses today
        node = dap.Win32Provider().build_node(d.hwnd, None)
        report("product_OCREngine_image", dap.OCREngine()._image_of(node, dap.CaptureEngine()))
    finally:
        d.stop()
    return 0


def _rect(hwnd):
    r = hin.wt.RECT()
    _u32.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


if __name__ == "__main__":
    sys.exit(main())
