"""Why does visual_cursor._draw_badge strand a font handle? Reproduce the body WITHOUT its
`except Exception: pass` so the raising call names itself.

Measured (traced prefix run, 2026-10-05): 4154 live GDI handles, ALL from
visual_cursor.py:756 (CreateFontW inside _draw_badge) on the animation thread — that is the
process walking to the 10,000-object cap, which is what makes every later PrintWindow capture
come back blank inside a long suite run. The badge's delete path never runs for them, so either
an exception is swallowed on the way, or the restore order leaves the object selected.
"""
import ctypes
import ctypes.wintypes as wt
import sys

u32 = ctypes.windll.user32
g32 = ctypes.windll.gdi32


class BMI(ctypes.Structure):
    _fields_ = [("biSize", wt.UINT), ("biWidth", ctypes.c_int), ("biHeight", ctypes.c_int),
                ("biPlanes", ctypes.c_ushort), ("biBitCount", ctypes.c_ushort),
                ("biCompression", wt.UINT), ("biSizeImage", wt.UINT),
                ("biXPelsPerMeter", ctypes.c_int), ("biYPelsPerMeter", ctypes.c_int),
                ("biClrUsed", wt.UINT), ("biClrImportant", wt.UINT)]


def badge_body(hdc_mem, x, y, text):
    """_draw_badge copied verbatim, except that NOTHING is swallowed."""
    hfont = g32.CreateFontW(12, 0, 0, 0, 600, 0, 0, 0, 1, 0, 0, 0, 0, "Segoe UI")
    old_font = g32.SelectObject(hdc_mem, hfont)

    size = wt.SIZE()
    u32.GetTextExtentPoint32W(hdc_mem, text, len(text), ctypes.byref(size))

    pad_x, pad_y = 7, 3
    rect_left, rect_top = x, y
    rect_right, rect_bottom = x + size.cx + pad_x * 2, y + size.cy + pad_y * 2

    pen_b = g32.CreatePen(0, 1, 0x00FFFF00)
    brush_b = g32.CreateSolidBrush(0x001A1624)
    old_p = g32.SelectObject(hdc_mem, pen_b)
    old_br = g32.SelectObject(hdc_mem, brush_b)

    u32.RoundRect(hdc_mem, rect_left, rect_top, rect_right, rect_bottom, 10, 10)

    g32.SetBkMode(hdc_mem, 1)
    g32.SetTextColor(hdc_mem, 0x00FFFFFF)
    u32.TextOutW(hdc_mem, rect_left + pad_x, rect_top + pad_y, text, len(text))

    g32.SelectObject(hdc_mem, old_p)
    g32.SelectObject(hdc_mem, old_br)
    g32.SelectObject(hdc_mem, old_font)
    g32.DeleteObject(pen_b)
    g32.DeleteObject(brush_b)
    r = g32.DeleteObject(hfont)
    print(f"    DeleteObject(hfont) returned {r}   (0 = refused, handle stays alive)")
    print(f"    NOTE old_br is the PEN that was in the slot before brush_b, i.e. pen_b itself -> "
          f"restoring it re-selects pen_b, so DeleteObject(pen_b) can never succeed")


def main():
    iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    hdc_screen = u32.GetDC(0)
    hdc_mem = g32.CreateCompatibleDC(hdc_screen)
    bmi = BMI()
    bmi.biSize = ctypes.sizeof(BMI)
    bmi.biWidth, bmi.biHeight, bmi.biPlanes, bmi.biBitCount = 640, 400, 1, 32
    ppv = ctypes.c_void_p()
    hbmp = g32.CreateDIBSection(hdc_mem, ctypes.byref(bmi), 0, ctypes.byref(ppv), None, 0)
    old = g32.SelectObject(hdc_mem, hbmp)
    for i in range(iterations):
        print(f"frame {i}:")
        try:
            badge_body(hdc_mem, 40, 40, ">> MOVING")
        except Exception as exc:                          # noqa: BLE001
            print(f"    RAISED (and the real code swallows this, stranding the font): "
                  f"{type(exc).__name__}: {exc}")
    g32.SelectObject(hdc_mem, old)
    g32.DeleteObject(hbmp)
    g32.DeleteDC(hdc_mem)
    u32.ReleaseDC(0, hdc_screen)


if __name__ == "__main__":
    main()
