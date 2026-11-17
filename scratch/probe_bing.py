import re, sys, base64, urllib.parse, requests
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
UA = "hojaiga-professor/1.0 (+local user-guide reader; honours robots.txt)"
for q in ('filetype:pdf (intitle:"user manual" OR intitle:"user guide") "OBS Studio"', '(inurl:docs OR inurl:manual OR inurl:help) "Blender" (guide OR documentation OR manual)'):
    r = requests.get("https://www.bing.com/search", params={"q": q, "setlang": "en"}, headers={"User-Agent": UA}, timeout=20)
    t = r.text
    print("==", q[:60], r.status_code, len(t), "b_algo:", t.count('class="b_algo"'), "captcha?", any(k in t.lower() for k in ("captcha", "unusual traffic", "are you a robot")))
    for m in re.finditer(r'<li class="b_algo".*?<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', t, flags=re.S):
        href, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
        real = href
        if "bing.com/ck/a" in href:
            u = urllib.parse.parse_qs(urllib.parse.urlsplit(href.replace("&amp;", "&")).query).get("u", [""])[0]
            if u.startswith("a1"):
                b = u[2:]
                b += "=" * (-len(b) % 4)
                try:
                    real = base64.urlsafe_b64decode(b).decode("utf-8", "replace")
                except Exception as e:
                    real = "DECODE-FAIL " + str(e)
        print("  ", title[:50].ljust(50), real[:90])
