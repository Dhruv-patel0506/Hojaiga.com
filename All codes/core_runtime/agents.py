"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Core File
Name: agents.py

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [agents.py]
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
Dependencies: enum, typing, __future__, time, asyncio...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: agents.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
Universal Agent Runtime (agents.py)
===================================
A standalone floating service that runs universally alongside the Hojaiga Automation OS.
This is NOT an Organ. Instead, it is a runtime layer that connects via the CNS (Organ 02)
to execute workloads across three hierarchical tiers of agents: Permanent, Sub, and Temporary.

Design Constraints:
- Business logic stays out of this file (it lives in Organs).
- Uses hierarchical checkpoints to measure task completion.
- Reports roll upward to the CNS, then to the Brain (via session bus) if blocked.
- Uses dynamic lease-based sockets.
- Parallel execution via asyncio.
- Resource-aware concurrency (checks Organ 30 before spawning).
- Avoids GUI/Chrome automation collisions via strict environment locks/permissions.
"""


import asyncio
import enum
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Awaitable

# Optional typing integration with the Hojaiga OS
try:
    from core_organs.organ_02_cns_single_file import EventEnvelope, MessageType, now_ms
except ImportError:
    # Stubs if run entirely isolated
    def now_ms() -> int: return int(time.time() * 1000)

log = logging.getLogger("agents_runtime")

# ============================================================================
# Checkpoint Hierarchy
# ============================================================================

class CheckpointState(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

@dataclass
class AtomicCheckpoint:
    """The smallest unit of work. Executed by a TemporaryAgent."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    state: CheckpointState = CheckpointState.PENDING
    result_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

@dataclass
class SubCheckpoint:
    """A major milestone made of several atomic steps. Managed by a SubAgent."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    atomic_steps: List[AtomicCheckpoint] = field(default_factory=list)
    state: CheckpointState = CheckpointState.PENDING

    def update_state(self) -> None:
        if not self.atomic_steps:
            return
        if any(step.state == CheckpointState.FAILED for step in self.atomic_steps):
            self.state = CheckpointState.FAILED
        elif all(step.state == CheckpointState.COMPLETED for step in self.atomic_steps):
            self.state = CheckpointState.COMPLETED
        else:
            self.state = CheckpointState.IN_PROGRESS

@dataclass
class MainCheckpoint:
    """The root task tracked by a PermanentAgent."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    sub_checkpoints: List[SubCheckpoint] = field(default_factory=list)
    state: CheckpointState = CheckpointState.PENDING

    def update_state(self) -> None:
        if not self.sub_checkpoints:
            return
        if any(sub.state == CheckpointState.FAILED for sub in self.sub_checkpoints):
            self.state = CheckpointState.FAILED
        elif all(sub.state == CheckpointState.COMPLETED for sub in self.sub_checkpoints):
            self.state = CheckpointState.COMPLETED
        else:
            self.state = CheckpointState.IN_PROGRESS


# ============================================================================
# Runtime Services (Mock/Facades for CNS & Resource Manager)
# ============================================================================

class CNSFacade:
    """Facade for publishing lease-based socket events back to CNS."""
    async def report_upward(self, topic: str, payload: dict, requires_brain_help: bool = False) -> None:
        log.info(f"[CNS UPWARD] Topic: {topic} | Requires Brain: {requires_brain_help} | Payload: {payload}")
        # In a real environment, this connects to the Session Bus / CNS TCP Socket
        await asyncio.sleep(0.01)

class ResourceManagerFacade:
    """Facade for leasing hardware resources and tracking locks to avoid collisions."""
    def __init__(self) -> None:
        self.active_locks: Set[str] = set()

    async def request_lease(self, agent_id: str, ram_mb: int, cpu_pct: float) -> bool:
        log.debug(f"[{agent_id}] Lease granted: {ram_mb}MB RAM, {cpu_pct}% CPU")
        return True

    async def acquire_lock(self, lock_name: str) -> bool:
        """Used to prevent GUI/Chrome collisions."""
        if lock_name in self.active_locks:
            return False
        self.active_locks.add(lock_name)
        return True

    async def release_lock(self, lock_name: str) -> None:
        self.active_locks.discard(lock_name)


# ============================================================================
# Agent Worker Classes
# ============================================================================

class AgentPermission(str, enum.Enum):
    CHROME_CDP = "CHROME_CDP"
    GUI_AUTOMATION = "GUI_AUTOMATION"
    FILESYSTEM_READ = "FILESYSTEM_READ"
    FILESYSTEM_WRITE = "FILESYSTEM_WRITE"
    NETWORK_OUTBOUND = "NETWORK_OUTBOUND"


class BaseAgent:
    def __init__(self, agent_id: str, cns: CNSFacade, resource_manager: ResourceManagerFacade):
        self.agent_id = agent_id
        self.cns = cns
        self.resource_manager = resource_manager
        self.permissions: Set[AgentPermission] = set()
        
    async def acquire_exclusive_environment(self, perm: AgentPermission) -> bool:
        """Acquire a global lock for permissions that collide (GUI, Chrome)."""
        if perm not in self.permissions:
            raise PermissionError(f"Agent {self.agent_id} lacks permission {perm.value}")
        return await self.resource_manager.acquire_lock(perm.value)
        
    async def release_exclusive_environment(self, perm: AgentPermission) -> None:
        await self.resource_manager.release_lock(perm.value)


class TemporaryAgent(BaseAgent):
    """
    Temporary agents do atomic steps only. They do not self-delete; they finish,
    report upward, and wait for garbage collection or reassignment by the SubAgent.
    """
    def __init__(self, agent_id: str, cns: CNSFacade, resource_manager: ResourceManagerFacade):
        super().__init__(agent_id, cns, resource_manager)

    async def execute_atomic(self, checkpoint: AtomicCheckpoint, execution_callback: Callable[[], Awaitable[Dict[str, Any]]]) -> None:
        """Executes a single atomic unit of work and reports the result upward."""
        checkpoint.state = CheckpointState.IN_PROGRESS
        await self.cns.report_upward("AGENT_STEP_STARTED", {"agent_id": self.agent_id, "checkpoint_id": checkpoint.id})
        
        # Check for collision-heavy permissions
        holds_chrome = False
        holds_gui = False
        try:
            if AgentPermission.CHROME_CDP in self.permissions:
                holds_chrome = await self.acquire_exclusive_environment(AgentPermission.CHROME_CDP)
                if not holds_chrome:
                    raise RuntimeError("Failed to acquire exclusive Chrome CDP lock. Collision avoided.")
                    
            if AgentPermission.GUI_AUTOMATION in self.permissions:
                holds_gui = await self.acquire_exclusive_environment(AgentPermission.GUI_AUTOMATION)
                if not holds_gui:
                    raise RuntimeError("Failed to acquire exclusive GUI lock. Collision avoided.")

            # Business logic execution (passed as callback so agents.py stays generic)
            result = await execution_callback()
            
            checkpoint.result_data = result
            checkpoint.state = CheckpointState.COMPLETED
            await self.cns.report_upward("AGENT_STEP_COMPLETED", {"agent_id": self.agent_id, "checkpoint_id": checkpoint.id})
            
        except Exception as e:
            checkpoint.error_message = str(e)
            checkpoint.state = CheckpointState.FAILED
            # Roll upward to CNS/Brain on failure
            await self.cns.report_upward(
                "AGENT_STEP_FAILED", 
                {"agent_id": self.agent_id, "checkpoint_id": checkpoint.id, "error": str(e)},
                requires_brain_help=True
            )
        finally:
            if holds_chrome:
                await self.release_exclusive_environment(AgentPermission.CHROME_CDP)
            if holds_gui:
                await self.release_exclusive_environment(AgentPermission.GUI_AUTOMATION)


class SubAgent(BaseAgent):
    """
    SubAgents manage major checkpoints. They spawn TemporaryAgents, ensure resource
    quotas are met, run atomic steps in parallel, and roll up states to the PermanentAgent.
    """
    def __init__(self, agent_id: str, cns: CNSFacade, resource_manager: ResourceManagerFacade):
        super().__init__(agent_id, cns, resource_manager)
        self.managed_temporaries: List[TemporaryAgent] = []

    async def execute_sub_checkpoint(self, checkpoint: SubCheckpoint, steps_map: Dict[str, Callable[[], Awaitable[Dict[str, Any]]]]) -> None:
        checkpoint.state = CheckpointState.IN_PROGRESS
        
        # Request lease for the overall SubAgent operation
        await self.resource_manager.request_lease(self.agent_id, ram_mb=512, cpu_pct=20.0)

        tasks = []
        for idx, atomic in enumerate(checkpoint.atomic_steps):
            # Spawn Temporary Agent for each atomic step
            temp_agent_id = f"{self.agent_id}-temp-{idx}"
            temp_agent = TemporaryAgent(temp_agent_id, self.cns, self.resource_manager)
            # Inherit non-colliding permissions for the temp worker (mock example)
            temp_agent.permissions = self.permissions.copy()
            
            self.managed_temporaries.append(temp_agent)
            
            if atomic.id in steps_map:
                tasks.append(temp_agent.execute_atomic(atomic, steps_map[atomic.id]))

        # Execute parallel branches
        await asyncio.gather(*tasks)

        # Roll up results
        checkpoint.update_state()
        if checkpoint.state == CheckpointState.FAILED:
            await self.cns.report_upward(
                "SUBAGENT_CHECKPOINT_FAILED", 
                {"agent_id": self.agent_id, "checkpoint_id": checkpoint.id},
                requires_brain_help=True
            )
        else:
            await self.cns.report_upward("SUBAGENT_CHECKPOINT_COMPLETED", {"agent_id": self.agent_id, "checkpoint_id": checkpoint.id})


class PermanentAgent(BaseAgent):
    """
    Permanent Agents are long-running domain specialists. They idle waiting for jobs,
    share work (load balance), and break main checkpoints down into sub-checkpoints.
    """
    def __init__(self, domain: str, cns: CNSFacade, resource_manager: ResourceManagerFacade):
        super().__init__(f"perm-{domain}-{uuid.uuid4().hex[:6]}", cns, resource_manager)
        self.domain = domain
        self.is_idle = True

    async def listen_and_process(self, main_checkpoint: MainCheckpoint, workflow_map: Dict[str, Dict[str, Callable[[], Awaitable[Dict[str, Any]]]]]) -> None:
        """
        In a real scenario, this would loop listening to the CNS.
        Here we simulate accepting a MainCheckpoint and breaking it down.
        """
        self.is_idle = False
        main_checkpoint.state = CheckpointState.IN_PROGRESS
        
        try:
            for sub_cp in main_checkpoint.sub_checkpoints:
                # Share work / spawn SubAgent
                sub_agent = SubAgent(f"sub-{self.agent_id}-{uuid.uuid4().hex[:4]}", self.cns, self.resource_manager)
                # Assign permissions based on domain knowledge
                if "web" in self.domain.lower():
                    sub_agent.permissions.add(AgentPermission.CHROME_CDP)
                    
                steps_map = workflow_map.get(sub_cp.id, {})
                await sub_agent.execute_sub_checkpoint(sub_cp, steps_map)
                
                # If a sub checkpoint fails, the permanent agent escalates the whole failure
                main_checkpoint.update_state()
                if main_checkpoint.state == CheckpointState.FAILED:
                    break
                    
        finally:
            self.is_idle = True
            if main_checkpoint.state == CheckpointState.FAILED:
                await self.cns.report_upward(
                    "PERMANENT_TASK_FAILED", 
                    {"agent_id": self.agent_id, "checkpoint_id": main_checkpoint.id},
                    requires_brain_help=True
                )
            else:
                main_checkpoint.state = CheckpointState.COMPLETED
                await self.cns.report_upward("PERMANENT_TASK_COMPLETED", {"agent_id": self.agent_id, "checkpoint_id": main_checkpoint.id})

# End of agents.py
