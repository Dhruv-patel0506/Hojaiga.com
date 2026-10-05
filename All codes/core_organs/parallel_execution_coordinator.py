"""
Parallel Execution Coordinator for Hojaiga Multi-Agent Swarm

Coordinates parallel execution of temporary agents across the swarm.
Manages task queues, resource allocation, and prevents deadlocks.
Ensures no overlap on same task/link.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Any
from collections import deque
import json

logger = logging.getLogger("hojaiga.parallel_coordinator")


class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResourceState(str, Enum):
    """Resource state."""
    AVAILABLE = "available"
    BUSY = "busy"
    LOCKED = "locked"


@dataclass
class Task:
    """Task for temporary agent execution."""
    task_id: str
    temp_agent_id: str
    checkpoint_id: str
    objective: str
    assigned_sub_agent: Optional[str] = None
    assigned_link: Optional[str] = None
    no_overlap: bool = True
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)  # Tasks this depends on
    dependents: List[str] = field(default_factory=list)  # Tasks that depend on this


@dataclass
class Resource:
    """Resource (link, session, etc.) for task execution."""
    resource_id: str
    resource_type: str  # "link", "session", "browser", etc.
    state: ResourceState = ResourceState.AVAILABLE
    locked_by: Optional[str] = None  # Task ID that locked this resource
    last_used: Optional[float] = None


class ParallelExecutionCoordinator:
    """
    Coordinates parallel execution of temporary agents.
    
    Features:
    - Task queue management
    - Resource allocation
    - Deadlock prevention
    - No-overlap enforcement
    - Parallel execution monitoring
    - Dependency resolution
    """
    
    def __init__(self, max_parallel_tasks: int = 10):
        self.max_parallel_tasks = max_parallel_tasks
        self.tasks: Dict[str, Task] = {}
        self.resources: Dict[str, Resource] = {}
        self.task_queue: deque[str] = deque()  # Queue of task IDs
        self.running_tasks: Set[str] = set()
        self.completed_tasks: Set[str] = set()
        self.locked_resources: Dict[str, str] = {}  # resource_id -> task_id
        
        # Resource pools
        self.available_links: Set[str] = set()
        self.available_sessions: Set[str] = set()
        
        self._running = False
        self._coordinator_task: Optional[asyncio.Task[None]] = None
        
        logger.info(f"[ParallelCoordinator] Initialized with max_parallel_tasks={max_parallel_tasks}")
    
    def add_tasks(self, temp_agent_tasks: List[Dict[str, Any]], 
                  execution_graph: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        Add temporary agent tasks to the coordinator.
        
        Args:
            temp_agent_tasks: List of temporary agent tasks from enhanced compiler
            execution_graph: Execution graph with dependencies
        
        Returns:
            List of task IDs
        """
        task_ids = []
        
        for task_info in temp_agent_tasks:
            task_id = f"task_{uuid.uuid4().hex[:8]}"
            
            task = Task(
                task_id=task_id,
                temp_agent_id=task_info.get("temp_agent_id"),
                checkpoint_id=task_info.get("checkpoint_id"),
                objective=task_info.get("objective"),
                assigned_sub_agent=task_info.get("assigned_sub_agent"),
                assigned_link=task_info.get("assigned_link"),
                no_overlap=task_info.get("no_overlap", True)
            )
            
            self.tasks[task_id] = task
            self.task_queue.append(task_id)
            task_ids.append(task_id)
            
            logger.info(f"[ParallelCoordinator] Added task {task_id}: {task.objective[:50]}...")
        
        # Process execution graph for dependencies
        if execution_graph:
            self._process_dependencies(execution_graph)
        
        logger.info(f"[ParallelCoordinator] Added {len(task_ids)} tasks to queue")
        return task_ids
    
    def _process_dependencies(self, execution_graph: Dict[str, Any]):
        """Process execution graph to extract task dependencies."""
        edges = execution_graph.get("edges") or execution_graph.get("dependencies") or []
        
        for edge in edges:
            from_node = edge.get("from")
            to_node = edge.get("to")
            
            # Find task IDs corresponding to these nodes
            # A checkpoint may map to several temporary-agent tasks; link them all
            from_task_ids = [tid for tid, t in self.tasks.items() if t.checkpoint_id == from_node]
            to_task_ids = [tid for tid, t in self.tasks.items() if t.checkpoint_id == to_node]
            
            for from_task_id in from_task_ids:
                for to_task_id in to_task_ids:
                    if from_task_id == to_task_id:
                        continue
                    self.tasks[to_task_id].dependencies.append(from_task_id)
                    self.tasks[from_task_id].dependents.append(to_task_id)
                    logger.info(f"[ParallelCoordinator] Dependency: {to_task_id} depends on {from_task_id}")
    
    def _find_task_by_checkpoint(self, checkpoint_id: str) -> Optional[str]:
        """Find task ID by checkpoint ID."""
        for task_id, task in self.tasks.items():
            if task.checkpoint_id == checkpoint_id:
                return task_id
        return None
    
    def add_resource(self, resource_id: str, resource_type: str):
        """
        Add a resource to the coordinator.
        
        Args:
            resource_id: Resource identifier
            resource_type: Resource type (link, session, browser, etc.)
        """
        resource = Resource(resource_id=resource_id, resource_type=resource_type)
        self.resources[resource_id] = resource
        
        if resource_type == "link":
            self.available_links.add(resource_id)
        elif resource_type == "session":
            self.available_sessions.add(resource_id)
        
        logger.info(f"[ParallelCoordinator] Added resource {resource_id} (type: {resource_type})")
    
    def can_start_task(self, task_id: str) -> bool:
        """
        Check if a task can start.
        
        A task can start if:
        1. All dependencies are completed
        2. Required resources are available
        3. Max parallel tasks not exceeded
        4. No overlap with running tasks (if no_overlap=True)
        
        Args:
            task_id: Task identifier
        
        Returns:
            True if task can start
        """
        task = self.tasks.get(task_id)
        if not task:
            return False
        
        # Check dependencies
        for dep_id in task.dependencies:
            if dep_id not in self.completed_tasks:
                logger.debug(f"[ParallelCoordinator] Task {task_id} waiting for dependency {dep_id}")
                return False
        
        # Check max parallel tasks
        if len(self.running_tasks) >= self.max_parallel_tasks:
            logger.debug(f"[ParallelCoordinator] Task {task_id} waiting: max parallel tasks reached")
            return False
        
        # Check no-overlap constraint
        if task.no_overlap:
            # Check if link/session is already in use
            if task.assigned_link and task.assigned_link in self.locked_resources:
                logger.debug(f"[ParallelCoordinator] Task {task_id} waiting: link {task.assigned_link} locked")
                return False
            if task.assigned_sub_agent and task.assigned_sub_agent in self.locked_resources:
                logger.debug(f"[ParallelCoordinator] Task {task_id} waiting: sub-agent {task.assigned_sub_agent} locked")
                return False
        
        return True
    
    def start_task(self, task_id: str) -> bool:
        """
        Start a task execution.
        
        Args:
            task_id: Task identifier
        
        Returns:
            True if task started successfully
        """
        task = self.tasks.get(task_id)
        if not task:
            logger.error(f"[ParallelCoordinator] Task {task_id} not found")
            return False
        
        if not self.can_start_task(task_id):
            logger.warning(f"[ParallelCoordinator] Task {task_id} cannot start yet")
            return False
        
        # Lock resources
        if task.no_overlap:
            if task.assigned_link:
                self.locked_resources[task.assigned_link] = task_id
                logger.info(f"[ParallelCoordinator] Locked link {task.assigned_link} for task {task_id}")
            if task.assigned_sub_agent:
                self.locked_resources[task.assigned_sub_agent] = task_id
                logger.info(f"[ParallelCoordinator] Locked sub-agent {task.assigned_sub_agent} for task {task_id}")
        
        # Update task status
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()
        self.running_tasks.add(task_id)
        
        logger.info(f"[ParallelCoordinator] Started task {task_id}: {task.objective[:50]}...")
        return True
    
    def complete_task(self, task_id: str, result: Optional[Dict[str, Any]] = None, error: Optional[str] = None):
        """
        Mark a task as completed.
        
        Args:
            task_id: Task identifier
            result: Task result
            error: Task error (if failed)
        """
        task = self.tasks.get(task_id)
        if not task:
            logger.error(f"[ParallelCoordinator] Task {task_id} not found")
            return
        
        # Unlock resources
        if task.no_overlap:
            if task.assigned_link and self.locked_resources.get(task.assigned_link) == task_id:
                del self.locked_resources[task.assigned_link]
                logger.info(f"[ParallelCoordinator] Unlocked link {task.assigned_link}")
            if task.assigned_sub_agent and self.locked_resources.get(task.assigned_sub_agent) == task_id:
                del self.locked_resources[task.assigned_sub_agent]
                logger.info(f"[ParallelCoordinator] Unlocked sub-agent {task.assigned_sub_agent}")
        
        # Update task status
        if error:
            task.status = TaskStatus.FAILED
            task.error = error
            logger.error(f"[ParallelCoordinator] Task {task_id} failed: {error}")
        else:
            task.status = TaskStatus.COMPLETED
            task.result = result
            logger.info(f"[ParallelCoordinator] Task {task_id} completed")
        
        task.completed_at = time.time()
        self.running_tasks.discard(task_id)
        self.completed_tasks.add(task_id)

        # Remove from the queue if still enqueued (prevents re-start after completion)
        try:
            self.task_queue.remove(task_id)
        except ValueError:
            pass
    
    async def start(self):
        """Start the parallel execution coordinator."""
        if self._running:
            logger.warning("[ParallelCoordinator] Already running")
            return
        
        self._running = True
        self._coordinator_task = asyncio.create_task(self._coordination_loop())
        logger.info("[ParallelCoordinator] Started")
    
    async def stop(self):
        """Stop the parallel execution coordinator."""
        self._running = False
        if self._coordinator_task:
            self._coordinator_task.cancel()
            try:
                await self._coordinator_task
            except asyncio.CancelledError:
                pass
        logger.info("[ParallelCoordinator] Stopped")
    
    async def _coordination_loop(self):
        """Main coordination loop."""
        while self._running:
            try:
                # Process task queue
                while self.task_queue and len(self.running_tasks) < self.max_parallel_tasks:
                    task_id = self.task_queue[0]  # Peek at front
                    
                    if self.can_start_task(task_id):
                        task_id = self.task_queue.popleft()  # Actually remove
                        self.start_task(task_id)
                    else:
                        # Can't start this task yet, check next
                        # In production, would implement smarter scheduling
                        break
                
                # Small delay to prevent busy-waiting
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"[ParallelCoordinator] Coordination loop error: {e}")
                await asyncio.sleep(1)
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get coordinator status.
        
        Returns:
            Status dictionary
        """
        total_tasks = len(self.tasks)
        pending_tasks = sum(1 for t in self.tasks.values() if t.status == TaskStatus.PENDING)
        queued_tasks = sum(1 for t in self.tasks.values() if t.status == TaskStatus.QUEUED)
        running_tasks = len(self.running_tasks)
        completed_tasks = len(self.completed_tasks)
        failed_tasks = sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED)
        
        return {
            "running": self._running,
            "total_tasks": total_tasks,
            "pending_tasks": pending_tasks,
            "queued_tasks": queued_tasks,
            "running_tasks": running_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "locked_resources": len(self.locked_resources),
            "available_links": len(self.available_links),
            "available_sessions": len(self.available_sessions),
            "max_parallel_tasks": self.max_parallel_tasks
        }
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get status of a specific task.
        
        Args:
            task_id: Task identifier
        
        Returns:
            Task status dictionary
        """
        task = self.tasks.get(task_id)
        if not task:
            return None
        
        return {
            "task_id": task.task_id,
            "temp_agent_id": task.temp_agent_id,
            "checkpoint_id": task.checkpoint_id,
            "objective": task.objective,
            "status": task.status.value,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "dependencies": task.dependencies,
            "dependents": task.dependents
        }
    
    def is_complete(self) -> bool:
        """Check if all tasks are complete."""
        return len(self.completed_tasks) == len(self.tasks) and len(self.tasks) > 0


# Singleton instance
_coordinator_instance = None


def get_parallel_coordinator(max_parallel_tasks: int = 10) -> ParallelExecutionCoordinator:
    """Get the singleton parallel coordinator instance."""
    global _coordinator_instance
    if _coordinator_instance is None:
        _coordinator_instance = ParallelExecutionCoordinator(max_parallel_tasks)
    return _coordinator_instance


if __name__ == "__main__":
    # Test the parallel coordinator
    print("Testing Parallel Execution Coordinator")
    print("=" * 60)
    
    coordinator = get_parallel_coordinator(max_parallel_tasks=3)
    
    # Add some test tasks
    test_tasks = [
        {"temp_agent_id": "temp_1", "checkpoint_id": "checkpoint_1", "objective": "Task 1", "no_overlap": True},
        {"temp_agent_id": "temp_2", "checkpoint_id": "checkpoint_1", "objective": "Task 2", "no_overlap": True},
        {"temp_agent_id": "temp_3", "checkpoint_id": "checkpoint_2", "objective": "Task 3", "no_overlap": True},
        {"temp_agent_id": "temp_4", "checkpoint_id": "checkpoint_2", "objective": "Task 4", "no_overlap": True},
        {"temp_agent_id": "temp_5", "checkpoint_id": "checkpoint_3", "objective": "Task 5", "no_overlap": True},
    ]
    
    task_ids = coordinator.add_tasks(test_tasks)
    print(f"Added {len(task_ids)} tasks")
    
    # Add resources
    coordinator.add_resource("link_1", "link")
    coordinator.add_resource("link_2", "link")
    coordinator.add_resource("session_1", "session")
    
    # Test starting tasks
    print("\nStarting tasks...")
    for task_id in task_ids[:3]:
        if coordinator.start_task(task_id):
            print(f"  Started {task_id}")
        else:
            print(f"  Could not start {task_id}")
    
    # Get status
    status = coordinator.get_status()
    print(f"\nCoordinator Status:")
    print(f"  Total tasks: {status['total_tasks']}")
    print(f"  Running tasks: {status['running_tasks']}")
    print(f"  Completed tasks: {status['completed_tasks']}")
    print(f"  Locked resources: {status['locked_resources']}")
    
    # Complete a task
    print("\nCompleting task...")
    coordinator.complete_task(task_ids[0], result={"success": True})
    
    # Get status again
    status = coordinator.get_status()
    print(f"\nCoordinator Status after completion:")
    print(f"  Running tasks: {status['running_tasks']}")
    print(f"  Completed tasks: {status['completed_tasks']}")
    print(f"  Locked resources: {status['locked_resources']}")
