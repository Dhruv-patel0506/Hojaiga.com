"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 37 Enhancement
Name: Dynamic Model Manager

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e1e;stroke:#333;stroke-width:2px;color:#d4d4d4;
    classDef component fill:#2d2d2d;stroke:#569cd6;stroke-width:2px;color:#d4d4d4;
    
    MANAGER[Dynamic Model Manager]
    
    MANAGER --> MONITOR[Model Health Monitor]
    
    MANAGER --> LOADER[Model Loader]
    
    MANAGER --> UNLOADER[Model Unloader]
    
    MANAGER --> SCHEDULER[Task Queue Scheduler]
    
    MONITOR --> HEALTH[Health Database]
    
    class MANAGER component
    class MONITOR component
    class LOADER component
    class UNLOADER component
    class SCHEDULER component
```

Inputs: Task queue, model requests
Outputs: Model loading/unloading decisions, health status
Dependencies: requests, logging, typing, subprocess...
"""

from __future__ import annotations

import logging
import json
import time
import subprocess
import threading
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, field
from enum import Enum
import requests

logger = logging.getLogger("hojaiga.organ37.dynamic_model_manager")


class ModelStatus(str, Enum):
    """Status of a model in the system."""
    NOT_LOADED = "not_loaded"
    LOADING = "loading"
    LOADED = "loaded"
    UNLOADING = "unloading"
    ERROR = "error"


class ModelPriority(str, Enum):
    """Priority levels for model loading."""
    CRITICAL = "critical"  # Always loaded (main brain)
    HIGH = "high"  # Load on startup
    MEDIUM = "medium"  # Load on demand
    LOW = "low"  # Load only when needed


@dataclass
class ModelSpec:
    """Specification for a model."""
    name: str
    ollama_name: str
    size_gb: float
    priority: ModelPriority
    capabilities: List[str]
    status: ModelStatus = ModelStatus.NOT_LOADED
    last_used: float = 0.0
    load_count: int = 0
    load_time_sec: float = 0.0
    health_score: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "ollama_name": self.ollama_name,
            "size_gb": self.size_gb,
            "priority": self.priority.value,
            "capabilities": self.capabilities,
            "status": self.status.value,
            "last_used": self.last_used,
            "load_count": self.load_count,
            "load_time_sec": self.load_time_sec,
            "health_score": self.health_score
        }


@dataclass
class ModelRequest:
    """Request for a model to be loaded."""
    model_name: str
    required_capability: str
    priority: int = 1
    caller: str = "unknown"
    requested_at: float = 0.0


class DynamicModelManager:
    """
    Dynamic model manager that loads/unloads models based on:
    - Task queue demand
    - Memory constraints
    - Model priority
    - Health monitoring
    """
    
    def __init__(self, ollama_url: str = "http://127.0.0.1:11434/api"):
        self.ollama_url = ollama_url
        self._models: Dict[str, ModelSpec] = {}
        self._loaded_models: Set[str] = set()
        self._request_queue: List[ModelRequest] = []
        self._queue_lock = threading.Lock()
        self._max_memory_gb = 16.0  # Maximum memory to use for models
        self._current_memory_gb = 0.0
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        
        # Initialize model specifications
        self._initialize_models()
    
    def _initialize_models(self) -> None:
        """Initialize the model specifications."""
        # Define available models - Updated to Qwen3.1 for unified tutor compatibility
        self._models = {
            "qwen3_1_main": ModelSpec(
                name="qwen3_1_main",
                ollama_name="qwen2.5:3b",  # Will be upgraded to qwen3.1 when available
                size_gb=1.9,
                priority=ModelPriority.CRITICAL,
                capabilities=["text", "completion", "tools", "reasoning", "vision", "tutor_compatible"]
            ),
            "qwen3_1_vision": ModelSpec(
                name="qwen3_1_vision",
                ollama_name="qwen2.5vl:3b",  # Will be upgraded to qwen3.1-vision when available
                size_gb=3.2,
                priority=ModelPriority.HIGH,
                capabilities=["vision", "multimodal", "text_vision", "tutor_compatible"]
            ),
            "qwen3_1_backup": ModelSpec(
                name="qwen3_1_backup",
                ollama_name="qwen2.5:3b",
                size_gb=1.9,
                priority=ModelPriority.HIGH,
                capabilities=["text", "completion", "tools", "reasoning", "tutor_compatible"]
            ),
            "llama3": ModelSpec(
                name="llama3",
                ollama_name="llama3:latest",
                size_gb=4.7,
                priority=ModelPriority.MEDIUM,
                capabilities=["text", "completion", "tools", "reasoning"]
            ),
            "llama3_2_vision": ModelSpec(
                name="llama3_2_vision",
                ollama_name="llama3.2-vision:latest",
                size_gb=7.8,
                priority=ModelPriority.LOW,
                capabilities=["vision", "multimodal", "advanced_vision"]
            )
        }
        
        logger.info(f"[Model Manager] Initialized {len(self._models)} model specifications")
    
    def start(self) -> None:
        """Start the dynamic model manager."""
        if self._running:
            logger.info("[Model Manager] Already running")
            return
        
        self._running = True
        
        # Load critical and high priority models on startup
        self._load_startup_models()
        
        # Start health monitor thread
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True, name="model-monitor")
        self._monitor_thread.start()
        
        logger.info("[Model Manager] Started dynamic model manager")
    
    def stop(self) -> None:
        """Stop the dynamic model manager."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
        logger.info("[Model Manager] Stopped dynamic model manager")
    
    def _load_startup_models(self) -> None:
        """Load critical and high priority models on startup."""
        startup_models = [
            spec for spec in self._models.values()
            if spec.priority in [ModelPriority.CRITICAL, ModelPriority.HIGH]
        ]
        
        logger.info(f"[Model Manager] Loading {len(startup_models)} startup models...")
        
        for spec in startup_models:
            self._load_model(spec.name)
    
    def request_model(self, model_name: str, required_capability: str, 
                     caller: str = "unknown", priority: int = 1) -> bool:
        """
        Request a model to be loaded for a task.
        
        Args:
            model_name: Name of the model to request
            required_capability: Capability needed from the model
            caller: Component requesting the model
            priority: Priority of the request
        
        Returns:
            True if model is available, False otherwise
        """
        with self._queue_lock:
            if model_name not in self._models:
                logger.warning(f"[Model Manager] Unknown model requested: {model_name}")
                return False
            
            spec = self._models[model_name]
            
            # Check if model has required capability
            if required_capability not in spec.capabilities:
                logger.warning(f"[Model Manager] Model {model_name} doesn't have capability: {required_capability}")
                return False
            
            # Add to request queue
            request = ModelRequest(
                model_name=model_name,
                required_capability=required_capability,
                priority=priority,
                caller=caller,
                requested_at=time.time()
            )
            self._request_queue.append(request)
            
            logger.info(f"[Model Manager] Model requested: {model_name} by {caller} (priority: {priority})")
            
            # Process queue
            self._process_queue()
            
            return True
    
    def _process_queue(self) -> None:
        """Process the model request queue."""
        if not self._request_queue:
            return
        
        # Sort by priority (higher priority first)
        self._request_queue.sort(key=lambda r: r.priority, reverse=True)
        
        # Process requests
        for request in self._request_queue[:]:
            model_name = request.model_name
            spec = self._models[model_name]
            
            # Check if already loaded
            if model_name in self._loaded_models:
                spec.last_used = time.time()
                logger.info(f"[Model Manager] Model {model_name} already loaded")
                continue
            
            # Check memory constraints
            if self._current_memory_gb + spec.size_gb > self._max_memory_gb:
                # Need to unload some models
                self._unload_low_priority_models(spec.size_gb)
            
            # Load the model
            if self._load_model(model_name):
                spec.last_used = time.time()
                spec.load_count += 1
                self._loaded_models.add(model_name)
                self._current_memory_gb += spec.size_gb
            else:
                logger.error(f"[Model Manager] Failed to load model: {model_name}")
        
        # Clear processed requests
        self._request_queue.clear()
    
    def _load_model(self, model_name: str) -> bool:
        """Load a model using Ollama."""
        spec = self._models[model_name]
        
        try:
            spec.status = ModelStatus.LOADING
            start_time = time.time()
            
            # Use Ollama to pull/load the model
            payload = {
                "model": spec.ollama_name,
                "prompt": "test",
                "stream": False
            }
            
            response = requests.post(f"{self.ollama_url}/api/generate", 
                                     json=payload, timeout=120)
            
            spec.status = ModelStatus.LOADED
            spec.load_time_sec = time.time() - start_time
            spec.health_score = 1.0  # Initial health score
            
            logger.info(f"[Model Manager] Loaded model: {model_name} in {spec.load_time_sec:.2f}s")
            
            return True
            
        except Exception as e:
            spec.status = ModelStatus.ERROR
            logger.error(f"[Model Manager] Failed to load model {model_name}: {e}")
            return False
    
    def _unload_low_priority_models(self, required_space_gb: float) -> None:
        """Unload low priority models to free up memory."""
        # Get models sorted by priority and last used time
        candidates = [
            (name, spec)
            for name, spec in self._models.items()
            if name in self._loaded_models
            and spec.priority == ModelPriority.LOW
        ]
        
        # Sort by last used (oldest first)
        candidates.sort(key=lambda x: x[1].last_used)
        
        freed_gb = 0.0
        
        for model_name, spec in candidates:
            if freed_gb >= required_space_gb:
                break
            
            if self._unload_model(model_name):
                freed_gb += spec.size_gb
                logger.info(f"[Model Manager] Unloaded low-priority model: {model_name}")
        
        if freed_gb < required_space_gb:
            logger.warning(f"[Model Manager] Could not free enough memory: needed {required_space_gb}GB, freed {freed_gb}GB")
    
    def _unload_model(self, model_name: str) -> bool:
        """Unload a model (simplified - Ollama doesn't have explicit unload)."""
        spec = self._models[model_name]
        
        try:
            spec.status = ModelStatus.UNLOADING
            
            # Ollama doesn't have explicit unload, but we can mark it as not loaded
            # In a real implementation, this would involve:
            # - Sending a keepalive timeout
            # - Or restarting Ollama without the model
            
            spec.status = ModelStatus.NOT_LOADED
            self._loaded_models.discard(model_name)
            self._current_memory_gb -= spec.size_gb
            
            logger.info(f"[Model Manager] Unloaded model: {model_name}")
            
            return True
            
        except Exception as e:
            spec.status = ModelStatus.ERROR
            logger.error(f"[Model Manager] Failed to unload model {model_name}: {e}")
            return False
    
    def _monitor_loop(self) -> None:
        """Background health monitoring loop."""
        logger.info("[Model Manager] Health monitor started")
        
        while self._running:
            try:
                time.sleep(30)  # Check every 30 seconds
                
                # Check health of loaded models
                for model_name in list(self._loaded_models):
                    self._check_model_health(model_name)
                
                # Update health scores based on age
                self._update_health_scores()
                
                # Unload idle low-priority models
                self._unload_idle_models()
                
            except Exception as e:
                logger.error(f"[Model Manager] Monitor loop error: {e}")
        
        logger.info("[Model Manager] Health monitor stopped")
    
    def _check_model_health(self, model_name: str) -> None:
        """Check the health of a loaded model."""
        spec = self._models[model_name]
        
        try:
            # Send a simple test prompt
            payload = {
                "model": spec.ollama_name,
                "prompt": "test",
                "stream": False
            }
            
            start_time = time.time()
            response = requests.post(f"{self.ollama_url}/api/generate",
                                     json=payload, timeout=15)
            duration = time.time() - start_time
            
            if response.status_code == 200:
                # Update health score based on response time
                if duration < 5.0:
                    spec.health_score = min(1.0, spec.health_score + 0.1)
                elif duration > 30.0:
                    spec.health_score = max(0.0, spec.health_score - 0.2)
                
                logger.debug(f"[Model Manager] Model {model_name} health check: {spec.health_score:.2f} (duration: {duration:.2f}s)")
            else:
                spec.health_score = max(0.0, spec.health_score - 0.3)
                logger.warning(f"[Model Manager] Model {model_name} health check failed with status {response.status_code}")
                
        except Exception as e:
            spec.health_score = max(0.0, spec.health_score - 0.3)
            logger.error(f"[Model Manager] Model {model_name} health check error: {e}")
    
    def _update_health_scores(self) -> None:
        """Update health scores based on age since last use."""
        for spec in self._models.values():
            if spec.status == ModelStatus.LOADED:
                age_seconds = time.time() - spec.last_used
                # Decay health score slowly over time
                decay = max(0.0, age_seconds / 3600.0 * 0.1)  # 10% decay per hour of inactivity
                spec.health_score = max(0.0, spec.health_score - decay)
    
    def _unload_idle_models(self) -> None:
        """Unload models that haven't been used recently."""
        idle_threshold_seconds = 600  # 10 minutes
        
        for model_name in list(self._loaded_models):
            spec = self.models[model_name]
            
            # Only unload low priority models
            if spec.priority != ModelPriority.LOW:
                continue
            
            # Check if idle
            idle_time = time.time() - spec.last_used
            if idle_time > idle_threshold_seconds:
                if self._unload_model(model_name):
                    logger.info(f"[Model Manager] Unloaded idle model: {model_name} (idle for {idle_time:.0f}s)")
    
    def get_model_status(self, model_name: str) -> Optional[ModelSpec]:
        """Get the current status of a model."""
        return self._models.get(model_name)
    
    def get_all_model_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all models."""
        return {
            name: spec.to_dict()
            for name, spec in self._models.items()
        }
    
    def get_memory_usage(self) -> Dict[str, float]:
        """Get current memory usage statistics."""
        return {
            "current_gb": self._current_memory_gb,
            "max_gb": self._max_memory_gb,
            "utilization": self._current_memory_gb / self._max_memory_gb if self._max_memory_gb > 0 else 0.0,
            "loaded_count": len(self._loaded_models)
        }


# Singleton instance
_model_manager_instance: Optional[DynamicModelManager] = None

def get_model_manager() -> DynamicModelManager:
    """Get the singleton model manager instance."""
    global _model_manager_instance
    if _model_manager_instance is None:
        _model_manager_instance = DynamicModelManager()
    return _model_manager_instance


def request_model(model_name: str, required_capability: str, 
                 caller: str = "unknown", priority: int = 1) -> bool:
    """
    Convenience function to request a model.
    
    Args:
        model_name: Name of the model to request
        required_capability: Capability needed
        caller: Component requesting the model
        priority: Priority of the request
    
    Returns:
        True if model is available, False otherwise
    """
    manager = get_model_manager()
    return manager.request_model(model_name, required_capability, caller, priority)
