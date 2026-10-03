# **Organ 01 — Brain Specification Document**

## **1\. Overview**

The Brain Organ is the central cognitive runtime of the Hojaiga Automation Operating System. It provides single-instance local LLM reasoning, goal-directed planning, task decomposition, prompt assembly, strategy generation, and self-reflection without relying on cloud services or external model fallbacks. Operating under a strictly managed cold-start/warm-execution lifecycle via `llama.cpp`, the Brain Organ leverages GPU memory solely during active processing tasks and releases VRAM upon task completion.

MD+ 3

## **2\. Purpose**

The purpose of the Brain Organ is to provide deterministic, context-aware reasoning and high-level orchestration across all Hojaiga organs. It translates user goals and system triggers into valid, executable plan trees and structured pipeline actions while upholding the system’s governing Constitution, Law Book, and Policy Manual.

MD+ 4

## **3\. Architecture Philosophy**

In alignment with Chapter 1 of the Master Architecture Blueprint and Universal Law 3 (Separation of Responsibility), the Brain Organ does not directly manipulate OS windows, store raw knowledge databases, or handle direct network routing. It acts strictly as an analytical decision-maker. It communicates through standardized Unix Domain Sockets or IPC Named Pipes using JSON-Schema validation. The Brain is treated as a transient resource: off by default, loaded on demand, and unloaded after an idle grace period to maximize host hardware efficiency.

MD+ 4

## **4\. Primary Responsibilities**

* **Reasoning & Context Understanding:** Process natural language and structured system state to formulate semantic plans.  
   MD+ 1  
* **Goal & Plan Management:** Decompose broad goals into DAG-based (Directed Acyclic Graph) sub-task execution trees.  
   MD  
* **Lifecycle & Model Management:** Control `llama.cpp` process lifecycle, bootstrap missing Qwen3 models, and manage VRAM allocations.  
   MD  
* **Strategy & Prompt Compilation:** Dynamically construct structured system prompts incorporating governing policies, active tools, and long-term memory contexts.  
   MD+ 1  
* **Self-Reflection & Validation:** Evaluate task results, detect execution anomalies, and generate corrective re-planning strategies.  
   MD+ 2

## **5\. Internal Modules**

* `brain_core`: Main orchestration entry point and public API listener.  
* `model_manager`: Manages `llama.cpp` process invocation, health checks, model bootstrapping, and VRAM deallocation.  
   MD  
* `planner`: Handles goal decomposition and sub-task generation.  
   MD  
* `prompt_builder`: Compiles system prompts, injecting Constitution constraints and active organ sockets.  
   MD+ 2  
* `strategy_generator`: Synthesizes contingency execution branches when failures occur.  
   MD+ 1  
* `reflection_engine`: Evaluates task execution outputs against intended success criteria.  
   MD+ 2  
* `brain_compiler`: Translates natural language strategies into strictly formatted JSON execution DSLs.  
   MD

## **6\. Internal Folder Structure**

/organ\_01\_brain  
├── bin/  
│   └── llama.cpp/            \# llama.cpp binaries  
├── models/  
│   └── qwen3-8b-instruct.gguf \# Primary local LLM weights  
├── src/  
│   ├── core/  
│   │   ├── brain\_core.py  
│   │   └── lifecycle.py  
│   ├── model\_manager/  
│   │   ├── process\_control.py  
│   │   └── vram\_monitor.py  
│   ├── planner/  
│   │   ├── task\_decomposer.py  
│   │   └── dsl\_compiler.py  
│   ├── prompt/  
│   │   ├── builder.py  
│   │   └── templates/  
│   ├── reflection/  
│   │   └── evaluator.py  
│   └── sockets/  
│       ├── ipc\_server.py  
│       └── protocol.py  
├── tests/  
└── config.json

## **7\. Public Interfaces**

* `IPC /tmp/hojaiga_brain.sock` (Linux/Unix) or `\\.\pipe\hojaiga_brain` (Windows):  
   MD  
  * `POST /v1/plan`: Receives goal description; returns task execution DAG.  
  * `POST /v1/reflect`: Receives task execution logs; returns validity and recovery strategies.  
     MD+ 1  
  * `POST /v1/complete`: Receives raw prompt context; returns formatted structural completion.  
     MD  
  * `GET /v1/status`: Returns current model lifecycle state (UNLOADED, LOADING, READY, BUSY, GRACE\_PERIOD).  
     MD

## **8\. Internal Interfaces**

* `ModelManagerInterface`:  
  * `boot_engine()`: Starts `llama.cpp` with specified hardware flags.  
     MD  
  * `shutdown_engine()`: Gracefully terminates `llama.cpp` process.  
     MD  
  * `check_vram_usage()`: Queries GPU driver for memory footprints.  
     MD  
* `PromptBuilderInterface`:  
  * `compile_system_prompt(domain, context_layers)`: Assembles final prompt token sequence.  
     MD

## **9\. Socket Definitions**

* Socket Name: `hojaiga_brain_ipc`

   MD  
* Transport: Named Pipe (Windows: `\\.\pipe\hojaiga_brain_ipc`)  
   MD  
* Framing: Length-prefixed JSON-RPC 2.0 over binary stream.  
   MD  
* Max Payload: 16 MB.

## **10\. Pipeline Definitions**

* `BrainInferencePipeline`:  
  1. Receive IPC Message \-\> 2\. Acquire Execution Lock \-\> 3\. Check/Trigger Model Lifecycle Warmup \-\> 4\. Assemble Prompt via `prompt_builder` \-\> 5\. Execute HTTP/gRPC call to `llama.cpp` \-\> 6\. Parse & Validate Schema Output \-\> 7\. Reset Grace Period Timer \-\> 8\. Return Response JSON.  
      MD

## **11\. Incoming Connections**

* **CNS (Organ 02):** Main caller for task decomposition, strategy generation, and system reflection.  
   MD  
* **Agents (Organ 10):** Direct agent query routing via CNS proxy for specialized sub-reasoning tasks.  
   MD

## **12\. Outgoing Connections**

* **Model Manager \-\> llama.cpp Process:** Low-level HTTP/REST interface (`[http://127.0.0.1:8080](http://127.0.0.1:8080)`) restricted strictly to localhost loopback.  
   MD  
* **CNS (Organ 02):** Emit system lifecycle events (`BRAIN_READY`, `BRAIN_SHUTDOWN`, `BRAIN_ERROR`).  
   MD

## **13\. State Management**

The Brain Organ relies on a deterministic state machine:

* `UNLOADED`: Process dormant, VRAM released.  
   MD  
* `LOADING`: `llama.cpp` launching, loading Qwen3 8B weights into GPU VRAM.  
   MD  
* `READY`: Listening, idle timer active.  
   MD  
* `BUSY`: Inference actively processing.  
   MD  
* `GRACE_PERIOD`: Waiting for subsequent requests before triggering auto-shutdown.  
   MD

\[UNLOADED\] \--(Task Arrives)--\> \[LOADING\] \--\> \[READY\] \--\> (Inference Request) \--\> \[BUSY\]  
     ^                                         |                                  |  
     |                                   (Idle Timeout)                  (Task Completes)  
     |                                         |                                  |  
     \+---------------------------------- \[GRACE\_PERIOD\] \<-------------------------+

## **14\. Event Definitions**

* `EVENT_BRAIN_STATE_CHANGED`: Broadcasts transitions between lifecycle states.  
   MD  
* `EVENT_BRAIN_INFERENCE_START`: Fired when a prompt processing sequence begins.  
   MD  
* `EVENT_BRAIN_INFERENCE_COMPLETE`: Transmits token generation stats, runtime latency, and status code.  
   MD  
* `EVENT_BRAIN_RESOURCE_EXHAUSTED`: Triggered if VRAM allocation fails.  
   MD

## **15\. Data Contracts**

JSON  
{  
  "$schema": "http://json-schema.org/draft-07/schema\#",  
  "title": "BrainPlanRequest",  
  "type": "object",  
  "properties": {  
    "request\_id": { "type": "string", "format": "uuid" },  
    "goal": { "type": "string" },  
    "context": {  
      "type": "object",  
      "properties": {  
        "active\_apps": { "type": "array", "items": { "type": "string" } },  
        "memory\_highlights": { "type": "array", "items": { "type": "string" } }  
      },  
      "required": \["active\_apps"\]  
    },  
    "constraints": { "type": "array", "items": { "type": "string" } }  
  },  
  "required": \["request\_id", "goal", "context"\]  
}

## **16\. Internal Database Structures**

The Brain Organ maintains no persistent user data store to comply with stateless cognitive design. It uses an in-memory SQLite operational database (`:memory:`) for active context management:

MD+ 1

* Table `active_plans` (`plan_id` TEXT PRIMARY KEY, `goal` TEXT, `created_at` TIMESTAMP, `status` TEXT).  
   MD  
* Table `inference_cache` (`prompt_hash` TEXT PRIMARY KEY, `response_json` TEXT, `timestamp` TIMESTAMP).  
   MD

## **17\. Cache Strategy**

* Deterministic task generation patterns are stored in an in-memory execution plan cache (`LRU Cache`, maximum 128 entries).  
* Identical strategy sub-queries bypass full LLM inference if prompt state and context hashes match active cache records.

## **18\. Memory Strategy**

* RAM footprint: Under 1.5 GB for core host process runtime overhead.  
   MD  
* Offloads prompt-building intermediate string buffers immediately after tokenization.  
   MD

## **19\. Thread Safety**

* Multi-threading within `brain_core` protected by mutual exclusion locks (`std::mutex` / Python `threading.Lock`) around process control and IPC handlers.  
* Only one active inference task is executed on the local `llama.cpp` instance at any point in time to avoid VRAM Thrashing.  
   MD

## **20\. Concurrency**

* Single-threaded inference execution model enforced at the backend level. Incoming IPC tasks are queued in a priority FIFO task channel managed by the CNS.  
   MD

## **21\. Hardware Optimization**

* Built specifically for Intel Core i7 host CPU architecture and NVIDIA RTX 3050 (4 GB VRAM).  
   MD  
* Flash Attention-2 enabled within `llama.cpp` compilation flags.  
   MD  
* Quantization scheme: Q4\_K\_M for Qwen3 8B Instruct model to fit entirely within 3.5 GB VRAM runtime allocation, leaving 0.5 GB VRAM headroom for Windows DWM.  
   MD

## **22\. GPU Usage**

* Restricted purely to `llama.cpp` process execution for matrix multiplication operations during token generation.  
   MD  
* Zero GPU usage when Brain is in `UNLOADED` or `GRACE_PERIOD` states.  
   MD

## **23\. CPU Usage**

* High utilization during prompt tokenization and initial KV-cache pre-fill stages.  
   MD  
* Low overhead (\<2%) during idle states.  
   MD

## **24\. SSD Usage**

* Runtime binaries, active log appenders, and local model file caching reside on SSD.  
   MD+ 1  
* Minimal write cycles: Reads Qwen3 model weights directly from SSD into RAM/VRAM during cold start.  
   MD

## **25\. HDD Usage**

* Long-term archive of historical reasoning traces, prompt logging dumps, and model binary archives offloaded to external HDD.  
   MD+ 1

## **26\. Security Model**

* Strictly local execution: Bindings forced to `127.0.0.1` or OS local IPC pipes.  
   MD  
* No external network access or remote API integration allowed within the Brain runtime.  
   MD

## **27\. Permissions**

* Executable permissions restricted to the local OS user running Hojaiga.  
   MD+ 1  
* No administrative or root privilege requirements for the `llama.cpp` child process.  
   MD

## **28\. Logging**

* Structured JSON logging adhering to Policy Manual Chapter 8\.  
   MD+ 1  
* Tracks `execution_id`, `prompt_tokens`, `completion_tokens`, `vram_allocated_mb`, and `generation_latency_ms`.  
   MD+ 1

## **29\. History Recording**

* Append-only execution history entries written via CNS logging pipelines to external HDD storage.  
   MD+ 2

## **30\. Recovery Strategy**

* Automatic process crash recovery: If `llama.cpp` unexpected exits, `model_manager` catches SIGSEGV/SIGABRT, purges stale locks, and restarts instance up to 3 times before raising a critical system failure to CNS.  
   MD+ 2

## **31\. Failure Handling**

* Fallback to heuristic sub-goal execution trees if Qwen3 generation produces invalid schema outputs after 2 retry attempts.  
   MD+ 1

## **32\. Validation Rules**

* Every generation output is schema-validated via `jsonschema` engine.  
   MD  
* If validation fails, error details are appended to system context and sent back to the model for one correction pass.  
   MD+ 1

## **33\. Testing Strategy**

* Unit tests for Prompt Assembly, Model Lifecycle Management, and IPC message parsing.  
   MD  
* Integration tests utilizing mock `llama.cpp` HTTP responses to verify edge-case handling.  
   MD

## **34\. Extension Points**

* Plugin interfaces for dynamic prompt layer injection (e.g., domain-specific tool definitions dynamically added to Qwen3 system context).  
   MD+ 1

## **35\. Future Compatibility**

* Model weights drop-in upgradeable via `model_manager` directory swap without modifying core API interfaces.  
   MD+ 1

## **36\. Versioning**

* Semantic Versioning: `v1.0.0` core definition. Breaking IPC payload contract changes increment major version.  
   MD+ 1

## **37\. Dependencies**

* `llama.cpp` pre-compiled binaries with CUDA 12.x support.  
   MD  
* `Qwen3-8B-Instruct-Q4_K_M.gguf`

   MD  
* Python 3.11+ / C++17 core runtimes.  
   MD

## **38\. Interaction with Other Organs**

* **CNS (Organ 02):** Controls Brain life cycles and dispatches plans.  
   MD  
* **Memory (Organ 03):** Supplies contextual history for prompt assembly.  
   MD+ 1  
* **Knowledge (Organ 04):** Provides verified domain facts injected into reasoning steps.  
   MD+ 1

## **39\. Mermaid Component Diagram**

Code snippet  
graph TD  
    CNS\[CNS Organ 02\] \--\>|IPC Sockets| BC\[Brain Core\]  
    BC \--\> PM\[Prompt Builder\]  
    BC \--\> MM\[Model Manager\]  
    BC \--\> PE\[Planner Engine\]  
    BC \--\> RE\[Reflection Engine\]  
    MM \--\>|Process Spawn / HTTP| Llama\[llama.cpp Engine\]  
    Llama \--\>|Loads Weights| GPU\[NVIDIA RTX 3050 VRAM\]

## **40\. Mermaid Sequence Diagram**

Code snippet  
sequenceDiagram  
    participant CNS as CNS Organ  
    participant BC as Brain Core  
    participant MM as Model Manager  
    participant LLM as llama.cpp Process

    CNS-\>\>BC: POST /v1/plan (Goal)  
    BC-\>\>MM: Ensure Model Available()  
    alt Model Unloaded  
        MM-\>\>LLM: Spawn Process & Load Qwen3  
        LLM--\>\>MM: Ready (VRAM Allocated)  
    end  
    BC-\>\>LLM: POST /completion (Compiled System \+ User Prompt)  
    LLM--\>\>BC: JSON DSL Response  
    BC-\>\>CNS: Return Executable DAG  
    Note over BC,MM: Idle Grace Period Starts  
    MM-\>\>LLM: Grace Period Expired \-\> Terminate Process

## **41\. Mermaid Flow Diagram**

Code snippet  
flowchart TD  
    A\[Receive Execution Goal\] \--\> B{Model Loaded?}  
    B \-- No \--\> C\[Model Manager Spawns llama.cpp\]  
    C \--\> D\[Allocate VRAM & Load Qwen3\]  
    D \--\> E\[Assemble Prompt Context\]  
    B \-- Yes \--\> E  
    E \--\> F\[Execute LLM Inference\]  
    F \--\> G{Validate JSON Output}  
    G \-- Invalid \--\> H\[Append Retry System Prompt\]  
    H \--\> F  
    G \-- Valid \--\> I\[Return Plan DAG to CNS\]  
    I \--\> J\[Start Shutdown Grace Timer\]

## **42\. Mermaid State Diagram**

Code snippet  
stateDiagram-v2  
    \[\*\] \--\> Unloaded  
    Unloaded \--\> Loading : Task Request  
    Loading \--\> Ready : Model In VRAM  
    Ready \--\> Busy : Inference Started  
    Busy \--\> GracePeriod : Task Finished  
    GracePeriod \--\> Busy : New Task Arrives  
    GracePeriod \--\> Unloaded : Timer Expired (Release VRAM)

## **43\. Mermaid Folder Diagram**

Code snippet  
graph TD  
    Root\[organ\_01\_brain\] \--\> Bin\[bin/llama.cpp\]  
    Root \--\> Models\[models/qwen3-8b\]  
    Root \--\> Src\[src/\]  
    Src \--\> Core\[core/brain\_core.py\]  
    Src \--\> MM\[model\_manager/\]  
    Src \--\> Plan\[planner/\]  
    Src \--\> Prompt\[prompt/\]  
    Src \--\> Sock\[sockets/\]

## **44\. Mermaid Socket Diagram**

Code snippet  
graph LR  
    CNS\[CNS Client Organ\] \-- JSON-RPC over NamedPipe \--\> Pipe\[\\\\.\\pipe\\hojaiga\_brain\_ipc\]  
    Pipe \--\> IPC Server\[Brain IPC Server Listener\]  
    IPC Server \--\> Internal Queue\[Brain Task Queue\]  
    Internal Queue \--\> HTTP \[Local Loopback HTTP 127.0.0.1:8080\]  
    HTTP \--\> Llama\[llama.cpp Process\]

## **45\. Mermaid Pipeline Diagram**

Code snippet  
graph LR  
    Sub1\[1. Payload Ingestion\] \--\> Sub2\[2. Schema Validation\]  
    Sub2 \--\> Sub3\[3. Model Lifecycle Hook\]  
    Sub3 \--\> Sub4\[4. System Prompt Assembly\]  
    Sub4 \--\> Sub5\[5. GPU Inference\]  
    Sub5 \--\> Sub6\[6. Structural DSL Parsing\]  
    Sub6 \--\> Sub7\[7. Output Dispatch\]

## **46\. Engineering Recommendations**

* Enforce strict quantization verification (`Q4_K_M`) during startup to prevent accidental loading of fp16 models that would cause RTX 3050 Out-Of-Memory (OOM) faults.  
   MD  
* Utilize a 30-second grace period for auto-shutdown to balance response times for continuous tasks and immediate VRAM release for standalone jobs.  
   MD

## **47\. Tradeoffs**

* **Single LLM Engine vs. Multi-Model Pipeline:** Reduced parallel reasoning capabilities in exchange for strict compliance with the target hardware's 4 GB VRAM restriction.  
   MD  
* **Cold-Start Latency vs. Memory Footprint:** Loading model weights on demand incurs a 3-5 second delay on cold requests but ensures zero idle VRAM overhead.  
   MD

## **48\. Alternatives Considered**

* **vLLM / Ollama Services:** Rejected due to higher idle memory footprints and background runtime overhead compared to a tailored `llama.cpp` process lifecycle wrapper.  
   MD  
* **Dual-Model (7B Planning \+ 1.5B Fast Execution):** Rejected due to strict architectural constraint specifying a single Brain model instance.  
   MD

## **49\. Future Improvements**

* Implementation of custom speculative decoding models on host CPU to accelerate initial KV-cache processing.  
   MD  
* Fine-tuning specialized Qwen3 LoRA adaptors for precise Hojaiga DSL generation.  
   MD

## **50\. Claude Implementation Instructions**

1. Initialize directory structure as detailed in Section 6\.  
    MD  
2. Implement `model_manager/process_control.py` to handle `llama.cpp` invocation with parameters: `--n-gpu-layers 99 -c 4096 --temp 0.1`.  
    MD  
3. Implement `sockets/ipc_server.py` using Windows Named Pipes (`win32pipe`) / Unix Sockets.  
    MD  
4. Enforce JSON schema validation on every generation pass.  
    MD  
5. Validate VRAM clearance upon process lifecycle termination.  
    MD

