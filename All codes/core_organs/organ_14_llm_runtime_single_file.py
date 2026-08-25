"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 14
Name: Llm Runtime Single File

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Llm Runtime Single File]
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
Dependencies: urllib.request, enum, pathlib, __future__, typing...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: organ_14_llm_runtime_single_file.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
Organ 14 — LLM Runtime (Hojaiga Automation OS)
================================================
Single-file consolidated implementation.

Authority chain: Constitution -> Law Book -> Policy Manual ->
Master Architecture Blueprint -> Organ Specification ->
Organ_14_LLM_Runtime.md

Scope (per Organ_14_LLM_Runtime.md, Section 1):
    LLM Gateway, Provider Manager, Runtime Manager, Model Registry,
    Model Loader, Inference Engine, Prompt Dispatcher, Token Stream
    Manager, GPU/CPU Resource Management, VRAM/KV Cache Management,
    Model Download/Import, Model Verification, Provider Abstraction,
    Brain <-> Runtime Socket, Prompt/Response Pipelines, Security,
    Health/Recovery, Fallback/Compatibility.

Strict negative constraints (Section 1.2):
    This organ performs NO reasoning, planning, tool selection, task
    decision making, or autonomous model selection. It only executes
    inference requests for the explicit model IDs supplied by the
    Brain via the documented socket contract.
"""


import abc
import contextlib
import dataclasses
import enum
import hashlib
import json
import logging
import os
import queue
import shutil
import threading
import time
import uuid
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

# ═════════════════════════════════════════════════════════════════════════
# SECTION 0 — LOGGING (Append-only, Law Book Foundational Law 7)
# ═════════════════════════════════════════════════════════════════════════

logger = logging.getLogger("hojaiga.organ14.llm_runtime")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | organ14.llm_runtime | %(message)s")
    )
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ═════════════════════════════════════════════════════════════════════════
# SECTION 1 — DATA CONTRACTS
# ═════════════════════════════════════════════════════════════════════════

class RuntimeState(enum.Enum):
    UNLOADED = "UNLOADED"
    LOADING = "LOADING"
    LOADED_IDLE = "LOADED_IDLE"
    BUSY_INFERENCE = "BUSY_INFERENCE"
    UNLOADING = "UNLOADING"
    FAULTED = "FAULTED"


class RequestStatus(enum.Enum):
    QUEUED = "QUEUED"
    DISPATCHED = "DISPATCHED"
    STREAMING = "STREAMING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ProviderKind(enum.Enum):
    LLAMA_CPP = "llama.cpp"
    CLOUD_FALLBACK = "cloud_fallback"
    OPENROUTER = "openrouter"
    GROQ = "groq"
    NVIDIA = "nvidia"


@dataclasses.dataclass(frozen=True)
class ModelDescriptor:
    """Registry entry for a single model artifact."""
    model_id: str
    display_name: str
    file_path: str
    sha256: str
    quantization: str
    context_window: int
    provider: ProviderKind
    parameters_b: float
    gpu_layers: int = 0
    signature: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d["provider"] = self.provider.value
        return d


@dataclasses.dataclass(frozen=True)
class InferenceRequest:
    """Contract: Brain -> LLM Gateway (SOCK_LLM_BRAIN)."""
    request_id: str
    model_id: str
    prompt: str
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9
    stop_sequences: tuple = ()
    stream: bool = True
    correlation_id: Optional[str] = None
    issued_at: float = dataclasses.field(default_factory=time.time)

    @staticmethod
    def new(model_id: str, prompt: str, **kwargs: Any) -> "InferenceRequest":
        return InferenceRequest(request_id=_new_id("req"), model_id=model_id, prompt=prompt, **kwargs)


@dataclasses.dataclass(frozen=True)
class TokenChunk:
    """A single unit of the response stream."""
    request_id: str
    token_text: str
    token_index: int
    is_final: bool = False
    finish_reason: Optional[str] = None


@dataclasses.dataclass(frozen=True)
class InferenceResult:
    """Contract: LLM Gateway -> Brain (final aggregate response)."""
    request_id: str
    model_id: str
    status: RequestStatus
    text: str
    tokens_generated: int
    ttft_ms: float
    total_ms: float
    tokens_per_second: float
    error: Optional[str] = None


@dataclasses.dataclass
class ResourceSnapshot:
    vram_total_mb: int
    vram_used_mb: int
    ram_total_mb: int
    ram_used_mb: int
    kv_cache_mb: int
    active_model_id: Optional[str]
    timestamp: float = dataclasses.field(default_factory=time.time)


# ═════════════════════════════════════════════════════════════════════════
# SECTION 2 — EXCEPTIONS
# ═════════════════════════════════════════════════════════════════════════

class LLMRuntimeError(Exception):
    """Base error for the LLM Runtime organ."""


class ModelNotFoundError(LLMRuntimeError):
    pass


class ModelIntegrityError(LLMRuntimeError):
    pass


class VRAMAllocationError(LLMRuntimeError):
    pass


class ProviderFaultError(LLMRuntimeError):
    pass


class RequestCancelledError(LLMRuntimeError):
    pass


# ═════════════════════════════════════════════════════════════════════════
# SECTION 3 — PROVIDER ABSTRACTION (IModelProvider contract)
# ═════════════════════════════════════════════════════════════════════════

class IModelProvider(abc.ABC):
    """Stable provider contract. New backends implement this only."""

    @abc.abstractmethod
    def initialize(self, config: Dict[str, Any]) -> None: ...

    @abc.abstractmethod
    def load_model(self, descriptor: ModelDescriptor) -> None: ...

    @abc.abstractmethod
    def unload_model(self) -> None: ...

    @abc.abstractmethod
    def execute_inference(
        self, request: InferenceRequest, token_callback: Callable[[TokenChunk], None]
    ) -> InferenceResult: ...

    @abc.abstractmethod
    def interrupt(self, request_id: str) -> None: ...

    @property
    @abc.abstractmethod
    def name(self) -> str: ...


class LlamaCppProvider(IModelProvider):
    """
    Provider binding for llama.cpp local inference.

    This binds to a llama.cpp server/library at the process boundary. The
    actual token generation call is delegated to `_generate` which callers
    may monkeypatch/replace with a real llama.cpp binding (e.g. llama-cpp-python)
    without touching any other component in this organ.
    """

    def __init__(self) -> None:
        self._active_descriptor: Optional[ModelDescriptor] = None
        self._cancelled: set = set()
        self._lock = threading.Lock()
        self._initialized = False

    @property
    def name(self) -> str:
        return ProviderKind.LLAMA_CPP.value

    def initialize(self, config: Dict[str, Any]) -> None:
        self._config = dict(config)
        self._initialized = True
        logger.info("LlamaCppProvider initialized with config keys=%s", list(config.keys()))

    def load_model(self, descriptor: ModelDescriptor) -> None:
        if not self._initialized:
            raise ProviderFaultError("Provider not initialized before load_model")
        if not os.path.exists(descriptor.file_path):
            raise ModelNotFoundError(f"Model weights missing on disk: {descriptor.file_path}")
        with self._lock:
            self._active_descriptor = descriptor
        logger.info("LlamaCppProvider loaded model_id=%s gpu_layers=%d", descriptor.model_id, descriptor.gpu_layers)

    def unload_model(self) -> None:
        with self._lock:
            self._active_descriptor = None
        logger.info("LlamaCppProvider unloaded active model")

    def interrupt(self, request_id: str) -> None:
        self._cancelled.add(request_id)

    def execute_inference(
        self, request: InferenceRequest, token_callback: Callable[[TokenChunk], None]
    ) -> InferenceResult:
        if self._active_descriptor is None or self._active_descriptor.model_id != request.model_id:
            raise ProviderFaultError(
                f"Requested model_id={request.model_id} is not the currently loaded model"
            )
        start = time.time()
        first_token_time: Optional[float] = None
        generated_text: List[str] = []
        try:
            for index, token_text in enumerate(self._generate(request)):
                if request.request_id in self._cancelled:
                    self._cancelled.discard(request.request_id)
                    raise RequestCancelledError(request.request_id)
                if first_token_time is None:
                    first_token_time = time.time()
                generated_text.append(token_text)
                token_callback(
                    TokenChunk(
                        request_id=request.request_id,
                        token_text=token_text,
                        token_index=index,
                        is_final=False,
                    )
                )
            end = time.time()
            final_text = "".join(generated_text)
            token_callback(
                TokenChunk(
                    request_id=request.request_id,
                    token_text="",
                    token_index=len(generated_text),
                    is_final=True,
                    finish_reason="stop",
                )
            )
            ttft_ms = ((first_token_time or end) - start) * 1000.0
            total_ms = (end - start) * 1000.0
            tps = (len(generated_text) / total_ms * 1000.0) if total_ms > 0 else 0.0
            return InferenceResult(
                request_id=request.request_id,
                model_id=request.model_id,
                status=RequestStatus.COMPLETED,
                text=final_text,
                tokens_generated=len(generated_text),
                ttft_ms=ttft_ms,
                total_ms=total_ms,
                tokens_per_second=tps,
            )
        except RequestCancelledError:
            return InferenceResult(
                request_id=request.request_id,
                model_id=request.model_id,
                status=RequestStatus.CANCELLED,
                text="".join(generated_text),
                tokens_generated=len(generated_text),
                ttft_ms=0.0,
                total_ms=(time.time() - start) * 1000.0,
                tokens_per_second=0.0,
                error="cancelled_by_caller",
            )

    def _generate(self, request: InferenceRequest) -> Iterator[str]:
        """
        Deterministic-shape token generator bound to the loaded model.
        Replace this method (or the provider entirely) to bind a real
        llama.cpp inference call; the rest of the organ is provider-agnostic.
        """
        remaining = request.max_tokens
        seed_text = request.prompt.strip().split()
        cursor = 0
        while remaining > 0:
            word = seed_text[cursor % len(seed_text)] if seed_text else "..."
            cursor += 1
            remaining -= 1
            token = f"{word} "
            if any(stop and stop in token for stop in request.stop_sequences):
                break
            yield token
            time.sleep(0)  # cooperative yield point, no artificial latency


class CloudFallbackProvider(IModelProvider):
    """Fallback provider used only when the local provider faults and a
    fallback model/provider pair is explicitly configured (Section 25)."""

    def __init__(self) -> None:
        self._active_descriptor: Optional[ModelDescriptor] = None
        self._initialized = False

    @property
    def name(self) -> str:
        return ProviderKind.CLOUD_FALLBACK.value

    def initialize(self, config: Dict[str, Any]) -> None:
        self._config = dict(config)
        self._initialized = True

    def load_model(self, descriptor: ModelDescriptor) -> None:
        self._active_descriptor = descriptor

    def unload_model(self) -> None:
        self._active_descriptor = None

    def interrupt(self, request_id: str) -> None:
        return

    def execute_inference(
        self, request: InferenceRequest, token_callback: Callable[[TokenChunk], None]
    ) -> InferenceResult:
        raise ProviderFaultError(
            "CloudFallbackProvider requires an explicit external binding; none configured."
        )




class HttpStreamProvider(IModelProvider):
    def __init__(self, endpoint: str, auth_header_prefix: str, env_var: str):
        self.endpoint = endpoint
        self.auth_header_prefix = auth_header_prefix
        self.env_var = env_var
        self._active_descriptor: Optional[ModelDescriptor] = None
        self._cancelled: set = set()
        self._initialized = False

    def initialize(self, config: Dict[str, Any]) -> None:
        self._config = dict(config)
        self._initialized = True

    def load_model(self, descriptor: ModelDescriptor) -> None:
        self._active_descriptor = descriptor

    def unload_model(self) -> None:
        self._active_descriptor = None

    def interrupt(self, request_id: str) -> None:
        self._cancelled.add(request_id)

    def execute_inference(
        self, request: InferenceRequest, token_callback: Callable[[TokenChunk], None]
    ) -> InferenceResult:
        if not self._active_descriptor:
            raise ProviderFaultError("No active model loaded")

        api_key = os.environ.get(self.env_var)
        if not api_key:
            raise ProviderFaultError(f"Missing API key environment variable: {self.env_var}")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"{self.auth_header_prefix} {api_key}",
            "User-Agent": "Antigravity/1.0"
        }

        payload = {
            "model": self._active_descriptor.file_path,  # use file_path to store model name
            "messages": [{"role": "user", "content": request.prompt}],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": True
        }
        if request.stop_sequences:
            payload["stop"] = list(request.stop_sequences)

        req = urllib.request.Request(self.endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")

        start = time.time()
        first_token_time: Optional[float] = None
        generated_text: List[str] = []
        token_index = 0

        try:
            with urllib.request.urlopen(req) as response:
                for line in response:
                    if request.request_id in self._cancelled:
                        self._cancelled.discard(request.request_id)
                        raise RequestCancelledError(request.request_id)

                    line = line.decode("utf-8").strip()
                    if not line or not line.startswith("data: "):
                        continue
                    
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                        
                    try:
                        data = json.loads(data_str)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        
                        if content:
                            if first_token_time is None:
                                first_token_time = time.time()
                                
                            generated_text.append(content)
                            token_callback(
                                TokenChunk(
                                    request_id=request.request_id,
                                    token_text=content,
                                    token_index=token_index,
                                    is_final=False,
                                )
                            )
                            token_index += 1
                    except Exception:
                        pass
                        
            end = time.time()
            final_text = "".join(generated_text)
            token_callback(
                TokenChunk(
                    request_id=request.request_id,
                    token_text="",
                    token_index=token_index,
                    is_final=True,
                    finish_reason="stop",
                )
            )
            ttft_ms = ((first_token_time or end) - start) * 1000.0
            total_ms = (end - start) * 1000.0
            tps = (len(generated_text) / total_ms * 1000.0) if total_ms > 0 else 0.0
            return InferenceResult(
                request_id=request.request_id,
                model_id=request.model_id,
                status=RequestStatus.COMPLETED,
                text=final_text,
                tokens_generated=len(generated_text),
                ttft_ms=ttft_ms,
                total_ms=total_ms,
                tokens_per_second=tps,
            )
            
        except RequestCancelledError:
            return InferenceResult(
                request_id=request.request_id,
                model_id=request.model_id,
                status=RequestStatus.CANCELLED,
                text="".join(generated_text),
                tokens_generated=len(generated_text),
                ttft_ms=0.0,
                total_ms=(time.time() - start) * 1000.0,
                tokens_per_second=0.0,
                error="cancelled_by_caller",
            )
        except Exception as e:
            raise ProviderFaultError(f"HTTP stream failed: {e}")

class OpenRouterProvider(HttpStreamProvider):
    @property
    def name(self) -> str:
        return ProviderKind.OPENROUTER.value
    def __init__(self):
        super().__init__("https://openrouter.ai/api/v1/chat/completions", "Bearer", "OPENROUTER_API_KEY_1")

class GroqProvider(HttpStreamProvider):
    @property
    def name(self) -> str:
        return ProviderKind.GROQ.value
    def __init__(self):
        super().__init__("https://api.groq.com/openai/v1/chat/completions", "Bearer", "GROQ_API_KEY_1")

class NvidiaProvider(HttpStreamProvider):
    @property
    def name(self) -> str:
        return ProviderKind.NVIDIA.value
    def __init__(self):
        super().__init__("https://integrate.api.nvidia.com/v1/chat/completions", "Bearer", "NVIDIA_API_KEY_1")

# ═════════════════════════════════════════════════════════════════════════
# SECTION 4 — MODEL REGISTRY & VERIFICATION
# ═════════════════════════════════════════════════════════════════════════

class ModelVerifier:
    """SHA-256 and structural integrity checks (Section 1.1 — Model Integrity)."""

    GGUF_MAGIC = b"GGUF"

    @staticmethod
    def compute_sha256(file_path: str, chunk_size: int = 8 * 1024 * 1024) -> str:
        digest = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def verify(cls, descriptor: ModelDescriptor) -> None:
        if descriptor.provider in (ProviderKind.OPENROUTER, ProviderKind.GROQ, ProviderKind.NVIDIA, ProviderKind.CLOUD_FALLBACK):
            return
        if not os.path.exists(descriptor.file_path):
            raise ModelNotFoundError(f"Missing weight file: {descriptor.file_path}")
        with open(descriptor.file_path, "rb") as f:
            header = f.read(4)
        if header != cls.GGUF_MAGIC:
            raise ModelIntegrityError(
                f"Structural header mismatch for {descriptor.model_id}: expected GGUF magic bytes"
            )
        actual = cls.compute_sha256(descriptor.file_path)
        if actual != descriptor.sha256:
            raise ModelIntegrityError(
                f"SHA-256 mismatch for {descriptor.model_id}: expected={descriptor.sha256} actual={actual}"
            )


class ModelRegistry:
    """Registry surface — enforces checksum verification before registration."""

    def __init__(self, verify_on_register: bool = True) -> None:
        self._models: Dict[str, ModelDescriptor] = {}
        self._lock = threading.RLock()
        self._verify_on_register = verify_on_register

    def register(self, descriptor: ModelDescriptor) -> None:
        if self._verify_on_register:
            ModelVerifier.verify(descriptor)
        with self._lock:
            self._models[descriptor.model_id] = descriptor
        logger.info("Model registered: %s (%s, %.1fB params)", descriptor.model_id,
                    descriptor.quantization, descriptor.parameters_b)

    def unregister(self, model_id: str) -> None:
        with self._lock:
            self._models.pop(model_id, None)

    def get(self, model_id: str) -> ModelDescriptor:
        with self._lock:
            descriptor = self._models.get(model_id)
        if descriptor is None:
            raise ModelNotFoundError(f"No such registered model_id={model_id}")
        return descriptor

    def list_models(self) -> List[ModelDescriptor]:
        with self._lock:
            return list(self._models.values())

    def import_from_manifest(self, manifest_path: str) -> None:
        """Bulk import from a JSON manifest (Model Download/Import)."""
        with open(manifest_path, "r", encoding="utf-8") as f:
            entries = json.load(f)
        for entry in entries:
            descriptor = ModelDescriptor(
                model_id=entry["model_id"],
                display_name=entry["display_name"],
                file_path=entry["file_path"],
                sha256=entry["sha256"],
                quantization=entry["quantization"],
                context_window=int(entry["context_window"]),
                provider=ProviderKind(entry.get("provider", ProviderKind.LLAMA_CPP.value)),
                parameters_b=float(entry["parameters_b"]),
                gpu_layers=int(entry.get("gpu_layers", 0)),
                signature=entry.get("signature"),
            )
            self.register(descriptor)


class ModelDownloader:
    """Model import from a local staging path onto the managed model store."""

    def __init__(self, model_store_dir: str) -> None:
        self.model_store_dir = Path(model_store_dir)
        self.model_store_dir.mkdir(parents=True, exist_ok=True)

    def import_local_file(self, source_path: str, model_id: str) -> str:
        source = Path(source_path)
        if not source.exists():
            raise ModelNotFoundError(f"Import source does not exist: {source_path}")
        destination = self.model_store_dir / f"{model_id}.gguf"
        shutil.copy2(source, destination)
        logger.info("Imported model artifact %s -> %s", source_path, destination)
        return str(destination)


# ═════════════════════════════════════════════════════════════════════════
# SECTION 5 — RESOURCE MANAGEMENT (GPU/CPU/VRAM/KV Cache)
# ═════════════════════════════════════════════════════════════════════════

class ResourceManager:
    """
    Owns VRAM/RAM bookkeeping for the LLM Runtime organ only.

    NOTE: Per Master_Architecture_Blueprint, GPU/VRAM top-level ownership
    resides with the Brain organ; this manager tracks the runtime's own
    allocation footprint and enforces the configured ceiling so that the
    runtime never exceeds hardware budget on the target machine
    (RTX 3050, 4GB VRAM). It reports telemetry outward; it does not claim
    exclusive system-wide VRAM ownership.
    """

    def __init__(self, max_vram_mb: int, max_ram_mb: int) -> None:
        self.max_vram_mb = max_vram_mb
        self.max_ram_mb = max_ram_mb
        self._vram_used_mb = 0
        self._ram_used_mb = 0
        self._kv_cache_mb = 0
        self._active_model_id: Optional[str] = None
        self._lock = threading.RLock()

    def estimate_vram_footprint(self, descriptor: ModelDescriptor) -> int:
        if descriptor.provider in (ProviderKind.OPENROUTER, ProviderKind.GROQ, ProviderKind.NVIDIA, ProviderKind.CLOUD_FALLBACK):
            return 0
        bytes_per_param = {"Q4_K_M": 0.6, "Q5_K_M": 0.7, "Q8_0": 1.05, "F16": 2.1}.get(
            descriptor.quantization, 0.75
        )
        weight_mb = int(descriptor.parameters_b * 1000 * bytes_per_param)
        kv_mb = int(descriptor.context_window * 0.002 * max(descriptor.gpu_layers, 1))
        return weight_mb + kv_mb

    def allocate_for_model(self, descriptor: ModelDescriptor) -> None:
        needed = self.estimate_vram_footprint(descriptor)
        with self._lock:
            if needed > self.max_vram_mb:
                raise VRAMAllocationError(
                    f"Model {descriptor.model_id} requires ~{needed}MB VRAM, "
                    f"exceeds ceiling {self.max_vram_mb}MB"
                )
            self._vram_used_mb = needed
            self._kv_cache_mb = int(needed * 0.15)
            self._active_model_id = descriptor.model_id
        logger.info("VRAM allocated: %dMB for model_id=%s (ceiling=%dMB)",
                    needed, descriptor.model_id, self.max_vram_mb)

    def release(self) -> None:
        with self._lock:
            self._vram_used_mb = 0
            self._kv_cache_mb = 0
            self._active_model_id = None
        logger.info("VRAM released; GPU memory freed")

    def snapshot(self) -> ResourceSnapshot:
        with self._lock:
            return ResourceSnapshot(
                vram_total_mb=self.max_vram_mb,
                vram_used_mb=self._vram_used_mb,
                ram_total_mb=self.max_ram_mb,
                ram_used_mb=self._ram_used_mb,
                kv_cache_mb=self._kv_cache_mb,
                active_model_id=self._active_model_id,
            )


# ═════════════════════════════════════════════════════════════════════════
# SECTION 6 — RUNTIME MANAGER (lifecycle state machine)
# ═════════════════════════════════════════════════════════════════════════

class RuntimeManager:
    """
    Owns the load/unload lifecycle state machine for the active model.
    State transitions:
        UNLOADED -> LOADING -> LOADED_IDLE -> BUSY_INFERENCE -> LOADED_IDLE
        LOADED_IDLE -> UNLOADING -> UNLOADED
        (any) -> FAULTED  on unrecoverable provider error
    """

    _VALID_TRANSITIONS = {
        RuntimeState.UNLOADED: {RuntimeState.LOADING},
        RuntimeState.LOADING: {RuntimeState.LOADED_IDLE, RuntimeState.FAULTED},
        RuntimeState.LOADED_IDLE: {RuntimeState.BUSY_INFERENCE, RuntimeState.UNLOADING, RuntimeState.FAULTED},
        RuntimeState.BUSY_INFERENCE: {RuntimeState.LOADED_IDLE, RuntimeState.FAULTED},
        RuntimeState.UNLOADING: {RuntimeState.UNLOADED, RuntimeState.FAULTED},
        RuntimeState.FAULTED: {RuntimeState.UNLOADED},
    }

    def __init__(
        self,
        registry: ModelRegistry,
        resource_manager: ResourceManager,
        provider_factory: Callable[[ProviderKind], IModelProvider],
        idle_grace_period_s: float = 60.0,
    ) -> None:
        self._registry = registry
        self._resources = resource_manager
        self._provider_factory = provider_factory
        self._idle_grace_period_s = idle_grace_period_s
        self._state = RuntimeState.UNLOADED
        self._active_provider: Optional[IModelProvider] = None
        self._active_model_id: Optional[str] = None
        self._lock = threading.RLock()
        self._idle_timer: Optional[threading.Timer] = None

    @property
    def state(self) -> RuntimeState:
        return self._state

    @property
    def active_model_id(self) -> Optional[str]:
        return self._active_model_id

    def _transition(self, target: RuntimeState) -> None:
        allowed = self._VALID_TRANSITIONS.get(self._state, set())
        if target not in allowed:
            raise LLMRuntimeError(f"Illegal state transition {self._state} -> {target}")
        logger.info("RuntimeManager state: %s -> %s", self._state.value, target.value)
        self._state = target

    def _cancel_idle_timer(self) -> None:
        if self._idle_timer is not None:
            self._idle_timer.cancel()
            self._idle_timer = None

    def _arm_idle_timer(self) -> None:
        self._cancel_idle_timer()
        self._idle_timer = threading.Timer(self._idle_grace_period_s, self._on_idle_timeout)
        self._idle_timer.daemon = True
        self._idle_timer.start()

    def _on_idle_timeout(self) -> None:
        with self._lock:
            if self._state == RuntimeState.LOADED_IDLE:
                logger.info("Idle grace period elapsed; auto-unloading model %s", self._active_model_id)
                self._unload_locked()

    def load_model(self, model_id: str) -> IModelProvider:
        with self._lock:
            if self._active_model_id == model_id and self._state == RuntimeState.LOADED_IDLE:
                self._arm_idle_timer()
                return self._active_provider  # type: ignore[return-value]
            if self._state not in (RuntimeState.UNLOADED, RuntimeState.LOADED_IDLE):
                raise LLMRuntimeError(f"Cannot load model while state={self._state.value}")
            if self._state == RuntimeState.LOADED_IDLE:
                self._unload_locked()
            descriptor = self._registry.get(model_id)
            self._transition(RuntimeState.LOADING)
            try:
                self._resources.allocate_for_model(descriptor)
                provider = self._provider_factory(descriptor.provider)
                provider.initialize({"model_store": str(Path(descriptor.file_path).parent)})
                provider.load_model(descriptor)
            except Exception as exc:
                self._transition(RuntimeState.FAULTED)
                self._resources.release()
                logger.error("Model load failed for %s: %s", model_id, exc)
                raise
            self._active_provider = provider
            self._active_model_id = model_id
            self._transition(RuntimeState.LOADED_IDLE)
            self._arm_idle_timer()
            return provider

    def begin_inference(self) -> None:
        with self._lock:
            self._cancel_idle_timer()
            self._transition(RuntimeState.BUSY_INFERENCE)

    def end_inference(self, faulted: bool = False) -> None:
        with self._lock:
            self._transition(RuntimeState.FAULTED if faulted else RuntimeState.LOADED_IDLE)
            if not faulted:
                self._arm_idle_timer()

    def _unload_locked(self) -> None:
        if self._active_provider is None:
            self._transition(RuntimeState.UNLOADED) if self._state != RuntimeState.UNLOADED else None
            return
        self._cancel_idle_timer()
        self._transition(RuntimeState.UNLOADING)
        try:
            self._active_provider.unload_model()
        finally:
            self._resources.release()
            self._active_provider = None
            self._active_model_id = None
            self._transition(RuntimeState.UNLOADED)

    def unload_model(self) -> None:
        with self._lock:
            self._unload_locked()

    def recover_from_fault(self) -> None:
        with self._lock:
            if self._state != RuntimeState.FAULTED:
                return
            self._resources.release()
            self._active_provider = None
            self._active_model_id = None
            self._transition(RuntimeState.UNLOADED)
            logger.warning("RuntimeManager recovered from FAULTED -> UNLOADED")


# ═════════════════════════════════════════════════════════════════════════
# SECTION 7 — PROVIDER MANAGER
# ═════════════════════════════════════════════════════════════════════════

class ProviderManager:
    """Execution broker: translates gateway requests into provider calls,
    applies fallback policy on provider faults."""

    def __init__(
        self,
        registry: ModelRegistry,
        runtime_manager: RuntimeManager,
        fallback_model_id: Optional[str] = None,
    ) -> None:
        self._registry = registry
        self._runtime = runtime_manager
        self._fallback_model_id = fallback_model_id

    def dispatch(
        self, request: InferenceRequest, token_callback: Callable[[TokenChunk], None]
    ) -> InferenceResult:
        provider = self._runtime.load_model(request.model_id)
        self._runtime.begin_inference()
        try:
            result = provider.execute_inference(request, token_callback)
            self._runtime.end_inference(faulted=(result.status == RequestStatus.FAILED))
            return result
        except RequestCancelledError:
            self._runtime.end_inference(faulted=False)
            raise
        except LLMRuntimeError as primary_error:
            self._runtime.end_inference(faulted=True)
            self._runtime.recover_from_fault()
            if self._fallback_model_id and self._fallback_model_id != request.model_id:
                logger.warning(
                    "Primary provider faulted (%s); attempting fallback model_id=%s",
                    primary_error, self._fallback_model_id,
                )
                fallback_request = dataclasses.replace(request, model_id=self._fallback_model_id)
                fallback_provider = self._runtime.load_model(fallback_request.model_id)
                self._runtime.begin_inference()
                try:
                    result = fallback_provider.execute_inference(fallback_request, token_callback)
                    self._runtime.end_inference(faulted=(result.status == RequestStatus.FAILED))
                    return result
                except LLMRuntimeError as fallback_error:
                    self._runtime.end_inference(faulted=True)
                    self._runtime.recover_from_fault()
                    raise ProviderFaultError(
                        f"Primary and fallback providers both failed: "
                        f"primary={primary_error}, fallback={fallback_error}"
                    ) from fallback_error
            raise

    def interrupt(self, model_id: str, request_id: str) -> None:
        if self._runtime.active_model_id == model_id and self._runtime._active_provider:  # noqa: SLF001
            self._runtime._active_provider.interrupt(request_id)  # noqa: SLF001


# ═════════════════════════════════════════════════════════════════════════
# SECTION 8 — TOKEN STREAM MANAGER & PROMPT DISPATCHER
# ═════════════════════════════════════════════════════════════════════════

class TokenStreamManager:
    """Zero-copy-oriented broker between provider callbacks and consumers.
    Each request gets its own bounded queue; consumers pull via iterator."""

    def __init__(self, max_queue_size: int = 4096) -> None:
        self._streams: Dict[str, "queue.Queue[Optional[TokenChunk]]"] = {}
        self._max_queue_size = max_queue_size
        self._lock = threading.Lock()

    def open_stream(self, request_id: str) -> None:
        with self._lock:
            self._streams[request_id] = queue.Queue(maxsize=self._max_queue_size)

    def push(self, chunk: TokenChunk) -> None:
        stream = self._streams.get(chunk.request_id)
        if stream is None:
            return
        stream.put(chunk)
        if chunk.is_final:
            stream.put(None)

    def consume(self, request_id: str, timeout_s: float = 30.0) -> Iterator[TokenChunk]:
        stream = self._streams.get(request_id)
        if stream is None:
            raise LLMRuntimeError(f"No open stream for request_id={request_id}")
        while True:
            item = stream.get(timeout=timeout_s)
            if item is None:
                break
            yield item
        self.close_stream(request_id)

    def close_stream(self, request_id: str) -> None:
        with self._lock:
            self._streams.pop(request_id, None)


class PromptDispatcher:
    """Prompt assembly, bounds validation, and enqueue-for-execution."""

    def __init__(self, max_prompt_chars: int = 200_000, max_tokens_ceiling: int = 8192) -> None:
        self._max_prompt_chars = max_prompt_chars
        self._max_tokens_ceiling = max_tokens_ceiling

    def validate(self, request: InferenceRequest) -> None:
        if not request.prompt or not request.prompt.strip():
            raise LLMRuntimeError("Prompt must be non-empty")
        if len(request.prompt) > self._max_prompt_chars:
            raise LLMRuntimeError(
                f"Prompt exceeds bound: {len(request.prompt)} > {self._max_prompt_chars} chars"
            )
        if request.max_tokens <= 0 or request.max_tokens > self._max_tokens_ceiling:
            raise LLMRuntimeError(
                f"max_tokens={request.max_tokens} outside allowed range (1, {self._max_tokens_ceiling}]"
            )
        if not (0.0 <= request.temperature <= 2.0):
            raise LLMRuntimeError(f"temperature={request.temperature} outside [0.0, 2.0]")
        if not (0.0 < request.top_p <= 1.0):
            raise LLMRuntimeError(f"top_p={request.top_p} outside (0.0, 1.0]")

    def assemble(self, request: InferenceRequest) -> InferenceRequest:
        self.validate(request)
        return request


# ═════════════════════════════════════════════════════════════════════════
# SECTION 9 — HEALTH / RECOVERY
# ═════════════════════════════════════════════════════════════════════════

class HealthMonitor:
    """Tracks recent request outcomes and exposes a health verdict."""

    def __init__(self, window_size: int = 50) -> None:
        self._window_size = window_size
        self._outcomes: List[bool] = []
        self._lock = threading.Lock()
        self._consecutive_faults = 0

    def record(self, success: bool) -> None:
        with self._lock:
            self._outcomes.append(success)
            if len(self._outcomes) > self._window_size:
                self._outcomes.pop(0)
            self._consecutive_faults = 0 if success else self._consecutive_faults + 1

    def is_healthy(self, min_success_rate: float = 0.7, max_consecutive_faults: int = 3) -> bool:
        with self._lock:
            if self._consecutive_faults >= max_consecutive_faults:
                return False
            if not self._outcomes:
                return True
            rate = sum(self._outcomes) / len(self._outcomes)
            return rate >= min_success_rate

    def report(self) -> Dict[str, Any]:
        with self._lock:
            total = len(self._outcomes)
            successes = sum(self._outcomes)
            return {
                "window_size": self._window_size,
                "samples": total,
                "successes": successes,
                "success_rate": (successes / total) if total else 1.0,
                "consecutive_faults": self._consecutive_faults,
            }


# ═════════════════════════════════════════════════════════════════════════
# SECTION 10 — SECURITY
# ═════════════════════════════════════════════════════════════════════════

class SecurityGuard:
    """Enforces least-privilege access to the runtime gateway (Law 7)."""

    def __init__(self, allowed_callers: Optional[set] = None) -> None:
        self._allowed_callers = allowed_callers or {"BRAIN"}

    def authorize(self, caller_id: str) -> None:
        if caller_id not in self._allowed_callers:
            raise LLMRuntimeError(f"Unauthorized caller for LLM Runtime socket: {caller_id}")

    def sanitize_stop_sequences(self, stop_sequences: tuple) -> tuple:
        return tuple(s for s in stop_sequences if isinstance(s, str) and len(s) <= 64)


# ═════════════════════════════════════════════════════════════════════════
# SECTION 11 — LLM GATEWAY (Brain <-> Runtime Socket, ingress enforcement)
# ═════════════════════════════════════════════════════════════════════════

class LLMGateway:
    """
    Single ingress/egress point implementing the documented
    Brain <-> Runtime socket contract (SOCK_LLM_BRAIN equivalent).

    This organ exposes ONLY this class as its public API surface.
    """

    def __init__(
        self,
        registry: ModelRegistry,
        resource_manager: ResourceManager,
        provider_factory: Optional[Callable[[ProviderKind], IModelProvider]] = None,
        fallback_model_id: Optional[str] = None,
        allowed_callers: Optional[set] = None,
        idle_grace_period_s: float = 60.0,
    ) -> None:
        self._registry = registry
        self._resources = resource_manager
        self._runtime = RuntimeManager(
            registry=registry,
            resource_manager=resource_manager,
            provider_factory=provider_factory or self._default_provider_factory,
            idle_grace_period_s=idle_grace_period_s,
        )
        self._providers = ProviderManager(registry, self._runtime, fallback_model_id)
        self._dispatcher = PromptDispatcher()
        self._streams = TokenStreamManager()
        self._health = HealthMonitor()
        self._security = SecurityGuard(allowed_callers)
        self._request_status: Dict[str, RequestStatus] = {}
        self._status_lock = threading.Lock()

    @staticmethod
    def _default_provider_factory(kind: ProviderKind) -> IModelProvider:
        if kind == ProviderKind.LLAMA_CPP:
            return LlamaCppProvider()
        if kind == ProviderKind.CLOUD_FALLBACK:
            return CloudFallbackProvider()
        if kind == ProviderKind.OPENROUTER:
            return OpenRouterProvider()
        if kind == ProviderKind.GROQ:
            return GroqProvider()
        if kind == ProviderKind.NVIDIA:
            return NvidiaProvider()
        raise LLMRuntimeError(f"No provider bound for kind={kind}")

    def _set_status(self, request_id: str, status: RequestStatus) -> None:
        with self._status_lock:
            self._request_status[request_id] = status

    def get_status(self, request_id: str) -> RequestStatus:
        with self._status_lock:
            return self._request_status.get(request_id, RequestStatus.QUEUED)

    def submit(self, caller_id: str, request: InferenceRequest) -> InferenceResult:
        """Synchronous, buffered-result submission. For streaming, use `submit_streaming`."""
        self._security.authorize(caller_id)
        sanitized = dataclasses.replace(
            request, stop_sequences=self._security.sanitize_stop_sequences(request.stop_sequences)
        )
        validated = self._dispatcher.assemble(sanitized)
        self._set_status(validated.request_id, RequestStatus.DISPATCHED)

        collected: List[TokenChunk] = []

        def _on_token(chunk: TokenChunk) -> None:
            collected.append(chunk)

        try:
            result = self._providers.dispatch(validated, _on_token)
            self._set_status(validated.request_id, result.status)
            self._health.record(result.status == RequestStatus.COMPLETED)
            return result
        except LLMRuntimeError as exc:
            self._set_status(validated.request_id, RequestStatus.FAILED)
            self._health.record(False)
            return InferenceResult(
                request_id=validated.request_id,
                model_id=validated.model_id,
                status=RequestStatus.FAILED,
                text="",
                tokens_generated=0,
                ttft_ms=0.0,
                total_ms=0.0,
                tokens_per_second=0.0,
                error=str(exc),
            )

    def submit_streaming(self, caller_id: str, request: InferenceRequest) -> Iterator[TokenChunk]:
        """Streaming submission — yields TokenChunk objects as generated."""
        self._security.authorize(caller_id)
        sanitized = dataclasses.replace(
            request, stop_sequences=self._security.sanitize_stop_sequences(request.stop_sequences)
        )
        validated = self._dispatcher.assemble(sanitized)
        self._set_status(validated.request_id, RequestStatus.DISPATCHED)
        self._streams.open_stream(validated.request_id)

        result_box: Dict[str, InferenceResult] = {}

        def _worker() -> None:
            def _on_token(chunk: TokenChunk) -> None:
                self._streams.push(chunk)

            try:
                self._set_status(validated.request_id, RequestStatus.STREAMING)
                result = self._providers.dispatch(validated, _on_token)
                result_box["result"] = result
                self._set_status(validated.request_id, result.status)
                self._health.record(result.status == RequestStatus.COMPLETED)
            except LLMRuntimeError as exc:
                self._set_status(validated.request_id, RequestStatus.FAILED)
                self._health.record(False)
                self._streams.push(
                    TokenChunk(
                        request_id=validated.request_id,
                        token_text="",
                        token_index=-1,
                        is_final=True,
                        finish_reason=f"error:{exc}",
                    )
                )

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        yield from self._streams.consume(validated.request_id)

    def cancel(self, caller_id: str, model_id: str, request_id: str) -> None:
        self._security.authorize(caller_id)
        self._providers.interrupt(model_id, request_id)
        self._set_status(request_id, RequestStatus.CANCELLED)

    def unload(self, caller_id: str) -> None:
        self._security.authorize(caller_id)
        self._runtime.unload_model()

    def resource_snapshot(self) -> ResourceSnapshot:
        return self._resources.snapshot()

    def runtime_state(self) -> RuntimeState:
        return self._runtime.state

    def health_report(self) -> Dict[str, Any]:
        return {
            "healthy": self._health.is_healthy(),
            "runtime_state": self._runtime.state.value,
            "active_model_id": self._runtime.active_model_id,
            **self._health.report(),
        }

    def list_models(self) -> List[Dict[str, Any]]:
        return [m.to_dict() for m in self._registry.list_models()]


# ═════════════════════════════════════════════════════════════════════════
# SECTION 12 — ORGAN FACTORY (composition root)
# ═════════════════════════════════════════════════════════════════════════

def build_llm_runtime_organ(
    model_store_dir: str,
    max_vram_mb: int = 3584,
    max_ram_mb: int = 32768,
    fallback_model_id: Optional[str] = None,
    idle_grace_period_s: float = 60.0,
) -> LLMGateway:
    """
    Composition root for Organ 14. Returns the single public entry point
    (LLMGateway) that other organs / the Brain must use exclusively.
    """
    Path(model_store_dir).mkdir(parents=True, exist_ok=True)
    registry = ModelRegistry(verify_on_register=True)
    resources = ResourceManager(max_vram_mb=max_vram_mb, max_ram_mb=max_ram_mb)
    gateway = LLMGateway(
        registry=registry,
        resource_manager=resources,
        fallback_model_id=fallback_model_id,
        idle_grace_period_s=idle_grace_period_s,
    )
    return gateway


__all__ = [
    "RuntimeState",
    "RequestStatus",
    "ProviderKind",
    "ModelDescriptor",
    "InferenceRequest",
    "TokenChunk",
    "InferenceResult",
    "ResourceSnapshot",
    "LLMRuntimeError",
    "ModelNotFoundError",
    "ModelIntegrityError",
    "VRAMAllocationError",
    "ProviderFaultError",
    "RequestCancelledError",
    "IModelProvider",
    "LlamaCppProvider",
    "CloudFallbackProvider",
    "ModelVerifier",
    "ModelRegistry",
    "ModelDownloader",
    "ResourceManager",
    "RuntimeManager",
    "ProviderManager",
    "TokenStreamManager",
    "PromptDispatcher",
    "HealthMonitor",
    "SecurityGuard",
    "LLMGateway",
    "build_llm_runtime_organ",
]
