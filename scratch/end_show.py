import ctypes, time
u=ctypes.windll.user32
for h in (5113700, 853910):
    if u.IsWindow(h):
        u.PostMessageW(h, 0x0100, 0x1B, 0); u.PostMessageW(h, 0x0101, 0x1B, 0)
time.sleep(1.5)
print([bool(u.IsWindow(h)) for h in (5113700, 853910)])
for h in (5113700, 853910):
    if u.IsWindow(h): u.PostMessageW(h, 0x0010, 0, 0)
time.sleep(1.5)
print([bool(u.IsWindow(h)) for h in (5113700, 853910)])
