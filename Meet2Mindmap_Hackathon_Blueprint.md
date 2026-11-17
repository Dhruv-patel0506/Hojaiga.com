# 📈 Meet2Mindmap (Live Spatial Tutor & Whiteboard Weaver)
### Comprehensive Hackathon Implementation Blueprint & 6-Day Execution Plan

This document serves as the master specification sheet, technical architecture guide, and step-by-step 6-day execution playbook for **Meet2Mindmap**. This project converts messy, unstructured spoken audio (lectures, meetings, brainstorms) into a dynamic, real-time, hand-sketched spatial mindmap on an infinite digital canvas.

---

## 🏛️ 1. Project Specifications & Architectural Pillars

### The Core Problem
Traditional meeting recorders and lecture note-takers output massive, static walls of text (transcripts) that suffer from near-zero post-event engagement. Humans process visual spatial relationships 60,000 times faster than text, yet toolsets remain locked in document views.

### The Solution: Meet2Mindmap
A dual-engine pipeline that intercepts audio, extracts conceptual nodes and relational directional dependencies using a structured LLM pipeline, maps them into dynamic 2D coordinates, and visualizes them instantly on an infinite hand-drawn whiteboard canvas.

### Full Tech Stack Selection
*   **Audio Pipeline:** Python `sounddevice` + `faster-whisper` (Local option using the `base.en` or `small.en` quantized weights) OR **Deepgram/OpenAI Whisper API** (Cloud option for 100% processing stability).
*   **Backend Server:** **FastAPI** (Python 3.11+) utilizing **WebSockets** for persistent, low-latency, full-duplex client-server data streaming.
*   **Structured AI Orchestration:** **Pydantic-AI** framework combined with an **OpenAI-compatible local server (Ollama)** running `llama3:8b` or `qwen2.5:7b`, with a rapid configuration switch to **Groq API / OpenAI API** if local compute constraints arise.
*   **Frontend Interface:** **Vite + React + TypeScript** single-page application.
*   **Canvas Engine:** **@tldraw/tldraw SDK** (v2+), configured with native hand-drawn styles (`dash: "draw"`) for an organic classroom-whiteboard aesthetic.

---

## 🛠️ 2. Core System Architecture & Data Flow

```
[ Ambient Microphone Audio / Speaker Stream ]
                     │
                     ▼ (Continuous Audio Buffers via PyAudio/SoundDevice)
┌────────────────────────────────────────────────────────────────────────┐
│ 🐍 PYTHON BACKEND ENGINE (FastAPI Window)                              │
│                                                                        │
│ 1. Transcriber Layer: Chunks processed via Faster-Whisper               │
│ 2. Context Window Buffer: Accumulates raw transcript tokens            │
│ 3. Pydantic-AI Engine: Feeds structured prompts to LLM (Ollama/Groq)   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼ (Strict JSON Shape/Edge Deltas)
                          [ WebSocket Interface ]
                                    │
                                    ▼ (React Hooks Update Canvas Store)
┌────────────────────────────────────────────────────────────────────────┐
│ ⚛️ FRONTEND INTERFACE (React + Vite + TypeScript)                       │
│                                                                        │
│ 4. State Dispatcher: Intercepts JSON deltas from WS connection        │
│ 5. tldraw Canvas: Programmatically creates rectangles & arrows         │
└────────────────────────────────────────────────────────────────────────┘
```

### The Strict JSON Schema Payload
Every single state message emitted from the Python server across the WebSocket to the React frontend follows this deterministic JSON schema strictly validated by Pydantic:

```json
{
  "reasoning": "Detected transition from discussing photosynthesis reactants to light-dependent reactions.",
  "new_nodes": [
    {
      "id": "node_chloroplast",
      "label": "Chloroplast Organelle",
      "x": 450.0,
      "y": 200.0,
      "color": "green"
    },
    {
      "id": "node_thylakoid",
      "label": "Thylakoid Membrane",
      "x": 650.0,
      "y": 350.0,
      "color": "blue"
    }
  ],
  "new_edges": [
    {
      "from_node": "node_chloroplast",
      "to_node": "node_thylakoid",
      "label": "contains site of"
    }
  ]
}
```

---

## 📅 3. Comprehensive Day-by-Day Implementation Roadmap

### 🗓️ Day 1: Groundwork, Local Environments & Audio Pipelines
*   **Objective:** Establish operational local runtimes, test compute limitations, and successfully stream text out of spoken voice inside the terminal.
*   **Step 1.1 [Backend Setup]:** Initialize your local Python environment using `poetry` or `venv` (Python 3.11+). Install fundamental libraries: `pip install fastapi uvicorn faster-whisper sounddevice numpy pydantic pydantic-ai`.
*   **Step 1.2 [Ollama Verification]:** Download and execute the native **Ollama** desktop installer. Run `ollama pull llama3` or `ollama pull qwen2.5:7b` via terminal. Verify execution performance by sending a basic curl request to check standard token generation speeds on your system.
*   **Step 1.3 [Audio Capture Script]:** Author an isolated test file `audio_test.py`. Utilize `sounddevice` to capture raw input from the system's microphone in continuous 5-second buffers. Feed these raw numpy arrays into `faster-whisper` using the `base.en` quantization configuration.
*   **Step 1.4 [Sanity Check]:** End the day by standing in front of the laptop, speaking, and watching high-accuracy text strings print cleanly on the console window without crashing or dropping buffers.

### 🗓️ Day 2: The Structured JSON Backend Engine (AI Orchestration)
*   **Objective:** Transform unstructured transcripts into highly reliable, structured structural layout configurations.
*   **Step 2.1 [FastAPI Base Boilerplate]:** Build `main.py` configuring a foundational `FastAPI` instance with standard Cross-Origin Resource Sharing (CORS) middleware rules enabled. Add a standard WebSocket routing block path `/stream-graph`.
*   **Step 2.2 [Pydantic Models]:** Construct explicit Python definitions matching the schema framework (`MindNode`, `MindEdge`, `MindMapDelta`). Use Pydantic fields to hard-constrain property descriptions so the LLM explicitly understands the properties it must generate.
*   **Step 2.3 [Spatial Prompts Engineering]:** Write a rigorous system prompt instructing the model to act as a visual data architect. Force the model to calculate layout tracking positions dynamically (e.g., modifying `x` and `y` coordinates sequentially using 250px grid margins to prevent nodes from stacking on top of each other).
*   **Step 2.4 [State Test Mocking]:** Feed a pre-written multi-paragraph educational script into the backend execution pipeline, observing the output logs to ensure it yields valid JSON arrays without code formatting breaks or truncated blocks.

### 🗓️ Day 3: Frontend Canvas Initialization & WebSockets Setup
*   **Objective:** Bring the visual web browser environment to life and establish real-time data connection pipes.
*   **Step 3.1 [React Vite Scaffold]:** Execute `npm create vite@latest frontend -- --template react-ts`. Install core web elements: `npm install @tldraw/tldraw`. Verify that an interactive infinite grid displays in your web browser.
*   **Step 3.2 [WebSocket Context Listener]:** Write a custom React lifecycle hook (`useMindmapSocket.ts`) targeting `ws://localhost:8000/stream-graph`. Configure robust automatic reconnect retry counters to protect the frontend view state if the backend environment needs a rapid code reboot during presentation evaluations.
*   **Step 3.3 [tldraw Store Interceptor]:** Bind inbound payload signals directly into active `tldraw` instances using the functional hook interface on standard component mounts. Use `editor.store.transact()` to batch state operations cleanly, avoiding UI stuttering.
*   **Step 3.4 [Visual Verification]:** Wire up a basic browser button that injects dummy JSON nodes onto the canvas on demand, verifying that shapes display correctly on the canvas layer.

### 🗓️ Day 4: Mathematical Spatial Layout Engine & State Persistence
*   **Objective:** Mitigate overlap issues, prevent geometric cluttering, and optimize temporal long-term memory structures.
*   **Step 4.1 [Algorithmic Layout Enhancements]:** Implement a mathematical layout helper inside the backend logic. If the AI proposes an analytical node structure within a 150px proximity threshold of a previously logged element, apply an offset modifier to move the new node into open visual coordinates.
*   **Step 4.2 [Incremental Memory Windowing]:** Prevent the local AI from experiencing context window fatigue as your transcript lengths grow. Implement a shifting context queue that keeps the most recent 2 minutes of conversation text, while passing a compact list of existing node IDs so it knows how to attach new links correctly without recreating duplicate boxes.
*   **Step 4.3 [Dynamic Color Mapping]:** Map distinct color sets according to node themes (e.g., operational execution items use `blue`, critical conceptual definitions use `red`, completed themes use `green`).

### 🗓️ Day 5: Implement Canvas Commands ("The Wow Feature")
*   **Objective:** Add interactive two-way communication capabilities that differentiate your project from basic one-way dashboards.
*   **Step 5.1 [Whiteboard Canvas Interaction]:** Override `tldraw` UI configuration parameters to support secondary custom component overlays. Build a context-aware menu flag that triggers when a user clicks on a node.
*   **Step 5.2 [Canvas Commands Pipeline]:** Add a feature that allows users to select a specific node cluster and type or say a command like: *"Expand extensively on this specific concept."*
*   **Step 5.3 [Targeted Prompt Dispatching]:** Capture the command, bundle it with the target node's title, and prioritize it over the background microphone stream. This forces the local Llama instance to inject rich deep-dive notes directly into the chosen visual workspace sector.
*   **Step 5.4 [Polishing CSS & Aesthetics]:** Configure all `tldraw` geo props to use `dash: "draw"` and `fill: "semi"` to make the final application look like a clean, high-production whiteboard utility.

### 🗓️ Day 6: Performance Testing, Air-Gap Mocking & Demo Prep
*   **Objective:** Harden application stability, record polished project deliverables, and prepare for zero-connectivity scenarios.
*   **Step 6.1 [Stress Testing]:** Play a complex 5-minute technical recording into the microphone channel. Watch for potential memory leaks, coordinate drifting, or layout collisions, and fine-tune your backend buffer sizes accordingly.
*   **Step 6.2 [The Air-Gap Verification]:** Test the entire stack completely offline. Disconnect all external network paths (Wi-Fi, Ethernet) to ensure the local Ollama and Faster-Whisper engines process everything locally on your laptop without calling cloud resources.
*   **Step 6.3 [Hackathon Presentation Video Recording]:** Film a tight, concise 3-minute project walkthrough video. Spend 45 seconds explaining the core user problem, and dedicate the remaining time to showing the live real-time graph expanding organically as you speak.
*   **Step 6.4 [GitHub Project Submission Push]:** Organize your codebase repository. Draft a structured markdown README with installation instructions (`git clone`, `pip install`, `npm install`, `ollama run`), making it trivial for hackathon judges to verify and test your project locally.

---

## 🚀 4. Pro-Tips for Hackathon Success

1. **Prioritize the Visual Demo Setup:** Judges usually evaluate dozens of submissions rapidly. Ensure your demo starts over a visually engaging topic (e.g., *"How a Rocket Engine Works"* or *"The History of the internet"*) to generate immediate visual impact.
2. **Optimize VRAM Buffers Early:** If running an 8B model alongside React tools pushes your laptop to its performance limits, switch your model target parameter to `qwen2.5:3b` or route to the **Groq API Cloud Engine** using their free tier. This lets you swap from local compute to high-speed cloud infrastructure by simply changing a single base URL line of code.
3. **Use the "Hand-Drawn" Aesthetic:** Emphasize the unique whiteboard theme. The contrast of complex AI structure mixed with an informal, hand-drawn look makes the project highly memorable compared to generic dashboards.
