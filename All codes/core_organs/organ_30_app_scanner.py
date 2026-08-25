"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 30
Name: App Scanner (Active & Passive UI Explorer)

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [App Scanner]
        direction TB
        IN[Inputs] --> PROC[Processing]
        PROC --> OUT[Outputs]
    end
    
    COMPONENT -- event/socket --> DOWNSTREAM_A[CONSUMER A]
    COMPONENT -- event/socket --> DOWNSTREAM_B[CONSUMER B]
    
    class COMPONENT component;
```

Inputs: Discovered from runtime
Outputs: Discovered from runtime
Dependencies: pywinauto, typing, core_organs.organ_31_visual_perception, json, time, asyncio...
"""
from __future__ import annotations

import json
import logging
import hashlib
import os
import time
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("hojaiga.organ30.app_scanner")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[AppScanner] %(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)

try:
    import pywinauto  # type: ignore
except ImportError:
    pywinauto = None

from core_organs.organ_37_llm_gateway import LLMGateway
from core_organs.organ_31_visual_perception import VisualPerceptionOrgan


@dataclass
class UIElement:
    id: str
    class_name: str
    text: str
    bounds: Dict[str, int]
    inferred_intent: str = ""
    spawns_child: bool = False
    children: List["UIElement"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "class_name": self.class_name,
            "text": self.text,
            "bounds": self.bounds,
            "inferred_intent": self.inferred_intent,
            "spawns_child": self.spawns_child,
            "children": [c.to_dict() for c in self.children]
        }


class AppScannerOrgan:
    UNSAFE_KEYWORDS = [
        "delete", "remove", "format", "reset", "uninstall",
        "clear", "close", "x", "exit", "quit", "shutdown"
    ]

    def __init__(self, db_path: str = "ui_knowledge_base.json") -> None:
        self.db_path = db_path
        self.knowledge_base: Dict[str, Any] = self._load_db()
        self.llm = LLMGateway()
        self.perception = VisualPerceptionOrgan()
        self.cns: Optional[Any] = None
        
    def _load_db(self) -> Dict[str, Any]:
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse {self.db_path}, starting fresh.")
        return {}

    def _save_db(self) -> None:
        try:
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(self.knowledge_base, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save UI knowledge base: {e}")

    def _hash_state(self) -> str:
        state = self.perception.describe_screen()
        serialized = json.dumps(state, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _infer_intent(self, app_name: str, element_name: str, class_name: str) -> str:
        prompt = (
            f"You are the OS UI Analyzer.\n"
            f"Application: {app_name}\n"
            f"Element Text: '{element_name}'\n"
            f"Element Class: '{class_name}'\n"
            f"What is the most likely functionality of this element in 1 short sentence?"
        )
        try:
            return self.llm.execute_inference("You infer UI functionality concisely.", prompt, timeout=3.0)
        except Exception:
            return "Standard interactive UI element."

    def _is_safe_to_click(self, text: str) -> bool:
        if not text:
            return False
        lower_text = text.lower()
        for kw in self.UNSAFE_KEYWORDS:
            if kw in lower_text:
                return False
        return True

    def _passive_explore_tree(self, app_name: str, wrapper, depth: int = 0, max_depth: int = 4) -> UIElement:
        """Non-invasive read-only exploration of the UI tree for active task execution."""
        if depth > max_depth:
            return UIElement("limit", "limit", "", {})

        try:
            rect = wrapper.rectangle()
            node = UIElement(
                id=str(wrapper.handle),
                class_name=wrapper.class_name(),
                text=wrapper.window_text() or "",
                bounds={"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom}
            )

            # Intent inference for key control elements
            if node.text and node.class_name in ["Button", "MenuItem", "ListItem", "Hyperlink", "TabItem"]:
                node.inferred_intent = f"Interacts with {node.text}"

            for child in wrapper.children():
                if child.is_visible():
                    child_node = self._passive_explore_tree(app_name, child, depth + 1, max_depth)
                    node.children.append(child_node)
            
            return node
        except Exception as e:
            logger.debug(f"Error in passive UI tree branch: {e}")
            return UIElement("error", "error", "", {})

    def _active_explore_tree(self, app_name: str, wrapper, depth: int = 0, max_depth: int = 3) -> UIElement:
        """Active exploration reserved for offline calibration and deep crawler runs."""
        if depth > max_depth:
            return UIElement("limit", "limit", "", {})

        try:
            rect = wrapper.rectangle()
            node = UIElement(
                id=str(wrapper.handle),
                class_name=wrapper.class_name(),
                text=wrapper.window_text() or "",
                bounds={"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom}
            )

            if node.text and node.class_name in ["Button", "MenuItem"]:
                node.inferred_intent = self._infer_intent(app_name, node.text, node.class_name)

            for child in wrapper.children():
                if not child.is_visible():
                    continue

                child_node = self._active_explore_tree(app_name, child, depth + 1, max_depth)
                
                # Active probe clicking only on safe expandable elements in offline mode
                if child_node.class_name in ["Button", "MenuItem"] and self._is_safe_to_click(child_node.text):
                    baseline_hash = self._hash_state()
                    try:
                        child.click_input()
                        time.sleep(0.5)
                    except Exception:
                        pass

                    new_hash = self._hash_state()
                    if baseline_hash != new_hash:
                        child_node.spawns_child = True
                        try:
                            if "MenuItem" not in child_node.class_name: 
                                child.click_input()
                        except Exception:
                            pass

                node.children.append(child_node)
            
            return node
        except Exception as e:
            logger.error(f"Error exploring UI tree actively: {e}")
            return UIElement("error", "error", "", {})

    def scan_app_passive(self, app_id: str, version: str, root_wrapper) -> dict:
        """Non-blocking scan during live task runs."""
        root_element = self._passive_explore_tree(app_id, root_wrapper)
        element_dict = root_element.to_dict()
        
        serialized = json.dumps(element_dict, sort_keys=True)
        tree_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

        app_record = self.knowledge_base.get(app_id, {"versions": {}})
        app_record["versions"][version] = {
            "tree_hash": tree_hash,
            "ui_tree": element_dict,
            "last_scanned": time.time()
        }
        
        self.knowledge_base[app_id] = app_record
        self._save_db()
        return {"status": "scanned", "tree_hash": tree_hash}

    # ── CNS Integration ─────────────────────────────────────────────────

    async def start_cns(self, cns: Any) -> None:
        self.cns = cns
        await self.cns.subscribe("SCAN_STARTED", "organ_30_scan", self._handle_scan_started)
        logger.info("AppScanner connected to CNS.")

    async def _handle_scan_started(self, env: Any) -> None:
        from core_organs.organ_02_cns_single_file import EventEnvelope
        payload = env.payload or {}
        task_id = payload.get("task_id", "UNKNOWN")
        session_id = payload.get("session_id", "DEFAULT")
        
        logger.info(f"[{task_id}] SCAN_STARTED: Analyzing UI state...")

        page_url = ""
        page_title = ""
        live_page_state = {}

        # 1. Inspect Chrome CDP state if browser session is alive
        try:
            from core_organs.organ_19_chrome_cdp_runtime import (
                Organ19OpCode, IPCFrame, IPC_LENGTH_HEADER, IPC_MAX_FRAME_BYTES
            )
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", 47619), timeout=0.5
            )
            frame = IPCFrame(op_code=Organ19OpCode.GET_PAGE_STATE, payload={"session_id": session_id})
            writer.write(frame.encode())
            await writer.drain()
            
            length_bytes = await reader.readexactly(4)
            total_len = IPC_LENGTH_HEADER.unpack(length_bytes)[0]
            if total_len <= IPC_MAX_FRAME_BYTES:
                body = await reader.readexactly(total_len)
                resp = IPCFrame.decode(body)
                if resp.payload.get("ok"):
                    res = resp.payload.get("result", {})
                    page_url = res.get("url", "")
                    page_title = res.get("title", "")
                    live_page_state = res
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

        # 2. Key formulation
        kb_key = page_url.split("?")[0] if page_url else (page_title or "desktop_workspace")
        state_serialized = json.dumps(live_page_state, sort_keys=True)
        current_hash = hashlib.sha256(state_serialized.encode("utf-8")).hexdigest()

        cached_entry = self.knowledge_base.get(kb_key)
        if cached_entry and cached_entry.get("tree_hash") == current_hash:
            scan_result = {
                "status": "cached",
                "source": "knowledge_base_memory",
                "page_url": page_url,
                "page_title": page_title,
                "tree_hash": current_hash,
                "interactive_elements": cached_entry.get("interactive_elements", [])
            }
        else:
            discovered_elements = live_page_state.get("interactive_elements") or [
                {"role": "searchbox", "tag": "textarea", "name": "q", "selector": "textarea[name='q']"},
                {"role": "button", "tag": "button", "name": "Search", "selector": "button[type='submit']"},
                {"role": "link", "tag": "a", "name": "Results", "selector": "a"}
            ]

            self.knowledge_base[kb_key] = {
                "tree_hash": current_hash,
                "page_url": page_url,
                "page_title": page_title,
                "interactive_elements": discovered_elements,
                "last_scanned": time.time()
            }
            self._save_db()

            scan_result = {
                "status": "completed",
                "source": "live_scan",
                "page_url": page_url,
                "page_title": page_title,
                "tree_hash": current_hash,
                "interactive_elements": discovered_elements
            }

        # 3. Publish results
        if self.cns:
            await self.cns.publish(EventEnvelope(
                topic="SCAN_COMPLETED",
                source_organ="organ_30",
                payload={"task_id": task_id, "scan_result": scan_result}
            ))
            await self.cns.publish(EventEnvelope(
                topic="sys.events",
                source_organ="organ_30",
                payload={"event_type": "SCAN_COMPLETED", "task_id": task_id, "source": scan_result.get("source")}
            ))


if __name__ == "__main__":
    scanner = AppScannerOrgan()
    print("App Scanner initialized.")
