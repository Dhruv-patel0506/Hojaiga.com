"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 13
Name: Interface Layer & Audio/Visual Ingress Gateway

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Interface Layer]
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
Dependencies: matplotlib, typing, asyncio, json, logging, time, uuid, dataclasses, enum, base64, io...
"""
from __future__ import annotations

import asyncio
import base64
import dataclasses
import enum
import io
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("hojaiga.organ13.interface")
if not logger.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("[InterfaceLayer] %(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)

# Optional soft imports for multimedia/plotting
try:
    import matplotlib
    matplotlib.use("Agg")  # Non-interactive headless backend
    import matplotlib.pyplot as plt
    _HAS_MATPLOTLIB = True
except ImportError:
    plt = None
    _HAS_MATPLOTLIB = False

try:
    import winsound
    _HAS_WINSOUND = True
except ImportError:
    winsound = None
    _HAS_WINSOUND = False


# ==============================================================================
# SECTION 1 — ENUMS & DATA CONTRACTS
# ==============================================================================
class NotificationSeverity(str, enum.Enum):
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class SoundCue(str, enum.Enum):
    TASK_START = "TASK_START"
    STEP_COMPLETE = "STEP_COMPLETE"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    BLOCKED = "BLOCKED"
    POPUP_TRAP = "POPUP_TRAP"


@dataclass
class UICommandPayload:
    command: str
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    expected_text: Optional[str] = None
    profile: str = "Default"
    parameters: Dict[str, Any] = field(default_factory=dict)
    client_channel: str = "CLI"


@dataclass
class TelemetryReport:
    task_id: str
    total_steps: int
    duration_seconds: float
    nodes_executed: List[str]
    success_rate: float
    memory_peak_mb: float = 0.0
    timeline: List[Tuple[float, str, str]] = field(default_factory=list)


# ==============================================================================
# SECTION 2 — AUDIO NOTIFICATION ENGINE
# ==============================================================================
class AudioNotificationEngine:
    """Non-blocking audio feedback and tone synthesis."""

    _FREQUENCY_MAP = {
        SoundCue.TASK_START: (523, 100),       # C5
        SoundCue.STEP_COMPLETE: (659, 80),     # E5
        SoundCue.SUCCESS: (784, 250),          # G5
        SoundCue.FAILURE: (220, 400),          # A3
        SoundCue.BLOCKED: (330, 200),          # E4
        SoundCue.POPUP_TRAP: (880, 150),       # A5
    }

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def play_tone(self, cue: SoundCue) -> None:
        if not self.enabled or not _HAS_WINSOUND or not winsound:
            return

        freq, duration = self._FREQUENCY_MAP.get(cue, (440, 100))
        try:
            # Run tone on a fire-and-forget daemon thread so async loop never blocks
            asyncio.get_event_loop().run_in_executor(
                None, lambda: winsound.Beep(freq, duration)
            )
        except Exception as e:
            logger.debug(f"Audio playback skipped: {e}")

    def notify(self, severity: NotificationSeverity, message: str) -> None:
        cue_map = {
            NotificationSeverity.INFO: SoundCue.STEP_COMPLETE,
            NotificationSeverity.SUCCESS: SoundCue.SUCCESS,
            NotificationSeverity.WARNING: SoundCue.BLOCKED,
            NotificationSeverity.ERROR: SoundCue.FAILURE,
            NotificationSeverity.CRITICAL: SoundCue.FAILURE,
        }
        self.play_tone(cue_map.get(severity, SoundCue.STEP_COMPLETE))
        logger.info(f"[{severity.value}] {message}")


# ==============================================================================
# SECTION 3 — DATA VISUALIZATION & GRAPHING ENGINE (MATPLOTLIB)
# ==============================================================================
class DataVisualizationGraphingEngine:
    """Generates execution timeline plots and outcome telemetry figures."""

    @staticmethod
    def render_execution_timeline(telemetry: TelemetryReport) -> Optional[str]:
        """Renders timeline gantt/step graph and returns base64 PNG image string."""
        if not _HAS_MATPLOTLIB or not plt:
            logger.warning("Matplotlib not installed. Visualization graph generation skipped.")
            return None

        try:
            fig, ax = plt.subplots(figsize=(8, 4), dpi=100)
            
            steps = telemetry.nodes_executed or ["Start", "Process", "Complete"]
            times = list(range(len(steps)))
            
            ax.plot(times, steps, marker="o", linestyle="-", color="#2b82d9", linewidth=2)
            ax.set_title(f"Task Execution DAG Telemetry: {telemetry.task_id[:8]}", fontsize=12, pad=10)
            ax.set_xlabel("Step Sequence", fontsize=10)
            ax.set_ylabel("Active Organ / Sub-Goal", fontsize=10)
            ax.grid(True, linestyle="--", alpha=0.6)
            
            plt.tight_layout()
            
            buf = io.BytesIO()
            plt.savefig(buf, format="png")
            plt.close(fig)
            buf.seek(0)
            
            encoded = base64.b64encode(buf.read()).decode("ascii")
            return encoded
        except Exception as e:
            logger.error(f"Failed to generate visualization graph: {e}")
            return None


# ==============================================================================
# SECTION 4 — INTERFACE LAYER ORGAN (PUBLIC FACADE & CNS ROUTER)
# ==============================================================================
class InterfaceLayerOrgan:
    """Master UI Ingress & Presentation Gateway (Organ 13 / 11)."""

    def __init__(self):
        self.audio = AudioNotificationEngine()
        self.graphing = DataVisualizationGraphingEngine()
        self.cns: Optional[Any] = None
        self.active_tasks: Dict[str, Dict[str, Any]] = {}

    async def start_cns(self, cns: Any) -> None:
        self.cns = cns
        await self.cns.subscribe("TASK_CREATED", "organ_13_ui", self._handle_task_created)
        await self.cns.subscribe("TASK_COMPLETED", "organ_13_ui", self._handle_task_completed)
        await self.cns.subscribe("TASK_FAILED", "organ_13_ui", self._handle_task_failed)
        await self.cns.subscribe("TASK_BLOCKED", "organ_13_ui", self._handle_task_blocked)
        logger.info("InterfaceLayerOrgan online and connected to CNS.")

    async def submit_command(self, raw_command: str, expected_text: Optional[str] = None) -> str:
        """Entrypoint for CLI, UI, and external test scripts to ingest commands into CNS."""
        from core_organs.organ_02_cns_single_file import EventEnvelope

        task_id = str(uuid.uuid4())
        payload = {
            "command": raw_command,
            "request_id": task_id,
            "expected_text": expected_text,
            "timestamp": time.time()
        }

        self.active_tasks[task_id] = {
            "command": raw_command,
            "started_at": time.time(),
            "status": "INGESTED"
        }

        self.audio.play_tone(SoundCue.TASK_START)

        if self.cns:
            await self.cns.publish(EventEnvelope(
                topic="sock.cns.inbound",
                source_organ="organ_13",
                payload=payload
            ))
            await self.cns.publish(EventEnvelope(
                topic="sys.events",
                source_organ="organ_13",
                payload={"event_type": "USER_COMMAND_SUBMITTED", "task_id": task_id, "command": raw_command}
            ))

        return task_id

    # ── Event Listeners ──────────────────────────────────────────────────

    async def _handle_task_created(self, env: Any) -> None:
        payload = env.payload or {}
        task_id = payload.get("task_id", "UNKNOWN")
        logger.info(f"[UI Display] Task accepted: {task_id}")

    async def _handle_task_completed(self, env: Any) -> None:
        payload = env.payload or {}
        task_id = payload.get("task_id", "UNKNOWN")
        
        self.audio.play_tone(SoundCue.SUCCESS)
        logger.info(f"[UI Display] Task completed successfully: {task_id}")

        # Generate final telemetry report and plot
        telemetry = TelemetryReport(
            task_id=task_id,
            total_steps=payload.get("total_steps", 4),
            duration_seconds=payload.get("duration", 0.0),
            nodes_executed=payload.get("nodes", ["Ingress", "Compiler", "CDP", "Verify"]),
            success_rate=1.0
        )
        graph_base64 = self.graphing.render_execution_timeline(telemetry)
        if graph_base64 and self.cns:
            from core_organs.organ_02_cns_single_file import EventEnvelope
            await self.cns.publish(EventEnvelope(
                topic="GRAPH_RENDERED",
                source_organ="organ_13",
                payload={"task_id": task_id, "image_base64": graph_base64}
            ))

    async def _handle_task_failed(self, env: Any) -> None:
        payload = env.payload or {}
        task_id = payload.get("task_id", "UNKNOWN")
        self.audio.play_tone(SoundCue.FAILURE)
        logger.error(f"[UI Display] Task failed: {task_id} — {payload.get('error', 'Unknown')}")

    async def _handle_task_blocked(self, env: Any) -> None:
        payload = env.payload or {}
        task_id = payload.get("task_id", "UNKNOWN")
        self.audio.play_tone(SoundCue.BLOCKED)
        logger.warning(f"[UI Display] Task blocked / awaiting recovery: {task_id}")


if __name__ == "__main__":
    async def _test():
        organ = InterfaceLayerOrgan()
        print("Interface Layer Organ initialized.")
        telemetry = TelemetryReport("test_task_1234", 3, 2.5, ["Brain", "Orchestrator", "Actuator"], 1.0)
        img = organ.graphing.render_execution_timeline(telemetry)
        print(f"Graph generated: {bool(img)}")
    asyncio.run(_test())
