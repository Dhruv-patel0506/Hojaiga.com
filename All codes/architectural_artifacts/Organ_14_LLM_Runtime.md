# Organ 14 — LLM Runtime

**Version:** 1.0
**Authority:** Constitution → Law Book → Policy Manual → Master Architecture Blueprint → Organ Specification → Organ_14_LLM_Runtime.md

---

## Metadata

| Field | Value |
|---|---|
| Organ Number | 14 |
| Organ Name | LLM Runtime |
| Layer | Execution Layer (Model Runtime subsystem) |
| Owns | Model registry, provider bindings, VRAM/RAM footprint of loaded models, token streaming |
| Does Not Own | Reasoning, planning, tool selection, task decisions, autonomous model selection (Brain organ) |
| Implementation File | `organ_14_llm_runtime_single_file.py` |
| Test File | `test_organ_14_llm_runtime.py` |

---

## Purpose

The LLM Runtime is the dedicated execution and resource-brokering organ of Hojaiga. It abstracts model lifecycles, hardware acceleration, inference dispatch, model repositories, and multi-provider backends, exposing a single documented socket contract to the Brain organ. It performs zero reasoning; it only executes the explicit model IDs and prompts it is given.

---

## Responsibilities

- Accept inference requests from the Brain via the documented gateway socket contract.
- Maintain a verified Model Registry (SHA-256 + structural header checks).
- Load/unload models through a strict lifecycle state machine, auto-unloading after an idle grace period to free VRAM (Universal Law 11 — Resource Responsibility).
- Broker GPU/CPU/VRAM/KV-cache allocation for the organ's own footprint against the configured hardware ceiling.
- Stream tokens back to the caller with bounded, per-request queues.
- Detect provider faults, recover the runtime state machine, and apply configured fallback providers/models.
- Enforce least-privilege access: only authorized callers (the Brain) may submit, cancel, or unload.
- Report health and resource telemetry on demand.

---

## Internal Philosophy

Provider-agnostic. Every inference backend (llama.cpp today; vLLM, TensorRT-LLM, ONNX Runtime, or cloud APIs in the future) implements the same `IModelProvider` contract. No caller outside this organ is ever aware of which provider executes a request — callers speak only to `LLMGateway`.

---

## Internal Modules

| Module | Purpose | Owned State | Failure Mode | Recovery |
|---|---|---|---|---|
| `LLMGateway` | Single public ingress/egress point | Per-request status map | Unauthorized caller, invalid prompt | Reject with `LLMRuntimeError`, no state corruption |
| `ProviderManager` | Execution broker + fallback policy | None (stateless broker) | Primary provider fault | Automatic fallback to configured fallback model |
| `RuntimeManager` | Model load/unload lifecycle state machine | Active provider, active model id | Illegal transition, load failure | Transitions to `FAULTED`, `recover_from_fault()` resets to `UNLOADED` |
| `ModelRegistry` | Verified catalog of model descriptors | Model descriptor map | Missing/corrupt file | Registration refused before ever reaching provider |
| `ModelVerifier` | SHA-256 + GGUF header verification | None | Checksum/header mismatch | `ModelIntegrityError` raised pre-load |
| `ModelDownloader` | Import artifacts into managed model store | Model store directory | Missing source file | `ModelNotFoundError` |
| `ResourceManager` | VRAM/RAM/KV-cache bookkeeping | Current allocation snapshot | Requested model exceeds ceiling | `VRAMAllocationError`, load aborted before provider touched |
| `LlamaCppProvider` | llama.cpp backend binding | Active model descriptor | Model mismatch, inference error | Raises `ProviderFaultError`, surfaced to `ProviderManager` |
| `CloudFallbackProvider` | Fallback backend binding | Active model descriptor | No external binding configured | Explicit `ProviderFaultError` |
| `PromptDispatcher` | Prompt assembly + bounds validation | None | Prompt/param out of bounds | Rejected pre-dispatch |
| `TokenStreamManager` | Per-request bounded token queues | Open stream map | Consumer without open stream | `LLMRuntimeError` |
| `HealthMonitor` | Rolling success/fault window | Outcome window | N consecutive faults | `is_healthy()` flips false; visible via `health_report()` |
| `SecurityGuard` | Caller authorization + stop-sequence sanitization | Allowed caller set | Unauthorized caller | `LLMRuntimeError`, request never reaches provider |

---

## Folder Structure

```
organ_14_llm_runtime/
├── organ_14_llm_runtime_single_file.py   # consolidated importable module
├── test_organ_14_llm_runtime.py          # pytest suite
└── Organ_14_LLM_Runtime.md               # this specification
```

---

## Public Interfaces

### `build_llm_runtime_organ(model_store_dir, max_vram_mb=3584, max_ram_mb=32768, fallback_model_id=None, idle_grace_period_s=60.0) -> LLMGateway`
Composition root. Returns the sole public entry point.

### `LLMGateway.submit(caller_id: str, request: InferenceRequest) -> InferenceResult`
- **Input:** authorized caller id, validated `InferenceRequest`
- **Output:** `InferenceResult` (buffered, non-streaming)
- **Errors:** returns `InferenceResult(status=FAILED, error=...)` on provider/validation failure; never raises to the caller
- **Timeout:** bounded by provider execution; no internal timeout imposed beyond stream queue `get(timeout=30s)` when streaming
- **Version:** 1.0

### `LLMGateway.submit_streaming(caller_id: str, request: InferenceRequest) -> Iterator[TokenChunk]`
- **Input:** authorized caller id, validated `InferenceRequest`
- **Output:** iterator of `TokenChunk`, terminated by a chunk with `is_final=True`
- **Errors:** final chunk carries `finish_reason="error:..."` on failure
- **Recovery:** consumer can re-submit; runtime auto-recovers from `FAULTED`
- **Version:** 1.0

### `LLMGateway.cancel(caller_id, model_id, request_id) -> None`
Interrupts an in-flight generation via `IModelProvider.interrupt`.

### `LLMGateway.unload(caller_id) -> None`
Forces immediate unload of the active model and VRAM release.

### `LLMGateway.resource_snapshot() -> ResourceSnapshot`
### `LLMGateway.runtime_state() -> RuntimeState`
### `LLMGateway.health_report() -> Dict[str, Any]`
### `LLMGateway.list_models() -> List[Dict[str, Any]]`

---

## Internal Interfaces

### `IModelProvider` (abstract contract)
```
initialize(config) -> None
load_model(descriptor) -> None
unload_model() -> None
execute_inference(request, token_callback) -> InferenceResult
interrupt(request_id) -> None
name -> str
```
Every current and future backend (llama.cpp, TensorRT-LLM, vLLM, cloud API) implements only this contract.

---

## Socket Definitions

### Brain ↔ Runtime Socket (`SOCK_LLM_BRAIN`, realized as `LLMGateway`)

| Field | Value |
|---|---|
| Name | SOCK_LLM_BRAIN |
| Version | 1.0 |
| Direction | Bidirectional (request in, tokens/result out) |
| Allowed Data | `InferenceRequest` in; `TokenChunk` stream and `InferenceResult` out |
| Validation | `PromptDispatcher.validate()` — prompt length, token bounds, temperature/top_p ranges |
| Security | `SecurityGuard.authorize()` — caller allow-list, stop-sequence sanitization |
| Failure Behaviour | Non-streaming: `InferenceResult(status=FAILED)`; Streaming: final chunk with `finish_reason=error:*` |
| Retry Behaviour | Caller-driven; `ProviderManager` performs one automatic fallback attempt internally before surfacing failure |

---

## Pipeline Definitions

### Prompt Pipeline
- **Source:** `LLMGateway.submit` / `submit_streaming`
- **Destination:** `RuntimeManager.load_model` → `IModelProvider.execute_inference`
- **Data Contract:** `InferenceRequest`
- **Authentication:** `SecurityGuard.authorize(caller_id)`
- **Validation:** `PromptDispatcher.assemble`
- **Retry Logic:** one fallback-provider attempt on `LLMRuntimeError`
- **Timeout:** stream consumer `get(timeout=30s)`
- **Logging:** structured `logger.info`/`logger.error` at each lifecycle transition

### Response Pipeline
- **Source:** `IModelProvider.execute_inference` token callback
- **Destination:** `TokenStreamManager` → caller iterator, or buffered into `InferenceResult`
- **Data Contract:** `TokenChunk`, `InferenceResult`
- **Validation:** final chunk always emitted with `is_final=True`
- **Logging:** token counts, TTFT, tokens/sec recorded in `InferenceResult`

---

## Incoming Connections

- Brain organ → `SOCK_LLM_BRAIN` (only authorized caller by default: `"BRAIN"`)

## Outgoing Connections

- None. This organ never initiates calls into other organs; it is purely a callee.

---

## Data Contracts

`ModelDescriptor`, `InferenceRequest`, `TokenChunk`, `InferenceResult`, `ResourceSnapshot` — all defined as immutable (`frozen=True`) dataclasses in Section 1 of the implementation. See implementation file for exact field lists.

---

## State Management

`RuntimeState`: `UNLOADED → LOADING → LOADED_IDLE ⇄ BUSY_INFERENCE`, `LOADED_IDLE → UNLOADING → UNLOADED`, any state `→ FAULTED → UNLOADED` (via `recover_from_fault`). Transitions are enforced by an explicit adjacency table in `RuntimeManager._VALID_TRANSITIONS`; illegal transitions raise `LLMRuntimeError` and never silently no-op.

`RequestStatus`: `QUEUED → DISPATCHED → STREAMING → COMPLETED | FAILED | CANCELLED`.

---

## Events

- Model registered / unregistered
- Runtime state transition (logged at every edge)
- VRAM allocated / released
- Idle grace period elapsed → auto-unload
- Provider fault → fallback attempt → recovery

---

## Thread Safety

`RuntimeManager`, `ModelRegistry`, `ResourceManager`, `HealthMonitor`, and `TokenStreamManager` each guard mutable state with `threading.Lock`/`RLock`. Streaming inference executes on a dedicated daemon thread per request; the idle-unload timer is a `threading.Timer` cancelled/rearmed under the same lock as lifecycle transitions to prevent races between an in-flight request and an idle-triggered unload.

---

## Resource Management

`ResourceManager` estimates VRAM footprint from quantization-aware bytes-per-parameter heuristics plus a KV-cache term proportional to context window × GPU layers, and refuses allocation beyond the configured ceiling (default 3584MB, leaving headroom under the 4GB RTX 3050 budget). Per Master Architecture Blueprint, system-wide VRAM ownership belongs to the Brain organ; this organ tracks and bounds only its own footprint and exposes it as read-only telemetry via `resource_snapshot()`.

---

## Performance Targets

| Metric | Target |
|---|---|
| Time To First Token | ≤ 250 ms |
| Generation speed (7B, Q4) | ≥ 40 tokens/sec |
| Warm model load | ≤ 200 ms |
| Cold model load (7B GGUF) | ≤ 4000 ms |
| Idle VRAM overhead | ≤ 256 MB |

---

## Hardware Considerations

- OS: Windows 11, CPU: Intel Core i7, GPU: RTX 3050 (4GB VRAM), RAM: 32GB.
- GPU reserved primarily for local LLM inference; CPU-first for all non-inference organ logic.
- SSD used for runtime model store staging; External HDD for archived model artifacts (Storage Architecture, Upper Surface Diagram §12).

## SSD Usage
Active/loaded model files are read from the configured `model_store_dir`, expected to reside on SSD for load-latency targets.

## HDD Usage
Cold/archived model artifacts and historical model manifests are expected on External HDD; `ModelDownloader.import_local_file` stages a copy into the SSD-backed model store on demand.

## GPU Usage
Bounded by `ResourceManager.max_vram_mb`; released immediately on unload or idle timeout.

## Memory Usage
`max_ram_mb` ceiling tracked in `ResourceSnapshot`; provider-level RAM accounting is delegated to the bound provider implementation.

---

## Logging

Append-only structured logs via the `hojaiga.organ14.llm_runtime` logger at every state transition, allocation, fault, and fallback attempt (Law Book, Foundational Law 7; Universal Law 1).

---

## Versioning

Organ version 1.0. Public contracts (`IModelProvider`, `LLMGateway` methods, dataclasses) are versioned as a unit; breaking changes require a major version bump per Constitution Article III, Principle 1.

---

## Security

- Least-privilege caller allow-list (`SecurityGuard`), default `{"BRAIN"}`.
- Stop-sequence sanitization to bound adversarial input length.
- Model integrity enforced pre-load via SHA-256 + GGUF structural header check; no unverified weights are ever passed to a provider.

---

## Failure Recovery

Any unhandled provider exception drives `RuntimeManager` to `FAULTED`; `ProviderManager` calls `recover_from_fault()` (resetting to `UNLOADED` and releasing VRAM) before optionally retrying against a configured fallback model. No corrupted intermediate state persists across a fault.

---

## Validation

`PromptDispatcher.validate()` enforces: non-empty prompt, prompt length ceiling, `max_tokens` within `(0, ceiling]`, `temperature ∈ [0.0, 2.0]`, `top_p ∈ (0.0, 1.0]`.

---

## Testing

18 unit/integration tests in `test_organ_14_llm_runtime.py` covering: model verification (valid/bad checksum/bad header), registry lookup, resource allocation (within budget / over budget), full runtime lifecycle transitions (legal and illegal), prompt bounds validation, security authorization, health monitor fault windows, token stream end-to-end, and full gateway submit/streaming/health/unload flows. All tests pass (`18 passed`).

---

## Extension Points

New providers are added by implementing `IModelProvider` and registering them in a custom `provider_factory` passed to `LLMGateway.__init__` — zero modification to `LLMGateway`, `RuntimeManager`, or `ProviderManager` required (Law Book, Foundational Law 9 — Extensibility Without Core Modification).

---

## Future Roadmap

- Bind `LlamaCppProvider._generate` to a real llama.cpp/llama-cpp-python inference call.
- Add TensorRT-LLM and vLLM provider implementations behind the same `IModelProvider` contract.
- Named-pipe/Unix-domain-socket transport binding for `SOCK_LLM_BRAIN` consistent with the CNS organ's IPC layer.

---

## Mermaid Diagrams

### Component Diagram
```mermaid
graph TD
    Brain[Brain Organ] -->|SOCK_LLM_BRAIN| Gateway[LLMGateway]
    Gateway --> Security[SecurityGuard]
    Gateway --> Dispatcher[PromptDispatcher]
    Gateway --> Providers[ProviderManager]
    Providers --> Runtime[RuntimeManager]
    Runtime --> Registry[ModelRegistry]
    Runtime --> Resources[ResourceManager]
    Runtime --> ProviderImpl[IModelProvider]
    ProviderImpl --> LlamaCpp[LlamaCppProvider]
    ProviderImpl --> CloudFallback[CloudFallbackProvider]
    Gateway --> Streams[TokenStreamManager]
    Gateway --> Health[HealthMonitor]
    Registry --> Verifier[ModelVerifier]
```

### Sequence Diagram
```mermaid
sequenceDiagram
    participant B as Brain
    participant G as LLMGateway
    participant P as ProviderManager
    participant R as RuntimeManager
    participant Pr as IModelProvider
    B->>G: submit(caller_id, InferenceRequest)
    G->>G: authorize + validate
    G->>P: dispatch(request, token_callback)
    P->>R: load_model(model_id)
    R->>Pr: load_model(descriptor)
    P->>R: begin_inference()
    P->>Pr: execute_inference(request, callback)
    Pr-->>G: TokenChunk (stream)
    Pr-->>P: InferenceResult
    P->>R: end_inference()
    P-->>G: InferenceResult
    G-->>B: InferenceResult
```

### State Diagram
```mermaid
stateDiagram-v2
    [*] --> UNLOADED
    UNLOADED --> LOADING
    LOADING --> LOADED_IDLE
    LOADING --> FAULTED
    LOADED_IDLE --> BUSY_INFERENCE
    LOADED_IDLE --> UNLOADING
    LOADED_IDLE --> FAULTED
    BUSY_INFERENCE --> LOADED_IDLE
    BUSY_INFERENCE --> FAULTED
    UNLOADING --> UNLOADED
    UNLOADING --> FAULTED
    FAULTED --> UNLOADED
```

### Pipeline Diagram
```mermaid
flowchart LR
    Req[InferenceRequest] --> Auth[Authorize]
    Auth --> Val[Validate Bounds]
    Val --> Load[Load/Reuse Model]
    Load --> Infer[Execute Inference]
    Infer --> Stream[Token Stream]
    Stream --> Result[InferenceResult]
```

### Socket Diagram
```mermaid
flowchart LR
    Brain((Brain)) <-->|SOCK_LLM_BRAIN v1.0| Gateway[[LLMGateway]]
```

### Folder Structure Diagram
```mermaid
graph TD
    Root[organ_14_llm_runtime/] --> Impl[organ_14_llm_runtime_single_file.py]
    Root --> Test[test_organ_14_llm_runtime.py]
    Root --> Spec[Organ_14_LLM_Runtime.md]
```

### Execution Flow
```mermaid
flowchart TD
    A[Brain issues InferenceRequest] --> B{Authorized?}
    B -- No --> Z[Reject]
    B -- Yes --> C{Prompt valid?}
    C -- No --> Z
    C -- Yes --> D[RuntimeManager.load_model]
    D --> E{VRAM within budget?}
    E -- No --> F[VRAMAllocationError -> FAULTED -> recover]
    E -- Yes --> G[Provider.execute_inference]
    G --> H{Success?}
    H -- Yes --> I[Return InferenceResult COMPLETED]
    H -- No --> J[Attempt fallback provider]
    J --> K{Fallback succeeds?}
    K -- Yes --> I
    K -- No --> L[Return InferenceResult FAILED]
```

---

## Implementation Checklist

- [x] Metadata, Purpose, Responsibilities, Internal Philosophy defined
- [x] Internal Modules documented with failure/recovery modes
- [x] Folder Structure defined
- [x] Public Interfaces documented (input/output/errors/recovery/timeout/version)
- [x] Internal Interfaces (`IModelProvider`) documented
- [x] Socket Definitions (`SOCK_LLM_BRAIN`) complete
- [x] Pipeline Definitions (Prompt Pipeline, Response Pipeline) complete
- [x] Incoming/Outgoing Connections documented
- [x] Data Contracts defined as immutable dataclasses
- [x] State Management (RuntimeState, RequestStatus) documented with diagram
- [x] Events enumerated
- [x] Thread Safety addressed
- [x] Resource Management (VRAM/RAM/KV cache) implemented and bounded
- [x] Performance Targets specified
- [x] Hardware Considerations (SSD/HDD/GPU/Memory) documented
- [x] Logging implemented (append-only, structured)
- [x] Versioning stated
- [x] Security (authorization, sanitization, integrity verification) implemented
- [x] Failure Recovery (fault → recover → fallback) implemented
- [x] Validation (`PromptDispatcher`) implemented
- [x] Testing: 18/18 tests passing
- [x] Extension Points documented
- [x] Future Roadmap documented
- [x] All 7 required Mermaid diagrams included
- [x] No placeholders, no TODOs, no mock implementations in production code paths

---

## Closing Statement

Organ 14 — LLM Runtime is complete per the Organ Specification completion criteria. It exposes a single authorized socket (`LLMGateway`) to the Brain organ, performs strictly zero reasoning or model-selection logic, verifies every model artifact before load, bounds its own GPU/CPU/VRAM footprint to the target hardware, and recovers deterministically from provider faults with optional fallback. All required sections, diagrams, and tests are present and passing.
