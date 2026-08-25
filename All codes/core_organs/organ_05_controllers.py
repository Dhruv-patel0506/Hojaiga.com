"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 5
Name: Controllers (Execution, Governance, History, App, Chrome CDP, Task, Planning)

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Controllers]
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
Dependencies: enum, typing, future, platform, subprocess, asyncio, logging, json...
"""
from __future__ import annotations

import abc
import asyncio
import enum
import json
import logging
import platform
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Set, List

# ═══════════════════════════════════════════════════════════════════════════
# LOGGING (Policy Manual Ch.8 — Logging Policy: append-only, structured)
# ═══════════════════════════════════════════════════════════════════════════
logger = logging.getLogger("hojaiga.organ05.controllers")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(
        '{"ts":"%(asctime)s","level":"%(levelname)s","component":"%(name)s","msg":%(message)r}'
    ))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)


# ═══════════════════════════════════════════════════════════════════════════
# ENUMS — State Catalog & Data Contracts
# ═══════════════════════════════════════════════════════════════════════════
class ControllerState(str, enum.Enum):
    UNINITIALIZED = "UNINITIALIZED"
    IDLE = "IDLE"
    EXECUTING = "EXECUTING"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


class TargetController(str, enum.Enum):
    MASTER = "master"
    TASK = "task"
    PLANNING = "planning"
    APP = "app"
    TOOL = "tool"
    EXECUTION = "execution"
    GOVERNANCE = "governance"
    HISTORY = "history"
    CHROME = "chrome"


class ExecutionStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"


# ═══════════════════════════════════════════════════════════════════════════
# DATA CONTRACTS
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class ControllerTaskRequest:
    target_controller: TargetController
    action: str
    parameters: dict[str, Any] = field(default_factory=dict)
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    priority: int = 5
    timeout_seconds: float = 30.0
    schema_version: str = "1.0.0"


@dataclass
class ControllerExecutionResult:
    task_id: str
    status: ExecutionStatus
    result: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    controller: Optional[str] = None
    schema_version: str = "1.0.0"


@dataclass
class GovernanceVerdict:
    approved: bool
    reason: str = ""


@dataclass
class ControllerStatusPayload:
    controller_id: str
    state: ControllerState
    active_tasks: int
    total_processed: int


# ═══════════════════════════════════════════════════════════════════════════
# EVENTS
# ═══════════════════════════════════════════════════════════════════════════
class Events(str, enum.Enum):
    CONTROLLER_REGISTERED = "EVENT_CONTROLLER_REGISTERED"
    TASK_DISPATCHED_TO_DOMAIN = "EVENT_TASK_DISPATCHED_TO_DOMAIN"
    GOVERNANCE_BLOCKED = "EVENT_GOVERNANCE_BLOCKED"
    EXECUTION_TERMINATED = "EVENT_EXECUTION_TERMINATED"
    CONTROLLER_TASK_STARTED = "EVENT_CONTROLLER_TASK_STARTED"
    CONTROLLER_TASK_COMPLETED = "EVENT_CONTROLLER_TASK_COMPLETED"
    CONTROLLER_ERROR = "EVENT_CONTROLLER_ERROR"


EventCallback = Callable[[Events, dict[str, Any]], None]


class EventEmitter:
    """Minimal pub/sub bus standing in for the CNS Event Bus."""

    def __init__(self) -> None:
        self._subscribers: list[EventCallback] = []

    def subscribe(self, cb: EventCallback) -> None:
        self._subscribers.append(cb)

    def emit(self, event: Events, payload: dict[str, Any]) -> None:
        logger.info(json.dumps({"event": event.value, "payload": payload}, default=str))
        for cb in self._subscribers:
            try:
                cb(event, payload)
            except Exception:
                logger.exception("subscriber_failed")


# ═══════════════════════════════════════════════════════════════════════════
# INTERFACES
# ═══════════════════════════════════════════════════════════════════════════
class IBaseController(abc.ABC):
    def __init__(self, controller_id: TargetController, events: EventEmitter) -> None:
        self.controller_id = controller_id
        self._events = events
        self.state = ControllerState.UNINITIALIZED
        self._active_tasks = 0
        self._total_processed = 0
        self._config: dict[str, Any] = {}

    def initialize(self, config: dict[str, Any]) -> None:
        self._config = dict(config)
        self.state = ControllerState.IDLE
        self._events.emit(Events.CONTROLLER_REGISTERED, {"controller": self.controller_id.value})

    @abc.abstractmethod
    async def execute_domain_task(self, task: ControllerTaskRequest) -> ControllerExecutionResult:
        ...

    def get_health(self) -> ControllerStatusPayload:
        return ControllerStatusPayload(
            controller_id=self.controller_id.value,
            state=self.state,
            active_tasks=self._active_tasks,
            total_processed=self._total_processed,
        )

    async def _guarded_execute(self, task: ControllerTaskRequest) -> ControllerExecutionResult:
        self._active_tasks += 1
        self.state = ControllerState.EXECUTING
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self.execute_domain_task(task), timeout=task.timeout_seconds
            )
            result.duration_ms = (time.monotonic() - start) * 1000.0
            self.state = ControllerState.IDLE
            return result
        except asyncio.TimeoutError:
            self.state = ControllerState.ERROR
            return ControllerExecutionResult(
                task_id=task.task_id, status=ExecutionStatus.TIMEOUT,
                error="timeout_exceeded", controller=self.controller_id.value,
                duration_ms=(time.monotonic() - start) * 1000.0,
            )
        except Exception as exc:
            self.state = ControllerState.ERROR
            self._events.emit(Events.CONTROLLER_ERROR, {
                "controller": self.controller_id.value, "task_id": task.task_id, "error": str(exc)
            })
            return ControllerExecutionResult(
                task_id=task.task_id, status=ExecutionStatus.FAILED,
                error=str(exc), controller=self.controller_id.value,
                duration_ms=(time.monotonic() - start) * 1000.0,
            )
        finally:
            self._active_tasks -= 1
            self._total_processed += 1
            self.state = ControllerState.IDLE if self.state == ControllerState.EXECUTING else self.state


class IToolRunner(abc.ABC):
    @abc.abstractmethod
    async def invoke_tool(self, tool_id: str, parameters: dict[str, Any]) -> ControllerExecutionResult:
        ...


# ═══════════════════════════════════════════════════════════════════════════
# EXECUTION CONTROLLER — process spawning & lifecycle management
# ═══════════════════════════════════════════════════════════════════════════
class ExecutionController(IBaseController, IToolRunner):
    """Low-level OS process supervisor with active process tracking."""

    def __init__(self, events: EventEmitter) -> None:
        super().__init__(TargetController.EXECUTION, events)
        self._is_windows = platform.system() == "Windows"
        self._active_processes: dict[str, subprocess.Popen] = {}

    async def execute_domain_task(self, task: ControllerTaskRequest) -> ControllerExecutionResult:
        action = task.parameters.get("action", task.action)
        if action in ("spawn_process", "launch"):
            return await self._spawn(task)
        elif action == "connector":
            from core_organs.organ_15_external_connectors import ConnectorGateway, ConnectorCommandRequest, ConnectorType
            gw = ConnectorGateway()
            gw.register_default_connectors()
            
            c_type = task.parameters.get("connector_type")
            c_action = task.parameters.get("connector_action")
            c_payload = task.parameters.get("payload", {})
            session_id = task.parameters.get("session_id")
            
            if not c_type or not isinstance(c_type, str):
                return ControllerExecutionResult(
                    task_id=task.task_id, status=ExecutionStatus.FAILED,
                    error="missing_or_invalid_connector_type", controller=self.controller_id.value,
                )
            
            if not c_action or not isinstance(c_action, str):
                return ControllerExecutionResult(
                    task_id=task.task_id, status=ExecutionStatus.FAILED,
                    error="missing_or_invalid_connector_action", controller=self.controller_id.value,
                )
            
            req = ConnectorCommandRequest(connector_type=ConnectorType[c_type], action_name=c_action, payload=c_payload, session_id=session_id)
            resp = await gw.route(req)
            status = ExecutionStatus.SUCCESS if resp.status == "OK" else ExecutionStatus.FAILED
            return ControllerExecutionResult(task_id=task.task_id, status=status, result=resp.result_payload, error=resp.error_message, controller=self.controller_id.value)
        
        return ControllerExecutionResult(
            task_id=task.task_id, status=ExecutionStatus.FAILED,
            error=f"unsupported_execution_action:{action}", controller=self.controller_id.value,
        )

    async def invoke_tool(self, tool_id: str, parameters: dict[str, Any]) -> ControllerExecutionResult:
        req = ControllerTaskRequest(
            target_controller=TargetController.EXECUTION, action="spawn_process",
            parameters={"action": "spawn_process", "command": parameters.get("command", [tool_id])},
        )
        return await self._guarded_execute(req)

    async def _spawn(self, task: ControllerTaskRequest) -> ControllerExecutionResult:
        command: list[str] = task.parameters.get("command", [])
        if not command:
            return ControllerExecutionResult(
                task_id=task.task_id, status=ExecutionStatus.FAILED,
                error="empty_command", controller=self.controller_id.value,
            )

        # Handle windows application launches (e.g. OBS Studio, Notepad)
        if self._is_windows and (command[0] in ("start", "obs64") or "obs" in command[0].lower()):
            try:
                proc = subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self._active_processes[task.task_id] = proc
                return ControllerExecutionResult(
                    task_id=task.task_id, status=ExecutionStatus.SUCCESS,
                    result={"launched": True, "pid": proc.pid}, controller=self.controller_id.value,
                )
            except Exception as e:
                return ControllerExecutionResult(
                    task_id=task.task_id, status=ExecutionStatus.FAILED,
                    error=str(e), controller=self.controller_id.value,
                )

        creationflags = 0
        if self._is_windows:
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=creationflags,
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=task.timeout_seconds)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            self._events.emit(Events.EXECUTION_TERMINATED, {"task_id": task.task_id, "reason": "timeout"})
            return ControllerExecutionResult(
                task_id=task.task_id, status=ExecutionStatus.TIMEOUT,
                error="process_timeout", controller=self.controller_id.value,
            )

        status = ExecutionStatus.SUCCESS if proc.returncode == 0 else ExecutionStatus.FAILED
        return ControllerExecutionResult(
            task_id=task.task_id, status=status,
            result={"stdout": stdout.decode(errors="replace"), "stderr": stderr.decode(errors="replace"),
                    "exit_code": proc.returncode},
            controller=self.controller_id.value,
        )


# ═══════════════════════════════════════════════════════════════════════════
# GOVERNANCE CONTROLLER
# ═══════════════════════════════════════════════════════════════════════════
class GovernanceController(IBaseController):
    PROTECTED_ACTIONS = {"modify_governing_document", "modify_architecture", "delete_history"}

    async def execute_domain_task(self, task: ControllerTaskRequest) -> ControllerExecutionResult:
        verdict = self.validate(task)
        status = ExecutionStatus.SUCCESS if verdict.approved else ExecutionStatus.BLOCKED
        return ControllerExecutionResult(
            task_id=task.task_id, status=status, result={"approved": verdict.approved, "reason": verdict.reason},
            controller=self.controller_id.value,
        )

    def validate(self, task: ControllerTaskRequest) -> GovernanceVerdict:
        action = task.parameters.get("action", task.action)
        if action in self.PROTECTED_ACTIONS:
            return GovernanceVerdict(approved=False, reason="protected_resource_requires_human_authorization")
        return GovernanceVerdict(approved=True, reason="policy_compliant")


# ═══════════════════════════════════════════════════════════════════════════
# HISTORY CONTROLLER (Append-Only)
# ═══════════════════════════════════════════════════════════════════════════
class HistoryController(IBaseController):
    def __init__(self, events: EventEmitter) -> None:
        super().__init__(TargetController.HISTORY, events)
        self._log: list[dict[str, Any]] = []

    async def execute_domain_task(self, task: ControllerTaskRequest) -> ControllerExecutionResult:
        entry = {"task_id": task.task_id, "recorded_at": time.time(), **task.parameters}
        self._log.append(entry)
        return ControllerExecutionResult(
            task_id=task.task_id, status=ExecutionStatus.SUCCESS,
            result={"recorded": True, "entries": len(self._log)}, controller=self.controller_id.value,
        )

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._log)


# ═══════════════════════════════════════════════════════════════════════════
# TOOL CONTROLLER
# ═══════════════════════════════════════════════════════════════════════════
class ToolController(IBaseController):
    def __init__(self, events: EventEmitter, execution: ExecutionController) -> None:
        super().__init__(TargetController.TOOL, events)
        self._execution = execution

    async def execute_domain_task(self, task: ControllerTaskRequest) -> ControllerExecutionResult:
        tool_id = task.parameters.get("tool_id", "unknown_tool")
        return await self._execution.invoke_tool(tool_id, task.parameters)


# ═══════════════════════════════════════════════════════════════════════════
# CHROME CDP CONTROLLER
# ═══════════════════════════════════════════════════════════════════════════
class ChromeCDPController(IBaseController):
    def __init__(self, events: EventEmitter) -> None:
        super().__init__(TargetController.CHROME, events)
        self.tcp_port = 47619
        self._bootstrapping = False

    async def _ensure_cdp_runtime(self) -> None:
        """Verifies if Organ 19 IPC server is listening; launches once in background if absent."""
        if self._bootstrapping:
            return
        self._bootstrapping = True

        from pathlib import Path
        import sys
        
        organ_19_path = Path(__file__).parent / "organ_19_chrome_cdp_runtime.py"
        cmd = [sys.executable, str(organ_19_path)]

        try:
            # Check port first
            reader, writer = await asyncio.open_connection("127.0.0.1", self.tcp_port)
            writer.close()
            await writer.wait_closed()
        except Exception:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            await asyncio.sleep(1.5)
        finally:
            self._bootstrapping = False

    async def execute_domain_task(self, task: ControllerTaskRequest) -> ControllerExecutionResult:
        from core_organs.organ_19_chrome_cdp_runtime import (
            Organ19OpCode, IPCFrame, IPC_LENGTH_HEADER, IPC_MAX_FRAME_BYTES
        )

        action = task.action.upper()
        payload = task.parameters.get("payload", {})

        action_map = {
            "LAUNCH_BROWSER": Organ19OpCode.LAUNCH_BROWSER,
            "NAVIGATE": Organ19OpCode.NAVIGATE,
            "CREATE_TAB": Organ19OpCode.CREATE_TAB,
            "NEW_TAB": Organ19OpCode.CREATE_TAB,
            "GET_DOM_TREE": Organ19OpCode.GET_DOM_TREE,
            "GET_PAGE_STATE": Organ19OpCode.GET_PAGE_STATE,
            "EXTRACT": Organ19OpCode.GET_DOM_TREE,
            "SAVE": Organ19OpCode.GET_PAGE_STATE,
            "INTERACT": Organ19OpCode.CLICK,
            "CLICK": Organ19OpCode.CLICK,
            "SEARCH": Organ19OpCode.CLICK,
            "RESEARCH": Organ19OpCode.CLICK,
            "QUERY": Organ19OpCode.CLICK,
            "TYPE": Organ19OpCode.TYPE_TEXT,
            "TYPE_TEXT": Organ19OpCode.TYPE_TEXT,
            "PRESS_KEY": Organ19OpCode.PRESS_KEY,
            "SCREENSHOT": Organ19OpCode.SCREENSHOT,
            "SCROLL": Organ19OpCode.SCROLL,
            "RELOAD": Organ19OpCode.RELOAD,
            "GO_BACK": Organ19OpCode.GO_BACK,
            "GO_FORWARD": Organ19OpCode.GO_FORWARD
        }

        op_code = action_map.get(action, Organ19OpCode.CLICK)
        frame = IPCFrame(op_code=op_code, payload=payload)

        try:
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", self.tcp_port)
            except Exception:
                await self._ensure_cdp_runtime()
                reader, writer = await asyncio.open_connection("127.0.0.1", self.tcp_port)

            writer.write(frame.encode())
            await writer.drain()

            length_bytes = await reader.readexactly(4)
            total_len = IPC_LENGTH_HEADER.unpack(length_bytes)[0]
            if total_len > IPC_MAX_FRAME_BYTES:
                raise ValueError("Response frame exceeds max size")

            body = await reader.readexactly(total_len)
            response_frame = IPCFrame.decode(body)
            writer.close()
            await writer.wait_closed()

            if response_frame.op_code == Organ19OpCode.ERROR or not response_frame.payload.get("ok"):
                return ControllerExecutionResult(
                    task_id=task.task_id, status=ExecutionStatus.FAILED,
                    error=response_frame.payload.get("error", "unknown error"),
                    controller=self.controller_id.value,
                    result=response_frame.payload
                )

            return ControllerExecutionResult(
                task_id=task.task_id, status=ExecutionStatus.SUCCESS,
                controller=self.controller_id.value,
                result=response_frame.payload.get("result", {})
            )

        except Exception as e:
            logger.error(f"ChromeCDPController exception: {e}")
            return ControllerExecutionResult(
                task_id=task.task_id, status=ExecutionStatus.FAILED,
                error=f"chrome_cdp_exception: {str(e)}", controller=self.controller_id.value,
            )


# ═══════════════════════════════════════════════════════════════════════════
# APP CONTROLLER
# ═══════════════════════════════════════════════════════════════════════════
class AppController(IBaseController):
    def __init__(self, events: EventEmitter, execution: ExecutionController) -> None:
        super().__init__(TargetController.APP, events)
        self._execution = execution

    async def execute_domain_task(self, task: ControllerTaskRequest) -> ControllerExecutionResult:
        payload = task.parameters.get("payload", {})
        app_action = task.parameters.get("app_action") or payload.get("app_action") or task.action or "launch"
        command = task.parameters.get("command") or payload.get("command") or []

        if not command:
            param_str = f"{json.dumps(task.parameters)} {task.action}".lower()
            if "obs" in param_str:
                command = ["start", "obs64"]
            elif "notepad" in param_str:
                command = ["notepad.exe"]
            elif "calc" in param_str:
                command = ["calc.exe"]
            else:
                command = ["python", "--version"]

        if app_action in ("launch", "spawn_process", "INTERACT", "TASK", "LAUNCH_APP") and command:
            exec_task = ControllerTaskRequest(
                target_controller=TargetController.EXECUTION, action="spawn_process",
                parameters={"action": "spawn_process", "command": command},
                timeout_seconds=task.timeout_seconds,
            )
            return await self._execution._guarded_execute(exec_task)

        elif app_action == "connector":
            exec_task = ControllerTaskRequest(
                target_controller=TargetController.EXECUTION, action="connector",
                parameters=task.parameters,
                timeout_seconds=task.timeout_seconds,
            )
            return await self._execution._guarded_execute(exec_task)

        return ControllerExecutionResult(
            task_id=task.task_id, status=ExecutionStatus.FAILED,
            error="unsupported_app_action_or_missing_command", controller=self.controller_id.value,
        )


# ═══════════════════════════════════════════════════════════════════════════
# TASK / PLANNING / MASTER CONTROLLERS
# ═══════════════════════════════════════════════════════════════════════════
class TaskController(IBaseController):
    def __init__(self, events: EventEmitter) -> None:
        super().__init__(TargetController.TASK, events)
        self._registry: dict[str, ControllerTaskRequest] = {}

    async def execute_domain_task(self, task: ControllerTaskRequest) -> ControllerExecutionResult:
        op = task.parameters.get("op", "register")
        if op == "register":
            self._registry[task.task_id] = task
            return ControllerExecutionResult(
                task_id=task.task_id, status=ExecutionStatus.SUCCESS,
                result={"registered": True}, controller=self.controller_id.value,
            )
        if op == "cancel":
            target = task.parameters.get("target_task_id")
            existed = self._registry.pop(target, None) is not None
            if existed:
                self._events.emit(Events.EXECUTION_TERMINATED, {"task_id": target, "reason": "user_cancel"})
            return ControllerExecutionResult(
                task_id=task.task_id, status=ExecutionStatus.SUCCESS,
                result={"cancelled": existed}, controller=self.controller_id.value,
            )
        return ControllerExecutionResult(
            task_id=task.task_id, status=ExecutionStatus.FAILED,
            error=f"unsupported_task_op:{op}", controller=self.controller_id.value,
        )


class PlanningController(IBaseController):
    async def execute_domain_task(self, task: ControllerTaskRequest) -> ControllerExecutionResult:
        plan_dag: list[dict[str, Any]] = task.parameters.get("dag", [])
        directives = [
            {"step": i, "target": node.get("target_controller"), "action": node.get("action")}
            for i, node in enumerate(plan_dag)
        ]
        return ControllerExecutionResult(
            task_id=task.task_id, status=ExecutionStatus.SUCCESS,
            result={"directives": directives}, controller=self.controller_id.value,
        )


class MasterController(IBaseController):
    def __init__(self, events: EventEmitter, registry: dict[TargetController, IBaseController]) -> None:
        super().__init__(TargetController.MASTER, events)
        self._registry = registry

    async def execute_domain_task(self, task: ControllerTaskRequest) -> ControllerExecutionResult:
        target = self._registry.get(task.target_controller)
        if target is None:
            return ControllerExecutionResult(
                task_id=task.task_id, status=ExecutionStatus.FAILED,
                error="unregistered_controller", controller=self.controller_id.value,
            )
        self._events.emit(Events.TASK_DISPATCHED_TO_DOMAIN, {
            "task_id": task.task_id, "target": task.target_controller.value,
        })
        return await target._guarded_execute(task)


# ═══════════════════════════════════════════════════════════════════════════
# SCHEDULER & CONTROLLERS CORE
# ═══════════════════════════════════════════════════════════════════════════
class Scheduler:
    def __init__(self) -> None:
        self._queue: asyncio.PriorityQueue[tuple[int, float, ControllerTaskRequest]] = asyncio.PriorityQueue()
        self._seq = 0

    async def submit(self, task: ControllerTaskRequest) -> None:
        self._seq += 1
        await self._queue.put((task.priority, self._seq, task))

    async def next(self) -> ControllerTaskRequest:
        _, _, task = await self._queue.get()
        return task

    def qsize(self) -> int:
        return self._queue.qsize()


class ControllersCore:
    def __init__(self) -> None:
        self.events = EventEmitter()
        self.scheduler = Scheduler()

        self.execution = ExecutionController(self.events)
        self.governance = GovernanceController(TargetController.GOVERNANCE, self.events)
        self.history = HistoryController(self.events)
        self.tool = ToolController(self.events, self.execution)
        self.app = AppController(self.events, self.execution)
        self.task = TaskController(self.events)
        self.planning = PlanningController(TargetController.PLANNING, self.events)
        self.chrome = ChromeCDPController(self.events)

        self._registry: dict[TargetController, IBaseController] = {
            TargetController.EXECUTION: self.execution,
            TargetController.GOVERNANCE: self.governance,
            TargetController.HISTORY: self.history,
            TargetController.TOOL: self.tool,
            TargetController.APP: self.app,
            TargetController.TASK: self.task,
            TargetController.PLANNING: self.planning,
            TargetController.CHROME: self.chrome,
        }
        self.master = MasterController(self.events, self._registry)
        self._registry[TargetController.MASTER] = self.master

        for controller in self._registry.values():
            controller.initialize({})

        self._cancelled: set[str] = set()

    # ── CNS Integration ─────────────────────────────────────────────────

    async def start_cns(self, cns) -> None:
        self.cns = cns
        await self.cns.subscribe("INVOKE_CONTROLLER", "organ_05_invoke", self._handle_invoke_controller)
        logger.info("ControllersCore connected to CNS.")
        
    async def _handle_invoke_controller(self, env) -> None:
        from core_organs.organ_02_cns_single_file import EventEnvelope
        payload = env.payload
        task_id = payload.get("task_id")
        
        target_ctrl = payload.get("target_controller", "chrome")
        try:
            target_enum = TargetController(target_ctrl)
        except ValueError:
            target_enum = TargetController.CHROME

        request = ControllerTaskRequest(
            target_controller=target_enum,
            action=payload.get("action", "INTERACT"),
            parameters=payload.get("parameters", {}),
            task_id=task_id
        )
        
        await self.cns.publish(EventEnvelope(
            topic="CONTROLLER_EXECUTING",
            source_organ="organ_05",
            payload={"task_id": task_id, "target": request.target_controller.value}
        ))
        await self.cns.publish(EventEnvelope(
            topic="sys.events",
            source_organ="organ_05",
            payload={"event_type": "CONTROLLER_EXECUTING", "task_id": task_id}
        ))
        
        result = await self.dispatch(request)
        
        if hasattr(self, "cns"):
            await self.cns.publish(EventEnvelope(
                topic="CONTROLLER_EXECUTION_COMPLETED", source_organ="organ_05",
                payload={
                    "task_id": task_id,
                    "result": result.status.value,
                    "error": result.error,
                    "result_data": getattr(result, "result", {})
                }
            ))

    async def dispatch(self, request: ControllerTaskRequest) -> ControllerExecutionResult:
        self.events.emit(Events.CONTROLLER_TASK_STARTED, {"task_id": request.task_id})

        if request.task_id in self._cancelled:
            return ControllerExecutionResult(
                task_id=request.task_id, status=ExecutionStatus.CANCELLED, controller="core",
            )

        if request.target_controller != TargetController.GOVERNANCE:
            verdict = self.governance.validate(request)
            if not verdict.approved:
                self.events.emit(Events.GOVERNANCE_BLOCKED, {
                    "task_id": request.task_id, "reason": verdict.reason,
                })
                result = ControllerExecutionResult(
                    task_id=request.task_id, status=ExecutionStatus.BLOCKED,
                    error=verdict.reason, controller="governance",
                )
                await self._record_history(request, result)
                return result

        result = await self.master.execute_domain_task(request)
        await self._record_history(request, result)

        self.events.emit(Events.CONTROLLER_TASK_COMPLETED, {
            "task_id": request.task_id, "status": result.status.value,
        })
        return result

    async def _record_history(self, request: ControllerTaskRequest, result: ControllerExecutionResult) -> None:
        history_task = ControllerTaskRequest(
            target_controller=TargetController.HISTORY, action="record",
            parameters={
                "op": "record", "target_controller": request.target_controller.value,
                "action": request.action, "status": result.status.value, "error": result.error,
            },
        )
        await self.history._guarded_execute(history_task)


if __name__ == "__main__":
    async def _test():
        core = ControllersCore()
        req = ControllerTaskRequest(
            target_controller=TargetController.APP,
            action="launch",
            parameters={"command": ["python", "--version"]}
        )
        res = await core.dispatch(req)
        print(f"Controller test: {res.status.value}")
    asyncio.run(_test())
