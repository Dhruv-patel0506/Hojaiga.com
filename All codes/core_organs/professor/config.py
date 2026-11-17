"""
professor.config -- every path, port, model profile and budget of the Professor layer, in one place.

Free + local only (master rule L1): the vision/brain model is a GGUF served by the local llama.cpp `llama-server`; nothing leaves the machine.
Every value can be overridden by an environment variable so tests run on scratch folders and a stronger model can be dropped in without code changes.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from typing import Dict, List, Optional

ROOT = os.environ.get("HOJAIGA_ROOT", r"D:\new_automation")
DATA_DIR = os.environ.get("HOJAIGA_PROF_DIR", os.path.join(ROOT, "data", "professor"))
SCAN_DIR = os.path.join(DATA_DIR, "scans")
LESSON_DIR = os.path.join(DATA_DIR, "lessons")
LOG_DIR = os.path.join(DATA_DIR, "logs")
ICON_DB = os.path.join(DATA_DIR, "icon_memory.db")
REPO_DB = os.path.join(DATA_DIR, "repo_graph.db")
CALIBRATION_FILE = os.path.join(DATA_DIR, "calibration.json")
PROFILE_FILE = os.path.join(DATA_DIR, "server_profile.json")
DIVISIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "divisions.json")

MODELS_DIR = os.environ.get("HOJAIGA_MODELS_DIR", os.path.join(ROOT, "models"))
KOKORO_DIR = os.environ.get("HOJAIGA_KOKORO_DIR", os.path.join(ROOT, "kokoro_models"))
PIPER_DIR = os.environ.get("HOJAIGA_PIPER_DIR", os.path.join(ROOT, "piper_voices"))
PIPER_VOICE = os.environ.get("HOJAIGA_PIPER_VOICE", "en_US-lessac-medium")
ATLAS_DIR = os.environ.get("HOJAIGA_ATLAS_DIR", os.path.join(ROOT, "data", "atlas"))
KNOWLEDGE_BASES_DIR = os.path.join(ROOT, "data", "knowledge_bases")
ARCHITECTURE_STANDARDS_DIR = os.path.join(ROOT, "architechure standards-oragn files")      # the user's layer folders (sic)

VISION_URL = os.environ.get("HOJAIGA_PROF_VISION_URL", os.environ.get("HOJAIGA_QWEN_VL_URL", "http://127.0.0.1:8081")).rstrip("/")
OLLAMA_URL = os.environ.get("HOJAIGA_PROF_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_TEXT_MODEL = os.environ.get("HOJAIGA_PROF_OLLAMA_MODEL", "")                 # empty = discover (prefers qwen2.5:7b)
OFFLINE = os.environ.get("HOJAIGA_PROF_OFFLINE", "0") == "1"                       # no model calls at all (deterministic tiers only)

WINGET_LLAMA = (r"C:\Users\dhruv\AppData\Local\Microsoft\WinGet\Packages"
                r"\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\llama-server.exe")


def llama_server_binary() -> Optional[str]:
    """First llama-server that exists: env override, the WinGet install this project already uses, then PATH."""
    for cand in (os.environ.get("HOJAIGA_LLAMA_SERVER", ""), WINGET_LLAMA, shutil.which("llama-server") or ""):
        if cand and os.path.isfile(cand):
            return cand
    return None


@dataclass
class ModelProfile:
    """One local vision-language model the Professor can run on. `coord` is how the model writes boxes:
    norm1000 = 0..1000 relative grid (Qwen3-VL), pixels = absolute pixels of the image it was shown (Qwen2.5-VL), auto = calibrate."""
    name: str
    gguf: str
    mmproj: str
    coord: str = "auto"
    ngl: int = 12                         # layers on the 6 GB laptop GPU; the rest run on CPU (tuned by `server tune`)
    ctx: int = 6144
    image_tokens_budget: int = 1800       # per image sent in one request (Qwen: ~ (w/32)*(h/32) tokens)
    image_min_tokens: int = 1024          # llama.cpp: "Qwen-VL models require at minimum 1024 image tokens to function correctly on grounding tasks"
    patch: int = 32                       # pixels per image token side (patch 16 x spatial merge 2)
    note: str = ""

    def files_present(self) -> bool:
        return os.path.isfile(self.gguf) and os.path.isfile(self.mmproj)


def _profiles() -> Dict[str, ModelProfile]:
    m = MODELS_DIR
    out = {
        "qwen3-vl-8b": ModelProfile(
            "qwen3-vl-8b", os.path.join(m, "Qwen3-VL-8B-Instruct-Q4_K_M.gguf"), os.path.join(m, "mmproj-Qwen3-VL-8B-Instruct-f16.gguf"),
            coord="norm1000", ngl=int(os.environ.get("HOJAIGA_VISION_NGL", "12") or 12),
            note="best vision model already on disk; native 0-1000 box grid, strong OCR + GUI grounding"),
        "qwen2.5-vl-7b": ModelProfile(
            "qwen2.5-vl-7b", os.path.join(m, "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf"), os.path.join(m, "mmproj-Qwen_Qwen2.5-VL-7B-Instruct-f16.gguf"),
            coord="auto", ngl=24, note="fallback; absolute pixel boxes"),
    }
    custom = os.environ.get("HOJAIGA_PROF_GGUF", "")
    if custom:                                                           # drop-in slot for a GUI-grounding specialist
        out["custom"] = ModelProfile("custom", custom, os.environ.get("HOJAIGA_PROF_MMPROJ", ""),
                                     coord=os.environ.get("HOJAIGA_PROF_COORD", "auto"), ngl=int(os.environ.get("HOJAIGA_PROF_NGL", "12")),
                                     note="user supplied model")
    return out


PROFILES: Dict[str, ModelProfile] = _profiles()
PROFILE_ORDER = ["custom", "qwen3-vl-8b", "qwen2.5-vl-7b"]


def active_profile() -> Optional[ModelProfile]:
    """The profile to run: HOJAIGA_PROF_MODEL, else the first in PROFILE_ORDER whose files exist."""
    want = os.environ.get("HOJAIGA_PROF_MODEL", "")
    if want and want in PROFILES:
        return PROFILES[want]
    for name in PROFILE_ORDER:
        p = PROFILES.get(name)
        if p and p.files_present():
            return p
    return None


@dataclass
class Budgets:
    """Hard time/size caps (master rule L6: every wait is bounded)."""
    vlm_call_s: float = float(os.environ.get("HOJAIGA_PROF_VLM_TIMEOUT_S", "120"))
    vlm_label_sheet_s: float = 150.0
    text_call_s: float = float(os.environ.get("HOJAIGA_PROF_TEXT_TIMEOUT_S", "90"))
    scan_quick_s: float = 12.0
    scan_standard_s: float = 120.0
    scan_deep_s: float = 600.0
    uia_s: float = 8.0
    ocr_s: float = 25.0
    max_elements: int = 1500
    sheet_cells: int = 20                 # controls per contact sheet
    cell_px: int = 112                    # size of one cell on a contact sheet
    inventory_max: int = 140              # elements shown to the teaching model
    step_wait_s: float = 90.0             # how long a lesson waits for the learner to act on one step


BUDGETS = Budgets()


def ensure_dirs() -> None:
    for d in (DATA_DIR, SCAN_DIR, LESSON_DIR, LOG_DIR):
        os.makedirs(d, exist_ok=True)
