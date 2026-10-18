"""
sections -- the top-level HoJaiga router. A SECTION is a product module with `name`, `description` and `handle(task, **options) -> report`.
Mount more sections with `HoJaiga.mount(section)` (or by dropping a package under sections/ whose __init__ defines `section()`); the router sends a request to the section whose description matches best.
"""
from __future__ import annotations

import importlib
import pkgutil
import re
from typing import Any, Dict, List


class HoJaiga:
    def __init__(self) -> None:
        self.sections: Dict[str, Any] = {}

    def mount(self, section: Any) -> "HoJaiga":
        self.sections[section.name] = section
        return self

    def discover(self) -> "HoJaiga":
        """Mount every package of this folder that offers `section()`."""
        import sections as pkg
        for m in pkgutil.iter_modules(pkg.__path__):
            if not m.ispkg:
                continue
            mod = importlib.import_module(f"sections.{m.name}")
            if hasattr(mod, "section") and m.name not in self.sections:
                self.mount(mod.section())
        return self

    def choose(self, task: str) -> str:
        def words(s: str) -> set:
            return set(re.findall(r"[a-z]{3,}", s.lower()))
        want = words(task)
        best = sorted(((len(want & words(s.description + " " + s.name)), n) for n, s in self.sections.items()), reverse=True)
        return best[0][1] if best else ""

    def handle(self, task: str, section: str = "", **options: Any) -> Dict[str, Any]:
        name = section or self.choose(task)
        if name not in self.sections:
            return {"error": f"no section named {name!r}; mounted: {sorted(self.sections)}"}
        rep = self.sections[name].handle(task, **options)
        rep["section"] = name
        return rep

    def listing(self) -> List[Dict[str, str]]:
        return [{"name": n, "description": s.description} for n, s in self.sections.items()]
