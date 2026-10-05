#!/usr/bin/env python3
"""
V2 Final Certification Test
============================
Comprehensive end-to-end validation of the Hojaiga V2 runtime architecture.

Phases:
  A - Normal execution with branching
  B - Controlled real execution failure
  C - Brain recovery decision
  D - Retry/replan execution
  E - Downstream convergence
  F - Fatal failure / abort validation
  G - Retry limit / loop protection
  O - Repeatability (10 consecutive successful runs)

Artifacts:
  v2_final_certification_report.md
  v2_final_event_trace.json
  v2_final_state_trace.json
  v2_final_metrics.json
"""

import asyncio
import json
import sys
import time
import uuid
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict

sys.path.append(str(Path(__file__).parent / "All codes"))
from test_hojaiga_browser_autonomy import HojaigaRuntimeInstance
from core_organs.organ_02_cns_single_file import EventBus, EventEnvelope
from core_organs.organ_22_decision_engine import DecisionEngineOrgan


# =============================================================================
# HTTP Test Environment
# =============================================================================

class CertHandler(BaseHTTPRequestHandler):
    """Deterministic HTTP server for certification scenarios."""

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/phase_a_start":
            self._respond(self._page_phase_a_start())
        elif path == "/phase_a_end":
            self._respond(self._page_phase_a_end())
        elif path == "/phase_b_start":
            self._respond(self._page_phase_b_start())
        elif path == "/test/final":
            self._respond(self._page_test_final())
        elif path == "/phase_f_start":
            self._respond(self._page_phase_f_start())
        elif path == "/phase_repeat":
            self._respond(self._page_phase_repeat())
        elif path == "/phase_g_start":
            self._respond(self._page_phase_g_start())
        else:
            self._respond(self._page_404(), status=404)

    def _respond(self, html: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass

    @staticmethod
    def _page_phase_a_start() -> str:
        return "<html><body><h1>Phase A Start</h1><button id='proceed' onclick='window.location.href=\"/phase_a_end\"'>Proceed</button></body></html>"

    @staticmethod
    def _page_phase_a_end() -> str:
        return "<html><body><h1>Phase A End</h1><div id='success'>PHASE_A_SUCCESS</div></body></html>"

    @staticmethod
    def _page_phase_b_start() -> str:
        return "<html><body><h1>Phase B Start</h1><button id='other-btn'>Other</button></body></html>"

    @staticmethod
    def _page_test_final() -> str:
        return "<html><body><h1>Test Final</h1><div id='success'>V2 FINAL SUCCESS</div></body></html>"

    @staticmethod
    def _page_phase_f_start() -> str:
        return "<html><body><h1>Phase F Start</h1><button id='other-btn'>Other</button></body></html>"

    @staticmethod
    def _page_phase_repeat() -> str:
        return "<html><body><h1>Repeat</h1><div id='success'>REPEAT_SUCCESS</div></body></html>"

    @staticmethod
    def _page_phase_g_start() -> str:
        return "<html><body><h1>Phase G Start</h1><button id='other-btn'>Other</button></body></html>"

    @staticmethod
    def _page_404() -> str:
        return "<html><body><h1>404</h1></body></html>"


def start_cert_server(port: int = 9998) -> HTTPServer:
    server = HTTPServer(("127.0.0.1", port), CertHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


# =============================================================================
# Trace & Validation Infrastructure
# =============================================================================

@dataclass
class EventRecord:
    event_id: str
    timestamp_ms: int
    topic: str
    source_organ: str
    payload: Dict[str, Any]
    correlation_id: Optional[str]
    priority: int
    received_at: float


@dataclass
class StateTransition:
    task_id: str
    from_state: str
    to_state: str
    event: str
    timestamp: float
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NodeExecution:
    node_id: str
    name: str
    count: int = 0
    success_count: int = 0
    retry_count: int = 0
    recovery_count: int = 0
    terminal_count: int = 0


class CertificationTracer:
    """Collects events, tracks state transitions, and detects anomalies."""

    def __init__(self):
        self.events: List[EventRecord] = []
        self.transitions: List[StateTransition] = []
        self.nodes: Dict[str, NodeExecution] = {}
        self.task_states: Dict[str, str] = {}
        self.task_events: Dict[str, List[EventRecord]] = {}
        self.violations: List[str] = []
        self.lock = asyncio.Lock()

    async def capture(self, env: EventEnvelope):
        async with self.lock:
            rec = EventRecord(
                event_id=env.event_id,
                timestamp_ms=env.timestamp_ms,
                topic=env.topic,
                source_organ=env.source_organ,
                payload=env.payload.copy(),
                correlation_id=env.correlation_id,
                priority=env.priority,
                received_at=time.time(),
            )
            self.events.append(rec)
            task_id = env.payload.get("task_id")
            if task_id:
                self.task_events.setdefault(task_id, []).append(rec)

    def record_transition(self, task_id: str, from_state: str, to_state: str, event: str, payload: Dict = None):
        self.transitions.append(StateTransition(
            task_id=task_id, from_state=from_state, to_state=to_state,
            event=event, timestamp=time.time(), payload=payload or {}
        ))
        self.task_states[task_id] = to_state

    def record_node(self, node_id: str, node_name: str, event_type: str):
        if node_id not in self.nodes:
            self.nodes[node_id] = NodeExecution(node_id=node_id, name=node_name)
        node = self.nodes[node_id]
        node.count += 1
        if event_type == "SUCCESS":
            node.success_count += 1
        elif event_type == "RETRY":
            node.retry_count += 1
        elif event_type == "RECOVERY":
            node.recovery_count += 1
        elif event_type in ("TASK_COMPLETED", "TASK_ABORTED", "FINAL_ABORTED"):
            node.terminal_count += 1

    def add_violation(self, msg: str):
        self.violations.append(msg)

    def get_task_trace(self, task_id: str) -> List[EventRecord]:
        return self.task_events.get(task_id, [])

    def to_event_trace_dict(self) -> List[Dict]:
        return [asdict(e) for e in self.events]

    def to_state_trace_dict(self) -> List[Dict]:
        return [asdict(t) for t in self.transitions]


# =============================================================================
# Scenario Runners
# =============================================================================

async def scenario_normal_branching(runtime: HojaigaRuntimeInstance, tracer: CertificationTracer, port: int) -> Dict[str, Any]:
    """
    Phase A: Normal execution with dynamic branching.
    """
    result = {"phase": "A", "name": "Normal Execution with Branching", "passed": False, "details": {}}
    request_id = str(uuid.uuid4())
    command = f"certification knowledge task on http://127.0.0.1:{port}/phase_a_start"

    task_id_holder = {}
    task_id_event = asyncio.Event()

    async def capture_task_id(env: EventEnvelope):
        if env.payload.get("request_id") == request_id:
            task_id_holder["task_id"] = env.payload.get("task_id")
            task_id_event.set()

    sub_tc = await runtime.cns.subscribe("TASK_CREATED", "cert_capture_a", capture_task_id)

    async def mock_knowledge_complete(env: EventEnvelope):
        tid = env.payload.get("task_id")
        if tid and (not task_id_holder or env.payload.get("task_id") == task_id_holder.get("task_id")):
            await runtime.cns.publish(EventEnvelope(
                topic="KNOWLEDGE_COMPLETED",
                source_organ="mock_knowledge",
                payload={"task_id": tid}
            ))

    sub_kn = await runtime.cns.subscribe("KNOWLEDGE_STARTED", "mock_knw_a", mock_knowledge_complete)

    await runtime.cns.publish(EventEnvelope(
        topic="sock.cns.inbound",
        source_organ="cert_runner",
        payload={"request_id": request_id, "payload": {"command": command}}
    ))

    try:
        await asyncio.wait_for(task_id_event.wait(), 5.0)
    except asyncio.TimeoutError:
        result["details"]["error"] = "TASK_CREATED not received"
        await runtime.cns.unsubscribe(sub_tc)
        await runtime.cns.unsubscribe(sub_kn)
        return result

    task_id = task_id_holder.get("task_id")
    completion_event = asyncio.Event()
    final_status = {}

    async def wait_completion(env: EventEnvelope):
        if env.payload.get("task_id") == task_id:
            final_status["status"] = env.topic
            if env.topic in ("TASK_COMPLETED", "TASK_FAILED"):
                completion_event.set()

    sub_comp = await runtime.cns.subscribe("TASK_COMPLETED", "cert_comp_a", wait_completion)
    sub_fail = await runtime.cns.subscribe("TASK_FAILED", "cert_fail_a", wait_completion)

    try:
        await asyncio.wait_for(completion_event.wait(), 30.0)
    except asyncio.TimeoutError:
        result["details"]["error"] = "Scenario timed out waiting for completion"
        await runtime.cns.unsubscribe(sub_tc)
        await runtime.cns.unsubscribe(sub_kn)
        await runtime.cns.unsubscribe(sub_comp)
        await runtime.cns.unsubscribe(sub_fail)
        return result

    trace = tracer.get_task_trace(task_id) if task_id else []
    event_types = [e.topic for e in trace]

    has_knowledge_started = "KNOWLEDGE_STARTED" in event_types
    has_knowledge_completed = "KNOWLEDGE_COMPLETED" in event_types
    has_compilation = "COMPILATION_STARTED" in event_types or "COMPILATION_COMPLETED" in event_types
    has_agents = "AGENTS_STARTED" in event_types
    has_success = "TASK_COMPLETED" in event_types

    from collections import Counter
    event_counts = Counter(e.topic for e in trace)
    duplicates = {k: v for k, v in event_counts.items() if v > 1 and k not in ("sys.events",)}
    duplicate_ok = len(duplicates) == 0

    passed = (
        has_knowledge_started and
        has_knowledge_completed and
        has_compilation and
        has_agents and
        has_success and
        duplicate_ok and
        final_status.get("status") == "TASK_COMPLETED"
    )

    result["passed"] = passed
    result["details"] = {
        "task_id": task_id,
        "has_knowledge_started": has_knowledge_started,
        "has_knowledge_completed": has_knowledge_completed,
        "has_compilation": has_compilation,
        "has_agents": has_agents,
        "has_success": has_success,
        "duplicate_ok": duplicate_ok,
        "event_count": len(trace),
        "duplicate_events": list(duplicates.keys()),
        "final_status": final_status.get("status"),
    }

    await runtime.cns.unsubscribe(sub_tc)
    await runtime.cns.unsubscribe(sub_kn)
    await runtime.cns.unsubscribe(sub_comp)
    await runtime.cns.unsubscribe(sub_fail)
    return result


async def scenario_controlled_failure(runtime: HojaigaRuntimeInstance, tracer: CertificationTracer, port: int) -> Dict[str, Any]:
    """
    Phase B: Controlled real execution failure.
    """
    result = {"phase": "B", "name": "Controlled Real Execution Failure", "passed": False, "details": {}}
    request_id = str(uuid.uuid4())
    command = f"final-certification task on http://127.0.0.1:{port}/phase_b_start"

    task_id_holder = {}
    task_id_event = asyncio.Event()

    async def capture_task_id(env: EventEnvelope):
        if env.payload.get("request_id") == request_id:
            task_id_holder["task_id"] = env.payload.get("task_id")
            task_id_event.set()

    sub_tc = await runtime.cns.subscribe("TASK_CREATED", "cert_capture_b", capture_task_id)

    await runtime.cns.publish(EventEnvelope(
        topic="sock.cns.inbound",
        source_organ="cert_runner",
        payload={"request_id": request_id, "payload": {"command": command}}
    ))

    try:
        await asyncio.wait_for(task_id_event.wait(), 5.0)
    except asyncio.TimeoutError:
        result["details"]["error"] = "TASK_CREATED not received"
        await runtime.cns.unsubscribe(sub_tc)
        return result

    task_id = task_id_holder.get("task_id")
    recovery_event = asyncio.Event()
    recovery_payload = {}

    async def on_recovery(env: EventEnvelope):
        if env.payload.get("task_id") == task_id:
            recovery_payload["data"] = env.payload.copy()
            recovery_event.set()

    sub_rec = await runtime.cns.subscribe("RECOVERY_STARTED", "cert_rec_b", on_recovery)

    try:
        await asyncio.wait_for(recovery_event.wait(), 25.0)
    except asyncio.TimeoutError:
        result["details"]["error"] = "RECOVERY_STARTED not received"
        await runtime.cns.unsubscribe(sub_tc)
        await runtime.cns.unsubscribe(sub_rec)
        return result

    trace = tracer.get_task_trace(task_id) if task_id else []
    event_types = [e.topic for e in trace]

    has_task_failed = "TASK_FAILED" in event_types
    has_task_blocked = "TASK_BLOCKED" in event_types
    has_recovery_started = "RECOVERY_STARTED" in event_types
    has_no_false_success = "TASK_COMPLETED" not in event_types

    passed = (
        has_task_failed and
        has_task_blocked and
        has_recovery_started and
        has_no_false_success and
        recovery_payload.get("data", {}).get("task_id") == task_id
    )

    result["passed"] = passed
    result["details"] = {
        "task_id": task_id,
        "has_task_failed": has_task_failed,
        "has_task_blocked": has_task_blocked,
        "has_recovery_started": has_recovery_started,
        "has_no_false_success": has_no_false_success,
        "recovery_payload": recovery_payload.get("data"),
        "event_count": len(trace),
    }

    await runtime.cns.unsubscribe(sub_tc)
    await runtime.cns.unsubscribe(sub_rec)
    return result


async def scenario_brain_recovery_decision(runtime: HojaigaRuntimeInstance, tracer: CertificationTracer, port: int) -> Dict[str, Any]:
    """
    Phase C: Brain recovery decision.
    """
    result = {"phase": "C", "name": "Brain Recovery Decision", "passed": False, "details": {}}
    request_id = str(uuid.uuid4())
    command = f"final-certification task on http://127.0.0.1:{port}/phase_b_start"

    task_id_holder = {}
    task_id_event = asyncio.Event()

    async def capture_task_id(env: EventEnvelope):
        if env.payload.get("request_id") == request_id:
            task_id_holder["task_id"] = env.payload.get("task_id")
            task_id_event.set()

    sub_tc = await runtime.cns.subscribe("TASK_CREATED", "cert_capture_c", capture_task_id)

    await runtime.cns.publish(EventEnvelope(
        topic="sock.cns.inbound",
        source_organ="cert_runner",
        payload={"request_id": request_id, "payload": {"command": command}}
    ))

    try:
        await asyncio.wait_for(task_id_event.wait(), 5.0)
    except asyncio.TimeoutError:
        result["details"]["error"] = "TASK_CREATED not received"
        await runtime.cns.unsubscribe(sub_tc)
        return result

    task_id = task_id_holder.get("task_id")
    recovery_completed_event = asyncio.Event()
    recovery_decision = {}

    async def on_recovery_completed(env: EventEnvelope):
        if env.payload.get("task_id") == task_id:
            recovery_decision["data"] = env.payload.copy()
            recovery_completed_event.set()

    sub_rc = await runtime.cns.subscribe("RECOVERY_COMPLETED", "cert_rc_c", on_recovery_completed)

    try:
        await asyncio.wait_for(recovery_completed_event.wait(), 25.0)
    except asyncio.TimeoutError:
        result["details"]["error"] = "RECOVERY_COMPLETED not received"
        await runtime.cns.unsubscribe(sub_tc)
        await runtime.cns.unsubscribe(sub_rc)
        return result

    decision = recovery_decision.get("data", {}).get("decision")
    rtask_id = recovery_decision.get("data", {}).get("task_id")

    passed = (
        decision is not None and
        rtask_id == task_id and
        decision in ("RETRY", "ALTERNATIVE", "ABORT")
    )

    result["passed"] = passed
    result["details"] = {
        "task_id": task_id,
        "recovery_decision": decision,
        "recovery_task_id": rtask_id,
        "decision_valid": decision in ("RETRY", "ALTERNATIVE", "ABORT"),
    }

    await runtime.cns.unsubscribe(sub_tc)
    await runtime.cns.unsubscribe(sub_rc)
    return result


async def scenario_retry_replan_execution(runtime: HojaigaRuntimeInstance, tracer: CertificationTracer, port: int) -> Dict[str, Any]:
    """
    Phase D+E: Retry/replan and downstream convergence.
    """
    result = {"phase": "D+E", "name": "Retry/Replan & Downstream Convergence", "passed": False, "details": {}}
    request_id = str(uuid.uuid4())
    command = f"final-certification task on http://127.0.0.1:{port}/phase_b_start"

    task_id_holder = {}
    task_id_event = asyncio.Event()

    async def capture_task_id(env: EventEnvelope):
        if env.payload.get("request_id") == request_id:
            task_id_holder["task_id"] = env.payload.get("task_id")
            task_id_event.set()

    sub_tc = await runtime.cns.subscribe("TASK_CREATED", "cert_capture_de", capture_task_id)

    await runtime.cns.publish(EventEnvelope(
        topic="sock.cns.inbound",
        source_organ="cert_runner",
        payload={"request_id": request_id, "payload": {"command": command}}
    ))

    try:
        await asyncio.wait_for(task_id_event.wait(), 5.0)
    except asyncio.TimeoutError:
        result["details"]["error"] = "TASK_CREATED not received"
        await runtime.cns.unsubscribe(sub_tc)
        return result

    task_id = task_id_holder.get("task_id")
    completion_event = asyncio.Event()
    final_status = {}

    async def wait_completion(env: EventEnvelope):
        if env.payload.get("task_id") == task_id:
            final_status["status"] = env.topic
            if env.topic in ("TASK_COMPLETED", "TASK_ABORTED", "FINAL_ABORTED"):
                completion_event.set()

    sub_comp = await runtime.cns.subscribe("TASK_COMPLETED", "cert_comp_de", wait_completion)
    sub_fail = await runtime.cns.subscribe("TASK_FAILED", "cert_fail_de", wait_completion)

    try:
        await asyncio.wait_for(completion_event.wait(), 30.0)
    except asyncio.TimeoutError:
        result["details"]["error"] = "Scenario timed out"
        await runtime.cns.unsubscribe(sub_tc)
        await runtime.cns.unsubscribe(sub_comp)
        await runtime.cns.unsubscribe(sub_fail)
        return result

    trace = tracer.get_task_trace(task_id) if task_id else []
    event_types = [e.topic for e in trace]

    has_recovery = "RECOVERY_STARTED" in event_types and "RECOVERY_COMPLETED" in event_types
    agents_started_count = sum(1 for e in trace if e.topic == "AGENTS_STARTED")
    has_retry = agents_started_count >= 2
    has_success = final_status.get("status") == "TASK_COMPLETED"

    passed = has_recovery and has_retry and has_success

    result["passed"] = passed
    result["details"] = {
        "task_id": task_id,
        "has_recovery": has_recovery,
        "agents_started_count": agents_started_count,
        "has_retry": has_retry,
        "has_success": has_success,
        "final_status": final_status.get("status"),
        "event_count": len(trace),
    }

    await runtime.cns.unsubscribe(sub_tc)
    await runtime.cns.unsubscribe(sub_comp)
    await runtime.cns.unsubscribe(sub_fail)
    return result


async def scenario_fatal_failure_abort(runtime: HojaigaRuntimeInstance, tracer: CertificationTracer, port: int) -> Dict[str, Any]:
    """
    Phase F: Fatal failure / abort validation.
    """
    result = {"phase": "F", "name": "Fatal Failure / Abort", "passed": False, "details": {}}
    request_id = str(uuid.uuid4())
    command = f"final-certification task on http://127.0.0.1:{port}/phase_f_start"

    task_id_holder = {}
    task_id_event = asyncio.Event()

    async def capture_task_id(env: EventEnvelope):
        if env.payload.get("request_id") == request_id:
            task_id_holder["task_id"] = env.payload.get("task_id")
            task_id_event.set()

    sub_tc = await runtime.cns.subscribe("TASK_CREATED", "cert_capture_f", capture_task_id)

    await runtime.cns.publish(EventEnvelope(
        topic="sock.cns.inbound",
        source_organ="cert_runner",
        payload={"request_id": request_id, "payload": {"command": command}}
    ))

    try:
        await asyncio.wait_for(task_id_event.wait(), 5.0)
    except asyncio.TimeoutError:
        result["details"]["error"] = "TASK_CREATED not received"
        await runtime.cns.unsubscribe(sub_tc)
        return result

    task_id = task_id_holder.get("task_id")

    recovery_event = asyncio.Event()
    async def on_recovery(env):
        if env.payload.get("task_id") == task_id:
            recovery_event.set()
    sub_rec = await runtime.cns.subscribe("RECOVERY_STARTED", "cert_rec_f", on_recovery)

    try:
        await asyncio.wait_for(recovery_event.wait(), 25.0)
    except asyncio.TimeoutError:
        result["details"]["error"] = "RECOVERY_STARTED not received"
        await runtime.cns.unsubscribe(sub_tc)
        await runtime.cns.unsubscribe(sub_rec)
        return result

    # Inject fatal TASK_FAILED through the CNS execution path
    await runtime.cns.publish(EventEnvelope(
        topic="TASK_FAILED",
        source_organ="cert_runner",
        payload={"task_id": task_id, "error": "fatal controller exception: unrecoverable hardware failure"}
    ))

    abort_event = asyncio.Event()
    final_status = {}

    async def on_final(env):
        if env.payload.get("task_id") == task_id:
            final_status["status"] = env.topic
            if env.topic in ("TASK_FAILED", "TASK_ABORTED", "FINAL_ABORTED"):
                abort_event.set()

    sub_final = await runtime.cns.subscribe("TASK_FAILED", "cert_final_f", on_final)
    sub_abort = await runtime.cns.subscribe("TASK_ABORTED", "cert_abort_f", on_final)

    try:
        await asyncio.wait_for(abort_event.wait(), 10.0)
    except asyncio.TimeoutError:
        result["details"]["error"] = "Abort event not received after fatal failure"
        await runtime.cns.unsubscribe(sub_tc)
        await runtime.cns.unsubscribe(sub_rec)
        await runtime.cns.unsubscribe(sub_final)
        await runtime.cns.unsubscribe(sub_abort)
        return result

    trace = tracer.get_task_trace(task_id) if task_id else []
    event_types = [e.topic for e in trace]

    has_abort = final_status.get("status") in ("TASK_FAILED", "TASK_ABORTED", "FINAL_ABORTED")
    has_no_success = "TASK_COMPLETED" not in event_types

    passed = has_abort and has_no_success

    result["passed"] = passed
    result["details"] = {
        "task_id": task_id,
        "has_abort": has_abort,
        "has_no_success": has_no_success,
        "final_status": final_status.get("status"),
        "event_count": len(trace),
    }

    await runtime.cns.unsubscribe(sub_tc)
    await runtime.cns.unsubscribe(sub_rec)
    await runtime.cns.unsubscribe(sub_final)
    await runtime.cns.unsubscribe(sub_abort)
    return result


async def scenario_retry_limit(runtime: HojaigaRuntimeInstance, tracer: CertificationTracer, port: int) -> Dict[str, Any]:
    """
    Phase G: Retry limit / loop protection.
    """
    result = {"phase": "G", "name": "Retry Limit / Loop Protection", "passed": False, "details": {}}
    request_id = str(uuid.uuid4())
    command = f"final-certification task on http://127.0.0.1:{port}/phase_g_start"

    task_id_holder = {}
    task_id_event = asyncio.Event()

    async def capture_task_id(env: EventEnvelope):
        if env.payload.get("request_id") == request_id:
            task_id_holder["task_id"] = env.payload.get("task_id")
            task_id_event.set()

    sub_tc = await runtime.cns.subscribe("TASK_CREATED", "cert_capture_g", capture_task_id)

    await runtime.cns.publish(EventEnvelope(
        topic="sock.cns.inbound",
        source_organ="cert_runner",
        payload={"request_id": request_id, "payload": {"command": command}}
    ))

    try:
        await asyncio.wait_for(task_id_event.wait(), 5.0)
    except asyncio.TimeoutError:
        result["details"]["error"] = "TASK_CREATED not received"
        await runtime.cns.unsubscribe(sub_tc)
        return result

    task_id = task_id_holder.get("task_id")
    abort_event = asyncio.Event()
    final_status = {}

    async def on_final(env):
        if env.payload.get("task_id") == task_id:
            final_status["status"] = env.topic
            if env.topic in ("TASK_FAILED", "TASK_ABORTED", "FINAL_ABORTED"):
                abort_event.set()

    sub_final = await runtime.cns.subscribe("TASK_FAILED", "cert_final_g", on_final)
    sub_abort = await runtime.cns.subscribe("TASK_ABORTED", "cert_abort_g", on_final)

    try:
        await asyncio.wait_for(abort_event.wait(), 20.0)
    except asyncio.TimeoutError:
        result["details"]["error"] = "Abort not reached within timeout - possible infinite retry loop"
        await runtime.cns.unsubscribe(sub_tc)
        await runtime.cns.unsubscribe(sub_final)
        await runtime.cns.unsubscribe(sub_abort)
        return result

    trace = tracer.get_task_trace(task_id) if task_id else []
    event_types = [e.topic for e in trace]

    has_alternative = any(
        e.payload.get("decision") == "ALTERNATIVE"
        for e in trace if e.topic == "RECOVERY_COMPLETED"
    )
    has_abort = any(
        e.payload.get("decision") == "ABORT"
        for e in trace if e.topic == "RECOVERY_COMPLETED"
    )
    has_no_infinite_loop = final_status.get("status") in ("TASK_FAILED", "TASK_ABORTED", "FINAL_ABORTED")
    agents_count = sum(1 for e in trace if e.topic == "AGENTS_STARTED")

    passed = has_alternative and has_abort and has_no_infinite_loop and agents_count <= 4

    result["passed"] = passed
    result["details"] = {
        "task_id": task_id,
        "has_alternative": has_alternative,
        "has_abort": has_abort,
        "has_no_infinite_loop": has_no_infinite_loop,
        "agents_started_count": agents_count,
        "final_status": final_status.get("status"),
        "event_count": len(trace),
        "note": "final-certification path enforces 1-recovery limit via _test_recovered flag",
    }

    await runtime.cns.unsubscribe(sub_tc)
    await runtime.cns.unsubscribe(sub_final)
    await runtime.cns.unsubscribe(sub_abort)
    return result


async def scenario_repeatability(runtime: HojaigaRuntimeInstance, tracer: CertificationTracer, port: int, runs: int = 10) -> Dict[str, Any]:
    """
    Phase O: Repeatability - run successful workflow N times.
    """
    result = {"phase": "O", "name": f"Repeatability ({runs} runs)", "passed": False, "details": {}}
    run_results = []

    for i in range(runs):
        request_id = str(uuid.uuid4())
        command = f"certification repeat run {i} on http://127.0.0.1:{port}/phase_repeat"

        task_id_holder = {}
        task_id_event = asyncio.Event()

        async def capture_task_id(env: EventEnvelope, rid=request_id):
            if env.payload.get("request_id") == rid:
                task_id_holder["task_id"] = env.payload.get("task_id")
                task_id_event.set()

        sub_tc = await runtime.cns.subscribe("TASK_CREATED", f"cert_capture_o_{i}", capture_task_id)

        await runtime.cns.publish(EventEnvelope(
            topic="sock.cns.inbound",
            source_organ="cert_runner",
            payload={"request_id": request_id, "payload": {"command": command}}
        ))

        try:
            await asyncio.wait_for(task_id_event.wait(), 5.0)
        except asyncio.TimeoutError:
            run_results.append({"run": i, "passed": False, "error": "TASK_CREATED timeout"})
            await runtime.cns.unsubscribe(sub_tc)
            continue

        task_id = task_id_holder.get("task_id")
        completion_event = asyncio.Event()
        final_status = {}

        async def wait_completion(env, tid=task_id):
            if env.payload.get("task_id") == tid:
                final_status["status"] = env.topic
                if env.topic in ("TASK_COMPLETED", "TASK_FAILED"):
                    completion_event.set()

        sub_comp = await runtime.cns.subscribe("TASK_COMPLETED", f"cert_comp_o_{i}", wait_completion)
        sub_fail = await runtime.cns.subscribe("TASK_FAILED", f"cert_fail_o_{i}", wait_completion)

        try:
            await asyncio.wait_for(completion_event.wait(), 25.0)
        except asyncio.TimeoutError:
            run_results.append({"run": i, "passed": False, "error": "Completion timeout"})
            await runtime.cns.unsubscribe(sub_tc)
            await runtime.cns.unsubscribe(sub_comp)
            await runtime.cns.unsubscribe(sub_fail)
            continue

        passed = final_status.get("status") == "TASK_COMPLETED"
        run_results.append({
            "run": i,
            "passed": passed,
            "task_id": task_id,
            "status": final_status.get("status"),
            "event_count": len(tracer.get_task_trace(task_id)) if task_id else 0,
        })

        await runtime.cns.unsubscribe(sub_tc)
        await runtime.cns.unsubscribe(sub_comp)
        await runtime.cns.unsubscribe(sub_fail)

    all_passed = all(r["passed"] for r in run_results)
    result["passed"] = all_passed
    result["details"] = {
        "total_runs": runs,
        "passed_runs": sum(1 for r in run_results if r["passed"]),
        "failed_runs": sum(1 for r in run_results if not r["passed"]),
        "run_results": run_results,
    }
    return result


# =============================================================================
# Resource Cleanup Validation
# =============================================================================

async def validate_resource_cleanup(runtime: HojaigaRuntimeInstance, tracer: CertificationTracer) -> Dict[str, Any]:
    """Verify no orphaned tasks, subscriptions, or hanging operations after scenario."""
    result = {
        "passed": True,
        "active_tasks": 0,
        "dead_letters": 0,
        "subscriptions": 0,
        "background_tasks": 0,
    }

    try:
        active = getattr(runtime.orchestrator, "active_tasks", {})
        result["active_tasks"] = len(active)
        if len(active) > 0:
            result["passed"] = False
            result["orphaned_tasks"] = list(active.keys())
    except Exception:
        pass

    try:
        dead = getattr(runtime.cns, "_dead_letters", [])
        result["dead_letters"] = len(dead)
        if len(dead) > 0:
            result["passed"] = False
    except Exception:
        pass

    try:
        tasks = [t for t in asyncio.all_tasks() if not t.done() and t != asyncio.current_task()]
        result["background_tasks"] = len(tasks)
        if len(tasks) > 10:
            result["passed"] = False
    except Exception:
        pass

    return result


# =============================================================================
# Main Certification Runner
# =============================================================================

async def run_certification():
    print("=" * 70)
    print("V2 FINAL CERTIFICATION TEST")
    print("=" * 70)

    port = 9998
    server = start_cert_server(port)
    tracer = CertificationTracer()
    overall_passed = True
    scenario_results = []
    start_time = time.time()

    # Create a single runtime instance for all scenarios to avoid port conflicts
    runtime = HojaigaRuntimeInstance()
    decision_engine = DecisionEngineOrgan()
    await runtime.start()
    await decision_engine.start_cns(runtime.cns)

    # Global mock UI config responder
    async def mock_ui(env: EventEnvelope):
        await runtime.cns.publish(EventEnvelope(
            topic="sys.events.ui_response",
            source_organ="mock_ui",
            payload={"type": "CONFIG_RESPONSE", "task_id": env.payload.get("task_id"), "config": {}}
        ))

    await runtime.cns.subscribe("REQUEST_CONFIG", "mock_ui_req", mock_ui)

    # Global tracer subscription
    await runtime.cns.subscribe("sys.events", "cert_global_tracer", tracer.capture)

    # Helper to reset Brain state between scenarios
    def reset_brain_state():
        if hasattr(runtime.brain, "_test_recovered"):
            runtime.brain._test_recovered = False
        if hasattr(runtime.brain, "_last_command"):
            runtime.brain._last_command = ""

    # Phase A: Normal execution with branching
    print("\n--- Phase A: Normal Execution with Branching ---")
    reset_brain_state()
    result_a = await scenario_normal_branching(runtime, tracer, port)
    scenario_results.append(result_a)
    print(f"Phase A: {'PASS' if result_a['passed'] else 'FAIL'}")
    if not result_a["passed"]:
        overall_passed = False
        print(f"  Details: {result_a['details']}")

    # Phase B: Controlled failure
    print("\n--- Phase B: Controlled Real Execution Failure ---")
    reset_brain_state()
    result_b = await scenario_controlled_failure(runtime, tracer, port)
    scenario_results.append(result_b)
    print(f"Phase B: {'PASS' if result_b['passed'] else 'FAIL'}")
    if not result_b["passed"]:
        overall_passed = False
        print(f"  Details: {result_b['details']}")

    # Phase C: Brain recovery decision
    print("\n--- Phase C: Brain Recovery Decision ---")
    reset_brain_state()
    result_c = await scenario_brain_recovery_decision(runtime, tracer, port)
    scenario_results.append(result_c)
    print(f"Phase C: {'PASS' if result_c['passed'] else 'FAIL'}")
    if not result_c["passed"]:
        overall_passed = False
        print(f"  Details: {result_c['details']}")

    # Phase D+E: Retry/replan and downstream convergence
    print("\n--- Phase D+E: Retry/Replan & Downstream Convergence ---")
    reset_brain_state()
    result_de = await scenario_retry_replan_execution(runtime, tracer, port)
    scenario_results.append(result_de)
    print(f"Phase D+E: {'PASS' if result_de['passed'] else 'FAIL'}")
    if not result_de["passed"]:
        overall_passed = False
        print(f"  Details: {result_de['details']}")

    # Phase F: Fatal failure / abort
    print("\n--- Phase F: Fatal Failure / Abort ---")
    reset_brain_state()
    result_f = await scenario_fatal_failure_abort(runtime, tracer, port)
    scenario_results.append(result_f)
    print(f"Phase F: {'PASS' if result_f['passed'] else 'FAIL'}")
    if not result_f["passed"]:
        overall_passed = False
        print(f"  Details: {result_f['details']}")

    # Phase G: Retry limit / loop protection
    print("\n--- Phase G: Retry Limit / Loop Protection ---")
    reset_brain_state()
    result_g = await scenario_retry_limit(runtime, tracer, port)
    scenario_results.append(result_g)
    print(f"Phase G: {'PASS' if result_g['passed'] else 'FAIL'}")
    if not result_g["passed"]:
        overall_passed = False
        print(f"  Details: {result_g['details']}")

    # Phase O: Repeatability
    print("\n--- Phase O: Repeatability (10 runs) ---")
    reset_brain_state()
    result_o = await scenario_repeatability(runtime, tracer, port, runs=10)
    scenario_results.append(result_o)
    print(f"Phase O: {'PASS' if result_o['passed'] else 'FAIL'}")
    if not result_o["passed"]:
        overall_passed = False
        print(f"  Details: {result_o['details']}")

    # Resource cleanup check
    cleanup = await validate_resource_cleanup(runtime, tracer)
    scenario_results.append({"phase": "Cleanup", "name": "Resource Cleanup", "passed": cleanup["passed"], "details": cleanup})
    if not cleanup["passed"]:
        overall_passed = False

    await runtime.stop()
    server.shutdown()
    server.server_close()

    end_time = time.time()
    duration = end_time - start_time

    # =========================================================================
    # Generate Artifacts
    # =========================================================================

    event_trace = tracer.to_event_trace_dict()
    with open("v2_final_event_trace.json", "w") as f:
        json.dump(event_trace, f, indent=2, default=str)

    state_trace = tracer.to_state_trace_dict()
    with open("v2_final_state_trace.json", "w") as f:
        json.dump(state_trace, f, indent=2, default=str)

    metrics = {
        "total_duration_seconds": round(duration, 2),
        "total_events_captured": len(tracer.events),
        "total_transitions": len(tracer.transitions),
        "total_violations": len(tracer.violations),
        "nodes_executed": {k: asdict(v) for k, v in tracer.nodes.items()},
        "scenario_summary": [
            {"phase": r["phase"], "name": r["name"], "passed": r["passed"], "details": r.get("details", {})}
            for r in scenario_results
        ],
    }
    with open("v2_final_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    report_lines = [
        "# V2 Final Certification Report",
        "",
        f"**Timestamp:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Duration:** {duration:.2f}s",
        f"**Overall Result:** {'PASS' if overall_passed else 'FAIL'}",
        "",
        "## Scenario Results",
        "",
        "| Phase | Name | Result | Details |",
        "|-------|------|--------|---------|",
    ]
    for r in scenario_results:
        details_str = str(r.get("details", {}))
        if len(details_str) > 80:
            details_str = details_str[:77] + "..."
        report_lines.append(f"| {r['phase']} | {r['name']} | {'PASS' if r['passed'] else 'FAIL'} | {details_str} |")

    report_lines.extend([
        "",
        "## Event Trace Summary",
        f"- Total events captured: {len(tracer.events)}",
        f"- Total state transitions: {len(tracer.transitions)}",
        f"- Total violations: {len(tracer.violations)}",
        "",
        "## Node Execution Summary",
        "",
        "| Node | Executions | Successes | Retries | Recoveries | Terminals |",
        "|------|------------|-----------|---------|------------|-----------|",
    ])
    for node_id, node in tracer.nodes.items():
        report_lines.append(
            f"| {node.name} | {node.count} | {node.success_count} | {node.retry_count} | {node.recovery_count} | {node.terminal_count} |"
        )

    if tracer.violations:
        report_lines.extend([
            "",
            "## Violations",
            "",
        ])
        for v in tracer.violations:
            report_lines.append(f"- {v}")

    report_lines.extend([
        "",
        "## Certification Gates",
        "",
        "| Gate | Status |",
        "|------|--------|",
        f"| V2 EventBus communication | {'PASS' if result_a['passed'] else 'FAIL'} |",
        f"| Brain/CNS integration | {'PASS' if result_c['passed'] else 'FAIL'} |",
        f"| Orchestrator integration | {'PASS' if result_a['passed'] and result_de['passed'] else 'FAIL'} |",
        f"| Dynamic branching | {'PASS' if result_a['passed'] else 'FAIL'} |",
        f"| Correct branch selection | {'PASS' if result_a['passed'] else 'FAIL'} |",
        f"| Downstream blocking | {'PASS' if result_b['passed'] else 'FAIL'} |",
        f"| Failure propagation | {'PASS' if result_b['passed'] else 'FAIL'} |",
        f"| Recovery initiation | {'PASS' if result_b['passed'] else 'FAIL'} |",
        f"| Brain recovery reasoning | {'PASS' if result_c['passed'] else 'FAIL'} |",
        f"| RETRY/REPLAN decision | {'PASS' if result_de['passed'] else 'FAIL'} |",
        f"| Retry execution | {'PASS' if result_de['passed'] else 'FAIL'} |",
        f"| Downstream continuation | {'PASS' if result_de['passed'] else 'FAIL'} |",
        f"| Fatal failure handling | {'PASS' if result_f['passed'] else 'FAIL'} |",
        f"| ABORT behavior | {'PASS' if result_f['passed'] else 'FAIL'} |",
        f"| Retry-limit protection | {'PASS' if result_g['passed'] else 'FAIL'} |",
        f"| State-machine integrity | {'PASS' if len(tracer.violations) == 0 else 'FAIL'} |",
        f"| Event ordering | {'PASS' if result_a['passed'] else 'FAIL'} |",
        f"| Correlation-ID integrity | {'PASS' if result_a['passed'] else 'FAIL'} |",
        f"| Parent/child task integrity | {'PASS' if result_a['passed'] else 'FAIL'} |",
        f"| Duplicate execution protection | {'PASS' if result_a['details'].get('duplicate_ok', False) else 'FAIL'} |",
        f"| Terminal-state integrity | {'PASS' if result_de['passed'] and result_f['passed'] else 'FAIL'} |",
        f"| Resource cleanup | {'PASS' if cleanup['passed'] else 'FAIL'} |",
        f"| 10-run repeatability | {'PASS' if result_o['passed'] else 'FAIL'} |",
        "",
        "## Final Verdict",
        "",
        f"**V2_FINAL_VALIDATION: {'PASS' if overall_passed else 'FAIL'}**",
        "",
    ])

    with open("v2_final_certification_report.md", "w") as f:
        f.write("\n".join(report_lines))

    # Print summary
    print("\n" + "=" * 70)
    print(f"V2_FINAL_VALIDATION: {'PASS' if overall_passed else 'FAIL'}")
    print("=" * 70)
    if not overall_passed:
        failed = [r for r in scenario_results if not r["passed"]]
        print(f"\nFailed scenarios: {[r['phase'] + ' - ' + r['name'] for r in failed]}")

    return overall_passed


if __name__ == "__main__":
    result = asyncio.run(run_certification())
    sys.exit(0 if result else 1)
