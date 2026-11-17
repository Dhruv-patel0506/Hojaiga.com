import ast
import io


def patch(path, edits):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in edits:
        assert old in s, (path[-30:], old[:90])
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


B = "D:/new_automation/All codes/core_organs/"

# --- the test block
patch("D:/new_automation/scratch/p4_tests_block.py", [
    ("""            n._ctrl = Ctl(fn, kind)
            n.__class__ = type("FN2", (_FN,), {"ctrl": property(lambda self: self._ctrl)})
            nodes.append(n)""", """            n.ctrl = Ctl(fn, kind)
            nodes.append(n)"""),
    ("""        rep = GF.discover(ident, ix, web=True, fetch=GF.default_fetch, search=stub, allow_local_net=True, delay_s=0.0, max_pages=6, max_depth=1)""",
     """        external = []

        def local_only(url):                                   # the test must never reach the real internet: anything that is not the local doc site is refused and recorded
            if "127.0.0.1" not in url:
                external.append(url)
                return 0, "", b"", url
            return GF.default_fetch(url)

        rep = GF.discover(ident, ix, web=True, fetch=local_only, search=stub, allow_local_net=True, delay_s=0.0, max_pages=6, max_depth=1)"""),
    ("""                  "live_docs_searchable": bool(docs_hit) and "Add Marker" in docs_hit[0].text, "report_lists_the_queries": len(t3["queries"]) == 5 and t3["queries"][0]["kind"] == "pdf"}""",
     """                  "live_docs_searchable": bool(docs_hit) and "Add Marker" in docs_hit[0].text, "report_lists_the_queries": len(t3["queries"]) == 5 and t3["queries"][0]["kind"] == "pdf",
                  "test_never_reached_the_internet": external == []}"""),
    ("""        fg0, mouse0 = CAP.foreground_hwnd(), CAP.cursor_pos()
        ov.point(""", """        fg0, mouse0 = CAP.foreground_hwnd(), CAP.cursor_pos()
        time.sleep(0.3)
        user_moving = CAP.cursor_pos() != mouse0                 # if a person is moving the real mouse during the test, that check says nothing
        mouse0 = CAP.cursor_pos()
        ov.point("""),
    ("""\"real_mouse_never_moved\": mouse1 == mouse0, \"foreground_unchanged\": fg1 == fg0}
        return _verdict(checks, f\"planned""", """\"real_mouse_never_moved\": user_moving or mouse1 == mouse0, \"foreground_unchanged\": fg1 == fg0}
        return _verdict(checks, f\"(user was moving the mouse: {user_moving}) planned"""),
])

# --- the doc site serves bytes and a small real PDF
patch(B + "si_tests_professor.py", [
    ("""            "/docs/other_host.html": ("text/html", "<html><body><h1>Other host</h1><p>Reached through a different host name: must not be followed (same host only).</p></body></html>"),
        }""", """            "/docs/other_host.html": ("text/html", "<html><body><h1>Other host</h1><p>Reached through a different host name: must not be followed (same host only).</p></body></html>"),
            "/docs/guide.pdf": ("application/pdf", _tiny_pdf(["Atlas App User Manual", "Press Ctrl+M to add a marker quickly.", "Click Add Marker on the toolbar to place a marker in the view of the application window."])),
        }"""),
    ("""                    ct, body = site.pages[self.path]
                    return self._send(200, ct, body.replace("%PORT%", str(site.port)))""", """                    ct, body = site.pages[self.path]
                    return self._send(200, ct, body.replace("%PORT%", str(site.port)) if isinstance(body, str) else body)"""),
])

# --- the session demonstration accepts a picture (tests / screenshots)
patch(B + "professor/session.py", [
    ("    def demonstrate(self, skill: Any, hwnd: int = 0, speak: bool = True) -> Dict[str, Any]:", "    def demonstrate(self, skill: Any, hwnd: int = 0, speak: bool = True, image: Optional[Image.Image] = None) -> Dict[str, Any]:"),
    ("        from . import pointing\n        sm, img, info = self.look(hwnd)\n        cat, _arch = self.frame(sm, hwnd)\n        boxes, labels, hotkeys, missing", "        from . import pointing\n        sm, img, info = self.look(hwnd, image=image)\n        cat, _arch = self.frame(sm, hwnd)\n        boxes, labels, hotkeys, missing"),
])

# --- guide card: '**Ctrl**+**M**' is ONE chord, and a shortcut is labelled by what it does
patch(B + "professor/knowledge/guide_card.py", [
    ("""    for cite, text, division, source in rows:
        by_div.setdefault(division or "unclassified", [])""", """    chord_rx = re.compile(r"(?:\\*\\*[A-Za-z0-9]+\\*\\*\\s*\\+\\s*)+\\*\\*[A-Za-z0-9]+\\*\\*")
    for cite, raw_text, division, source in rows:
        text = chord_rx.sub(lambda m: m.group(0).replace("**", ""), raw_text)                 # '**Ctrl**+**M**' -> 'Ctrl+M' (one chord, not two interface terms)
        by_div.setdefault(division or "unclassified", [])"""),
    ("""                lead = _BOLD.search(sent)
                label = (lead.group(1) if lead and not chords_in(lead.group(1)) else re.sub(r"\\s+", " ", sent.replace("**", ""))[:60]).strip(" .:-")""", """                lead = _BOLD.search(sent)
                purpose = re.search(r"\\bto\\s+([a-z][^.\\n]{3,50})", sent)
                if lead and not chords_in(lead.group(1)):
                    label = lead.group(1)
                elif purpose:
                    label = purpose.group(1)
                else:
                    label = re.sub(r"\\s+", " ", sent.replace("**", ""))[:60]
                label = label.strip(" .:-")"""),
])
print("prereqs patched")
