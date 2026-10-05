"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 31 Enhancement
Name: Vision Model Health Monitor

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e;stroke:#333;stroke-width:2px;color:#d4d4d4;
    classDef component fill:#2d2d2d;stroke:#569cd6;stroke-width:2px;color:#d4d4d4;
    
    MONITOR[Vision Health Monitor]
    
    MONITOR --> HEALTH[Health Database]
    
    MONITOR --> PREWARM[Pre-warming Engine]
    
    MONITOR --> LATENCY[Latency Tracker]
    
    MONITOR --> FALLBACK[Fallback Manager]
    
    class MONITOR component
    class HEALTH component
    class PREWARM component
    class LATENCY component
    class FALLBACK component
```

Inputs: Vision model requests, execution results
Outputs: Health status, pre-warming triggers, fallback decisions
Dependencies: requests, logging, typing, threading...
"""

from __future__ import annotations

import logging
import time
import threading
import requests
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
import statistics

logger = logging.getLogger("hojaiga.organ31.vision_health_monitor")


class VisionModel(str, Enum):
    """Available vision models."""
    MOONDREAM = "moondream"
    MINICPM_V = "minicpm_v"
    QWEN2_5VL_3B = "qwen2_5vl_3b"
    LLAMA3_2_VISION = "llama3_2_vision"
    LLAVA_LLAMA3 = "llava_llama3"


class HealthStatus(str, Enum):
    """Health status of a vision model."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthMetric:
    """Health metric for a vision model."""
    model: VisionModel
    status: HealthStatus
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    latency_p99_ms: float = 0.0
    success_rate: float = 1.0
    error_count: int = 0
    total_requests: int = 0
    last_check: float = 0.0
    last_error: Optional[str] = None
    is_prewarmed: bool = False
    prewarmed_at: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model.value,
            "status": self.status.value,
            "latency_p50_ms": self.latency_p50_ms,
            "latency_p95_ms": self.latency_p95_ms,
            "latency_p99_ms": self.latency_p99_ms,
            "success_rate": self.success_rate,
            "error_count": self.error_count,
            "total_requests": self.total_requests,
            "last_check": self.last_check,
            "last_error": self.last_error,
            "is_prewarmed": self.is_prewarmed,
            "prewarmed_at": self.prewarmed_at
        }


@dataclass
class VisionRequest:
    """Record of a vision model request."""
    model: VisionModel
    timestamp: float
    latency_ms: float
    success: bool
    error: Optional[str] = None


class VisionHealthMonitor:
    """
    Vision model health monitor that:
    - Tracks latency and success rates for all vision models
    - Pre-warms models before first use
    - Detects degradation and triggers fallback
    - Provides health reports for decision making
    """
    
    def __init__(self, ollama_url: str = "http://127.0.0.1:11434/api"):
        self.ollama_url = ollama_url
        self._metrics: Dict[VisionModel, HealthMetric] = {}
        self._request_history: List[VisionRequest] = []
        self._history_lock = threading.Lock()
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._max_history = 1000
        self._health_check_interval = 60  # seconds
        
        # Initialize metrics for all vision models
        self._initialize_metrics()
    
    def _initialize_metrics(self) -> None:
        """Initialize health metrics for all vision models."""
        for model in VisionModel:
            self._metrics[model] = HealthMetric(
                model=model,
                status=HealthStatus.UNKNOWN,
                is_prewarmed=False
            )
        
        logger.info(f"[Vision Health] Initialized metrics for {len(VisionModel)} models")
    
    def start(self) -> None:
        """Start the vision health monitor daemon."""
        if self._running:
            logger.info("[Vision Health] Already running")
            return
        
        self._running = True
        
        # Pre-warm fast vision models
        self._prewarm_critical_models()
        
        # Start monitor thread
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True, name="vision-health-monitor")
        self._monitor_thread.start()
        
        logger.info("[Vision Health] Daemon started")
    
    def stop(self) -> None:
        """Stop the vision health monitor daemon."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
        logger.info("[Vision Health] Daemon stopped")
    
    def _prewarm_critical_models(self) -> None:
        """Pre-warm critical vision models on startup."""
        critical_models = [VisionModel.MOONDREAM, VisionModel.QWEN2_5VL_3B]
        
        logger.info(f"[Vision Health] Pre-warming {len(critical_models)} critical models...")
        
        for model in critical_models:
            if self._prewarm_model(model):
                logger.info(f"[Vision Health] Pre-warmed: {model.value}")
            else:
                logger.warning(f"[Vision Health] Failed to pre-warm: {model.value}")
    
    def _prewarm_model(self, model: VisionModel) -> bool:
        """Pre-warm a vision model with a simple test request."""
        try:
            ollama_name = self._get_ollama_name(model)
            
            # Send a simple text prompt to warm up the model
            payload = {
                "model": ollama_name,
                "prompt": "test",
                "stream": False
            }
            
            start_time = time.time()
            response = requests.post(f"{self.ollama_url}/api/generate",
                                     json=payload, timeout=30)
            duration_ms = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                metric = self._metrics[model]
                metric.is_prewarmed = True
                metric.prewarmed_at = time.time()
                metric.last_check = time.time()
                metric.status = HealthStatus.HEALTHY
                
                logger.info(f"[Vision Health] Pre-warmed {model.value} in {duration_ms:.0f}ms")
                return True
            else:
                logger.warning(f"[Vision Health] Pre-warm failed for {model.value}: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"[Vision Health] Pre-warm error for {model.value}: {e}")
            return False
    
    def record_request(self, model: VisionModel, latency_ms: float, 
                      success: bool, error: Optional[str] = None) -> None:
        """
        Record a vision model request for health tracking.
        
        Args:
            model: Vision model used
            latency_ms: Request latency in milliseconds
            success: Whether the request succeeded
            error: Error message if failed
        """
        with self._history_lock:
            request = VisionRequest(
                model=model,
                timestamp=time.time(),
                latency_ms=latency_ms,
                success=success,
                error=error
            )
            
            self._request_history.append(request)
            
            # Trim history
            if len(self._request_history) > self._max_history:
                self._request_history = self._request_history[-self._max_history:]
        
        # Update metrics
        self._update_metrics(model)
    
    def _update_metrics(self, model: VisionModel) -> None:
        """Update health metrics for a model based on recent history."""
        with self._history_lock:
            # Get recent requests for this model (last 100)
            recent = [r for r in self._request_history if r.model == model][-100:]
            
            if not recent:
                return
            
            metric = self._metrics[model]
            metric.total_requests = len(recent)
            metric.error_count = sum(1 for r in recent if not r.success)
            metric.success_rate = 1.0 - (metric.error_count / metric.total_requests)
            metric.last_check = time.time()
            
            # Calculate latency percentiles
            latencies = [r.latency_ms for r in recent if r.success]
            if latencies:
                metric.latency_p50_ms = statistics.median(latencies)
                metric.latency_p95_ms = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)
                metric.latency_p99_ms = statistics.quantiles(latencies, n=100)[98] if len(latencies) >= 100 else max(latencies)
            
            # Update health status
            if metric.success_rate < 0.8:
                metric.status = HealthStatus.UNHEALTHY
                metric.last_error = "Low success rate"
            elif metric.latency_p95_ms > 10000:  # 10 seconds
                metric.status = HealthStatus.DEGRADED
                metric.last_error = "High latency"
            else:
                metric.status = HealthStatus.HEALTHY
                metric.last_error = None
    
    def get_best_model(self, task_complexity: str = "medium") -> VisionModel:
        """
        Get the best available vision model for a task.
        
        Args:
            task_complexity: Complexity level (simple, medium, complex)
        
        Returns:
            Best available vision model
        """
        # Model selection based on complexity and health
        if task_complexity == "simple":
            # Fast models for simple tasks
            candidates = [VisionModel.MOONDREAM, VisionModel.QWEN2_5VL_3B]
        elif task_complexity == "complex":
            # Precision models for complex tasks
            candidates = [VisionModel.MINICPM_V, VisionModel.LLAMA3_2_VISION]
        else:
            # Balanced models for medium tasks
            candidates = [VisionModel.QWEN2_5VL_3B, VisionModel.MOONDREAM, VisionModel.MINICPM_V]
        
        # Select based on health
        for model in candidates:
            metric = self._metrics[model]
            if metric.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]:
                return model
        
        # Fallback to first candidate
        return candidates[0]
    
    def _monitor_loop(self) -> None:
        """Background health monitoring loop."""
        logger.info("[Vision Health] Monitor loop started")
        
        while self._running:
            try:
                time.sleep(self._health_check_interval)
                
                # Perform health checks on all models
                for model in VisionModel:
                    self._perform_health_check(model)
                
                # Clean up old history
                self._cleanup_history()
                
            except Exception as e:
                logger.error(f"[Vision Health] Monitor loop error: {e}")
        
        logger.info("[Vision Health] Monitor loop stopped")
    
    def _perform_health_check(self, model: VisionModel) -> None:
        """Perform a health check on a model."""
        try:
            ollama_name = self._get_ollama_name(model)
            
            # Send a simple test request
            payload = {
                "model": ollama_name,
                "prompt": "health check",
                "stream": False
            }
            
            start_time = time.time()
            response = requests.post(f"{self.ollama_url}/api/generate",
                                     json=payload, timeout=15)
            duration_ms = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                self.record_request(model, duration_ms, True)
                logger.debug(f"[Vision Health] Health check passed for {model.value}: {duration_ms:.0f}ms")
            else:
                self.record_request(model, duration_ms, False, f"HTTP {response.status_code}")
                logger.warning(f"[Vision Health] Health check failed for {model.value}: HTTP {response.status_code}")
                
        except Exception as e:
            self.record_request(model, 0, False, str(e))
            logger.error(f"[Vision Health] Health check error for {model.value}: {e}")
    
    def _cleanup_history(self) -> None:
        """Clean up old request history."""
        with self._history_lock:
            cutoff = time.time() - 3600  # Keep last hour
            self._request_history = [r for r in self._request_history if r.timestamp > cutoff]
    
    def _get_ollama_name(self, model: VisionModel) -> str:
        """Get the Ollama model name for a VisionModel enum."""
        mapping = {
            VisionModel.MOONDREAM: "moondream:latest",
            VisionModel.MINICPM_V: "minicpm-v:latest",
            VisionModel.QWEN2_5VL_3B: "qwen2.5vl:3b",
            VisionModel.LLAMA3_2_VISION: "llama3.2-vision:latest",
            VisionModel.LLAVA_LLAMA3: "llava-llama3:latest"
        }
        return mapping.get(model, model.value)
    
    def get_health_report(self) -> Dict[str, Dict[str, Any]]:
        """Get a comprehensive health report for all vision models."""
        return {
            model.value: metric.to_dict()
            for model, metric in self._metrics.items()
        }
    
    def get_model_health(self, model: VisionModel) -> Optional[HealthMetric]:
        """Get health status for a specific model."""
        return self._metrics.get(model)
    
    def should_use_fallback(self, model: VisionModel) -> bool:
        """Determine if a fallback model should be used."""
        metric = self._metrics.get(model)
        if not metric:
            return True
        
        return metric.status == HealthStatus.UNHEALTHY


# Singleton instance
_health_monitor_instance: Optional[VisionHealthMonitor] = None

def get_vision_health_monitor() -> VisionHealthMonitor:
    """Get the singleton vision health monitor instance."""
    global _health_monitor_instance
    if _health_monitor_instance is None:
        _health_monitor_instance = VisionHealthMonitor()
    return _health_monitor_instance


def record_vision_request(model: str, latency_ms: float, 
                         success: bool, error: Optional[str] = None) -> None:
    """
    Convenience function to record a vision request.
    
    Args:
        model: Vision model name
        latency_ms: Request latency
        success: Whether request succeeded
        error: Error message if failed
    """
    monitor = get_vision_health_monitor()
    try:
        model_enum = VisionModel(model.lower())
        monitor.record_request(model_enum, latency_ms, success, error)
    except ValueError:
        logger.warning(f"[Vision Health] Unknown model: {model}")


def get_best_vision_model(task_complexity: str = "medium") -> str:
    """
    Convenience function to get the best vision model.
    
    Args:
        task_complexity: Complexity level
    
    Returns:
        Best vision model name
    """
    monitor = get_vision_health_monitor()
    model = monitor.get_best_model(task_complexity)
    return model.value
