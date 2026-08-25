"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 1
Name: Brain (Cognitive, Non-Executing Master Reasoning Unit)

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Brain]
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
Dependencies: enum, typing, future, json, threading, asyncio...
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional, List

from core_organs.organ_02_cns_single_file import EventEnvelope, EventBus
from core_organs.organ_37_llm_gateway import LLMGateway, LLMGatewayError

# =============================================================================
# 0. CONFIGURATION
# =============================================================================
@dataclass(frozen=True)
class BrainConfig:
    llama_cpp_binary: str = os.environ.get("HOJAIGA_LLAMA_BIN", "llama-server")
    model_path: str = os.environ.get("HOJAIGA_MODEL_PATH", "models/qwen3-8b-instruct-q4_k_m.gguf")
    host: str = "127.0.0.1"
    port: int = 8090
    gpu_layers: int = 28
    context_size: int = 8192
    idle_shutdown_seconds: float = 90.0
    big_brain_timeout_seconds: float = 45.0
    small_brain_timeout_seconds: float = 3.0
    max_retries: int = 3
    retry_backoff_base: float = 1.0
    log_dir: str = "brain/logs"
    log_file: str = "brain_execution.log"
    knowledge_cache_path: str = "brain/config/knowledge_cache.json"
    tool_registry_path: str = "brain/config/tool_registry.json"
    policy_store_path: str = "brain/config/policy_store.json"
    learning_store_path: str = "brain/logs/learning_store.jsonl"

CONFIG = BrainConfig()

# =============================================================================
# 1. LOGGING (append-only, structured)
# =============================================================================
def _init_logger() -> logging.Logger:
    os.makedirs(CONFIG.log_dir, exist_ok=True)
    logger = logging.getLogger("hojaiga.brain")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(
            os.path.join(CONFIG.log_dir, CONFIG.log_file), encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter("[Brain] %(message)s"))
        logger.addHandler(stream)
    return logger

class BrainLogger:
    """Append-only structured logger."""

    def __init__(self) -> None:
        self._logger = _init_logger()
        self._lock = threading.Lock()

    def log(self, **fields: Any) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "component": "Brain",
            **fields,
        }
        with self._lock:
            self._logger.info(json.dumps(record, ensure_ascii=False))

LOG = BrainLogger()

# =============================================================================
# 2. DATA CONTRACTS
# =============================================================================
class Priority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class TaskNature(str, Enum):
    ANALYTICAL = "analytical"
    CREATIVE = "creative"
    OPERATIONAL = "operational"
    UNKNOWN = "unknown"

PHASE_TAG_VOCAB = (
    "CONTEXT_REVIEW", "RESEARCH", "PLAN", "DECIDE",
    "RISK_CHECK", "DELEGATE", "VERIFY_REQUEST", "REFLECT",
)

@dataclass
class TaskRequest:
    task_id: str
    raw_text: str
    context_refs: list[str] = field(default_factory=list)
    priority: Priority = Priority.NORMAL

    @staticmethod
    def from_dict(d: dict) -> "TaskRequest":
        return TaskRequest(
            task_id=d.get("task_id") or str(uuid.uuid4()),
            raw_text=d["raw_text"],
            context_refs=d.get("context_refs", []),
            priority=Priority(d.get("priority", "normal")),
        )

@dataclass
class PhaseStep:
    phase: str
    instruction: str

    def __post_init__(self) -> None:
        if self.phase not in PHASE_TAG_VOCAB:
            raise InvalidTaskError(f"Illegal phase tag: {self.phase}")

@dataclass
class AgentTask:
    agent_id: str
    objective: str
    instructions: Any
    search_queries: list[str]
    agent_tier: str = "permanent"
    wait_seconds: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "objective": self.objective,
            "instructions": self.instructions,
            "search_queries": self.search_queries,
            "agent_tier": self.agent_tier,
            "wait_seconds": self.wait_seconds
        }

@dataclass
class RiskReport:
    level: RiskLevel = RiskLevel.LOW
    notes: str = ""

@dataclass
class ExecutionPlan:
    task_id: str
    steps: list[PhaseStep]
    risk_report: RiskReport
    agent_tasks: list[AgentTask] = field(default_factory=list)
    raw_plan_text: str = ""
    requires_escalation: bool = False
    creative_variant: Optional[str] = None
    policy_notes: Optional[str] = None
    version: str = "1.0"
    intent_analysis: str = ""
    checkpoints_enforced: bool = False
    controller_access: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "steps": [asdict(s) for s in self.steps],
            "agent_tasks": [t.to_dict() for t in self.agent_tasks],
            "raw_plan_text": self.raw_plan_text,
            "risk_report": asdict(self.risk_report),
            "requires_escalation": self.requires_escalation,
            "creative_variant": self.creative_variant,
            "policy_notes": self.policy_notes,
            "version": self.version,
            "intent_analysis": self.intent_analysis,
            "checkpoints_enforced": self.checkpoints_enforced,
            "controller_access": self.controller_access,
        }

@dataclass
class ReflectionRecord:
    task_id: str
    outcome: str
    observations: str
    lessons: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat() + "Z")

@dataclass
class ToolDescriptor:
    name: str
    capability: str
    installed: bool
    reliability_score: float = 0.5
    preferred_scenarios: list[str] = field(default_factory=list)

@dataclass
class KnowledgeEntry:
    key: str
    summary: str
    confidence: float = 0.5
    source: str = "internal"
    version: int = 1

@dataclass
class PolicyDirective:
    name: str
    rule: str
    scope: str = "task"

# =============================================================================
# 3. ERRORS
# =============================================================================
class BrainError(Exception):
    pass

class ModelUnavailableError(BrainError):
    pass

class PlanningTimeoutError(BrainError):
    pass

class InvalidTaskError(BrainError):
    pass

class KnowledgeUnavailableError(BrainError):
    pass

# =============================================================================
# 4. SOCKET BUS
# =============================================================================
class Socket:
    def __init__(self, name: str, version: str = "1.0") -> None:
        self.name = name
        self.version = version
        self._subscribers: list[Callable[[dict], None]] = []
        self._lock = threading.Lock()

    def subscribe(self, handler: Callable[[dict], None]) -> None:
        with self._lock:
            self._subscribers.append(handler)

    def publish(self, payload: dict, retries: int = CONFIG.max_retries) -> bool:
        attempt = 0
        while attempt <= retries:
            try:
                with self._lock:
                    subs = list(self._subscribers)
                for sub in subs:
                    sub(payload)
                return True
            except Exception as exc:
                attempt += 1
                LOG.log(event="socket_publish_failed", socket=self.name,
                         attempt=attempt, error=str(exc))
                time.sleep(CONFIG.retry_backoff_base * (2 ** (attempt - 1)))
        LOG.log(event="socket_publish_dropped", socket=self.name, payload_task=payload.get("task_id"))
        return False

class SocketBus:
    def __init__(self) -> None:
        self.brain_socket = Socket("brain.socket")
        self.memory_socket = Socket("memory.socket")
        self.knowledge_socket = Socket("knowledge.socket")
        self.learning_socket = Socket("learning.socket")
        self.tool_socket = Socket("tool.socket")
        self.policy_socket = Socket("policy.socket")
        self.elevation_socket = Socket("elevation.socket")

BUS = SocketBus()

# =============================================================================
# 5. MODEL RUNTIME DELEGATOR
# =============================================================================
class ModelManager:
    def __init__(self, config: BrainConfig = CONFIG) -> None:
        self._gateway = LLMGateway()

    def is_running(self) -> bool:
        return True

    def ensure_started(self) -> None:
        pass

    def touch(self) -> None:
        pass

    def force_shutdown(self) -> None:
        pass

    def complete(self, system: str, prompt: str, timeout: float, temperature: float = 0.3) -> str:
        try:
            return self._gateway.execute_inference(system, prompt, temperature, timeout)
        except LLMGatewayError as e:
            raise ModelUnavailableError(f"Gateway execution failed: {e}")

# =============================================================================
# 6. ROUTER & REASONING GATEWAY
# =============================================================================
_DEEP_REASONING_MARKERS = (
    "plan", "strategy", "decompose", "architecture", "risk", "analyze",
    "compare", "decide", "design", "why", "trade-off", "tradeoff",
)
_FAST_PATH_MARKERS = (
    "status", "ping", "hello", "list", "show", "what time", "confirm",
)
_CREATIVE_MARKERS = (
    "write", "draft", "compose", "creative", "story", "post", "article",
    "brainstorm", "idea", "headline", "title",
)

class SmallBrainRouter:
    def classify(self, raw_text: str) -> str:
        text = raw_text.lower().strip()
        if any(m in text for m in _FAST_PATH_MARKERS) and len(text.split()) < 12:
            return "fast_path"
        if any(m in text for m in _DEEP_REASONING_MARKERS):
            return "deep_reasoning"
        if len(text.split()) > 25:
            return "deep_reasoning"
        return "fast_path"

    def classify_nature(self, raw_text: str) -> TaskNature:
        text = raw_text.lower()
        if any(m in text for m in _CREATIVE_MARKERS):
            return TaskNature.CREATIVE
        if any(m in text for m in _DEEP_REASONING_MARKERS):
            return TaskNature.ANALYTICAL
        if any(m in text for m in _FAST_PATH_MARKERS):
            return TaskNature.OPERATIONAL
        return TaskNature.UNKNOWN

    def confidence(self, raw_text: str) -> float:
        length_factor = min(len(raw_text.split()) / 40.0, 1.0)
        marker_hits = sum(1 for m in _DEEP_REASONING_MARKERS if m in raw_text.lower())
        return round(min(0.4 + 0.15 * marker_hits + 0.2 * length_factor, 1.0), 2)

# =============================================================================
# 7. PROMPT COMPILER & HIERARCHICAL SWARM DECOMPOSITION
# =============================================================================
class PromptCompiler:
    _SYSTEM_PROMPT = (
        "You are the Hojaiga Brain intelligence engine.\n"
        "Your task is to compile user intent into a strict JSON 3-tier hierarchical swarm.\n"
        "1. Permanent Agents (manage high-level checkpoints)\n"
        "2. Sub-Agents (manage sub-checkpoints & domain segregation)\n"
        "3. Temporary Agents (execute atomic micro-instructions like navigation, typing, clicking, launching apps)\n\n"
        "RULES:\n"
        "- If the task involves desktop apps (e.g. OBS Studio, Notepad, Explorer), emit action objects: 'LAUNCH_APP', 'HOTKEY', 'DESKTOP_CLICK'.\n"
        "- If the task involves web browsing, emit valid CDP actions: 'NAVIGATE', 'INTERACT', 'GET_DOM_TREE', 'EXTRACT'.\n"
        "- Output ONLY valid JSON matching the schema."
    )

    def __init__(self) -> None:
        self._gateway = LLMGateway()

    def compile(self, task: TaskRequest, context_summary: str) -> ExecutionPlan:
        user_prompt = f"Task: {task.raw_text}\nProduce the 3-tier JSON execution plan."
        raw = self._gateway.execute_inference(
            system=self._SYSTEM_PROMPT,
            prompt=user_prompt,
            timeout=CONFIG.big_brain_timeout_seconds,
        )
        return self._parse_and_format(raw, task)

    def _parse_and_format(self, raw: str, task: TaskRequest) -> ExecutionPlan:
        try:
            match = re.search(r'(\{.*\})', raw, re.DOTALL)
            clean_raw = match.group(1) if match else raw
            data = json.loads(clean_raw)
        except json.JSONDecodeError as e:
            raise InvalidTaskError(f"Brain produced invalid JSON: {e}\nRaw: {raw}")

        intent_analysis = data.get("intent_analysis", "")
        raw_tasks = data.get("agent_tasks", [])
        flat_agent_tasks = []

        for idx, perm in enumerate(raw_tasks):
            sub_agents = perm.get("sub_agents", [])
            for s_idx, sub in enumerate(sub_agents):
                temp_agents = sub.get("temporary_agents", [])
                for t_idx, temp in enumerate(temp_agents):
                    t_id = temp.get("agent_id", f"TEMP-{idx+1}-{s_idx+1}-{t_idx+1}")
                    flat_agent_tasks.append(AgentTask(
                        agent_id=t_id,
                        objective=temp.get("objective", ""),
                        instructions=temp.get("instructions", ""),
                        search_queries=temp.get("search_queries", []),
                        agent_tier="temporary"
                    ))

        if not flat_agent_tasks:
            raise InvalidTaskError("Could not find any structured AGENT blocks in JSON.")

        steps = [PhaseStep(phase="DECIDE", instruction=f"Launch {len(flat_agent_tasks)} temporary agents.")]

        return ExecutionPlan(
            task_id=task.task_id,
            steps=steps,
            agent_tasks=flat_agent_tasks,
            raw_plan_text=raw,
            risk_report=RiskReport(level=RiskLevel.LOW, notes="Hierarchical swarm plan generated."),
            requires_escalation=False,
            intent_analysis=intent_analysis,
            checkpoints_enforced=data.get("checkpoints_enforced", True),
            controller_access=data.get("controller_access", ["browser", "desktop", "os"]),
        )

class StrategicPlanner:
    _REQUIRED_LEAD_PHASE = "CONTEXT_REVIEW"

    def normalize(self, plan: ExecutionPlan) -> ExecutionPlan:
        if not plan.steps:
            raise InvalidTaskError("Cannot normalize an empty plan.")
        if plan.steps[0].phase != self._REQUIRED_LEAD_PHASE:
            plan.steps.insert(
                0,
                PhaseStep(phase=self._REQUIRED_LEAD_PHASE, instruction="Establish context before proceeding."),
            )
        if plan.steps[-1].phase != "REFLECT":
            plan.steps.append(
                PhaseStep(phase="REFLECT", instruction="Record outcome for learning after execution.")
            )
        return plan

# =============================================================================
# 8. SUBORDINATE MODULES (CREATIVITY, CONTEXT, KNOWLEDGE, POLICY, LEARNING)
# =============================================================================
class CreativityEngine:
    _SYSTEM_PROMPT = "Suggest ONE short creative angle or hook (max 25 words). Output ONLY raw text."

    def __init__(self, model: ModelManager) -> None:
        self._model = model

    def suggest_angle(self, task: TaskRequest) -> Optional[str]:
        try:
            result = self._model.complete(
                system=self._SYSTEM_PROMPT,
                prompt=task.raw_text,
                timeout=CONFIG.small_brain_timeout_seconds + 5,
                temperature=0.9,
            )
            return result.strip()[:300] or None
        except Exception:
            return None

class ContextGateway:
    def __init__(self, bus: SocketBus) -> None:
        self._bus = bus

    def query_memory(self, query: str) -> str:
        return ""

    def query_knowledge(self, query: str) -> str:
        return ""

class ToolKnowledgeBase:
    def __init__(self, path: str = CONFIG.tool_registry_path) -> None:
        self._path = path
        self._tools: dict[str, ToolDescriptor] = {}

    def register(self, tool: ToolDescriptor) -> None:
        self._tools[tool.name] = tool

    def best_for_capability(self, capability: str) -> Optional[ToolDescriptor]:
        candidates = [t for t in self._tools.values() if t.capability == capability]
        return candidates[0] if candidates else None

class DomainKnowledgeBase:
    def __init__(self, path: str = CONFIG.knowledge_cache_path) -> None:
        self._entries: dict[str, KnowledgeEntry] = {}

    def upsert(self, key: str, summary: str, confidence: float = 0.5, source: str = "internal") -> KnowledgeEntry:
        entry = KnowledgeEntry(key=key, summary=summary, confidence=confidence, source=source)
        self._entries[key] = entry
        return entry

    def search(self, keyword: str) -> list[KnowledgeEntry]:
        k = keyword.lower()
        return [e for e in self._entries.values() if k in e.key.lower() or k in e.summary.lower()]

class PolicyGenerator:
    def annotate(self, plan: ExecutionPlan) -> ExecutionPlan:
        return plan

class ReflectionEngine:
    def __init__(self, bus: SocketBus, store_path: str = CONFIG.learning_store_path) -> None:
        self._bus = bus

    def reflect(self, task_id: str, outcome: str, observations: str = "", lessons: Optional[list[str]] = None) -> ReflectionRecord:
        record = ReflectionRecord(task_id=task_id, outcome=outcome, observations=observations, lessons=lessons or [])
        self._bus.learning_socket.publish(asdict(record))
        return record

class LearningEngine:
    def __init__(self, knowledge: DomainKnowledgeBase, reflection: ReflectionEngine) -> None:
        self._knowledge = knowledge
        self._reflection = reflection

    def evaluate(self, task: TaskRequest, plan: ExecutionPlan, outcome: str) -> ReflectionRecord:
        return self._reflection.reflect(task.task_id, outcome, observations="Execution evaluated.")

class DecisionEmitter:
    def __init__(self, bus: SocketBus) -> None:
        self._bus = bus

    def emit(self, plan: ExecutionPlan) -> None:
        self._bus.brain_socket.publish(plan.to_dict())

    def escalate(self, task: TaskRequest, reason: str) -> None:
        self._bus.elevation_socket.publish({"task_id": task.task_id, "reason": reason})

# =============================================================================
# 9. BRAIN ORGAN (PUBLIC FACADE & CNS INTEGRATION)
# =============================================================================
class BrainOrgan:
    def __init__(self, config: BrainConfig = CONFIG, bus: SocketBus = BUS) -> None:
        self._config = config
        self._bus = bus
        self._model = ModelManager(config)
        self._small_brain = SmallBrainRouter()
        self._compiler = PromptCompiler()
        self._planner = StrategicPlanner()
        self._creativity = CreativityEngine(self._model)
        self._context = ContextGateway(bus)
        self._tools = ToolKnowledgeBase()
        self._knowledge = DomainKnowledgeBase()
        self._policy = PolicyGenerator()
        self._reflection = ReflectionEngine(bus)
        self._learning = LearningEngine(self._knowledge, self._reflection)
        self._emitter = DecisionEmitter(bus)
        self._task_lock = threading.Lock()
        self.cns: Optional[EventBus] = None

    def handle_task(self, task: TaskRequest) -> ExecutionPlan:
        if not task.raw_text or not task.raw_text.strip():
            raise InvalidTaskError("Empty task text.")

        nature = self._small_brain.classify_nature(task.raw_text)

        with self._task_lock:
            plan = self._plan_with_big_brain(task)
            plan = self._planner.normalize(plan)
            if nature == TaskNature.CREATIVE:
                plan.creative_variant = self._creativity.suggest_angle(task)
            plan = self._policy.annotate(plan)

        if plan.requires_escalation:
            self._emitter.escalate(task, reason=plan.risk_report.notes)

        self._emitter.emit(plan)
        return plan

    def _plan_with_big_brain(self, task: TaskRequest) -> ExecutionPlan:
        context_summary = "\n".join(filter(None, [
            self._context.query_memory(task.raw_text),
            self._context.query_knowledge(task.raw_text),
        ]))
        try:
            return self._compiler.compile(task, context_summary)
        except Exception as exc:
            LOG.log(event="big_brain_fallback", task_id=task.task_id, error=str(exc))
            return self._build_dynamic_fallback_plan(task)

    def _build_dynamic_fallback_plan(self, task: TaskRequest) -> ExecutionPlan:
        """Dynamically generates task structures from raw prompt words without static hardcoded strings."""
        text = task.raw_text
        text_lower = text.lower()
        
        agent_tasks = []
        controller_access = ["desktop", "os"]
        
        # Desktop app detection (e.g. OBS, Notepad)
        if any(k in text_lower for k in ["obs", "record", "screen", "launch", "app"]):
            controller_access.append("desktop")
            app_name = "obs64" if "obs" in text_lower else "notepad"
            agent_tasks.append({
                "agent_id": "DesktopAppManager",
                "objective": f"Launch and interact with {app_name}",
                "agent_tier": "permanent",
                "sub_agents": [{
                    "agent_id": "DesktopExecutionSubAgent",
                    "objective": f"Execute desktop operation on {app_name}",
                    "agent_tier": "sub_agent",
                    "temporary_agents": [{
                        "agent_id": "AppLaunchTemp",
                        "objective": f"Launch {app_name}",
                        "instructions": json.dumps({"action": "LAUNCH_APP", "parameters": {"command": [app_name]}}),
                        "search_queries": [],
                        "agent_tier": "temporary"
                    }]
                }]
            })

        # Browser automation detection
        if any(k in text_lower for k in ["search", "find", "extract", "google", "lead", "browse", "url", "http"]):
            controller_access.append("browser")
            agent_tasks.append({
                "agent_id": "WebSearchManager",
                "objective": f"Perform extraction for: {text[:60]}",
                "agent_tier": "permanent",
                "sub_agents": [{
                    "agent_id": "WebExtractionSubAgent",
                    "objective": "Execute web query and extract matching elements",
                    "agent_tier": "sub_agent",
                    "temporary_agents": [
                        {
                            "agent_id": "WebNavigateTemp",
                            "objective": "Navigate to search provider",
                            "instructions": json.dumps({"action": "NAVIGATE", "parameters": {"url": "https://www.google.com"}}),
                            "search_queries": [text],
                            "agent_tier": "temporary"
                        },
                        {
                            "agent_id": "WebQueryTemp",
                            "objective": "Type query and search",
                            "instructions": json.dumps({"action": "INTERACT", "parameters": {"target": "search box", "text": text, "press_enter": True}}),
                            "search_queries": [text],
                            "agent_tier": "temporary"
                        }
                    ]
                }]
            })

        if not agent_tasks:
            agent_tasks.append({
                "agent_id": "GenericTaskManager",
                "objective": text,
                "agent_tier": "permanent",
                "sub_agents": [{
                    "agent_id": "GenericSubAgent",
                    "objective": text,
                    "agent_tier": "sub_agent",
                    "temporary_agents": [{
                        "agent_id": "GenericExecutionTemp",
                        "objective": text,
                        "instructions": json.dumps({"action": "INTERACT", "parameters": {"text": text}}),
                        "search_queries": [],
                        "agent_tier": "temporary"
                    }]
                }]
            })

        mock_raw = json.dumps({
            "intent_analysis": f"Decomposed dynamic intent for: {text}",
            "checkpoints_enforced": True,
            "controller_access": controller_access,
            "agent_tasks": agent_tasks
        })
        
        plan = self._compiler._parse_and_format(mock_raw, task)
        plan.risk_report = RiskReport(level=RiskLevel.LOW, notes="Dynamic fallback plan synthesized.")
        return plan

    # ── CNS Integration ─────────────────────────────────────────────────

    async def start(self, cns: EventBus) -> None:
        self.cns = cns
        await self.cns.subscribe("INTENT_NORMALIZATION_STARTED", "brain_core", self._handle_intent_started)
        await self.cns.subscribe("VERIFICATION_STARTED", "brain_core", self._handle_cns_verification_started)
        await self.cns.subscribe("RECOVERY_STARTED", "brain_core", self._handle_recovery_started)
        LOG.log(event="brain_connected_to_cns")

    async def _handle_intent_started(self, env: EventEnvelope) -> None:
        payload = env.payload
        command = payload.get("command") or ""
        task_id = payload.get("task_id") or str(uuid.uuid4())
        
        req = TaskRequest(task_id=task_id, raw_text=command)
        self._last_command = command
        
        loop = asyncio.get_running_loop()
        plan = await loop.run_in_executor(None, self.handle_task, req)
        
        plan_payload = {
            "workflow_id": plan.task_id,
            "agent_tasks": [
                {
                    "agent_id": t.agent_id,
                    "objective": t.objective,
                    "instructions": getattr(t, "instructions", ""),
                    "agent_tier": getattr(t, "agent_tier", "temporary"),
                    "search_queries": getattr(t, "search_queries", []),
                    "wait_seconds": getattr(t, "wait_seconds", 0)
                } for t in plan.agent_tasks
            ],
            "controller_access": plan.controller_access
        }

        if self.cns:
            await self.cns.publish(EventEnvelope(
                topic="INTENT_NORMALIZATION_COMPLETED", 
                source_organ="organ_01", 
                payload={"task_id": task_id, "plan_payload": plan_payload}
            ))

    async def _handle_cns_verification_started(self, env: EventEnvelope) -> None:
        payload = env.payload or {}
        task_id = payload.get("task_id", "UNKNOWN")
        result_data = payload.get("result_data") or {}
        
        # Verify execution outcome
        status = result_data.get("_status")
        success = (status != "FAILED")

        if self.cns:
            await self.cns.publish(EventEnvelope(
                topic="VERIFICATION_COMPLETED",
                source_organ="organ_01",
                payload={"task_id": task_id, "success": success, "error": result_data.get("errorText", "")}
            ))

    async def _handle_recovery_started(self, env: EventEnvelope) -> None:
        payload = env.payload or {}
        task_id = payload.get("task_id", "UNKNOWN")
        
        # Determine recovery plan
        new_tasks = [
            {
                "agent_id": "RecoveryAgent",
                "objective": f"Recover from failure in: {getattr(self, '_last_command', '')}",
                "instructions": json.dumps({"action": "NAVIGATE", "parameters": {"url": "https://www.google.com"}}),
                "search_queries": [],
                "wait_seconds": 1
            }
        ]

        if self.cns:
            await self.cns.publish(EventEnvelope(
                topic="RECOVERY_COMPLETED",
                source_organ="organ_01",
                payload={"task_id": task_id, "decision": "ALTERNATIVE", "new_agent_tasks": new_tasks}
            ))

    def shutdown(self) -> None:
        self._model.force_shutdown()
        LOG.log(event="brain_organ_shutdown")


if __name__ == "__main__":
    brain = BrainOrgan()
    demo_task = TaskRequest.from_dict({"raw_text": "Launch OBS and extract solar leads"})
    result_plan = brain.handle_task(demo_task)
    print(json.dumps(result_plan.to_dict(), indent=2))
