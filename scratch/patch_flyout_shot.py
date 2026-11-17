import ast, io
P = "D:/new_automation/All codes/core_organs/professor/apprun.py"
s = io.open(P, "r", encoding="utf-8").read()
i0 = s.index("    def on_flyout(self, opener: Any, new_nodes: List[Any]) -> None:")
i1 = s.index("    # ----------------------------------------------------------------------------------------------- perception")
new = '''    def on_flyout(self, opener: Any, new_nodes: List[Any]) -> None:
        """A flyout is open: record what it holds. A parked WinUI pop-up paints nothing for any screenshot API, so the picture is DRAWN from the accessibility tree (name, accelerator, rectangle);
        a pop-up that does render is photographed and read with the vision pipeline as well."""
        if self._flyouts >= 8:
            return
        from . import capture as CAP, viz
        from core_organs import headless_input as hin, fast_uia
        try:
            pops = hin.popup_windows(self.hwnd)[:6]
            if not pops:
                return
            self._flyouts += 1
            tag = f"flyout_{self._flyouts:02d}_{re.sub(r'[^A-Za-z0-9]+', '_', opener.name)[:24]}"
            fr = CAP.grab_composite(self.hwnd, pops)
            if fr is not None and len(pops) and self.sess is not None and not CAP._is_blank(fr.image):
                try:
                    pb = CAP.window_info(pops[0]).box
                    if pb.overlap_frac(fr.image and CAP.window_info(self.hwnd).box) >= 0:                                       # composite includes a rendered popup
                        pass
                except Exception:
                    pass
            nodes = []
            for p in pops:
                nodes += fast_uia.snapshot(p, timeout_ms=3000) or []
            pb = CAP.window_info(pops[0]).box
            img = viz.render_popup(nodes, (pb.w, pb.h), f"{opener.name} flyout", (int(pb.x1), int(pb.y1)))
            self._save(tag, img)
        except Exception:
            pass

'''
s = s[:i0] + new + s[i1:]
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
