"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 12
Name: Integration Engine (Pipeline Hub & External Ecosystem Gateway)

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Integration Engine]
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
Dependencies: typing, asyncio, json, logging, time, uuid, dataclasses, enum, aiohttp/urllib...
"""
from __future__ import annotations

import asyncio
import dataclasses
import enum
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("hojaiga.organ12.integration")
if not logger.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("[IntegrationEngine] %(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)


# ==============================================================================
# SECTION 1 — PROTOCOLS, ENUMS & DATA CONTRACTS
# ==============================================================================
class IntegrationType(str, enum.Enum):
    REST_API = "REST_API"
    WEBHOOK = "WEBHOOK"
    DATABASE = "DATABASE"
    FILE_SYSTEM = "FILE_SYSTEM"
    EVENT_STREAM = "EVENT_STREAM"
    CLI_SUBPROCESS = "CLI_SUBPROCESS"


class PipelineStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    TIMEOUT = "TIMEOUT"


@dataclass
class IntegrationEndpoint:
    endpoint_id: str
    integration_type: IntegrationType
    target_uri: str
    auth_config: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 15.0
    retry_limit: int = 3
    is_active: bool = True


@dataclass
class PipelineStep:
    step_id: str
    endpoint_id: str
    action: str
    payload: Dict[str, Any] = field(default_factory=dict)
    transform_script: Optional[str] = None
    continue_on_failure: bool = False


@dataclass
class IntegrationExecutionResult:
    execution_id: str
    status: PipelineStatus
    step_results: List[Dict[str, Any]] = field(default_factory=list)
    output_data: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    duration_ms: float = 0.0


# ==============================================================================
# SECTION 2 — CIRCUIT BREAKER & FAULT TOLERANCE
# ==============================================================================
class CircuitBreakerOpenError(Exception):
    pass


class CircuitBreaker:
    """Protects downstream APIs and services from cascading failures."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout_s: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.is_open = False

    def record_success(self) -> None:
        self.failure_count = 0
        self.is_open = False

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.is_open = True
            logger.warning("Circuit breaker tripped OPEN. Backing off.")

    def check_state(self) -> None:
        if self.is_open:
            if time.time() - self.last_failure_time > self.recovery_timeout_s:
                self.is_open = False
                self.failure_count = 0
                logger.info("Circuit breaker entering HALF-OPEN probe state.")
            else:
                raise CircuitBreakerOpenError("Circuit breaker is currently OPEN.")


# ==============================================================================
# SECTION 3 — INTEGRATION DRIVERS & EXECUTORS
# ==============================================================================
class RestDriver:
    """Native asyncio HTTP connector."""

    async def execute(self, endpoint: IntegrationEndpoint, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        method = action.upper()
        headers = endpoint.auth_config.get("headers", {"Content-Type": "application/json"})
        
        try:
            import aiohttp  # type: ignore
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.request(
                    method=method,
                    url=endpoint.target_uri,
                    json=payload if method in ("POST", "PUT", "PATCH") else None,
                    params=payload if method == "GET" else None,
                    timeout=aiohttp.ClientTimeout(total=endpoint.timeout_seconds)
                ) as resp:
                    text = await resp.text()
                    try:
                        data = json.loads(text)
                    except Exception:
                        data = {"raw_text": text}
                    return {"status_code": resp.status, "data": data}
        except ImportError:
            # Shielded urllib fallback
            import urllib.request
            req = urllib.request.Request(
                endpoint.target_uri,
                data=json.dumps(payload).encode("utf-8") if method in ("POST", "PUT") else None,
                headers=headers,
                method=method
            )
            with urllib.request.urlopen(req, timeout=endpoint.timeout_seconds) as response:
                body = response.read().decode("utf-8")
                return {"status_code": response.status, "data": json.loads(body) if body else {}}


# ==============================================================================
# SECTION 4 — PIPELINE EXECUTION ENGINE
# ==============================================================================
class IntegrationPipelineEngine:
    def __init__(self):
        self.endpoints: Dict[str, IntegrationEndpoint] = {}
        self.breakers: Dict[str, CircuitBreaker] = {}
        self.rest_driver = RestDriver()

    def register_endpoint(self, endpoint: IntegrationEndpoint) -> None:
        self.endpoints[endpoint.endpoint_id] = endpoint
        self.breakers[endpoint.endpoint_id] = CircuitBreaker()

    async def execute_step(self, step: PipelineStep) -> Dict[str, Any]:
        endpoint = self.endpoints.get(step.endpoint_id)
        if not endpoint or not endpoint.is_active:
            raise ValueError(f"Endpoint '{step.endpoint_id}' not found or inactive.")

        breaker = self.breakers[step.endpoint_id]
        breaker.check_state()

        attempt = 0
        last_err = None
        while attempt <= endpoint.retry_limit:
            try:
                if endpoint.integration_type == IntegrationType.REST_API:
                    res = await self.rest_driver.execute(endpoint, step.action, step.payload)
                    breaker.record_success()
                    return res
                else:
                    return {"status": "success", "echo": step.payload}
            except Exception as e:
                attempt += 1
                last_err = e
                breaker.record_failure()
                if attempt > endpoint.retry_limit:
                    break
                await asyncio.sleep(0.5 * attempt)

        raise RuntimeError(f"Step {step.step_id} failed after {attempt} retries: {last_err}")

    async def run_pipeline(self, execution_id: str, steps: List[PipelineStep]) -> IntegrationExecutionResult:
        start_time = time.monotonic()
        results: List[Dict[str, Any]] = []
        accumulated_output: Dict[str, Any] = {}

        for step in steps:
            try:
                step_res = await self.execute_step(step)
                results.append({"step_id": step.step_id, "status": "SUCCESS", "output": step_res})
                if isinstance(step_res, dict):
                    accumulated_output.update(step_res)
            except CircuitBreakerOpenError as cbe:
                duration = (time.monotonic() - start_time) * 1000.0
                return IntegrationExecutionResult(
                    execution_id=execution_id,
                    status=PipelineStatus.CIRCUIT_OPEN,
                    step_results=results,
                    error_message=str(cbe),
                    duration_ms=duration
                )
            except Exception as e:
                logger.error(f"Pipeline step {step.step_id} execution failed: {e}")
                results.append({"step_id": step.step_id, "status": "FAILED", "error": str(e)})
                if not step.continue_on_failure:
                    duration = (time.monotonic() - start_time) * 1000.0
                    return IntegrationExecutionResult(
                        execution_id=execution_id,
                        status=PipelineStatus.FAILED,
                        step_results=results,
                        error_message=str(e),
                        duration_ms=duration
                    )

        duration = (time.monotonic() - start_time) * 1000.0
        return IntegrationExecutionResult(
            execution_id=execution_id,
            status=PipelineStatus.COMPLETED,
            step_results=results,
            output_data=accumulated_output,
            duration_ms=duration
        )


# ==============================================================================
# SECTION 5 — INTEGRATION ORGAN (PUBLIC FACADE & CNS HOOKS)
# ==============================================================================
class IntegrationOrgan:
    """Master Integration Gateway (Organ 12)."""

    def __init__(self):
        self.engine = IntegrationPipelineEngine()
        self.cns: Optional[Any] = None
        self._register_default_endpoints()

    def _register_default_endpoints(self) -> None:
        self.engine.register_endpoint(IntegrationEndpoint(
            endpoint_id="http_generic",
            integration_type=IntegrationType.REST_API,
            target_uri="https://httpbin.org/anything",
            timeout_seconds=5.0
        ))

    async def start_cns(self, cns: Any) -> None:
        self.cns = cns
        await self.cns.subscribe("INTEGRATION_REQUEST", "organ_12", self._handle_integration_request)
        await self.cns.subscribe("PIPELINE_EXECUTE", "organ_12", self._handle_pipeline_execute)
        logger.info("IntegrationOrgan connected to CNS.")

    async def _handle_integration_request(self, env: Any) -> None:
        from core_organs.organ_02_cns_single_file import EventEnvelope
        payload = env.payload or {}
        task_id = payload.get("task_id", str(uuid.uuid4()))
        action = payload.get("action", "GET")
        endpoint_id = payload.get("endpoint_id", "http_generic")

        step = PipelineStep(
            step_id=f"step_{uuid.uuid4().hex[:6]}",
            endpoint_id=endpoint_id,
            action=action,
            payload=payload.get("data", {})
        )

        result = await self.engine.run_pipeline(task_id, [step])

        if self.cns:
            await self.cns.publish(EventEnvelope(
                topic="INTEGRATION_COMPLETED",
                source_organ="organ_12",
                payload={
                    "task_id": task_id,
                    "status": result.status.value,
                    "output": result.output_data,
                    "error": result.error_message
                }
            ))

    async def _handle_pipeline_execute(self, env: Any) -> None:
        from core_organs.organ_02_cns_single_file import EventEnvelope
        payload = env.payload or {}
        task_id = payload.get("task_id", str(uuid.uuid4()))
        raw_steps = payload.get("steps", [])

        steps = [
            PipelineStep(
                step_id=s.get("step_id", f"s_{idx}"),
                endpoint_id=s.get("endpoint_id", "http_generic"),
                action=s.get("action", "GET"),
                payload=s.get("payload", {}),
                continue_on_failure=s.get("continue_on_failure", False)
            )
            for idx, s in enumerate(raw_steps)
        ]

        result = await self.engine.run_pipeline(task_id, steps)

        if self.cns:
            await self.cns.publish(EventEnvelope(
                topic="PIPELINE_COMPLETED",
                source_organ="organ_12",
                payload={
                    "task_id": task_id,
                    "status": result.status.value,
                    "results": result.step_results,
                    "error": result.error_message
                }
            ))


if __name__ == "__main__":
    async def _test():
        organ = IntegrationOrgan()
        print("Testing Integration Organ Pipeline...")
        step = PipelineStep("test_step", "http_generic", "GET", {"test": "value"})
        res = await organ.engine.run_pipeline("exec_001", [step])
        print(f"Pipeline Result: {res.status.value}, Duration: {res.duration_ms:.2f}ms")
    asyncio.run(_test())
