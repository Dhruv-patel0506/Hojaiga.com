"""
Organ 44 — Enhanced Scanner with External Resources (Playwright, FlaUI, OmniParser)

Responsibility: Supercharges the app scanner for speed and semantic action-mapping using
established, highly optimized external libraries.

External Resources:
- Playwright's Accessibility Snapshot (Web): Fast accessibility tree parsing in C++
- FlaUI via Pythonnet (Windows Desktop): Modern .NET wrapper for UIAutomation API
- Microsoft OmniParser: Vision parsing model for semantic UI understanding
- DOM-Action Graphs: Static action prediction from href, onclick, formaction attributes

Architecture:
  - Playwright Integration for web UI tree scanning
  - FlaUI Integration for Windows desktop app scanning
  - OmniParser Integration for semantic element understanding
  - DOM-Action Graph parser for static routing prediction
  - Fallback to legacy scanners when external tools unavailable
"""

import asyncio
import json
import logging
import re
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

if r"D:\new_automation\All codes" not in sys.path:
    sys.path.insert(0, r"D:\new_automation\All codes")

logger = logging.getLogger("hojaiga.organ44.enhanced_scanner")


class ScannerMode(Enum):
    """Scanner mode selection."""
    AUTO = "auto"  # Automatically choose best available scanner
    PLAYWRIGHT = "playwright"  # Use Playwright for web
    FLAUI = "flaui"  # Use FlaUI for desktop
    OMNIPARSER = "omniparser"  # Use OmniParser for vision-based parsing
    LEGACY = "legacy"  # Use legacy pywinauto/uiautomation


@dataclass
class UIElementEnhanced:
    """Enhanced UI element with semantic understanding."""
    element_id: str
    tag: str
    text: str
    bounds: Tuple[int, int, int, int]  # (left, top, right, bottom)
    is_visible: bool
    is_enabled: bool
    is_interactive: bool
    role: str  # button, link, input, etc.
    semantic_action: Optional[str] = None  # "Submits login form", "Opens profile dropdown"
    confidence: float = 1.0
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "element_id": self.element_id,
            "tag": self.tag,
            "text": self.text,
            "bounds": self.bounds,
            "is_visible": self.is_visible,
            "is_enabled": self.is_enabled,
            "is_interactive": self.is_interactive,
            "role": self.role,
            "semantic_action": self.semantic_action,
            "confidence": self.confidence,
            "attributes": self.attributes,
        }


class PlaywrightScanner:
    """Fast web UI tree scanning using Playwright's Accessibility Snapshot."""

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._available = False

    def _init_playwright(self):
        """Initialize Playwright if available."""
        if self._available:
            return

        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
            self._context = self._browser.new_context()
            self._page = self._context.new_page()
            self._available = True
            logger.info("[PlaywrightScanner] Initialized successfully")
        except ImportError:
            logger.warning("[PlaywrightScanner] Playwright not installed")
        except Exception as e:
            logger.error(f"[PlaywrightScanner] Failed to initialize: {e}")

    async def scan_web_page(self, url: str = None) -> List[UIElementEnhanced]:
        """Scan a web page using Playwright's accessibility snapshot."""
        if not self._available:
            self._init_playwright()
        
        if not self._available:
            return []

        try:
            if url:
                await self._page.goto(url, wait_until="networkidle", timeout=30000)
            
            # Get accessibility snapshot (native C++ parsing, very fast)
            snapshot = await self._page.accessibility.snapshot(
                interesting_only=True,
                root=None
            )
            
            elements = self._parse_accessibility_tree(snapshot)
            logger.info(f"[PlaywrightScanner] Scanned {len(elements)} elements")
            return elements
            
        except Exception as e:
            logger.error(f"[PlaywrightScanner] Scan failed: {e}")
            return []

    def _parse_accessibility_tree(self, node: Dict[str, Any], parent_bounds: Tuple[int, int, int, int] = None) -> List[UIElementEnhanced]:
        """Parse Playwright accessibility tree into UI elements."""
        elements = []
        
        if not node:
            return elements
        
        # Extract element info
        role = node.get("role", "").lower()
        name = node.get("name", "")
        
        # Only process interactive elements
        if role in ["button", "link", "textbox", "combobox", "checkbox", "radio", "menuitem", "tab"]:
            # Extract bounds if available
            bounds = parent_bounds or (0, 0, 0, 0)
            
            # Infer semantic action from role and name
            semantic_action = self._infer_semantic_action(role, name)
            
            element = UIElementEnhanced(
                element_id=str(id(node)),
                tag=role,
                text=name,
                bounds=bounds,
                is_visible=True,
                is_enabled=node.get("disabled", True) == False,
                is_interactive=True,
                role=role,
                semantic_action=semantic_action,
                confidence=0.95,
                attributes={"raw_node": node}
            )
            elements.append(element)
        
        # Recursively process children
        for child in node.get("children", []):
            elements.extend(self._parse_accessibility_tree(child, parent_bounds))
        
        return elements

    def _infer_semantic_action(self, role: str, text: str) -> Optional[str]:
        """Infer semantic action from role and text."""
        text_lower = text.lower()
        
        if role == "button":
            if "submit" in text_lower or "send" in text_lower or "login" in text_lower:
                return "Submits form"
            elif "cancel" in text_lower or "close" in text_lower:
                return "Closes dialog"
            elif "next" in text_lower or "continue" in text_lower:
                return "Navigates to next step"
            elif "back" in text_lower:
                return "Navigates back"
        
        elif role == "link":
            if "profile" in text_lower or "account" in text_lower:
                return "Opens profile/account"
            elif "settings" in text_lower or "preferences" in text_lower:
                return "Opens settings"
            elif "home" in text_lower:
                return "Navigates to home"
        
        return None

    def close(self):
        """Clean up Playwright resources."""
        if self._page:
            try:
                self._page.close()
            except Exception:
                pass
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass


class FlaUIScanner:
    """Fast Windows desktop app scanning using FlaUI via Pythonnet."""

    def __init__(self):
        self._available = False
        self._pythonnet_loaded = False

    def _init_pythonnet(self):
        """Initialize Pythonnet for .NET interop."""
        if self._pythonnet_loaded:
            return

        try:
            import pythonnet
            pythonnet.load()
            self._pythonnet_loaded = True
            
            # Import FlaUI
            import clr
            clr.AddReference("FlaUI.UIA3")
            from FlaUI.UIA3 import UIA
            self._UIA = UIA
            self._available = True
            logger.info("[FlaUIScanner] Initialized successfully")
        except ImportError:
            logger.warning("[FlaUIScanner] pythonnet or FlaUI not installed")
        except Exception as e:
            logger.error(f"[FlaUIScanner] Failed to initialize: {e}")

    def scan_desktop_app(self, app_name: str = None) -> List[UIElementEnhanced]:
        """Scan a Windows desktop app using FlaUI."""
        if not self._available:
            self._init_pythonnet()
        
        if not self._available:
            return []

        try:
            # Get the main window
            if app_name:
                window = self._UIA.GetMainWindow(app_name)
            else:
                window = self._UIA.GetFocusedWindow()
            
            if not window:
                logger.warning(f"[FlaUIScanner] Could not find window for: {app_name}")
                return []
            
            # Get all interactive elements
            elements = []
            for element in window.FindAllChildren(lambda e: e.IsEnabled and e.IsOffscreen == False):
                # Extract element info
                role = element.ControlType.ToString().lower()
                name = element.Name or ""
                
                if role in ["button", "hyperlink", "edit", "combobox", "list", "listitem", "menuitem"]:
                    bounds = element.BoundingRectangle
                    element_obj = UIElementEnhanced(
                        element_id=str(element.AutomationId),
                        tag=role,
                        text=name,
                        bounds=(bounds.Left, bounds.Top, bounds.Right, bounds.Bottom),
                        is_visible=True,
                        is_enabled=element.IsEnabled,
                        is_interactive=True,
                        role=role,
                        semantic_action=self._infer_semantic_action(role, name),
                        confidence=0.90,
                        attributes={"automation_id": element.AutomationId}
                    )
                    elements.append(element_obj)
            
            logger.info(f"[FlaUIScanner] Scanned {len(elements)} elements")
            return elements
            
        except Exception as e:
            logger.error(f"[FlaUIScanner] Scan failed: {e}")
            return []

    def _infer_semantic_action(self, role: str, text: str) -> Optional[str]:
        """Infer semantic action for desktop apps."""
        text_lower = text.lower()
        
        if role == "button":
            if "ok" in text_lower or "yes" in text_lower:
                return "Confirms action"
            elif "cancel" in text_lower or "no" in text_lower:
                return "Cancels action"
            elif "apply" in text_lower or "save" in text_lower:
                return "Applies changes"
        
        elif role == "hyperlink":
            if "help" in text_lower:
                return "Opens help"
            elif "about" in text_lower:
                return "Shows about info"
        
        return None


class OmniParserScanner:
    r"""Vision-based UI parsing using the LOCAL Microsoft OmniParser repo.

    The repo lives at D:\new_automation\OmniParser with weights already present
    (icon_detect/model.pt detector + icon_caption_florence captioner). There is
    NO pip package called `omni_parser` — the previous import was simply wrong.
    We repoint sys.path at the local repo and import util.omniparser.OmniParser.
    If torch or the weights are missing, the scanner honestly reports itself
    unavailable and returns nothing — it never fabricates detections.
    """

    OMNI_LOCAL_REPO = os.environ.get("HOJAIGA_OMNIPARSER_REPO", r"D:\new_automation\OmniParser")

    def __init__(self, model_path: str = None):
        self._model_path = model_path  # optional detector .pt override
        self._available = False
        self._model = None

    def _resolve_config(self) -> Dict[str, Any]:
        """Build the OmniParser config from weights actually on disk."""
        repo = self.OMNI_LOCAL_REPO
        som_path = self._model_path or os.path.join(repo, "weights", "icon_detect", "model.pt")
        caption_path = os.path.join(repo, "weights", "icon_caption_florence")
        return {
            "som_model_path": som_path,
            "caption_model_name": "florence2",
            "caption_model_path": caption_path,
            "BOX_TRESHOLD": float(os.environ.get("HOJAIGA_OMNI_BOX_TRESHOLD", "0.05")),
        }

    def _init_model(self):
        """Initialize OmniParser from the local repo (graceful if unavailable)."""
        if self._available:
            return
        cfg = self._resolve_config()
        if not os.path.isdir(self.OMNI_LOCAL_REPO):
            logger.warning("[OmniParserScanner] local repo not found at %s — vision tier off",
                           self.OMNI_LOCAL_REPO)
            return
        if not (os.path.exists(cfg["som_model_path"]) and os.path.isdir(cfg["caption_model_path"])):
            logger.warning("[OmniParserScanner] OmniParser weights missing — vision tier off")
            return
        try:
            if self.OMNI_LOCAL_REPO not in sys.path:
                sys.path.insert(0, self.OMNI_LOCAL_REPO)
            # The upstream repo spells the class 'Omniparser' (lowercase 'p');
            # accept either spelling so we never ImportError on a valid install.
            import util.omniparser as _omni_mod
            _omni_cls = getattr(_omni_mod, "Omniparser", None) or getattr(_omni_mod, "OmniParser", None)
            if _omni_cls is None:
                raise ImportError("no Omni parser class found in util.omniparser")
            self._model = _omni_cls(cfg)
            self._available = True
            logger.info("[OmniParserScanner] Initialized successfully from local repo")
        except ImportError as ie:
            logger.warning("[OmniParserScanner] OmniParser deps missing (torch/transformers) — off: %s", ie)
        except Exception as e:
            logger.error(f"[OmniParserScanner] Failed to initialize: {e}")

    # ---- the split vision tier (backlog 2.1) -------------------------------------------------------------------
    CAPTION_MAX_ICONS = int(os.environ.get("HOJAIGA_OMNI_CAPTION_MAX_ICONS", "60"))

    def _parse_fast(self, image) -> List[Dict[str, Any]]:
        """Detector + OCR only (use_local_semantics=False): text boxes with their OCR text, icon boxes with content None.
        Returns the upstream's own element dicts: {'type','bbox'(ratio xyxy),'interactivity','content'}."""
        from util.utils import get_som_labeled_img, check_ocr_box
        ratio = max(image.size) / 3200
        draw_cfg = {"text_scale": 0.8 * ratio, "text_thickness": max(int(2 * ratio), 1), "text_padding": max(int(3 * ratio), 1),
                    "thickness": max(int(3 * ratio), 1)}
        (text, ocr_bbox), _ = check_ocr_box(image, display_img=False, output_bb_format="xyxy",
                                            easyocr_args={"text_threshold": 0.8}, use_paddleocr=False)
        _img, _coords, elems = get_som_labeled_img(
            image, self._model.som_model, BOX_TRESHOLD=self._resolve_config()["BOX_TRESHOLD"], output_coord_in_ratio=True,
            ocr_bbox=ocr_bbox, draw_bbox_config=draw_cfg, caption_model_processor=None, ocr_text=text,
            use_local_semantics=False, iou_threshold=0.7, scale_img=False, batch_size=128)
        return list(elems or [])

    def _start_caption_job(self, image, items: List[Tuple[UIElementEnhanced, Dict[str, Any]]]) -> None:
        """Caption the icon boxes on ONE background worker and write the captions into the element objects the caller already holds.
        `caption_future` resolves to the number of icons named; callers may add a done-callback (the grounding cache does)."""
        from concurrent.futures import ThreadPoolExecutor
        icons = [(el, it) for el, it in items if it.get("content") is None]
        icons.sort(key=lambda p: -((p[1]["bbox"][2] - p[1]["bbox"][0]) * (p[1]["bbox"][3] - p[1]["bbox"][1])))
        icons = icons[: self.CAPTION_MAX_ICONS]
        self.caption_future = None
        if not icons or getattr(self._model, "caption_model_processor", None) is None:
            return
        if not hasattr(self, "_cap_pool"):
            self._cap_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="omni-caption")
        gen = getattr(self, "_cap_gen", 0)            # the job belongs to THIS window state; a newer parse invalidates it

        def _job() -> int:
            import numpy as np
            import torch
            from util.utils import get_parsed_content_icon
            t0 = time.time()
            boxes = torch.tensor([it["bbox"] for _el, it in icons])
            src = np.asarray(image.convert("RGB"))
            prev = torch.get_num_threads()
            caps: List[str] = []
            try:
                torch.set_num_threads(max(1, (os.cpu_count() or 4) // 4))        # leave most cores to the foreground
                for i in range(0, len(icons), 12):
                    if getattr(self, "_cap_gen", 0) != gen:                      # a newer parse started: stop, do not compete with it
                        break
                    caps += get_parsed_content_icon(boxes[i:i + 12], 0, src, self._model.caption_model_processor, batch_size=12)
            finally:
                torch.set_num_threads(prev)
            named = 0
            for (el, it), cap in zip(icons, caps):
                cap = (cap or "").strip()
                if cap:
                    el.text = cap
                    el.semantic_action = cap
                    it["content"] = cap
                    named += 1
            logger.info("[OmniParserScanner] captioned %d/%d icons in %.1fs (background)", named, len(icons), time.time() - t0)
            return named
        self.caption_future = self._cap_pool.submit(_job)

    def parse_screenshot(self, image_path: str, captions: Optional[str] = None) -> List[UIElementEnhanced]:
        """Parse a screenshot using the local OmniParser for semantic UI understanding.

        captions: 'lazy' (default; env HOJAIGA_OMNI_CAPTIONS) = detector + OCR now, icon captions in the background;
                  'sync' = the upstream blocking behaviour (detector + OCR + a caption for every icon, minutes on CPU);
                  'off'  = never caption.

        The model's parse() takes a base64 PNG and returns (annotated_img, list)
        where each item has a normalized [0,1] bbox, caption/content and an
        interactivity flag. We map those to image-pixel bounds and keep only
        actionable elements.
        """
        if not self._available:
            self._init_model()
        if not self._available:
            return []
        self._cap_gen = getattr(self, "_cap_gen", 0) + 1          # cancels any caption job of an OLDER window state

        try:
            import base64 as _b64
            from PIL import Image
            img = Image.open(image_path)
            w, h = img.size
            with open(image_path, "rb") as fh:
                b64 = _b64.b64encode(fh.read()).decode("ascii")
            mode = (captions or os.environ.get("HOJAIGA_OMNI_CAPTIONS", "lazy")).lower()
            self.caption_future = None
            try:
                if mode == "sync":
                    parsed = self._model.parse(b64)
                else:
                    parsed = (None, self._parse_fast(img))
            except (TypeError, ValueError) as pe:
                # Upstream OmniParser has no guard for "nothing detected" (blank / icon-free
                # window): depending on the stage it raises "'NoneType' object is not
                # iterable" (OCR empty) or "not enough values to unpack (expected 4, got 0)"
                # (torchvision box_convert on 0 boxes). Both are a legitimate empty result;
                # every other error still falls through to the ERROR path below.
                if re.search(r"NoneType|expected 4, got 0", str(pe)):
                    logger.info("[OmniParserScanner] PARSE returned 0 elements (no detections)")
                    return []
                raise
            # OmniParser returns None when OCR/detection finds nothing.
            if not parsed:
                logger.info("[OmniParserScanner] PARSE returned 0 elements (no detections)")
                return []
            _labeled, parsed_content_list = parsed
            pairs: List[Tuple[UIElementEnhanced, Dict[str, Any]]] = []

            elements: List[UIElementEnhanced] = []
            for i, item in enumerate(parsed_content_list or []):
                rel = item.get("bbox") or [0, 0, 0, 0]
                if len(rel) != 4:
                    continue
                # Normalized [0,1] -> image pixels (clamped).
                bounds = (
                    max(0, min(w, int(rel[0] * w))), max(0, min(h, int(rel[1] * h))),
                    max(0, min(w, int(rel[2] * w))), max(0, min(h, int(rel[3] * h))),
                )
                if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
                    continue
                text = (item.get("content") or item.get("caption") or "").strip()
                interactive = bool(item.get("interactivity", True))
                element = UIElementEnhanced(
                    element_id=f"omni_{item.get('id', i)}",
                    tag="vision_detected",
                    text=text,
                    bounds=bounds,
                    is_visible=True,
                    is_enabled=True,
                    is_interactive=interactive,
                    role="vision_element" if item.get("type") != "text" else "text",
                    semantic_action=text,
                    confidence=0.35,
                    attributes={"omniparser_raw": item},
                )
                elements.append(element)
                pairs.append((element, item))
            if mode == "lazy":
                self._start_caption_job(img, pairs)

            logger.info(f"[OmniParserScanner] Parsed {len(elements)} elements")
            return elements

        except Exception as e:
            logger.error(f"[OmniParserScanner] Parse failed: {e}")
            return []


class DOMActionGraphParser:
    """Parser for DOM-Action Graphs to predict static routing."""

    def __init__(self):
        self._available = True

    def parse_dom_actions(self, html_content: str) -> Dict[str, List[Dict[str, Any]]]:
        """Parse DOM to extract action graphs from href, onclick, formaction attributes."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            action_graph = {
                "links": [],
                "forms": [],
                "buttons": [],
                "interactions": []
            }
            
            # Extract links with href
            for a in soup.find_all('a', href=True):
                action_graph["links"].append({
                    "text": a.get_text(strip=True),
                    "href": a['href'],
                    "action": f"Navigate to {a['href']}",
                    "target": a.get('target', '_self')
                })
            
            # Extract forms with action
            for form in soup.find_all('form', action=True):
                action_graph["forms"].append({
                    "action": form['action'],
                    "method": form.get('method', 'GET'),
                    "action_type": "Form submission"
                })
            
            # Extract buttons with onclick
            for button in soup.find_all('button', onclick=True):
                action_graph["buttons"].append({
                    "text": button.get_text(strip=True),
                    "onclick": button['onclick'],
                    "action_type": "JavaScript action"
                })
            
            logger.info(f"[DOMActionGraph] Parsed {len(action_graph['links'])} links, "
                       f"{len(action_graph['forms'])} forms, {len(action_graph['buttons'])} buttons")
            return action_graph
            
        except ImportError:
            logger.warning("[DOMActionGraph] BeautifulSoup not installed")
            return {"links": [], "forms": [], "buttons": [], "interactions": []}
        except Exception as e:
            logger.error(f"[DOMActionGraph] Parse failed: {e}")
            return {"links": [], "forms": [], "buttons": [], "interactions": []}


class EnhancedScannerOrgan:
    """
    Enhanced Scanner Organ integrating external resources for fast, semantic UI scanning.

    Features:
    - Playwright Integration for web UI tree scanning
    - FlaUI Integration for Windows desktop app scanning
    - OmniParser Integration for semantic element understanding
    - DOM-Action Graph parser for static routing prediction
    - Automatic fallback to legacy scanners
    - Unified interface for all scanning modes
    """

    def __init__(self, mode: ScannerMode = ScannerMode.AUTO):
        self.mode = mode
        self._playwright = PlaywrightScanner()
        self._flaui = FlaUIScanner()
        self._omniparser = OmniParserScanner()
        self._dom_parser = DOMActionGraphParser()

    async def scan(self, target: str = None, target_type: str = "web") -> List[UIElementEnhanced]:
        """
        Scan a target using the best available scanner.

        Args:
            target: URL for web, app name for desktop, or image path for vision
            target_type: "web", "desktop", or "vision"
        """
        if self.mode == ScannerMode.AUTO:
            return await self._auto_scan(target, target_type)
        elif self.mode == ScannerMode.PLAYWRIGHT:
            return await self._playwright.scan_web_page(target)
        elif self.mode == ScannerMode.FLAUI:
            return self._flaui.scan_desktop_app(target)
        elif self.mode == ScannerMode.OMNIPARSER:
            return self._omniparser.parse_screenshot(target)
        else:
            logger.warning(f"[EnhancedScanner] Mode {self.mode} not implemented, falling back to auto")
            return await self._auto_scan(target, target_type)

    async def _auto_scan(self, target: str = None, target_type: str = "web") -> List[UIElementEnhanced]:
        """Automatically choose the best scanner based on target type."""
        if target_type == "web":
            # Try Playwright first for web
            elements = await self._playwright.scan_web_page(target)
            if elements:
                return elements
            # Fallback to legacy
            logger.warning("[EnhancedScanner] Playwright failed, would fallback to legacy scanner")
            return []
        
        elif target_type == "desktop":
            # Try FlaUI for desktop
            elements = self._flaui.scan_desktop_app(target)
            if elements:
                return elements
            # Fallback to legacy
            logger.warning("[EnhancedScanner] FlaUI failed, would fallback to legacy scanner")
            return []
        
        elif target_type == "vision":
            # Try OmniParser for vision
            elements = self._omniparser.parse_screenshot(target)
            if elements:
                return elements
            # Fallback to legacy
            logger.warning("[EnhancedScanner] OmniParser failed, would fallback to legacy scanner")
            return []
        
        return []

    def parse_dom_actions(self, html_content: str) -> Dict[str, List[Dict[str, Any]]]:
        """Parse DOM for action graphs."""
        return self._dom_parser.parse_dom_actions(html_content)

    def get_available_scanners(self) -> Dict[str, bool]:
        """Get status of all external scanners."""
        return {
            "playwright": self._playwright._available,
            "flaui": self._flaui._available,
            "omniparser": self._omniparser._available,
            "dom_parser": self._dom_parser._available,
        }

    def cleanup(self):
        """Clean up resources."""
        self._playwright.close()
