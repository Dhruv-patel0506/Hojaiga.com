"""harvest.paths -- where harvested data lives: <storage root>/harvest (the same root resolution as the RAG, so an unplugged SSD falls back identically and says so)."""
from __future__ import annotations

import os
from typing import List, Tuple


def harvest_dir(create: bool = True) -> Tuple[str, List[str]]:
    """(directory, degraded). HOJAIGA_HARVEST_DIR overrides; otherwise <rag storage root>/harvest."""
    env = os.environ.get("HOJAIGA_HARVEST_DIR", "").strip()
    if env:
        root, deg = env, []
    else:
        from core_organs.rag.storage import resolve_root
        base, deg = resolve_root()
        root = os.path.join(base, "harvest")
    if create:
        for sub in ("", "transcripts_json", "frames", "clips", "training"):
            os.makedirs(os.path.join(root, sub), exist_ok=True)
    return root, deg


def workbook_path(root: str = "") -> str:
    return os.path.join(root or harvest_dir()[0], "HoJaiga_Master_App_Dataset.xlsx")
