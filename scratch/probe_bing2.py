import re, sys, base64, time, urllib.parse, requests
UA = "hojaiga-professor/1.0 (+local user-guide reader; honours robots.txt)"


def bing(q, extra=None):
    params = {"q": q, "setlang": "en", "adlt": "strict", "mkt": "en-US", "cc": "US"}
    r = requests.get("https://www.bing.com/search", params=params, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}, timeout=20)
    out = []
    for m in re.finditer(r'<li class="b_algo".*?<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r.text, flags=re.S):
        href, title = m.group(1).replace("&amp;", "&"), re.sub(r"<[^>]+>", "", m.group(2))
        real = href
        if "bing.com/ck/a" in href:
            u = urllib.parse.parse_qs(urllib.parse.urlsplit(href).query).get("u", [""])[0]
            if u.startswith("a1"):
                b = u[2:] + "=" * (-len(u[2:]) % 4)
                try:
                    real = base64.urlsafe_b64decode(b).decode("utf-8", "replace")
                except Exception:
                    pass
        out.append((title.replace("&amp;", "&"), real))
    return r.status_code, out


if __name__ == "__main__":
  for name in ("OBS Studio", "Blender"):
    for label, q in (("pdf-simple", f'"{name}" "user guide" OR "user manual" filetype:pdf'),
                     ("docs-simple", f'"{name}" documentation OR manual inurl:docs'),
                     ("plain", f'"{name}" user guide manual documentation')):
        code, res = bing(q)
        print(f"== {name:10s} {label:11s} HTTP {code}: {len(res)} results")
        for t, u in res[:5]:
            print("    ", t[:52].ljust(52), u[:88])
        time.sleep(2.0)
