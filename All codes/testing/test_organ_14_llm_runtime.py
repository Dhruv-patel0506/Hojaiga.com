"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 14
Name: Llm Runtime

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Llm Runtime]
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
Dependencies: pytest, time, hashlib, core_organs.organ_14_llm_runtime_single_file, os...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: test_organ_14_llm_runtime.py]) --> output([Output Node])
```
"""

"""
Test suite — Organ 14 LLM Runtime.
Run with: pytest -q test_organ_14_llm_runtime.py
"""

import hashlib
import os
import time

import pytest  # type: ignore

from core_organs.organ_14_llm_runtime_single_file import (
    ModelDescriptor,
    ProviderKind,
    InferenceRequest,
    RequestStatus,
    RuntimeState,
    ModelRegistry,
    ModelVerifier,
    ModelIntegrityError,
    ModelNotFoundError,
    ResourceManager,
    VRAMAllocationError,
    RuntimeManager,
    LlamaCppProvider,
    build_llm_runtime_organ,
    PromptDispatcher,
    LLMRuntimeError,
    HealthMonitor,
    SecurityGuard,
    TokenStreamManager,
    TokenChunk,
)


GGUF_MAGIC = b"GGUF"


@pytest.fixture()
def fake_model_file(tmp_path):
    def _make(model_id: str, body: bytes = b"weights-payload-0000") -> ModelDescriptor:
        content = GGUF_MAGIC + body
        path = tmp_path / f"{model_id}.gguf"
        path.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        return ModelDescriptor(
            model_id=model_id,
            display_name=model_id,
            file_path=str(path),
            sha256=digest,
            quantization="Q4_K_M",
            context_window=4096,
            provider=ProviderKind.LLAMA_CPP,
            parameters_b=2.0,
            gpu_layers=20,
        )
    return _make


def test_model_verifier_accepts_valid_file(fake_model_file):
    descriptor = fake_model_file("mdl_ok")
    ModelVerifier.verify(descriptor)  # should not raise


def test_model_verifier_rejects_bad_checksum(fake_model_file, tmp_path):
    descriptor = fake_model_file("mdl_bad_hash")
    tampered = descriptor.__class__(**{**descriptor.__dict__, "sha256": "0" * 64})
    with pytest.raises(ModelIntegrityError):
        ModelVerifier.verify(tampered)


def test_model_verifier_rejects_bad_header(tmp_path):
    path = tmp_path / "bad.gguf"
    path.write_bytes(b"NOTGGUF-body")
    descriptor = ModelDescriptor(
        model_id="mdl_bad_header",
        display_name="bad",
        file_path=str(path),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        quantization="Q4_K_M",
        context_window=2048,
        provider=ProviderKind.LLAMA_CPP,
        parameters_b=7.0,
    )
    with pytest.raises(ModelIntegrityError):
        ModelVerifier.verify(descriptor)


def test_registry_get_missing_raises():
    registry = ModelRegistry()
    with pytest.raises(ModelNotFoundError):
        registry.get("does_not_exist")


def test_registry_register_and_list(fake_model_file):
    registry = ModelRegistry()
    descriptor = fake_model_file("mdl_list")
    registry.register(descriptor)
    assert [m.model_id for m in registry.list_models()] == ["mdl_list"]


def test_resource_manager_allocation_within_budget(fake_model_file):
    rm = ResourceManager(max_vram_mb=8000, max_ram_mb=32768)
    descriptor = fake_model_file("mdl_small")
    rm.allocate_for_model(descriptor)
    snap = rm.snapshot()
    assert snap.active_model_id == "mdl_small"
    assert snap.vram_used_mb > 0
    rm.release()
    assert rm.snapshot().active_model_id is None


def test_resource_manager_rejects_oversized_model(fake_model_file):
    rm = ResourceManager(max_vram_mb=100, max_ram_mb=32768)
    descriptor = fake_model_file("mdl_huge", body=b"x" * 10)
    oversized = descriptor.__class__(**{**descriptor.__dict__, "parameters_b": 70.0})
    with pytest.raises(VRAMAllocationError):
        rm.allocate_for_model(oversized)


def test_runtime_manager_lifecycle_transitions(fake_model_file):
    registry = ModelRegistry()
    descriptor = fake_model_file("mdl_cycle")
    registry.register(descriptor)
    rm = ResourceManager(max_vram_mb=8000, max_ram_mb=32768)
    runtime = RuntimeManager(
        registry=registry, resource_manager=rm,
        provider_factory=lambda kind: LlamaCppProvider(), idle_grace_period_s=999,
    )
    assert runtime.state == RuntimeState.UNLOADED
    runtime.load_model("mdl_cycle")
    assert runtime.state == RuntimeState.LOADED_IDLE
    runtime.begin_inference()
    assert runtime.state == RuntimeState.BUSY_INFERENCE
    runtime.end_inference()
    assert runtime.state == RuntimeState.LOADED_IDLE
    runtime.unload_model()
    assert runtime.state == RuntimeState.UNLOADED


def test_runtime_manager_illegal_transition_raises(fake_model_file):
    registry = ModelRegistry()
    descriptor = fake_model_file("mdl_illegal")
    registry.register(descriptor)
    rm = ResourceManager(max_vram_mb=8000, max_ram_mb=32768)
    runtime = RuntimeManager(
        registry=registry, resource_manager=rm,
        provider_factory=lambda kind: LlamaCppProvider(),
    )
    with pytest.raises(LLMRuntimeError):
        runtime.begin_inference()  # cannot begin inference while UNLOADED


def test_prompt_dispatcher_validates_bounds():
    dispatcher = PromptDispatcher(max_prompt_chars=10, max_tokens_ceiling=32)
    with pytest.raises(LLMRuntimeError):
        dispatcher.validate(InferenceRequest.new("mdl", "this prompt is way too long"))
    with pytest.raises(LLMRuntimeError):
        dispatcher.validate(InferenceRequest.new("mdl", "ok", max_tokens=0))
    with pytest.raises(LLMRuntimeError):
        dispatcher.validate(InferenceRequest.new("mdl", "ok", temperature=5.0))
    dispatcher.validate(InferenceRequest.new("mdl", "ok", max_tokens=8))  # should not raise


def test_security_guard_rejects_unauthorized_caller():
    guard = SecurityGuard(allowed_callers={"BRAIN"})
    guard.authorize("BRAIN")  # ok
    with pytest.raises(LLMRuntimeError):
        guard.authorize("RANDOM_CALLER")


def test_health_monitor_transitions_unhealthy_on_consecutive_faults():
    hm = HealthMonitor(window_size=10)
    for _ in range(3):
        hm.record(False)
    assert hm.is_healthy(max_consecutive_faults=3) is False


def test_token_stream_manager_end_to_end():
    tsm = TokenStreamManager()
    tsm.open_stream("req1")
    tsm.push(TokenChunk(request_id="req1", token_text="a", token_index=0))
    tsm.push(TokenChunk(request_id="req1", token_text="", token_index=1, is_final=True))
    collected = list(tsm.consume("req1"))
    assert len(collected) == 2
    assert collected[-1].is_final is True


def test_gateway_submit_end_to_end(fake_model_file):
    gateway = build_llm_runtime_organ(model_store_dir="/tmp/organ14_test_store", idle_grace_period_s=999)
    descriptor = fake_model_file("mdl_end2end")
    gateway._registry.register(descriptor)  # test-only direct registration
    request = InferenceRequest.new("mdl_end2end", "hello world from hojaiga", max_tokens=5)
    result = gateway.submit("BRAIN", request)
    assert result.status == RequestStatus.COMPLETED
    assert result.tokens_generated == 5
    assert result.text.strip() != ""


def test_gateway_rejects_unauthorized_caller(fake_model_file):
    gateway = build_llm_runtime_organ(model_store_dir="/tmp/organ14_test_store2", idle_grace_period_s=999)
    descriptor = fake_model_file("mdl_auth")
    gateway._registry.register(descriptor)
    request = InferenceRequest.new("mdl_auth", "hello", max_tokens=2)
    with pytest.raises(LLMRuntimeError):
        gateway.submit("UNKNOWN_CALLER", request)


def test_gateway_streaming_yields_final_chunk(fake_model_file):
    gateway = build_llm_runtime_organ(model_store_dir="/tmp/organ14_test_store3", idle_grace_period_s=999)
    descriptor = fake_model_file("mdl_stream")
    gateway._registry.register(descriptor)
    request = InferenceRequest.new("mdl_stream", "streaming test prompt", max_tokens=4)
    chunks = list(gateway.submit_streaming("BRAIN", request))
    assert any(c.is_final for c in chunks)
    deadline = time.time() + 2.0
    while gateway.get_status(request.request_id) not in (RequestStatus.COMPLETED, RequestStatus.FAILED):
        if time.time() > deadline:
            break
        time.sleep(0.01)
    assert gateway.get_status(request.request_id) == RequestStatus.COMPLETED


def test_gateway_health_report_shape(fake_model_file):
    gateway = build_llm_runtime_organ(model_store_dir="/tmp/organ14_test_store4", idle_grace_period_s=999)
    descriptor = fake_model_file("mdl_health")
    gateway._registry.register(descriptor)
    gateway.submit("BRAIN", InferenceRequest.new("mdl_health", "hi", max_tokens=2))
    report = gateway.health_report()
    assert "healthy" in report and "runtime_state" in report and "active_model_id" in report


def test_gateway_unload_releases_resources(fake_model_file):
    gateway = build_llm_runtime_organ(model_store_dir="/tmp/organ14_test_store5", idle_grace_period_s=999)
    descriptor = fake_model_file("mdl_unload")
    gateway._registry.register(descriptor)
    gateway.submit("BRAIN", InferenceRequest.new("mdl_unload", "hi", max_tokens=2))
    gateway.unload("BRAIN")
    assert gateway.runtime_state() == RuntimeState.UNLOADED
    assert gateway.resource_snapshot().vram_used_mb == 0
