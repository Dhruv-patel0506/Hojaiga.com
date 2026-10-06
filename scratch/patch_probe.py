p = r"D:\new_automation\scratch\probe_day1_full.py"
s = open(p, encoding="utf-8").read()
s = s.replace('with sb.LiveApp("notepad") as ln', '''_orig_crawl = bm.crawl_e0
def _wrapped(model, app, hwnd, *a, **k):
    t = time.time()
    try:
        r = _orig_crawl(model, app, hwnd, *a, **k)
        print("CRAWL", app, "->", {kk: vv for kk, vv in r.items() if kk in ("window_mode", "ingested", "skipped", "error")}, f"{time.time()-t:.1f}s", flush=True)
        return r
    except BaseException as e:
        print("CRAWL EXC", app, type(e).__name__, str(e)[:200], flush=True)
        raise
bm.crawl_e0 = _wrapped
with sb.LiveApp("notepad") as ln''', 1)
open(p, "w", encoding="utf-8").write(s)
print("patched")
