# 🚀 Meet2Mindmap (Live Spatial Tutor & Whiteboard Weaver)
### Complete 6-Day Hackathon Implementation Blueprint & Execution Guide

---

## 📌 1. Project Overview & Core Vision
**Meet2Mindmap** transforms long, static, and unengaging meeting transcripts or lecture audio streams into **live, structured, hand-drawn style mindmaps** on an infinite canvas. Instead of forcing users to scroll through blocks of text, this system visualizes logical progressions, causal loops, and conceptual branches in real time.

### The Problem
* **Cognitive Overload:** Text transcripts are dense, lack hierarchy, and fail to expose structural links between complex arguments.
* **Information Retention:** Users rarely review long documents or recorded lectures, leading to lost insights.

### The Solution
A **real-time audio ingestion pipeline** connected to a structured intelligence layout engine that extracts concepts and plots them instantly as hand-sketched boxes, circles, and directional arrows.

### The Technical Edge
1. **Low Latency:** Streaming audio window chunking processes text rapidly.
2. **Deterministic UI Bridge:** Combines flexible LLM spatial intuition with hard-coded relational canvas positioning.
3. **Immersive UI:** Utilizes the hand-drawn, sketch-like aesthetic of the canvas engine to make sessions feel organic.

---

## 🏗️ 2. Comprehensive System Architecture

```
[ Microphone Input / Audio Stream ]
                 │
                 ▼ (Continuous 5-7s Chunks)
┌────────────────────────────────────────────────────────────┐
│ PYTHON BACKEND (FastAPI + WebSockets)                     │
│                                                            │
│ 1. Ingestion Engine ──► Faster-Whisper (Local/API)         │
│                              │                             │
│                              ▼ (Raw Text Text Stream)       │
│ 2. Sliding Buffer ────► Aggregates Context Windows         │
│                              │                             │
│                              ▼ (Windowed Prompt Block)     │
│ 3. Pydantic-AI Layer ──► LLM Orchestrator (Ollama/Groq)   │
└──────────────────────────────┬─────────────────────────────┘
                               │
                               ▼ (Strict JSON Shape Deltas)
                     [ WebSocket Layer ]
                               │
                               ▼ (State Reducer Loop)
┌────────────────────────────────────────────────────────────┐
│ REACT FRONTEND (Vite + TypeScript)                         │
│                                                            │
│ 4. Rendering Canvas ──► tldraw SDK (Hand-Drawn Style)       │
└────────────────────────────────────────────────────────────┘
```

### Data Pipeline Flow
1. **Audio Layer:** Raw audio chunks are sent to a local `faster-whisper` model or a cloud audio endpoint.
2. **Context Windowing Engine:** Aggregates arriving text and buffers it. Every 5 seconds, it passes the text segment plus a historical map layout matrix to the LLM.
3. **Structured Intelligence Layer:** The LLM evaluates text and outputs an explicit delta change list (`new_nodes`, `new_edges`) using predefined JSON schema structures.
4. **Canvas Engine:** The React frontend parses the incoming JSON over WebSockets, looks up shape coordinates, and calls the canvas store interface to construct components instantly.

---

## 📋 3. Strict 6-Day Day-by-Day Implementation Roadmap

### 🗓️ DAY 1: Core Groundwork, Infrastructure & Ingestion Pipelines
* **Primary Objective:** Build the foundation of your execution stack. By tonight, speaking into your microphone must output text strings directly onto your backend developer terminal.
* **Step 1.1: System Environment Initialization**
  * Initialize your project folder structure exactly like this:
    ```
    meet2mindmap/
    ├── backend/
    │   ├── app.py
    │   └── requirements.txt
    └── frontend/
        ├── src/
        ├── package.json
        └── vite.config.ts
    ```
  * In the `backend/` folder, initialize a virtual environment: `python -m venv venv`. Activate it (`source venv/bin/activate` or `venv\Scripts\activate`).
* **Step 1.2: Install Audio Pipelines**
  * Run: `pip install fastapi uvicorn faster-whisper pyaudio channels websockets pydantic-ai pydantic`.
  * *Note on PyAudio:* If PyAudio installation fails on Windows, install it via `pip install pipwin` followed by `pipwin install pyaudio`. On Mac, run `brew install portaudio` before running `pip install pyaudio`.
* **Step 1.3: Develop the Streaming Audio Script**
  * Create `backend/audio_streamer.py`. Use `pyaudio` to open a continuous recording stream (16kHz, mono, 1024 chunk size).
  * Write a buffer thread that collects audio frames. Every 5 seconds, dump the raw binary data to a temporary in-memory file buffer and send it to `faster-whisper` (Base model).
* **Step 1.4: Validation Checkpoint**
  * Run the audio streamer script. Speak clearly into your microphone: *"This is a test of the Meet2Mindmap framework architecture."* Verify the console displays the exact text within 2 seconds of speaking.

### 🗓️ DAY 2: Structured Data Engine & LLM Schema Blueprinting
* **Primary Objective:** Enforce strict JSON output schemas on your LLM so it returns precise structural code parameters rather than open-ended explanations.
* **Step 2.1: Model Gateway Configuration**
  * Install **Ollama** on your machine. Pull the `llama3` model (`ollama pull llama3:8b`). Alternatively, if your system lacks a dedicated GPU, sign up for a **Groq API key** to handle remote high-speed text parsing.
* **Step 2.2: Define Strict Schemas**
  * In `backend/app.py`, define the Pydantic structural models for your canvas elements (`MindNode` and `MindEdge`). Ensure explicit variable type matching.
  * Define fields for unique ID tokens, text values, spatial grid vectors ($X, Y$), and visual element color states.
* **Step 2.3: Prompt Engineering Strategy & Spatial Math**
  * Instruct the LLM using custom system prompt criteria to calculate layout grid offsets. Ensure nodes do not stack at coordinates $(0, 0)$.
  * Use a simple radial bounding system: force the LLM to analyze existing nodes and offset new concepts by a minimum radius of 250 pixels.
* **Step 2.4: Integration Testing**
  * Hardcode a text string: *"Artificial intelligence requires data. Data feeds neural networks, which optimize weights using backpropagation."*
  * Execute your script and verify the output is a pristine JSON payload outlining nodes for "Artificial Intelligence", "Data", "Neural Networks", and "Backpropagation" complete with connecting relational arrows.

### 🗓️ DAY 3: Frontend Initialization & Canvas Engine Insertion
* **Primary Objective:** Build the visible canvas user interface and connect it to a mock backend streaming server.
* **Step 3.1: React & TypeScript Scaffold Setup**
  * Inside `frontend/`, run: `npm create vite@latest . -- --template react-ts`.
  * Install dependencies: `npm install @tldraw/tldraw lucide-react`.
  * Update your main app style sheets to remove standard document margins, ensuring the screen expands to a full viewport canvas.
* **Step 3.2: Mounting the Infinite Canvas Component**
  * Import `<Tldraw />` into your primary view controller page. Set up wrapper divs constraining layout bounds to `width: 100vw` and `height: 100vh`.
  * Use the `onMount` event handler loop to store a reference to the internal canvas `editor` instance in a state variable or React ref hook.
* **Step 3.3: Writing Programmatic Render Hooks**
  * Write a service utility file (`frontend/src/utils/canvasBridge.ts`). Create functions `drawNode(editor, node)` and `drawLink(editor, edge)`.
  * Use native canvas method calls like `editor.createShapes()` passing coordinates and configurations. Set the structural property parameter `dash: "draw"` to enforce the signature hand-drawn wireframe look.
* **Step 3.4: Mock Ingestion Testing**
  * Write a quick mock generator script that pushes synthetic node coordinates every 3 seconds to confirm your render state scales properly without blocking UI responsiveness.

### 🗓️ DAY 4: Connecting the WebSocket Architecture & State Synchronization
* **Primary Objective:** Connect your Python analytics engine to your React interface via live network hooks, making your system work end-to-end.
* **Step 4.1: Building the FastAPI WebSocket Server Router**
  * Update `backend/app.py` to handle incoming WebSocket handshakes at `/stream-graph`.
  * Ensure the server gracefully captures disconnect events to prevent system socket exhaustion during rapid live testing.
* **Step 4.2: Connecting the Audio Loop to the Data Framework**
  * Connect the Day 1 audio capturing thread to your FastAPI listener context.
  * **The Pipeline Integration:** Audio Stream ➔ Faster-Whisper Text ➔ Pydantic-AI/LLM Parser ➔ WebSocket Event Dispatcher.
* **Step 4.3: Building the React WebSocket Listener**
  * Create a custom hook in React (`useMindMapSocket`). Open a network connection to `ws://localhost:8000/stream-graph` when the canvas mounts.
  * Write an event parser that reads the arriving JSON stream, strips out raw metadata layers, and pushes the data structures directly to your canvas rendering hooks.
* **Step 4.4: End-to-End System Evaluation Checkpoint**
  * Start your backend and frontend apps. Speak into your microphone: *"We need a database, which will be connected to our server backend API."* Verify that two boxes linked by a directional arrow appear on your canvas within 5 seconds.

### 🗓️ DAY 5: Implementing "Canvas Commands" & Edge Case Minimisation
* **Primary Objective:** Build a key interactive feature to elevate your project and prevent interface layout collision bugs.
* **Step 5.1: The Canvas Command Extension Feature**
  * Enhance the frontend to support user interaction with the generated canvas.
  * Listen for double-click selection events on individual map shapes. Pull the selected node's text parameter into an input modal box.
  * Allow users to type custom directives like: *"Break this topic down into three sub-points."* Send this text along with the current node ID back to your backend over the WebSocket connection.
* **Step 5.2: Context Retention Strategy**
  * Prevent your backend AI from generating duplicate map blocks when analyzing long, continuous text streams.
  * Maintain a lightweight historical state record tracking all active node IDs and titles in a local Python list object. Include this list in your LLM system prompt so it links back to existing structures instead of rebuilding them.
* **Step 5.3: Visual Refinement Pass**
  * Standardize your element coloring logic: assign blue colors to central core concepts, green to secondary operational processes, and red to urgent timelines or warning indicators.

### 🗓️ DAY 6: Optimization, Polish & Preparing the Winning Demo
* **Primary Objective:** Bulletproof your application against failures, optimize run latency, and record an impactful project submission demo video.
* **Step 6.1: Memory Leak Mitigation & Canvas Optimization**
  * Run testing blocks spanning 10 continuous minutes of conversation. Ensure old nodes do not cause canvas UI stuttering.
  * Wrap your canvas event listeners inside React `useEffect` clean-up routines to prevent browser tab socket memory exhaustion bugs.
* **Step 6.2: Offline Sandbox Mode Configuration (The Winning Edge)**
  * If running models locally via Ollama and `faster-whisper`, configure your environment variables to disable external telemetry connections.
  * Test running your application while completely disconnected from the internet to prove your system operates as a fully air-gapped, secure deployment.
* **Step 6.3: Record Your Submission Pitch & Video Demo**
  * Structure a 3-minute video presentation layout:
    * **0:00 - 0:45:** The Pitch. Introduce the information retention problem and explain how Meet2Mindmap solves it.
    * **0:45 - 2:00:** The Core Demo. Speak live into your microphone and showcase the canvas rendering concepts in real time.
    * **2:00 - 2:30:** Interactive Feature Showpiece. Use your interactive canvas command to break down a node live on screen.
    * **2:30 - 3:00:** Technical Stack Architecture Review. Highlight your air-gapped data privacy strategy.

---

## 🛠️ 4. Explicit Implementation Code Blueprints

### Backend Framework Core (`backend/app.py`)
```python
import os
from typing import List, Literal, Optional
from fastapi import FastAPI, WebSocket
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel

app = FastAPI()

# Point to your local Ollama instance or update base_url for cloud endpoints
local_ollama_gateway = OpenAIModel(
    base_url="http://localhost:11434/v1",
    api_key="ollama", 
    model_name="llama3"
)

class MindNode(BaseModel):
    id: str = Field(description="Short alphanumeric identifier, e.g., 'node_tech'")
    label: str = Field(description="Punchy title string representing the topic (2-4 words maximum)")
    x: float = Field(description="Calculated grid X vector position. Space nodes cleanly apart.")
    y: float = Field(description="Calculated grid Y vector position. Space nodes cleanly apart.")
    color: Literal["black", "red", "blue", "green"] = "black"

class MindEdge(BaseModel):
    from_node: str = Field(description="Source Node identification string reference token")
    to_node: str = Field(description="Destination target Node identification string reference token")
    label: Optional[str] = Field(None, description="Optional brief label text describing the link")

class MindMapDelta(BaseModel):
    reasoning: str = Field(description="Internal design thoughts explaining why these updates match the transcript logic")
    new_nodes: List[MindNode] = Field(default_factory=list)
    new_edges: List[MindEdge] = Field(default_factory=list)

mindmap_agent = Agent(
    model=local_ollama_gateway,
    result_type=MindMapDelta,
    system_prompt=(
        "You are an expert real-time spatial cartographer. Your task is to transform conversational text transcript "
        "streams into structured, logically linked node-graph architectures. Avoid positioning shapes directly "
        "on top of one another. Provide clean, calculated pixel coordinates ($X, Y$) separated by at least 200-300 units "
        "to ensure a clean, legible layout. Keep titles brief and professional."
    )
)

@app.websocket("/stream-graph")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Capture speech-to-text string inputs sent via your ingest engine thread
            raw_transcript_stream = await websocket.receive_text()
            
            # Execute schema extraction via our structured LLM orchestrator layer
            analysis_output = await mindmap_agent.run(raw_transcript_stream)
            
            # Dispatch JSON modifications back to the frontend canvas layer
            await websocket.send_json(analysis_output.data.model_dump())
    except Exception as network_error:
        print(f"Network channel disconnected or caught an exception: {network_error}")
    finally:
        await websocket.close()
```

### Frontend Render Hook (`frontend/src/hooks/useMindMapSocket.ts`)
```typescript
import { useEffect, useRef } from 'react';
import { Editor, createShapeId } from '@tldraw/tldraw';

interface NodeStructure {
  id: string;
  label: string;
  x: number;
  y: number;
  color: string;
}

interface EdgeStructure {
  from_node: string;
  to_node: string;
  label?: string;
}

interface IncomingDataStream {
  reasoning: string;
  new_nodes: NodeStructure[];
  new_edges: EdgeStructure[];
}

export function useMindMapSocket(editor: Editor | null) {
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!editor) return;

    // Initialize connection to the backend pipeline socket channel
    const socket = new WebSocket('ws://localhost:8000/stream-graph');
    socketRef.current = socket;

    socket.onmessage = (event) => {
      const payload: IncomingDataStream = JSON.parse(event.data);

      // Perform a batch update to update elements efficiently
      editor.store.transact(() => {
        // Render arriving nodes
        payload.new_nodes.forEach((node) => {
          editor.createShapes([
            {
              id: createShapeId(node.id),
              type: 'geo',
              x: node.x,
              y: node.y,
              props: {
                geo: 'rectangle',
                text: node.label,
                color: node.color as any,
                dash: 'draw', // Hand-drawn aesthetic
                size: 'm',
              },
            },
          ]);
        });

        // Render connecting directional links
        payload.new_edges.forEach((edge) => {
          editor.createShapes([
            {
              id: createShapeId(`edge_${edge.from_node}_${edge.to_node}`),
              type: 'arrow',
              props: {
                fill: 'none',
                dash: 'draw',
                start: {
                  type: 'binding',
                  boundShapeId: createShapeId(edge.from_node),
                  normalizedAnchor: { x: 0.5, y: 0.5 },
                  isExact: false,
                },
                end: {
                  type: 'binding',
                  boundShapeId: createShapeId(edge.to_node),
                  normalizedAnchor: { x: 0.5, y: 0.5 },
                  isExact: false,
                },
              },
            },
          ]);
        });
      });
    };

    return () => {
      socket.close();
    };
  }, [editor]);

  return socketRef.current;
}
```

---

## 🏆 5. Hackathon Judging Matrix Alignment Strategy

To win your hackathon division track, frame your code presentation around these core evaluation pillars:

* **Technical Complexity (The "How It Works" Pillar):** Emphasize your use of strict data structures (`Pydantic-AI`) to build a predictable, transactional graph state, rather than just streaming raw text to a basic chat interface.
* **Design & User Experience (The "Wow" Pillar):** Emphasize how your real-time visual canvas addresses the issue of cognitive fatigue caused by reading walls of text. Show how it instantly visualizes concepts into a clean, sketch-like layout.
* **Practical Utility (The "Real-World Impact" Pillar):** Highlight the system's strict focus on data security. Show that your application can run fully locally, protecting sensitive lecture, corporate, or financial conversations from external data leaks.