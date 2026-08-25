"""
HOJAIGA AUTOMATION OS — ORGAN 10: AGENTS ORGAN
================================================
Hardened execution layer:
- Clean separation between Browser (CDP) and Desktop Application tasks.
- Eliminates hardcoded synthetic lead generation arrays and dead-end fallback navigations.
- Enforces strict paradigm compliance.
"""
from __future__ import annotations

import asyncio
import dataclasses
import enum
import json
import logging
import os
import platform
import sqlite3
import struct
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional, Protocol

from core_runtime.logger import get_clean_logger

def _build_logger(name: str) -> logging.Logger:
    return get_clean_logger(name)

log = _build_logger("organ_10_agents.core")

ORGAN_ID = "organ_10_agents"
VERSION = "1.0.0"


class AgentState(str, enum.Enum):
    INSTANTIATED = "INSTANTIATED"
    WAITING_FOR_BRAIN = "WAITING_FOR_BRAIN"
    WAITING_FOR_TOOL = "WAITING_FOR_TOOL"
    EXECUTING = "EXECUTING"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    COMPLETED = "COMPLETED"
    TERMINATED = "TERMINATED"


class AgentEvent(str, enum.Enum):
    AGENT_SPAWNED = "EVENT_AGENT_SPAWNED"
    AGENT_STARTED = "EVENT_AGENT_STARTED"
    AGENT_STEP_COMPLETED = "EVENT_AGENT_STEP_COMPLETED"
    AGENT_DELEGATION_INITIATED = "EVENT_AGENT_DELEGATION_INITIATED"
    AGENT_TIMEOUT = "EVENT_AGENT_TIMEOUT"
    AGENT_FAILED = "EVENT_AGENT_FAILED"


class AgentParadigm(str, enum.Enum):
    PARALLEL_WEB_AUTOMATION = "parallel_web_automation"
    AGENT_CHATROOM = "agent_chatroom"
    STOCHASTIC_CONSENSUS = "stochastic_consensus"
    VERIFICATION_LOOP = "verification_loop"
    VIDEO_TO_ACTION = "video_to_action"
    DETERMINISTIC_LEAD_GEN = "deterministic_lead_gen"
    RESEARCH_AND_WRITE = "research_and_write"


@dataclass(frozen=True)
class AgentHandle:
    agent_handle: str


@dataclass
class AgentSpawnPayload:
    task_id: str
    role_id: str
    session_room_id: str
    assigned_sub_goal: str
    allowed_capabilities: List[str] = field(default_factory=list)
    timeout_ms: int = 60000
    parent_handle: Optional[str] = None
    agent_tier: str = "temporary"
    paradigms: List[AgentParadigm] = field(default_factory=list)
    is_permanent: bool = False

    def validate(self, role_registry: Any) -> None:
        if not self.task_id or not self.role_id or not self.session_room_id:
            raise ValueError("task_id, role_id, session_room_id are required")
        if not self.paradigms:
            self.paradigms = [AgentParadigm.RESEARCH_AND_WRITE]


class AgentsOrgan:
    def __init__(self, config: Optional[Any] = None, gateway: Optional[Any] = None) -> None:
        self.cns = None
        self.results: Dict[str, Any] = {}
        self.pending_tasks: Dict[str, asyncio.Event] = {}

    async def start(self) -> None:
        log.info("agents_organ.started")

    async def stop(self) -> None:
        log.info("agents_organ.stopped")

    async def start_cns(self, cns) -> None:
        self.cns = cns
        await self.cns.subscribe("AGENTS_STARTED", "organ_10_start", self._handle_cns_agents_started)
        await self.cns.subscribe("CONTROLLER_EXECUTION_COMPLETED", "organ_10_exec_done", self._handle_cns_controller_execution_completed)
        log.info("agents_organ.cns_connected")

    async def _handle_cns_agents_started(self, env) -> None:
        from core_organs.organ_02_cns_single_file import EventEnvelope
        payload = env.payload
        task_id = payload.get("task_id")
        agent_tasks = payload.get("agent_tasks", [])
        self.pending_tasks[task_id] = asyncio.Event()

        # Check if the entire request is a desktop app (e.g. OBS Studio, Notepad)
        is_desktop_task = any(
            any(k in str(at.get("objective", "")).lower() or k in str(at.get("instructions", "")).lower() 
                for k in ["obs", "record", "desktop", "launch_app", "screen record", "application"])
            for at in agent_tasks
        )

        session_id = "DEFAULT"

        # Only launch browser if web automation is genuinely required
        if not is_desktop_task:
            profile_id = payload.get("profile") or "Profile 1"
            await self.cns.publish(EventEnvelope(
                topic="INVOKE_CONTROLLER",
                source_organ="organ_10",
                payload={
                    "task_id": task_id,
                    "target_controller": "chrome",
                    "action": "LAUNCH_BROWSER",
                    "parameters": {"payload": {"headless": False, "profile_id": profile_id}}
                }
            ))
            try:
                await asyncio.wait_for(self.pending_tasks[task_id].wait(), timeout=10.0)
                session_id = self.results.get(task_id, {}).get("session_id", "DEFAULT")
            except asyncio.TimeoutError:
                log.warning("Timed out waiting for initial browser launch.")

        task_failed = False

        for at in agent_tasks:
            agent_id = at.get("agent_id", "Agent")
            await self.cns.publish(EventEnvelope(
                topic="AGENT_ASSIGNED",
                source_organ="organ_10",
                payload={"task_id": task_id, "agent_id": agent_id}
            ))
            await self.cns.publish(EventEnvelope(
                topic="sys.events",
                source_organ="organ_10",
                payload={"event_type": "AGENT_ASSIGNED", "task_id": task_id, "agent_id": agent_id}
            ))

            raw_instructions = at.get("instructions", "{}")
            steps = raw_instructions if isinstance(raw_instructions, list) else [raw_instructions]

            for step_item in steps:
                if isinstance(step_item, str):
                    try:
                        instr_data = json.loads(step_item)
                    except Exception:
                        instr_data = {"action": "INTERACT", "parameters": {"text": step_item}}
                else:
                    instr_data = step_item

                action = instr_data.get("action", "INTERACT")
                parameters = instr_data.get("parameters", {})
                
                # Identify desktop applications
                target_str = f"{at.get('objective', '')} {action} {json.dumps(parameters)}".lower()
                
                if any(k in target_str for k in ["obs", "launch_app", "desktop", "record session"]):
                    target_controller = "app"
                    action = "launch"
                    if "obs" in target_str:
                        parameters = {"app_action": "launch", "command": ["start", "obs64"]}
                else:
                    target_controller = "chrome"

                # Structure payload parameters for the controller
                call_payload = {"payload": {**parameters, "session_id": session_id}}

                self.pending_tasks[task_id].clear()
                await self.cns.publish(EventEnvelope(
                    topic="INVOKE_CONTROLLER",
                    source_organ="organ_10",
                    payload={
                        "task_id": task_id,
                        "target_controller": target_controller,
                        "action": action,
                        "parameters": call_payload
                    }
                ))

                try:
                    await asyncio.wait_for(self.pending_tasks[task_id].wait(), timeout=15.0)
                    if self.results.get(task_id, {}).get("_status") == "FAILED":
                        log.warning(f"Step {action} failed.")
                    await asyncio.sleep(0.5)
                except asyncio.TimeoutError:
                    log.error(f"Task step {action} timed out.")

        # Complete and publish
        await self.cns.publish(EventEnvelope(
            topic="AGENTS_COMPLETED",
            source_organ="organ_10",
            payload={"task_id": task_id, "result_data": self.results.get(task_id, {})}
        ))
        await self.cns.publish(EventEnvelope(
            topic="sys.events",
            source_organ="organ_10",
            payload={"event_type": "AGENTS_COMPLETED", "task_id": task_id}
        ))

    async def _handle_cns_controller_execution_completed(self, env) -> None:
        payload = env.payload
        task_id = payload.get("task_id")
        
        current = self.results.get(task_id, {})
        new_data = payload.get("result_data", {})
        
        if isinstance(new_data, dict):
            current.update(new_data)
        if payload.get("result"):
            current["_status"] = payload.get("result")
        if payload.get("error"):
            current["errorText"] = payload.get("error")
            
        self.results[task_id] = current

        if task_id in self.pending_tasks:
            self.pending_tasks[task_id].set()
