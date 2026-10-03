"""
ModelPoolOrchestrator — Dynamic Model Pool & Asynchronous Outgoing Mailbox for Hojaiga OS.

Architectural Highlights:
1. Dynamic Tiered Model Pool (Fast Heartbeat, Vision Specialist, Deep Reasoning).
2. Dynamic VRAM Awareness (manages Ollama keep_alive so idle models unload and free GPU VRAM).
3. Non-Blocking Asynchronous Mailbox (each query gets a ticket_id, responses delivered independently
   without blocking the Brain or triggering Gatekeeper 429 rate limits).
"""

from __future__ import annotations

import os
import time
import json
import uuid
import queue
import logging
import asyncio
import threading
import requests
from typing import Dict, Any, Optional, Callable

logger = logging.getLogger("model_pool_orchestrator")


class ModelTier:
    FAST = "qwen2.5:3b"
    VISION = "qwen2.5vl:3b"
    VISION_REASON = "minicpm-v:latest"
    VISION_PRECISION = os.environ.get("HOJAIGA_VISION_PRECISION_ENDPOINT", "minicpm-v:latest")
    REASONING = "llama3:latest"
    LIGHTWEIGHT = "moondream:latest"


class ModelPoolOrchestrator:
    """Manages multi-model routing, VRAM caching, and non-blocking asynchronous response delivery."""

    _instance: Optional["ModelPoolOrchestrator"] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "ModelPoolOrchestrator":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self, ollama_url: str = "http://127.0.0.1:11434") -> None:
        self.ollama_url = ollama_url.rstrip("")

        # Outgoing Mailbox: ticket_id -> asyncio.Future / threading.Event
        self._mailbox: Dict[str, Dict[str, Any]] = {}
        self._mailbox_lock = threading.Lock()

        # Model utilization tracking: model_name -> {"in_use": bool, "last_used": float, "queue_depth": int}
        self._model_state: Dict[str, Dict[str, Any]] = {}
        self._model_state_lock = threading.Lock()

        # Dynamically adapt to host hardware specs
        try:
            from .host_hardware_profiler import HostHardwareProfiler
            self._host_profile = HostHardwareProfiler.get_instance().profile
            concurrency = self._host_profile.max_concurrency
            ModelTier.FAST = self._host_profile.preferred_fast_model
            ModelTier.VISION = self._host_profile.preferred_vision_model
            ModelTier.REASONING = self._host_profile.preferred_reasoning_model
            logger.info("[ModelPool] Hardware profiler tuned: tier=%s, workers=%d, GPU=%s (%.1fGB VRAM)",
                        self._host_profile.tier, concurrency,
                        self._host_profile.specs.gpu_name, self._host_profile.specs.gpu_vram_gb)
        except Exception as e:
            logger.warning("[ModelPool] Hardware profiler fallback: %s", e)
            self._host_profile = None
            concurrency = 3

        # Active workers
        self._request_queue: queue.Queue = queue.Queue()
        self._running = True
        self._worker_threads = []
        for i in range(concurrency):
            t = threading.Thread(target=self._worker_loop, name=f"model-worker-{i}", daemon=True)
            t.start()
            self._worker_threads.append(t)

        logger.info("[ModelPool] Initialized with %d async worker threads, Ollama: %s", concurrency, self.ollama_url)

    # ── Model Utilization Tracking ─────────────────────────────────────────

    def _mark_model_busy(self, model_name: str):
        with self._model_state_lock:
            if model_name not in self._model_state:
                self._model_state[model_name] = {"in_use": False, "last_used": 0, "queue_depth": 0}
            self._model_state[model_name]["in_use"] = True
            self._model_state[model_name]["queue_depth"] += 1
            self._model_state[model_name]["last_used"] = time.time()

    def _mark_model_free(self, model_name: str):
        with self._model_state_lock:
            if model_name in self._model_state:
                self._model_state[model_name]["queue_depth"] = max(0, self._model_state[model_name]["queue_depth"] - 1)
                if self._model_state[model_name]["queue_depth"] == 0:
                    self._model_state[model_name]["in_use"] = False

    def is_model_busy(self, model_name: str) -> bool:
        with self._model_state_lock:
            state = self._model_state.get(model_name, {})
            return state.get("in_use", False) and state.get("queue_depth", 0) > 0

    def get_available_model(self, preferred: str, fallbacks: list = None) -> str:
        """Return preferred model if available, else first available fallback."""
        if not self.is_model_busy(preferred):
            return preferred
        for fb in (fallbacks or []):
            if not self.is_model_busy(fb):
                logger.info("[ModelPool] %s busy, routing to fallback: %s", preferred, fb)
                return fb
        # All busy — return preferred anyway (will queue)
        return preferred

    def preload_model(self, model_name: str) -> bool:
        """Send a minimal request to force Ollama to load a model into VRAM."""
        try:
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
                "keep_alive": "30m",
                "options": {"temperature": 0, "num_predict": 1},
            }
            resp = requests.post(f"{self.ollama_url}/api/chat", json=payload, timeout=60)
            if resp.status_code == 200:
                logger.info("[ModelPool] Preloaded model: %s", model_name)
                return True
        except Exception as e:
            logger.warning("[ModelPool] Preload failed for %s: %s", model_name, e)
        return False

    def get_model_state(self) -> Dict[str, Any]:
        """Return current model utilization snapshot."""
        with self._model_state_lock:
            return {k: {kk: vv for kk, vv in v.items()} for k, v in self._model_state.items()}

    # ── Task Verification (Backup for CrewAI) ──────────────────────────────

    def verify_task_completion(self, task_description: str, screenshot_b64: str = "",
                               actual_result: str = "") -> Dict[str, Any]:
        """
        Use vision model to verify if a task completed successfully.
        Sits idle until called by auditor as a backup confirmation.
        Returns: {"success": bool, "confidence": float, "reason": str, "suggestion": str}
        """
        if not screenshot_b64 and not actual_result:
            return {"success": False, "confidence": 0.0, "reason": "No visual or text evidence provided", "suggestion": "Retry the task"}

        # NO pre-check auto-pass — every verification goes through the LLM
        # to prevent false positives from fabricated agent responses.

        prompt = (
            f"You are a task verification expert. Your ONLY job is to verify if THIS specific task completed.\n\n"
            f"ORIGINAL TASK: {task_description}\n"
        )
        if actual_result:
            prompt += f"\nWHAT ACTUALLY HAPPENED: {actual_result}\n"
        prompt += (
            "\nDoes the actual result satisfy the original task? Ignore any other tasks or context.\n"
            "IMPORTANT: Do NOT assume success. If the actual result is vague, missing details, or does not "
            "clearly describe the specific actions asked for, mark as failure. "
            "For example: if the task asks to 'click calculator buttons 2+2=' but the actual result only says "
            "'typed text' without mentioning calculator interaction, that is a FAILURE. "
            "Respond in JSON format ONLY:\n"
            '{"success": true/false, "confidence": 0.0-1.0, "reason": "brief explanation", '
            '"suggestion": "retry/fix/abandon or empty string if success"}'
        )

        system = (
            "You are a strict task verifier. ONLY compare the ACTUAL RESULT against the ORIGINAL TASK. "
            "Do NOT reference any other tasks, websites, or unrelated topics. "
            "If the actual result clearly shows the task was done, say success=true."
        )

        try:
            model = self.select_model_for_task("vision", has_images=bool(screenshot_b64))
            if screenshot_b64:
                result = self.execute_sync(
                    prompt=prompt, system=system,
                    model=model, task_type="vision",
                    image_b64=screenshot_b64, timeout=30.0
                )
            else:
                result = self.execute_sync(
                    prompt=prompt, system=system,
                    model=model, task_type="fast",
                    timeout=15.0
                )

            # Parse JSON from response
            import re, json as _json
            m = re.search(r"\{.*\}", result, re.DOTALL)
            if m:
                parsed = _json.loads(m.group(0))
                return {
                    "success": parsed.get("success", False),
                    "confidence": float(parsed.get("confidence", 0.0)),
                    "reason": parsed.get("reason", ""),
                    "suggestion": parsed.get("suggestion", ""),
                }
        except Exception as e:
            logger.warning("[ModelPool] Verification failed: %s", e)

        return {"success": False, "confidence": 0.0, "reason": "Verification model unavailable", "suggestion": "Retry"}

    def select_model_for_task(self, task_type: str, has_images: bool = False) -> str:
        """Dynamically choose the best model based on modality, complexity, and availability."""
        if has_images or task_type.lower() in ("vision", "visual_grounding", "screen_inspect", "deep_scan"):
            # Vision: prefer qwen2.5vl:3b (fast), fallback to minicpm-v (precision), then moondream
            return self.get_available_model(ModelTier.VISION, fallbacks=[ModelTier.VISION_PRECISION, ModelTier.LIGHTWEIGHT])
        if task_type.lower() in ("vision_reason", "ocr", "text_extraction", "document_reading"):
            # Heavy vision (OCR, dense text): prefer minicpm-v, fallback to qwen2.5vl:3b
            return self.get_available_model(ModelTier.VISION_REASON, fallbacks=[ModelTier.VISION, ModelTier.LIGHTWEIGHT])
        if task_type.lower() in ("vision_precision", "visual_localization", "bounding_box", "complex_vision"):
            # Precision vision: prefer llama.cpp endpoint (Qwen2.5-VL-7B), fallback to minicpm-v
            return self.get_available_model(ModelTier.VISION_PRECISION, fallbacks=[ModelTier.VISION_REASON, ModelTier.LIGHTWEIGHT])
        if task_type.lower() in ("deep_reasoning", "complex_replan", "code_generation", "strategy"):
            # Reasoning: prefer llama3, fallback to fast model
            return self.get_available_model(ModelTier.REASONING, fallbacks=[ModelTier.FAST])
        # Default fast model with fallback to vision
        return self.get_available_model(ModelTier.FAST, fallbacks=[ModelTier.VISION])

    def _get_keep_alive(self, model_name: str) -> str:
        """VRAM Management: keep fast model warm, unload heavy models when idle based on hardware profile."""
        if self._host_profile:
            if model_name == ModelTier.FAST:
                return self._host_profile.vram_keep_alive_fast
            elif model_name == ModelTier.VISION:
                return self._host_profile.vram_keep_alive_specialist
            elif model_name == ModelTier.VISION_REASON:
                return "5m"  # Keep minicpm-v warm for OCR tasks
            return "2m"
        if model_name == ModelTier.FAST:
            return "30m"  # Keep warm
        if model_name == ModelTier.VISION:
            return "5m"   # Unload after 5m idle to free VRAM
        if model_name == ModelTier.VISION_REASON:
            return "5m"   # Keep minicpm-v warm for OCR tasks
        return "2m"       # Heavy models unload quickly

    def submit_query_async(
        self,
        prompt: str,
        system: str = "You are an autonomous AI engine.",
        model: Optional[str] = None,
        task_type: str = "fast",
        image_b64: Optional[str] = None,
        callback: Optional[Callable[[str, str], None]] = None,
        timeout: float = 30.0,
    ) -> str:
        """
        Non-blocking query submission. Returns a ticket_id immediately.
        Response will be placed in the outgoing mailbox and optional callback invoked.
        """
        ticket_id = f"ticket_{uuid.uuid4().hex[:8]}"
        chosen_model = model or self.select_model_for_task(task_type, has_images=bool(image_b64))

        event = threading.Event()
        with self._mailbox_lock:
            self._mailbox[ticket_id] = {
                "ticket_id": ticket_id,
                "status": "PENDING",
                "model": chosen_model,
                "response": None,
                "error": None,
                "event": event,
                "created_at": time.time(),
                "callback": callback,
                "timeout": timeout,
            }

        job = {
            "ticket_id": ticket_id,
            "prompt": prompt,
            "system": system,
            "model": chosen_model,
            "image_b64": image_b64,
            "timeout": timeout,
        }
        self._request_queue.put(job)
        logger.debug("[ModelPool] Submitted %s to queue (model: %s)", ticket_id, chosen_model)
        return ticket_id

    async def execute_async(
        self,
        prompt: str,
        system: str = "You are an autonomous AI engine.",
        model: Optional[str] = None,
        task_type: str = "fast",
        image_b64: Optional[str] = None,
        timeout: float = 30.0,
    ) -> str:
        """Async-native execution that awaits the specific ticket without blocking other coroutines."""
        ticket_id = self.submit_query_async(
            prompt=prompt,
            system=system,
            model=model,
            task_type=task_type,
            image_b64=image_b64,
            timeout=timeout,
        )

        loop = asyncio.get_running_loop()
        start = time.time()
        while time.time() - start < timeout:
            with self._mailbox_lock:
                entry = self._mailbox.get(ticket_id)
                if entry and entry["status"] in ("COMPLETED", "FAILED"):
                    if entry["status"] == "COMPLETED":
                        return entry["response"]
                    raise RuntimeError(entry.get("error", "Model execution failed"))
            await asyncio.sleep(0.05)

        raise TimeoutError(f"Model pool query {ticket_id} timed out after {timeout}s")

    def execute_sync(
        self,
        prompt: str,
        system: str = "You are an autonomous AI engine.",
        model: Optional[str] = None,
        task_type: str = "fast",
        image_b64: Optional[str] = None,
        timeout: float = 30.0,
    ) -> str:
        """Synchronous convenience wrapper that waits for the specific ticket."""
        ticket_id = self.submit_query_async(
            prompt=prompt,
            system=system,
            model=model,
            task_type=task_type,
            image_b64=image_b64,
            timeout=timeout,
        )

        with self._mailbox_lock:
            event = self._mailbox[ticket_id]["event"]

        signaled = event.wait(timeout=timeout)
        if not signaled:
            raise TimeoutError(f"Model pool query {ticket_id} timed out after {timeout}s")

        with self._mailbox_lock:
            entry = self._mailbox[ticket_id]
            if entry["status"] == "COMPLETED":
                return entry["response"]
            raise RuntimeError(entry.get("error", "Model execution failed"))

    def _worker_loop(self) -> None:
        """Worker thread loop to process jobs and deliver directly to the outgoing mailbox."""
        while self._running:
            try:
                job = self._request_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            ticket_id = job["ticket_id"]
            model = job["model"]
            prompt = job["prompt"]
            system = job["system"]
            image_b64 = job.get("image_b64")
            timeout = job.get("timeout", 30.0)

            self._mark_model_busy(model)
            try:
                # Detect if model is an HTTP endpoint (llama.cpp) or Ollama model
                is_http_endpoint = model.startswith("http://") or model.startswith("https://")

                if is_http_endpoint:
                    # llama.cpp OpenAI-compatible endpoint
                    content = self._call_http_endpoint(model, prompt, system, image_b64, timeout)
                    self._deliver_result(ticket_id, content, error=None)
                else:
                    # Ollama endpoint
                    keep_alive = self._get_keep_alive(model)
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt, **({"images": [image_b64]} if image_b64 else {})},
                        ],
                        "stream": False,
                        "keep_alive": keep_alive,
                        "options": {"temperature": 0.1},
                    }

                    try:
                        resp = requests.post(f"{self.ollama_url}/api/chat", json=payload, timeout=timeout)
                        if resp.status_code == 200:
                            content = resp.json().get("message", {}).get("content", "").strip()
                            self._deliver_result(ticket_id, content, error=None)
                        else:
                            self._deliver_result(ticket_id, "", error=f"HTTP {resp.status_code}: {resp.text[:100]}")
                    except Exception as e:
                        self._deliver_result(ticket_id, "", error=str(e))
            finally:
                self._mark_model_free(model)
                self._request_queue.task_done()

    def _call_http_endpoint(self, endpoint: str, prompt: str, system: str, image_b64: Optional[str], timeout: float) -> str:
        """Call llama.cpp OpenAI-compatible endpoint."""
        messages = [{"role": "system", "content": system}]

        if image_b64:
            # Vision model - include image in message
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                ]
            })
        else:
            messages.append({"role": "user", "content": prompt})

        payload = {
            "model": "default",
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 2048,
        }

        # Ensure endpoint points to chat completions
        if not endpoint.endswith("/v1/chat/completions"):
            if endpoint.endswith("/v1"):
                endpoint = endpoint + "/chat/completions"
            elif not endpoint.endswith("/chat/completions"):
                endpoint = endpoint.rstrip("/") + "/v1/chat/completions"

        resp = requests.post(endpoint, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()

    def _deliver_result(self, ticket_id: str, response: str, error: Optional[str] = None) -> None:
        """Deliver completed result to the mailbox and signal waiting agent."""
        callback = None
        with self._mailbox_lock:
            if ticket_id in self._mailbox:
                entry = self._mailbox[ticket_id]
                entry["status"] = "COMPLETED" if error is None else "FAILED"
                entry["response"] = response
                entry["error"] = error
                entry["delivered_at"] = time.time()
                callback = entry.get("callback")
                entry["event"].set()

        if callback:
            try:
                callback(ticket_id, response)
            except Exception as e:
                logger.debug("Callback for %s failed: %s", ticket_id, e)
        logger.debug("[ModelPool] Delivered result for %s (status: %s)", ticket_id, "SUCCESS" if not error else "FAILED")
