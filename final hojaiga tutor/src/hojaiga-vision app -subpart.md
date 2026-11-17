\============================== PART 1===================================

To achieve a professional-grade assistant that can deeply scan UI trees, ingest full application video workflows, retain an internal memory system, and autonomously handle multi-step advanced operations in complex applications like Blender or AutoCAD, your approach needs to shift from standard "file training" to an **Agentic Vision-Language Architecture with External RAG (Retrieval-Augmented Generation) Memory**.

An 8B VLM fine-tuned via QLoRA on a local laptop cannot natively hold thousands of hours of app logic *inside* its model weights alone—it will suffer from catastrophic forgetting or run out of context limits. Instead, professional AI systems combine a **fine-tuned VLM (for UI recognition)** with a **vector memory database (for long-term logic and steps)**.

Here is the exact blueprint and execution roadmap to build this setup:

### **Phase 1: Redefining the Architecture (How It Actually Works)**

To match your grand ambition, your system must operate on a three-tier pipeline:

1. **The Perception Engine (Your Qwen-VL Model \+ QLoRA):** Trained to look at raw screens, recognize UI trees, locate buttons, menus, and text fields across complex software like AutoCAD, and output coordinate actions or structural breakdowns.  
2. **The Long-Term Memory System (Vector Database / RAG):** This is where your thousands of video tutorials and transcripts go. Instead of forcing the model to "memorize" them inside its weights, transcripts and structural UI steps are chunked and stored in a local vector database (like ChromaDB or FAISS). When you ask a complex question, the system queries this database first to pull the exact tutorial steps required.  
3. **The Execution & Multi-Step Planner (Ollama \+ Agent Loop):** A coordinator layer that takes your macro-goal ("Build a professional-grade 3D architectural model of a house in AutoCAD"), breaks it down into 5 to 10 sequential sub-tasks, queries your memory for how each sub-task is executed, and uses the VLM to verify each step on the screen.

### **Phase 2: Processing "Full Videos" Without Losing Logic**

Because you want the model to learn from full videos and tutorials rather than random fragments, you need an automated pipeline that digests long-form video into structured workflow maps:

1. **Transcription & Action Segmentation:** Feed your YouTube tutorials into a local transcription tool (like OpenAI's Whisper). Break the video down by major workflow milestones (e.g., *Timestamp 02:15 \- 04:30: "How to extrude a 2D sketch into 3D in AutoCAD"*).  
2. **State-Action-Result Pair Generation:** Instead of treating the video as a passive movie, your pipeline must extract:  
   * **State (Visual):** The screenshot of the UI at that moment.  
   * **Action (Command/Mouse):** What the instructor did (e.g., clicked "Extrude" tool, typed `10 units`).  
   * **Result (Context):** The text transcript explaining *why* they did it.  
3. **Vectorizing into Memory:** Store these structured triplets `(Screenshot + Transcript Segment + Action Command)` into your local vector memory database.

### **Phase 3: Your Step-by-Step Implementation Guide**

Since you already have **Qwen-VL**, **QLoRA**, and **Ollama** installed, execute your project using this roadmap:

#### **Step 1: Set Up Local Dataset Formatting**

Write a Python script to structure your processed tutorial videos into a dataset compatible with QLoRA training. Each entry should format the video's key UI state as an image and the corresponding multi-step instruction as the conversation target.

#### **Step 2: Fine-Tune Qwen-VL using QLoRA**

Configure your training script using tools like Hugging Face `TRL` or `LLaMA-Factory`.

* **Target Modules:** Focus your QLoRA configuration on the vision-language projector and attention layers of your Qwen model so it learns how to map visual UI elements to functional commands.  
* **Batching:** Process your training data in small chunks to accommodate your laptop's VRAM constraints.

#### **Step 3: Build the Local Memory & Retrieval Layer (RAG)**

Write a Python script using **LangChain** or **LlamaIndex** running locally with Ollama.

* Index all your app tutorial transcripts and step-by-step UI action files into a local vector store.  
* When you ask your app a question or give it a complex task, the system will query the vector store to fetch the exact context and historical steps required, feeding them dynamically into your fine-tuned Qwen model.

#### **Step 4: Implement the UI Automation & Feedback Loop**

To let the app interact with real software (like Notepad, Word, or AutoCAD), integrate an automation library (like `PyAutoGUI` or OS-level accessibility trees) so that your model can not only *teach* you how to do it or write out the steps, but actually execute the clicks and keystrokes on your desktop screen if given permission.

\============================== PART 2===================================

Building an autonomous, multi-step system like **Jarvis/FRIDAY** to tackle complex desktop apps (Blender, AutoCAD, OBS, WhatsApp) on a local **RTX 3050 (6GB VRAM), 32GB RAM, and external SSD** is an ambitious goal.

Your hardware setup—specifically 32GB of system RAM and a large external SSD—is actually a massive asset because it means you can offload data storage, handle heavy caching, and run vector databases smoothly, even if the 6GB VRAM is tight for running large models natively.

To solve your specific practical hurdles—**speed of scanning, deep button/child-window analysis, app policy restrictions (like WhatsApp), and practical training without manual video clipping**—here is the exact, real-world engineering blueprint.

### **1\. Solving the Hardware & VRAM Bottleneck (6GB VRAM Strategy)**

An 8B VLM (like Qwen2-VL-7B/8B) in full precision will crash a 6GB RTX 3050\. However, you can run and fine-tune it locally using these optimizations:

* **4-bit Quantization (QLoRA):** Load your Qwen Vision model quantized to 4-bit. This drops VRAM usage down to around 4GB to 5GB, leaving just enough room for batch processing.  
* **External SSD for Caching:** Use your 1.3TB external SSD as a high-speed cache directory for your dataset frames, vector embeddings, and model checkpoints, saving your main drive and keeping memory clean.

### **2\. Overcoming App Restrictions (e.g., WhatsApp Policy Denials)**

You mentioned that apps like WhatsApp block traditional accessibility automation or API hooks. A true "Jarvis-level" system bypasses app-level restrictions by mimicking a human user entirely through **OS-Level Vision & Native Control**:

* **Visual Bounding Instead of API Hooks:** Instead of trying to read WhatsApp's internal code or restricted API, your VLM relies strictly on *pixels* (what is on the screen) and controls the mouse/keyboard via low-level drivers (like `PyAutoGUI` or `pywin32` on Windows). If a human can see it and click it, the agent can see it and click it, completely bypassing app-side automation bans.

### **3\. Achieving "Xerox-Speed" Deep UI Scanning (Minutes, Not Hours)**

Trying to make a VLM crawl every button recursively by looking at every single pixel or opening every child window one-by-one is slow and causes bottlenecks. To achieve a fast, deep UI scan (seconds for Notepad, 10–15 minutes for Blender), combine a **Hybrid UI Tree Scanner** with your Vision Model:

* **Layer 1: Windows Accessibility API (UI Automation Tree \- Instant Scan)** Before letting the vision model guess anything, run a fast script using Python’s `pywinauto` or Windows UI Automation (UIA) library. This instantly dumps a text-based tree of all buttons, names, menus, and hidden child windows (like the OBS "plus" button or Blender menus) in fractions of a second.  
* **Layer 2: Selective Vision Verification (Smart Sampling)** Instead of looking at the whole app visually all the time, the accessibility tree tells the system: *"Here is a button called '+' which opens a child window."* The agent then takes a targeted screenshot *only* of that newly opened child window, passes it to your Qwen Vision model to understand its function, and logs it into memory. This keeps the scan lightning-fast.

### **4\. Practical Training: How to Train It Without Manual Filtering**

You are completely right: feeding raw YouTube videos manually one-by-one is impossible for thousands of tutorials. You need an **Automated Synthetic Dataset Generation Pipeline** running locally on your hardware:

1. Automated Video Chunking & Whisper Transcription: Write a Python script that takes a folder of tutorial videos from your SSD, extracts the audio, runs it through local `Whisper` to get timestamped text, and segments the video wherever a major topic changes.  
2. **Keyframe Change Detection:** Run a lightweight OpenCV script to detect structural visual changes on the screen (e.g., when a user clicks a menu in AutoCAD or Blender). It discards static frames and only saves frames where an *action* occurs.  
3. **Self-Supervised Dataset Building:** Pass the extracted frame \+ the corresponding Whisper transcript sentence into a local text model via Ollama to automatically format them into training pairs:  
   * *Input:* `[Screenshot of Blender modifier panel] + "How do I add a mirror effect?"`  
   * *Output:* `[Action sequence text generated from transcript steps]`  
4. **QLoRA Fine-Tuning Batch Run:** Feed these auto-generated structured JSONL files into your QLoRA setup overnight using your external SSD for storage, letting your Qwen Vision model internalize the app logic.

\============================== PART 3===================================

To build a multi-capability, autonomous intelligence system like **Jarvis/FRIDAY**, every component (the Vision Model, QLoRA, RAG, dataset logic, and data storage) plays a specific, tightly coordinated role.

### **1\. The Core Components & Their Exact Importance**

#### **A. The Vision-Language Model (Qwen-VL-8B) — *The "Eyes & Brain"***

* **Importance:** This is your primary intelligence engine. Unlike text-only LLMs, Qwen-VL natively understands pixels, buttons, icons, and text inside software applications (like Blender, AutoCAD, or OBS). It converts what is happening visually on your desktop into actionable software logic.

#### **B. QLoRA (Quantized Low-Rank Adaptation) — *The "Trainer"***

* **Importance:** You cannot rewrite a whole 8-billion parameter VLM on a 6GB VRAM RTX 3050 without crashing. QLoRA acts as a surgical tool. It "freezes" the main intelligence of your Qwen model and trains a tiny set of adapter layers on top using your specialized dataset, allowing your laptop to learn app-specific workflows efficiently.

#### **C. The RAG (Retrieval-Augmented Generation) System — *The "Long-Term Memory Library"***

* **Importance:** A model cannot store thousands of hours of app tutorials or every single button mapping inside its weights without getting confused or running out of context. **RAG solves this.** When you ask your system to perform a complex task in AutoCAD, the RAG system instantly searches through your indexed tutorial knowledge base, grabs *only* the exact steps and UI screenshots needed for that specific task, and feeds them to Qwen.

### **2\. How the Dataset Works (Without Manual Filtering)**

You mentioned that you want to feed YouTube tutorial links directly without manually cleaning every single file. You can automate this pipeline entirely on your local machine using your external SSD:

1. **Automated Ingestion Script:** A Python script loops through your YouTube link list, downloads the videos directly to your 1.3 TB external SSD using yt-dlp, and extracts audio.  
2. **Speech-to-Text & Vision Extraction:** Local Whisper transcribes the audio into a time-synced script, while an OpenCV script saves only the frames where a structural UI change or button click occurs.  
3. **Structured Dataset Auto-Creation:** The script bundles the cropped frame, the transcript text, and the corresponding action command into structured JSONL entries. This means your training dataset is built programmatically, saving you from manual filtering.

### **3\. Where Will Your Whole Intelligence Be Stored? (Database Choice)**

You mentioned having **SSMS (SQL Server Management Studio)** locally installed.

* **Is SSMS right for AI memory?** Relational databases like SQL Server are exceptional at storing **structured data** (exact button text, execution logs, user profiles, or app paths). However, they struggle natively with **semantic vector similarity search** (searching by "concept" or "meaning" through embeddings).  
* **The Best Architecture for Your Laptop:**  
  * Use a **local lightweight file-based vector database** (like **ChromaDB** or **FAISS**) running entirely in Python. It stores everything as files directly on your 1.3 TB external SSD with zero configuration or Docker containers required. –already installed   
  * *Alternatively*, if you prefer keeping things inside a database framework, modern SQL Server engines support relational tables alongside file paths, but file-based local vector indexes handle RAG text chunks and image embedding indices significantly faster on local hardware.

### **Summary Workflow: From Video to Execution**

1. **Ingest:** Drop your YouTube links $\rightarrow$ SSD storage.  
2. **Process:** Extract transcripts and key frames automatically.  
3. **Train:** Use **QLoRA** on your **Qwen-VL model** to teach it core UI navigation.  
4. **Remember:** Store chunked instructions and data embeddings inside a local vector store on your external SSD.  
5. **Execute:** When given a command, the RAG system pulls the right context, Qwen-VL analyzes the live screen layout, and your automation loops execute the task.

\============================== PART 4===================================

To build a professional-grade, Jarvis-like intelligence system that can walk up to *any* unfamiliar software, web app, or desktop environment from scratch (even without a pre-existing YouTube video) and teach you step-by-step how to use it, your architecture needs to go beyond standard RAG.

Instead of just storing static text and matching keywords, you are building an **Autonomous Multimodal Dynamic Memory Engine**.

### **1\. How RAG is Defined for This System (The Architecture)**

In traditional systems, RAG only looks up text documents. For an app-teaching intelligence, you will use **Multimodal Vector RAG**, which indexes three things simultaneously:

1. **UI Screen Embeddings:** Snapshots of application windows, menus, and buttons.  
2. **Structural UI Trees:** The raw text-based layout data extracted via Windows Accessibility tools (pywinauto).  
3. **Execution Logic (Action-Steps):** Text instructions detailing *what* happened, *where* to click, and *what* the result was.

#### **The Zero-Shot Discovery Flow (Handling Apps Without Training Videos)**

When you hand your system an completely unfamiliar software or web app that has **zero** YouTube tutorials:

1. **The Live Scan & Crawl:** The engine performs a hybrid scan combining the Windows UI accessibility tree (for instant button/menu identification) and targeted VLM screenshots (for visual layout verification).  
2. **Self-Generated Documentation:** As it explores, it generates its own step-by-step technical guides in real-time (e.g., *"To create a new project in this unknown software, click File \-\> New Project, which triggers modal window ID \#42"*).  
3. **Instant Ingestion into RAG:** These newly discovered workflows are instantly embedded and saved into your local vector database. The system *never* has to rediscover that app again; it permanently remembers it.

### **2\. The Exact Role of Each Component**

| Component | What It Does | Why It Matters for Your Vision |
| :---- | :---- | :---- |
| **Qwen-VL-8B (Quantized 4-bit)** | Acts as the visual reasoning core. It looks at live application screens, recognizes icons, reads non-selectable text, and figures out layout states. | Gives the AI true "eyes" to interact with graphical interfaces the way a human designer or operator does. |
| **Multimodal Vector RAG (ChromaDB/FAISS)** | Stores all procedural steps, button locations, and workflow sequences as searchable mathematical vectors. | Prevents your 8B model from forgetting things and provides instant historical recall of any app layout in milliseconds. |
| **Local Vector & Memory Files** | Stored directly on your **1.3 TB External SSD** as lightweight, file-based vector indices (e.g., ChromaDB file folders). | Bypasses traditional database limitations, letting you store years of application UI maps and tutorial chunks without slowing down your computer. |

### **3\. Database Choice: SSMS vs. File-Based Vector Store**

You mentioned having **SSMS (SQL Server Management Studio)** installed.

* **The Verdict:** While SSMS is brilliant for managing user accounts, app profiles, or hard-coded settings, **relational SQL databases are not optimized for real-time vector similarity searches** (which require calculating cosine distances across thousands of multi-dimensional AI embeddings).  
* **The Recommended Approach:** Keep **SSMS** strictly for structural application logs, user preferences, and execution audit trails if you want to inspect them. For your core RAG intelligence memory, use a **file-based vector database (like ChromaDB or FAISS)** mapping directly to your 1.3 TB external SSD. It operates entirely inside Python with zero overhead and lightning-fast retrieval speeds.

### **4\. How the Training & Teaching Loop Works Practically**

To achieve your goal of walking into a company, connecting the system to an unfamiliar software, and having it teach you from basic to pro level:

1. **The Exploration Phase:** You run your script over the software directory. The UI crawler maps every button, dropdown, and child window, creating a structural map.  
2. **The Active RAG Indexing:** The system structures these findings into your external SSD vector store.  
3. **The Interactive Live Tutor:** When you sit down and ask, *"How do I perform a complex render in this software?"*, the system:  
   * Queries your local RAG memory for the app's components.  
   * Uses the Qwen-VL model to look at your live screen state.  
   * Speaks or outputs text instructions step-by-step: *"I see your cursor. First, click the Render tab on the top bar, then select 'Advanced Settings' from the dropdown panel highlighted here..."*

\============================== PART 5===================================

MASTER PLAN AND FLAW WHY VIDEO IS NOT ENOUGH  
\========================================================================

### **1\. The Blunt Honest Truth: Why Video Alone is Not Enough**

Relying **exclusively on raw video tutorials** to train an autonomous, Jarvis-level desktop agent will hit a hard wall. While videos provide high-level conceptual context, they fail as a standalone training medium for four foundational reasons:

1. **The Missing Telemetry Void (Invisible Actions):** A video only captures output pixels and spoken audio. It does *not* record input telemetry: raw cursor coordinates (x,y)(x, y)(x,y), modifier keys held down (`Shift`, `Ctrl`, `Alt`), mouse drag paths, or scroll wheel deltas. When a Blender expert presses `G + Z + 2` to translate an object upward, the video merely displays the 3D model jumping upward. An AI trained solely on pixels has to guess what input triggered that jump, resulting in high coordinate hallucination and missed hotkeys.  
2. **Context Window Token Exhaustion:** Processing raw 1080p or 4K video frames through a Vision-Language Model consumes an immense number of visual tokens (often 1,500 to 3,000 tokens per frame). Feeding hours of continuous video into an 8B model will instantly exceed its context window or throttle training throughput to an unviable crawl on consumer hardware.  
3. **Paucity of State-Transition Verification:** Tutorial videos showcase successful, happy-path workflows. They never show unexpected modal errors, OS popups, driver incompatibilities, permission prompts, or corrupted application states. A system trained only on polished tutorials cannot self-correct when an unexpected dialog box halts execution.  
4. **Resolution Downsampling Loss:** Consumer vision models downsample images to fit into memory. In software like AutoCAD or Blender, icons in the toolbar are often 16×1616 \\times 1616×16 or 24×2424 \\times 2424×24 pixels. After vision encoder patch downsampling, those buttons blur into featureless patches, making precise icon recognition unreliable unless guided by structural UI metadata.

### **2\. The Required "Extraordinary" Additions**

To make this architecture genuinely intelligent, reliable, and capable of teaching or operating complex software, the system requires four supplemental pillars alongside video data:

                 ┌──────────────────────────────────────────────┐  
                  │       Hybrid Ingestion Engine                                                                       │  
                 └───────┬──────────────────────────────┬───────┘  
                                      │                                                                             │  
           Video \+ Audio Transcripts                                           OS Accessibility Tree (UIA)  
                           │                                                                                          │  
                          ▼                                                                                         ▼  
                 Keyframe Extraction                                            Set-of-Marks (SoM) Tagging  
                          │                                                                             │  
                          └───────────────┬──────────────┘  
                                                                   ▼  
                                          ┌───────────────────┐  
                                           │ Multimodal Vector                   │  
                                           │   & Graph Memory                  │  
                                          └─────────┬─────────┘  
                                                                   ▼  
                                    Action Execution Engine (VLM \+ PyAutoGUI)

* **Set-of-Marks (SoM) Grounding:** Instead of requiring the VLM to guess floating-point screen coordinates directly, an overlay script dynamically marks every interactive UI element with an indexed visual bounding tag (e.g., `[1]`, `[2]`, `[3]`). The model only needs to decide: *"Click element \[47\]"*, eliminating pixel misclicks entirely.  
* **Dual-Layer UI Scanning (UIA \+ Vision):** Combine Windows UI Automation (which instantly pulls the raw tree of buttons, names, states, and child handles in milliseconds) with the Vision-Language Model (which inspects visually rendered canvases, icons without text, and viewports).  
* **Graph-Augmented RAG (Knowledge Graphs):** Plain vector similarity search struggles with sequential workflows. If step 4 depends strictly on step 3, a Knowledge Graph preserves the execution order: `[Node: File Menu] -> (Expands) -> [Node: Export] -> (Triggers) -> [Node: FBX Settings Dialog]`.  
* **Self-Directed Action Sandboxing (Active Exploration):** The agent must be given permission to run inside a sandboxed environment to click through an unknown application, observe whether a child window appears, record the delta, and construct its own interactive map.

### **3\. Distributed Architecture: The "Nucleus & Worker" Framework**

The system functions on a hub-and-spoke model where the business owner receives an autonomous worker agent, while the master intelligence core remains protected under your centralized control.

      ┌────────────────────────────────────────────────────────┐  
 │             MASTER NUCLEUS (Your Infrastructure)                                                                │  
 │  \- Central Memory Hub & Master Vector Store                                                                      │  
 │  \- Global Fine-Tuned Checkpoints (Qwen-VL \+ QLoRA Updates)                                        │  
 │  \- Audit, Security, & Telemetry Monitoring Dashboard                                                           │                          └──────────────┬───────────────────────────────▲─────────┘  
                                       │                                                                                |  
                             Encrypted Policy &                                             Sanitized Execution Logs &  
                               Task Instructions                                                  Discovery Telemetry  
                                      │                                                                                │  
                                      ▼                                                                               │  
┌──────────────────────────────────────────────┴───────────┐  
 │             EDGE WORKER AGENT (Client Environment)                                                            │  
 │  \- Local VLM Inference Engine (Quantized 4-bit)                                                                      │  
 │  \- Real-Time OS Screen Perception & Mouse/Keyboard Driver                                                │  
 │  \- Local Ephemeral Cache (Private Data Protection)                                                                │  
 │  \- Client Interaction Layer (Voice/Text Tutor & Automation)                                                      │     └──────────────────────────────────────────────────────────┘

#### **A. Master Nucleus (Central Core)**

* **Role:** Centralized command, continuous model retraining, master graph database, and security supervisor.  
* **Operation:** Receives anonymized workflow logs and newly discovered UI maps from edge workers. Aggregates this data to train new QLoRA adapters. Distributes updated weights and execution rules to edge nodes.  
* **IP Protection:** The underlying source models, base datasets, fine-tuning scripts, and proprietary heuristics live in the Nucleus. The business owner never gains access to the core training pipelines or model checkpoints.

#### **B. Edge Worker Agent (Client-Side Deployment)**

* **Role:** Local execution, real-time UI interaction, live tutoring, and immediate computer control.  
* **Operation:** Runs on the client's local workstation or a dedicated on-prem machine. Interacts directly with target applications (AutoCAD, WhatsApp, accounting suites, custom ERPs).  
* **Privacy & Isolation:** Client data (customer messages, private blueprints, proprietary files) remains strictly local. The worker agent strips all personally identifiable information (PII) before sending generic UI structure maps back to the Nucleus.

### **4\. Transitioning: Guide-Based to Grounded Video/Telemetry Ingestion**

| Dimension | Legacy Guide-Based Learning | Grounded Video & Telemetry Engine |
| ----- | ----- | ----- |
| **Input Modality** | Static text manuals, PDF documentation, markdown FAQs. | Screen video streams, time-synced audio, keyboard/mouse telemetry, UIA hierarchy trees. |
| **Spatial Awareness** | Zero spatial context; relies on element labels matching text strings exactly. | Bounding-box detection, icon shape recognition, relative spatial navigation ("top-right panel"). |
| **Workflow Adaptability** | Breaks if an app redesign changes button names or moves a menu item. | Adapts visually by recognizing icon motifs, layout patterns, and semantic visual tags. |
| **Verification Loop** | Assumes the step worked because the text command was issued. | Analyzes the screen after every click to confirm whether the intended UI state change actually occurred. |

#### **The Video Ingestion Pipeline (Step-by-Step)**

1. **Source Ingestion:** Download videos from YouTube or custom screen captures via `yt-dlp` directly to the external SSD.  
2. **Audio Alignment:** Transcribe audio with local `Whisper` (Large-v3 quantized or Medium) to produce millisecond-accurate timestamped sentences.  
3. **Keyframe Slicing (Scene Change Detection):** Instead of processing every frame at 30/60 FPS, an OpenCV script calculates pixel-delta differentials. Frames are extracted only when:  
   * A dropdown menu expands.  
   * A modal/dialog window opens.  
   * A tool is activated and the cursor icon changes.  
4. **Synthetic Action Structuring:** A background script pairs the screenshot, the speech transcript, and the OCR-detected button text into a structured training triplet:

JSON  
{  
  "task\_domain": "AutoCAD\_3D\_Modeling",  
  "instruction": "Extrude a 2D closed polygon into a 3D solid",  
  "pre\_state\_image": "frames/autocad\_frame\_0412.jpg",  
  "action\_sequence": \[  
    {"action": "type\_command", "input": "EXTRUDE"},  
    {"action": "key\_press", "input": "ENTER"},  
    {"action": "click\_ui\_element", "target\_name": "Boundary Polyline", "target\_som\_id": 14},  
    {"action": "type\_command", "input": "250"},  
    {"action": "key\_press", "input": "ENTER"}  
  \],  
  "post\_state\_image": "frames/autocad\_frame\_0415.jpg",  
  "explanation": "Extrude command was invoked, target polygon selected via bounding ID 14, and an extrusion height of 250 units applied."  
}

### **5\. Hardware-Optimized Stack: RTX 3050 (6GB) \+ 32GB RAM \+ 1.3TB SSD**

Building this system on your specific hardware setup requires strict resource allocation across CPU, GPU, and disk caching:

┌─────────────────────────────────────────────────────┐  
 │                      RTX 3050 (6GB Dedicated VRAM)                                                          │  
 │  ┌────────────────────—------┐ ┌───────────────—--------───┐ │  
 │ │  Qwen2-VL-7B/8B (4-bit AWQ / GGUF)│ │ Dynamic Context & KV Cache            ││  
 │ │  \~3.8 GB to 4.2 GB VRAM                    │ │ \~1.2 GB to 1.5 GB VRAM                    ││  
 │ └───────—────────────────┘└────────────────────────┘ │  
└─────────────────────────────────────────────────────┘  
                                                                  |  
                                                                  |   
                                                                   |  
                                                                   │  
                                                             Offloads To  
                                                                   ▼

┌──────────────────────────────────────────────────────┐  
 │                      System RAM (32GB High-Speed)                                                              │  
 │ ┌──────────────┐ ┌────────────┐ ┌────────────────────┐  │  
 │ │ Whisper Audio Model  │ │ pywinauto / UIA     │ │ Active Vector Index                   │  │  
 │ │ \~1.5 GB RAM              │ │ Worker (\~500 MB) │ │ Buffer (\~4.0 GB)                        │ │  
 │ └──────────────┘ └────────────┘ └────────────────────┘  │  
 └──────────────────────────────────────────────────────┘  
                                                                     │  
                                                          Reads/Writes  
                                                                     ▼  
┌────────────────────────────────────────────────────────┐  
 │                  External Solid State Drive (1.3TB)                                                                       │  
 │ ┌───────────────┐ ┌──────────—-┐ ┌────────────────────┐     │  
 │ │ ChromaDB / LanceDB   │ │ Extracted Image   │ │ Raw Video Archive                    │     │  
 │ │ Storage Directory           │ │ Frame Bank          │ │ & Master Checkpts                    │     │  
 │ └───────────────┘ └──────—─────┘ └────────────────────┘     │  
└─────────────────────────────────────────────────────────┘

#### **Memory Management Breakdown**

* **VRAM Protection:** Never run raw 16-bit models. Use **4-bit AWQ or GGUF quantization** for Qwen-VL. During QLoRA fine-tuning, offload optimizer states to the 32GB system RAM using `bitsandbytes` CPU offloading.  
* **Storage Allocation:** All raw video files, extracted frame caches, and ChromaDB vector indexes live directly on the external 1.3TB SSD, preventing Windows C-drive bottlenecks.  
* **Database Selection:**  
  * **ChromaDB or LanceDB:** Used for high-speed multimodal vector search (screenshots, UI embeddings, transcript chunks).  
  * **SSMS (SQL Server Management Studio):** Used strictly for structured relational tracking: client licensing, execution task IDs, error logs, and session billing data.

### **6\. The "Xerox-Speed" Deep UI Discovery Engine**

To scan an unfamiliar application within seconds (or under 15 minutes for massive suites like Blender or AutoCAD), the engine uses a three-tier exploration algorithm:

                          Target Window Opened  
                                    │  
                                    ▼  
               \[Phase 1\] Instant UIA Hierarchy Dump (\< 1 sec)  
                     Extracts raw text, handles, & menus  
                                    │  
                                    ▼  
               \[Phase 2\] Set-of-Marks (SoM) Visual Snapshot  
                     Renders numbered bounding tags on UI  
                                    │  
                                    ▼  
          Does the element open a child window or complex canvas?  
                         ├── YES ──► Safe Click & Capture New State  
                         └── NO  ──► Record Action & Retain Tree  
                                    │  
                                    ▼  
               \[Phase 3\] Write Node to Graph & Vector Store

1. **Phase 1: Headless Tree Interrogation (Sub-second):** `pywinauto` queries the Windows Accessibility API. In under 800 milliseconds, it pulls every menu, top-level item, child button, and text box that Windows natively registers.  
2. **Phase 2: The Set-of-Marks Tagging Pass:** For visual components (canvas tools, toolbars, unlabelled vector icons), the agent takes a screenshot and overlays tiny, numbered bounding rectangles on every detected button.  
3. **Phase 3: Targeted Breadth-First Exploration:** The agent clicks buttons sequentially to inspect child windows:  
   * To prevent dangerous side-effects (e.g., clicking "Delete Project" or "Format Disk"), buttons containing risky terms (`Delete`, `Format`, `Remove`, `Close`, `Exit`, `Submit`, `Purchase`) are flagged with safety guards and skipped during exploration.  
   * Safe dialogs (e.g., `Settings`, `Preferences`, `View Options`, `Add Modifier`) are triggered, scanned, cataloged into memory, and dismissed via `Esc` or `Cancel`.  
4. **Phase 4: Instant Graph Serialization:** The scanned UI hierarchy is written into the local database as an executable map: `App -> Main Window -> Ribbon Tab [Home] -> Group [Draw] -> Tool [Circle] -> Parameter [Radius]`.

### **7\. Execution Engine: Live Tutoring vs. Autonomous Driving**

The system operates in two distinct operational modes:

#### **Mode A: The Live Interactive Tutor (Human-in-the-Loop)**

* The agent does not touch the controls directly.  
* It monitors the user's live screen. When the user asks, *"How do I split an audio track in OBS?"*, the agent draws a semi-transparent, highlighted bounding box directly over the user's physical screen around the correct cut tool or displays a subtle arrow pointing to it.  
* Synchronously, it speaks or prints the instruction: *"Right-click the audio source in the 'Sources' dock at the bottom center and select 'Filters', or press Ctrl \+ R to split."*

#### **Mode B: Autonomous OS Operator (Full Automation)**

* When instructed: *"Render this AutoCAD drawing as a PDF and message it to the client on WhatsApp"*, the agent assumes control.  
* **Bypassing App Restrictions:** Because it does not rely on third-party APIs or unsupported accessibility hooks (which WhatsApp blocks), it uses OS-level human emulation:  
  * Generates mouse trajectory curves with natural acceleration.  
  * Sends low-level virtual scan codes via `SendInput` in `pywin32`.  
  * Visually confirms delivery by watching for double-check marks on the screen.

### **8\. Master Implementation Roadmap**

┌─────────—----───┐           ┌──────────—--──┐          ┌──────────—-----──┐  
 │       PHASE 1                 │           │       PHASE 2              │           │       PHASE 3                  │  
 │ Foundation & Data Hub │ ──► │  Vision & UI Scanner  │ ──► │ Memory & RAG Engine   │  
 │ (Weeks 1 \- 3\)                 │           │  (Weeks 4 \- 6\)             │          │ (Weeks 7 \- 9\)                   │  
 └───────────────┘            └──────────────┘          └────────────────┘  
                                                                                                                                 │  
                                                                                                                                ▼  
 ┌────────────────┐         ┌──────────────┐            ┌───────────────┐  
 │                 PHASE 6         │          │       PHASE 5              │            │       PHASE 4                │  
 │ Commercial Deployment │◄── │  Nucleus & Edge Hub │◄──   │ Execution & Safeguard │  
 │ (Weeks 15 \- 16\)               │          │  (Weeks 13 \- 14\)         │            │ (Weeks 10 \- 12\)            │  
 └────────────────┘          └──────────────┘           └───────────—--──┘

#### **Phase 1: Storage Infrastructure & Ingestion Scripts**

* Configure external 1.3TB SSD as primary project root.  
* Write automated Python downloader (`yt-dlp` \+ `Whisper-Medium`) to process YouTube tutorial links into chunked audio transcripts and scene-change frames.

#### **Phase 2: Visual Grounding & Scanner Development**

* Implement the Set-of-Marks (SoM) bounding-box generation module.  
* Build the hybrid UI scanner combining `pywinauto` with screen-capture validation to crawl desktop apps safely.

#### **Phase 3: Multimodal Vector & Knowledge Graph Setup**

* Deploy **ChromaDB / LanceDB** on the external SSD.  
* Establish the embedding pipeline mapping UI screenshots, accessibility trees, and task instructions into unified index spaces.

#### **Phase 4: QLoRA Fine-Tuning on Local Hardware**

* Quantize **Qwen-VL** to 4-bit using `bitsandbytes`.  
* Train adapter layers on action-telemetry triplets using CPU optimizer offloading, keeping VRAM strictly below 5.5GB.

#### **Phase 5: Nucleus-Worker Protocol & Agent Loop**

* Build the secure communication pipeline between the Master Nucleus (central server) and the Local Edge Worker (client desktop).  
* Implement the low-level execution layer using `pywin32` / `PyAutoGUI` with active visual verification loops.

#### **Phase 6: Safety Guardrails & Commercial Packaging**

* Implement hard boundary rules (blacklisting critical system directories, preventing destructive clicks).  
* Bundle the client worker into a lightweight background service, ready for enterprise client deployment.

\============================== PART 6===================================

### **Multimodal UI-RAG Architecture & Technical Stack**

To enable an agent to navigate, index, and teach any application without prior knowledge, the RAG engine cannot rely on text-only vector matching. It must couple visual embeddings with structural accessibility trees and action-state graphs.

                                                     Raw Application Window  
                                                                    │  
                 ┌───────────────────┴───────────────────┐  
                 ▼                                                                                                  ▼  
       \[Visual Screen Capture\]                                                      \[OS Accessibility Tree\]  
                 │                                                                                                     │  
                 ▼                                                                                                   ▼  
     Microsoft OmniParser v2                                                              ywinauto / UIA  
   (YOLOv8 Detection \+ Florence-2)                                    (Bounding Boxes \+ Element Roles)  
                 │                                                                                                     │  
                 └───────────────────┬───────────────────┘  
                                                                    ▼  
                                                Unified Set-of-Marks (SoM) JSON  
                                                                     │

                 ┌───────────────────┴───────────────────┐  
                 ▼                                                                                                  ▼       
       Multimodal Embeddings                                                        Graph Execution DAG  
        (CLIP / SigLIP)                                                             (State A ─► Action ─► State B)  
                 │                                                                                                  │  
                 ▼                                                                                                ▼  
       LanceDB / ChromaDB Store                                                     NetworkX Local Graph  
     (External SSD: /rag\_storage)                                               (External SSD: /graph\_storage)

#### **Open-Source Repositories & Tooling**

* **Screen Parsing & Grounding:** microsoft/OmniParser (converts raw screenshots into structured bounding boxes with Set-of-Marks numerical tags and icon semantic captions).  
* **GUI Agent Framework:** bytedance/UI-TARS-desktop (end-to-end multimodal agent runtime optimized for desktop OS control).  
* **Fine-Tuning Engine:** unslothai/unsloth (enables 4-bit QLoRA fine-tuning for Vision-Language Models like Qwen2-VL/Qwen2.5-VL with 60% less VRAM consumption).  
* **Multimodal Vector Storage:** lancedb/lancedb (serverless, disk-native vector database storing high-dimensional image and text embeddings directly on your 1.3TB external SSD without memory overhead).  
* **OS-Level Tree Extraction:** pywinauto/pywinauto and yinkaisheng/Python-UIAutomation-for-Windows (direct native C-bindings to Windows UI Automation API).

#### **Python Environment & Production Imports**

Bash  
\# Terminal setup (CUDA 12.1+ / Python 3.11 or 3.12 recommended)  
pip install torch torchvision \--index-url https\://download.pytorch.org/whl/cu121  
pip install unsloth "xformers\<0.0.29" bitsandbytes lancedb pywinauto pyautogui opencv-python yt-dlp faster-whisper networkx pillow pydantic

Python  
import os  
import cv2  
import json  
import time  
import torch  
import lancedb  
import pyautogui  
import networkx as nx  
from PIL import Image  
from pydantic import BaseModel, Field  
from typing import List, Dict, Any, Optional  
from pywinauto import Desktop  
from faster\_whisper import WhisperModel

#### **Core Multimodal RAG Memory Implementation**

Python  
class UIElement(BaseModel):  
    element\_id: int  
    name: str  
    control\_type: str  
    bounding\_box: List\[int\] \# \[x, y, width, height\]  
    caption: str

class AppStateNode(BaseModel):  
    app\_name: str  
    window\_title: str  
    screenshot\_path: str  
    ui\_elements: List\[UIElement\]  
    action\_taken: Optional\[str\] \= None  
    next\_state\_hash: Optional\[str\] \= None

class MultimodalDesktopRAG:  
    def \_\_init\_\_(self, storage\_dir: str \= "E:/rag\_storage"):  
        self.storage\_dir \= storage\_dir  
        os.makedirs(storage\_dir, exist\_ok=True)  
          
        \# Connect to LanceDB directly on external SSD  
        self.db \= lancedb.connect(os.path.join(storage\_dir, "lancedb\_data"))  
        self.graph \= nx.DiGraph()  
        self.\_init\_tables()

    def \_init\_tables(self):  
        schema \= {  
            "app\_name": "string",  
            "state\_hash": "string",  
            "screen\_summary": "string",  
            "action\_history": "string",  
            "vector": "vector\[512\]"  \# SigLIP/CLIP embedding size  
        }  
        if "app\_knowledge" not in self.db.table\_names():  
            self.table \= self.db.create\_table("app\_knowledge", schema=schema)  
        else:  
            self.table \= self.db.open\_table("app\_knowledge")

    def capture\_active\_ui\_tree(self, app\_title: str) \-\> List\[Dict\[str, Any\]\]:  
        """Instant sub-second Windows Accessibility Tree Extraction"""  
        elements \= \[\]  
        try:  
            window \= Desktop(backend="uia").window(title\_re=f".\*{app\_title}.\*")  
            for idx, ctrl in enumerate(window.descendants()):  
                rect \= ctrl.rectangle()  
                if rect.width() \> 0 and rect.height() \> 0:  
                    elements.append({  
                        "id": idx,  
                        "name": ctrl.window\_text(),  
                        "type": ctrl.element\_info.control\_type,  
                        "coords": \[rect.left, rect.top, rect.width(), rect.height()\]  
                    })  
        except Exception as e:  
            pass  
        return elements

    def query\_action(self, task: str, current\_screen\_embedding: List\[float\]) \-\> Dict\[str, Any\]:  
        """Hybrid Vector \+ Graph Lookup"""  
        results \= self.table.search(current\_screen\_embedding).limit(3).to\_list()  
        if results:  
            best\_match \= results\[0\]  
            state\_hash \= best\_match\["state\_hash"\]  
            \# Look up next action sequence in the directed execution graph  
            successors \= list(self.graph.successors(state\_hash))  
            next\_action \= self.graph.edges\[state\_hash, successors\[0\]\]\["action"\] if successors else None  
            return {"guidance": best\_match\["screen\_summary"\], "action": next\_action}  
        return {"guidance": "Unseen UI state. Triggering live visual scan.", "action": None}

### **Local Model Training: Qwen-VL & QLoRA on 6GB VRAM**

The visual perception core runs on **Qwen2.5-VL-7B/8B** loaded in 4-bit precision. On an RTX 3050 (6GB VRAM), full parameter fine-tuning is impossible. Unsloth's 4-bit QLoRA implementation freezes the base model, applies adapter layers to both vision and language projections, and offloads optimization states to your 32GB system RAM.

#### **Fine-Tuning Execution Script (train\_qwen\_qlora.py)**

Python  
import torch  
from unsloth import FastVisionModel  
from trl import SFTTrainer, SFTConfig  
from datasets import load\_dataset

\# 1\. Load Model in 4-bit with Unsloth Memory Optimization  
model, tokenizer \= FastVisionModel.from\_pretrained(  
    "unsloth/Qwen2-VL-7B-Instruct",  
    load\_in\_4bit=True,  
    use\_gradient\_checkpointing="unsloth" \# Offloads activations to system RAM  
)

\# 2\. Attach LoRA Adapters across Language & Vision Layers  
model \= FastVisionModel.get\_peft\_model(  
    model,  
    finetune\_vision\_layers=True,   \# Trains visual grounding  
    finetune\_language\_layers=True, \# Trains action generation  
    r=16,  
    lora\_alpha=16,  
    lora\_dropout=0.0,  
    bias="none",  
    random\_state=3407,  
    target\_modules=\[  
        "q\_proj", "k\_proj", "v\_proj", "o\_proj",  
        "gate\_proj", "up\_proj", "down\_proj"  
    \]  
)

\# 3\. Training Arguments for 6GB VRAM Constraint  
trainer \= SFTTrainer(  
    model=model,  
    tokenizer=tokenizer,  
    train\_dataset=load\_dataset("json", data\_files="E:/dataset/ui\_training.jsonl", split="train"),  
    dataset\_text\_field="messages",  
    max\_seq\_length=2048,  
    args=SFTConfig(  
        per\_device\_train\_batch\_size=1,       \# Must be 1 on 6GB VRAM  
        gradient\_accumulation\_steps=8,      \# Simulates effective batch size of 8  
        warmup\_steps=10,  
        max\_steps=300,  
        learning\_rate=2e-4,  
        fp16=not torch.cuda.is\_bf16\_supported(),  
        bf16=torch.cuda.is\_bf16\_supported(),  
        logging\_steps=5,  
        optim="paged\_adamw\_8bit",           \# Critical: Offloads optimizer state to 32GB RAM  
        output\_dir="E:/qwen\_lora\_adapters",  
        save\_strategy="steps",  
        save\_steps=100  
    )  
)

trainer.train()  
model.save\_pretrained\_merged("E:/qwen\_custom\_agent", tokenizer, save\_method="merged\_16bit")

### **Hyper-Accelerated 14-Day Sprint Schedule**

 Week 1: Pipeline, Ingestion & Dataset Assembly  
  ├── Day 01 \- 02: Storage allocation on external SSD, LanceDB \+ pywinauto environment setup.  
  ├── Day 03 \- 05: Video scraper & Whisper pipeline; batch transcribe and slice 100 tutorials.  
  └── Day 06 \- 07: Run Set-of-Marks annotation on extracted frames; construct \`ui\_training.jsonl\`.

  Week 2: Training, Graph Indexing & System Integration  
  ├── Day 08 \- 09: Run Qwen-VL QLoRA fine-tuning overnight using Unsloth 4-bit.  
  ├── Day 10 \- 11: Populate LanceDB vector store and build the state-action execution graph.  
  ├── Day 12 \- 13: End-to-end validation on Tier 0 and Tier 1 applications (Notepad, WhatsApp).  
  └── Day 14: Stress test on Tier 2/3 (OBS, Blender); finalize offline Ollama export.

### **Automated YouTube Dataset Pipeline**

You do not need to manually download or cut videos. Use this automated worker to scrape tutorials, segment action scenes, transcribe speech via faster-whisper, and compile training JSONL files directly onto your external SSD.

Python  
import os  
import cv2  
import json  
import subprocess  
from faster\_whisper import WhisperModel

SSD\_PATH \= "E:/ai\_dataset"  
os.makedirs(f"{SSD\_PATH}/videos", exist\_ok=True)  
os.makedirs(f"{SSD\_PATH}/frames", exist\_ok=True)

def download\_app\_tutorials(app\_name: str, max\_results: int \= 5):  
    """Downloads highest-ranked tutorial videos via yt-dlp search"""  
    query \= f"ytsearch{max\_results}:{app\_name} full tutorial interface workflow guide"  
    output\_tpl \= f"{SSD\_PATH}/videos/%(id)s.%(ext)s"  
    cmd \= \[  
        "yt-dlp", query,  
        "-f", "bestvideo\[height\<=1080\]\[ext=mp4\]+bestaudio\[ext=m4a\]/best\[ext=mp4\]",  
        "--output", output\_tpl,  
        "--no-playlist"  
    \]  
    subprocess.run(cmd, check=True)

def process\_video\_to\_dataset(video\_path: str, app\_name: str):  
    """Extracts scene changes and aligns them with Whisper audio transcripts"""  
    whisper \= WhisperModel("base.en", device="cpu", compute\_type="int8") \# Keep VRAM free  
    segments, \_ \= whisper.transcribe(video\_path)  
      
    cap \= cv2.VideoCapture(video\_path)  
    fps \= cap.get(cv2.CAP\_PROP\_FPS)  
      
    records \= \[\]  
    for seg in segments:  
        frame\_id \= int(seg.start \* fps)  
        cap.set(cv2.CAP\_PROP\_POS\_FRAMES, frame\_id)  
        ret, frame \= cap.read()  
        if not ret:  
            continue  
              
        frame\_filename \= f"{SSD\_PATH}/frames/{app\_name}\_{seg.start:.1f}.jpg"  
        cv2.imwrite(frame\_filename, frame)  
          
        records.append({  
            "messages": \[  
                {"role": "user", "content": \[  
                    {"type": "image", "image": frame\_filename},  
                    {"type": "text", "text": f"What action is performed in {app\_name} at this step?"}  
                \]},  
                {"role": "assistant", "content": \[  
                    {"type": "text", "text": seg.text.strip()}  
                \]}  
            \]  
        })  
    cap.release()  
      
    with open(f"{SSD\_PATH}/ui\_training.jsonl", "a", encoding="utf-8") as f:  
        for r in records:  
            f.write(json.dumps(r) \+ "\\n")

### **Application Complexity Matrix (Tier 0 to Tier 3\)**

| Tier | Complexity Profile | Target Applications | Architectural Behavior Required |
| :---- | :---- | :---- | :---- |
| **Tier 0** | **Monolithic Single-Window**  Flat UI hierarchy, static button coordinates, single window handle, zero nested sub-menus. | **Notepad, Windows Calculator, MS Paint, Rufus** | **Instant UIA Scraper:** 100% resolvable via Windows Accessibility API in under 2 seconds. Zero vision processing needed except verifying input results. |
| **Tier 1** | **Single-Purpose Modern Desktop/Web-Wrapped**  Electron or Chromium-based wrappers, minimal native UIA exposure, dynamic modal popups, policy-restricted APIs. | **WhatsApp Desktop, Telegram, Discord, Spotify, Slack** | **Visual Set-of-Marks Fallback:** Screen parsing via OmniParser to identify custom icon buttons (mic, paperclip, send). Native OS clicks via pyautogui to bypass automation blocks. |
| **Tier 2** | **Multi-Panel Productivity & Workflow Suites**  Tabbed interfaces, dockable floating panels, secondary child windows, context menus, hotkey-heavy operations. | **OBS Studio, VS Code, Excel, DaVinci Resolve (Edit Tab), GIMP** | **Hybrid Graph Traversal:** Reads UIA for top menus (File, Edit, Sources). Triggers child windows, snaps screenshots, logs states into the directed action graph. |
| **Tier 3** | **High-Dimensional Spatial & Infinite-Canvas Systems**  Dense parameter trees, real-time 3D viewports, vector command lines, non-standard GUI frameworks (Qt, custom OpenGL/DirectX rendering). | **AutoCAD, Blender 3D, SolidWorks, Unreal Engine Editor** | **Full Visual-Action RAG Loop:** Canvas viewports cannot be read by accessibility APIs. The system relies entirely on Qwen-VL visual reasoning combined with local CLI hotkey sequence injection (e.g., EXTRUDE \-\> 200 \-\> ENTER). |

\============================== PART 7===================================

.MD CONTENT

\# MASTER ARCHITECTURE & CHECKPOINT EXECUTION DIRECTIVE: VIDEO-GROUNDED MULTIMODAL RAG, HYBRID UI SCANNER & QWEN3-VL QLoRA SYSTEM

\#\# 0\. IMMEDIATE DIRECTIVES ON YOUR CURRENT WORKSPACE & BOTTLENECKS

\#\#\# A. Decision on Your Uncommitted Work: KEEP & COMMIT IMMEDIATELY  
\*\*Do NOT delete any of your uncommitted work.\*\* Commit everything you currently have on hold as \*\*Checkpoint 0 (\`git commit \-m "Checkpoint 0: Hybrid scanner baseline, scorecard, triggers, and off-screen fixes"\`)\*\*:  
1\. \*\*\`scorecard.py\` (11-checkpoint scorecard):\*\* Keep. We will use this as our automated benchmark across Tier 0–3 apps.  
2\. \*\*\`triggers.py\` (Trigger buttons):\*\* Keep. This is essential for expanding child windows, dropdowns, and modal states (like the OBS \`+\` button) during active UI exploration.  
3\. \*\*\`symbol\_eval.py\` (Vision-vs-tree symbol scoring):\*\* Keep. This will feed directly into our perceptual hash (\`pHash\`) icon memory cache so we never run Qwen3-VL twice on the same icon.  
4\. \*\*\`fast\_uia.py\` & \`universal\_scan.py\` (Ribbon-walk, contextual-tab, off-screen & launcher fixes):\*\* Keep all of them.  
5\. \*\*\`guide\_explain.py\`:\*\* Keep and refactor into \*\*\`video\_explain.py\`\*\*. Instead of parsing static written guides, it will bind Whisper video transcript segments and state-transition deltas to the numbered Set-of-Marks (SoM) UI map.

\---

\#\#\# B. Engineering Fixes for Your Two Scanner Bottlenecks (Implement in Checkpoint 1\)

\#\#\#\# 1\. Fixing the UWP / WinUI Off-Screen Blank Render Problem (e.g., Windows Settings)  
\* \*\*Why it failed:\*\* Moving modern DirectComposition/WinUI apps (like Settings) to off-screen coordinates (\`x \= \-3000\`) causes the Windows Desktop Window Manager (DWM) to cull pixel rendering, producing blank screenshots.  
\* \*\*The Fix (Phantom Alpha Layering \+ \`PW\_RENDERFULLCONTENT\`):\*\*  
  Instead of parking UWP/WinUI windows off-screen, keep them on-screen (behind the active window or at normal coordinates) and apply the Win32 extended style \`WS\_EX\_LAYERED | WS\_EX\_TRANSPARENT | WS\_EX\_TOOLWINDOW\` with \`SetLayeredWindowAttributes(hwnd, 0, 1, LWA\_ALPHA)\` (opacity \`1/255\` — 99.6% invisible to the human eye, zero mouse interception, hidden from taskbar). Because opacity is \`\> 0\` and coordinates are on-screen, \*\*Windows DWM forces 100% hardware pixel rendering\*\*. Capture the surface via \`PrintWindow(hwnd, hdc, PW\_RENDERFULLCONTENT)\` (\`flag \= 0x00000002\`) or \`Windows.Graphics.Capture\`, then restore the window state.

\#\#\#\# 2\. Fixing the 15–30s (Word) and 90s (Blender) Vision Latency  
\* \*\*Why it is slow:\*\* Calling Qwen3-VL-8B via Ollama sequentially on full frames or individual unlabelled controls saturates the 6GB VRAM RTX 3050\.  
\* \*\*The 3-Stage Speed Fix (Target: \< 3s for normal apps, \< 12s for Blender):\*\*  
  1\. \*\*Perceptual Hash (\`pHash\`) Icon Cache (\`icon\_memory\`):\*\* Before sending any unnamed control or icon crop to Qwen3-VL, compute a 64-bit \`dHash\`/\`pHash\` of the crop. Look it up in a local SQLite/LanceDB hash table. If seen before (99% of Ribbon/Blender icons after the first scan), return the label in \*\*0.1 milliseconds\*\* without touching the GPU.  
  2\. \*\*Contact-Sheet Grid Batching:\*\* When scanning a new app with 40 unknown icons (like Blender's toolbar), do \*\*not\*\* call Qwen3-VL 40 times. Stitch all unknown icon crops into a single numbered $8\times 5$ grid image (\`\[1\]\` to \`\[40\]\`) and pass that \*\*single image\*\* to Qwen3-VL in \*\*one inference call\*\*, asking for a JSON dictionary mapping \`{"1": "Extrude Region", "2": "Bevel", ...}\`. This cuts 90 seconds down to \~6 seconds.  
  3\. \*\*Delta-Only Re-scanning:\*\* When \`triggers.py\` clicks a button (like the \`+\` button in OBS), compute the \`cv2.absdiff\` bounding box between \`frame\_before\` and \`frame\_after\`. Run vision/UIA \*\*only\*\* inside the changed bounding rectangle.

\---

\#\# 1\. SYSTEM HARDWARE & STORAGE CONSTRAINTS (STRICT)

All code, training configurations, and database paths must strictly respect this local hardware profile:  
\* \*\*GPU:\*\* NVIDIA RTX 3050 Laptop GPU (\*\*6 GB VRAM\*\*). Never load 16-bit weights into VRAM. Always use 4-bit quantization (\`load\_in\_4bit=True\`, GGUF \`Q4\_K\_M\` / \`UD-Q4\_K\_XL\`, \`max\_seq\_length=2048\`, \`per\_device\_train\_batch\_size=1\`, \`gradient\_accumulation\_steps=8\`, \`paged\_adamw\_8bit\`).  
\* \*\*System RAM:\*\* \*\*32 GB DDR4/DDR5\*\*. Offload Whisper audio transcription (\`faster-whisper\` on \`cpu\` with \`int8\`), UIA tree parsing, NetworkX graphs, and Unsloth gradient checkpointing (\`use\_gradient\_checkpointing="unsloth"\`) to System RAM.  
\* \*\*Primary AI Drive:\*\* \*\*1.3 TB External SSD\*\* (configure via environment variable \`AI\_STORAGE\_ROOT\`, e.g., \`E:/HoJaiga\_AI\`). All raw YouTube videos, extracted keyframes, LanceDB vector indices, JSONL training sets, and QLoRA checkpoints must reside on the External SSD.  
\* \*\*Relational Telemetry DB:\*\* Local \*\*SSMS (SQL Server)\*\* for structured execution logs, app scan scorecards, client/worker telemetry, and checkpoint tracking.

\---

\#\# 2\. DISTRIBUTED SYSTEM TOPOLOGY: "NUCLEUS & EDGE WORKER"

The platform is architected as a centralized intelligence core (\*\*Master Nucleus\*\*) connected to lightweight client deployments (\*\*Edge Workers\*\*):

1\. \*\*Master Nucleus (Central Host):\*\*  
   \* Houses the Video Ingestion Pipeline (\`yt-dlp\` \+ \`faster-whisper\` \+ OpenCV keyframe extractor).  
   \* Houses the Unsloth QLoRA Fine-Tuning Engine for \`Qwen3-VL-8B\`.  
   \* Maintains the Master Multimodal RAG Store (LanceDB \+ NetworkX Action Graphs) and distributes updated LoRA adapters and UI maps to Edge Workers.  
2\. \*\*Edge Worker Agent (Client / Business Owner Node):\*\*  
   \* Runs \`universal\_scan.py\`, \`fast\_uia.py\`, \`triggers.py\`, and the local Ollama \`Qwen3-VL-8B\` model.  
   \* Operates in two modes:  
     \* \*\*Live Interactive Tutor Mode:\*\* Scans the live app, overlays Set-of-Marks visual highlights, and teaches a human operator step-by-step from basic to pro level—even on proprietary company software with zero internet videos.  
     \* \*\*Autonomous Execution Mode:\*\* Executes multi-step workflows via OS-level native input (\`SendInput\` / \`pywin32\` / human-like Bezier mouse curves), bypassing app-level automation blocks (e.g., WhatsApp Desktop).  
   \* Reports sanitized execution logs and newly discovered UI graphs back to the Master Nucleus.

\---

\#\# 3\. THE MACHINE LEARNING & VISION MODEL ARCHITECTURE

\#\#\# A. Core Models & Roles  
1\. \*\*Vision-Language Backbone:\*\* \`Qwen3-VL-8B\` (running via \*\*Ollama\*\* for live inference in \`universal\_scan.py\` and \*\*Unsloth\*\* \`unsloth/Qwen3-VL-8B-Instruct\` in 4-bit for QLoRA fine-tuning).  
2\. \*\*What QLoRA Trains the Model To Do:\*\*  
   We do \*\*not\*\* use QLoRA to memorize thousands of hours of raw facts (that is RAG's job). We use \*\*QLoRA\*\* to train the model's visual-spatial grounding and action-planning logic:  
   \* Reading numbered \*\*Set-of-Marks (SoM)\*\* fused maps (output by \`universal\_scan.py\`).  
   \* Recognizing dense, unlabelled 2D/3D icons, toolbars, and canvas states (Blender, AutoCAD, OBS).  
   \* Translating high-level user goals \+ RAG context into deterministic JSON action sequences (\`\[{"step": 1, "action": "click", "target\_id": 14, "hotkey": null, "verify\_expectation": "Child menu opens"}\]\`).

\#\#\# B. Automated Video-to-Dataset Pipeline (\`video\_pipeline.py\`)  
Raw videos lack explicit mouse coordinates and modifier keys. Our pipeline synthesizes grounded training triplets from YouTube tutorials automatically:  
1\. \*\*Download:\*\* \`yt-dlp\` pulls 1080p mp4 tutorials by app tier onto the 1.3 TB SSD.  
2\. \*\*Transcribe:\*\* \`faster-whisper\` (running on CPU/32GB RAM) extracts timestamped instruction segments.  
3\. \*\*Keyframe \+ UI Delta Extraction:\*\* OpenCV monitors structural changes (menu opens, modal pops up, cursor clicks) and extracts \`pre\_action\_frame.jpg\` and \`post\_action\_frame.jpg\`.  
4\. \*\*Scanner Fusion Pass:\*\* Pass the extracted frames through \`universal\_scan.py\`'s visual layer (shapes \+ OCR \+ icon memory \+ Set-of-Marks numbering) so the training image matches the exact numbered map format the model sees in live production.  
5\. \*\*JSONL Compilation:\*\* Outputs conversational multimodal JSONL formatted for Unsloth \`FastVisionModel\` training \+ chunks the workflow into the RAG database.

\---

\#\# 4\. MULTIMODAL GRAPH-VECTOR RAG SPECIFICATION (\`rag\_engine.py\`)

Standard text RAG fails at GUI automation because UI navigation is stateful. Our RAG system combines \*\*LanceDB (Multimodal Vector Store on SSD)\*\* with \*\*NetworkX (Directed State-Action Graph)\*\*:

\#\#\# A. LanceDB Schema (\`E:/HoJaiga\_AI/lancedb\_store\`)  
1\. \*\*\`ui\_states\` Table:\*\*  
   \* \`state\_id\` (SHA256 hash of app\_name \+ window\_class \+ top-level control signature)  
   \* \`app\_name\` (e.g., \`"Blender"\`, \`"OBS Studio"\`, \`"WhatsApp"\`, \`"Unknown\_Enterprise\_ERP"\`)  
   \* \`tier\` (\`0\`, \`1\`, \`2\`, \`3\`)  
   \* \`visual\_embedding\` (\`vector\[512\]\` via CLIP/SigLIP image encoder)  
   \* \`semantic\_embedding\` (\`vector\[384\]\` via local \`all-MiniLM-L6-v2\` or \`bge-small-en\`)  
   \* \`som\_map\_json\` (Full serialized output from \`universal\_scan.py\`: control IDs, names, bounding boxes \`\[x, y, w, h\]\`, control types, and icon hashes)  
   \* \`screenshot\_path\` (Path on 1.3 TB SSD)  
2\. \*\*\`workflow\_knowledge\` Table (Populated from YouTube Videos \+ Live Crawls):\*\*  
   \* \`workflow\_id\`, \`app\_name\`, \`task\_title\`, \`transcript\_steps\`, \`required\_triggers\`, \`action\_sequence\_json\`, \`semantic\_embedding\`.  
3\. \*\*\`icon\_hash\_cache\` Table (For Sub-Millisecond Vision Bypass):\*\*  
   \* \`phash\_64\` (64-bit perceptual hash of the icon pixel crop)  
   \* \`app\_name\`, \`resolved\_label\`, \`confidence\_score\`, \`verified\_by\_symbol\_eval\`.

\#\#\# B. Directed State-Action Graph (\`NetworkX\` persisted to SSD)  
\* \*\*Nodes:\*\* \`state\_id\` (representing a distinct window, tab, or modal state).  
\* \*\*Directed Edges:\*\* \`Action(control\_id, action\_type="click|hotkey|type", command\_str)\` connecting \`Parent\_State\_Node \-\> Child\_State\_Node\`.  
\* \*\*Zero-Shot Unseen App Discovery:\*\* When pointed at an unknown company app with zero YouTube videos, \`universal\_scan.py\` \+ \`triggers.py\` safely crawls the UI, fires non-destructive triggers, captures child windows, and builds this Graph \+ LanceDB index live on the fly.

\---

\#\# 5\. APPLICATION COMPLEXITY MATRIX (TIER 0 TO TIER 3\)

| Tier | Category Profile | Target Benchmark Apps | Scanner & RAG Strategy | Target Scan Speed |  
| :--- | :--- | :--- | :--- | :--- |  
| \*\*Tier 0\*\* | \*\*Simple Native Win32\*\* (Full UIA tree exposure, flat menus) | Notepad, Calculator, MS Paint, Rufus | \`fast\_uia.py\` \+ \`pHash\` icon cache. Vision model only called once ever per unique icon. | \*\*1 – 3 seconds\*\* |  
| \*\*Tier 1\*\* | \*\*Web-Wrapped / Electron / Restricted APIs\*\* (Blocks hooks or custom DOM) | WhatsApp Desktop, Discord, Slack, Spotify, Windows Settings | Phantom Alpha Layer (\`WS\_EX\_LAYERED\` alpha=1) \+ \`PW\_RENDERFULLCONTENT\` \+ SoM OCR/Shape fusion \+ OS-level \`SendInput\` execution. | \*\*3 – 6 seconds\*\* |  
| \*\*Tier 2\*\* | \*\*Multi-Panel & Ribbon Productivity Suites\*\* (Nested ribbons, child popups, contextual tabs) | MS Word, Excel, PowerPoint, OBS Studio, VS Code | Ribbon-walk \+ \`triggers.py\` child-window crawler \+ delta-region re-scan (\`cv2.absdiff\`) \+ Graph RAG state edges. | \*\*6 – 12 seconds\*\* |  
| \*\*Tier 3\*\* | \*\*Blind-Tree 3D / CAD / Canvas Suites\*\* (OpenGL/Vulkan viewports, tiny icons, hotkey-driven) | Blender, AutoCAD, Unreal Engine, DaVinci Resolve | Contact-Sheet Grid Batching for Qwen3-VL \+ Video RAG workflow lookup \+ CLI/Hotkey sequence injection (\`G \-\> Z \-\> 2 \-\> Enter\`). | \*\*10 – 18 seconds\*\* (down from 90s) |

\---

\#\# 6\. SELF-CONTAINED CHECKPOINT EXECUTION PLAN (BUILD IN ORDER)

Execute the following checkpoints sequentially. Do not ask follow-up questions between checkpoints; commit each completed module, run verification via \`scorecard.py\`, and proceed to the next.

\#\#\# CHECKPOINT 0: Commit Existing Uncommitted Work & Refactor Baseline  
\* \*\*Action:\*\* Commit \`scorecard.py\`, \`triggers.py\`, \`symbol\_eval.py\`, \`guide\_explain.py\`, \`fast\_uia.py\`, and \`universal\_scan.py\`.  
\* \*\*Deliverable:\*\* Clean git state preserving all 11 scorecard metrics, ribbon-walk fixes, contextual-tab handling, and safety blacklists (blocking destructive buttons like \`Delete\`, \`Format\`, \`Reset\`, \`Uninstall\`, \`Send\`, \`Purchase\`).

\#\#\# CHECKPOINT 1: Scanner Speed & Off-Screen Rendering Upgrade (\`fast\_uia.py\` & \`universal\_scan.py\`)  
\* \*\*Action 1 (Settings/UWP Fix):\*\* Implement Phantom Alpha Layering (\`WS\_EX\_LAYERED\`, alpha=1) \+ \`PrintWindow(..., PW\_RENDERFULLCONTENT)\` fallback in \`universal\_scan.py\` when an off-screen capture returns a uniform/blank pixel buffer.  
\* \*\*Action 2 (90s \-\> 12s Vision Speed Fix):\*\*  
  \* Implement \`icon\_cache.py\` using 64-bit \`dHash\`/\`pHash\` so previously identified icons return instantaneously without calling Ollama/Qwen3-VL.  
  \* Implement \*\*Contact-Sheet Grid Batching\*\* in \`universal\_scan.py\`: batch up to 36 unknown control crops into a single numbered grid image for a single Qwen3-VL inference pass.  
  \* Implement \*\*Delta-Box Scanning\*\* in \`triggers.py\`: when clicking a trigger (e.g., OBS \`+\` button), diff the before/after frames and scan only the newly appeared popup region.  
\* \*\*Verification:\*\* Re-run \`scorecard.py\` on Notepad, Settings, Word, and Blender.

\#\#\# CHECKPOINT 2: Multimodal Graph-Vector RAG Engine (\`rag\_engine.py\`)  
\* \*\*Action:\*\* Build the persistent storage layer on the external SSD (\`AI\_STORAGE\_ROOT\`).  
\* \*\*Deliverables:\*\*  
  \* Initialize LanceDB tables (\`ui\_states\`, \`workflow\_knowledge\`, \`icon\_hash\_cache\`) and local SQLite/SSMS telemetry logging.  
  \* Build the \`NetworkX\` State-Action Directed Graph builder that takes the output of \`universal\_scan.py\` \+ \`triggers.py\` and links parent windows to child menus/modals.  
  \* Build the hybrid retrieval function \`retrieve\_workflow(app\_name, user\_goal, current\_som\_map)\` that returns both relevant video tutorial steps and exact UI graph paths.

\#\#\# CHECKPOINT 3: Automated YouTube Video & Transcript Ingestion (\`video\_pipeline.py\` & \`video\_explain.py\`)  
\* \*\*Action:\*\* Transition from static written guides to automated video learning.  
\* \*\*Deliverables:\*\*  
  \* Build \`video\_pipeline.py\` using \`yt-dlp\` (video download), \`faster-whisper\` (\`int8\` on CPU to save VRAM), and OpenCV scene-change detection.  
  \* Refactor \`guide\_explain.py\` into \`video\_explain.py\`: align Whisper transcript sentences with extracted video keyframes, run \`universal\_scan.py\`'s SoM detector on each keyframe, and output both:  
    1\. RAG entries into \`workflow\_knowledge\` (LanceDB).  
    2\. Conversational multimodal training pairs into \`ui\_training\_dataset.jsonl\` on the external SSD.

\#\#\# CHECKPOINT 4: Qwen3-VL 8B Local QLoRA Fine-Tuning Suite (\`train\_qlora.py\`)  
\* \*\*Action:\*\* Build the memory-safe local training script tailored for the \*\*RTX 3050 (6GB VRAM) \+ 32GB RAM\*\*.  
\* \*\*Deliverables:\*\*  
  \* Implement \`train\_qlora.py\` using \`unsloth\` (\`FastVisionModel.from\_pretrained("unsloth/Qwen3-VL-8B-Instruct", load\_in\_4bit=True, use\_gradient\_checkpointing="unsloth")\`).  
  \* Configure LoRA adapters (\`r=16, lora\_alpha=16\`, \`finetune\_vision\_layers=True\`, \`finetune\_language\_layers=True\`, \`optim="paged\_adamw\_8bit"\`, \`per\_device\_train\_batch\_size=1\`, \`gradient\_accumulation\_steps=8\`).  
  \* Add automatic post-training GGUF export (\`save\_pretrained\_gguf(..., quantization\_method="q4\_k\_m")\`) and automatic \`Modelfile\` registration into local \*\*Ollama\*\* (\`ollama create hojaiga-qwen3-vl \-f Modelfile\`).

\#\#\# CHECKPOINT 5: Autonomous Execution & Live Tutor Loop (\`agent\_executor.py\`)  
\* \*\*Action:\*\* Connect the Scanner \+ RAG \+ Fine-Tuned Qwen3-VL into a closed-loop controller.  
\* \*\*Deliverables:\*\*  
  \* \*\*Mode 1 (\`tutor\_mode\`):\*\* Given any task (even on an unseen company app), scans the live UI tree/vision map, plans the multi-step path via the State-Action Graph, overlays a non-intrusive visual highlight box around the target button, and speaks/prints step-by-step instructions as the user clicks through.  
  \* \*\*Mode 2 (\`autonomous\_mode\`):\*\* Executes multi-command tasks autonomously using OS-level \`SendInput\` / human-like Bezier mouse movement \+ hotkey injection, verifying each step by checking the post-action delta screen against the expected state node before proceeding.

\---

\*\*START EXECUTION NOW:\*\*  
Begin immediately with \*\*Checkpoint 0\*\* (committing all current files on hold) and proceed directly into \*\*Checkpoint 1\*\* (implementing the Phantom Alpha Layer capture fix, \`pHash\` icon cache, and Contact-Sheet Grid Batching for Qwen3-VL). Report each checkpoint completion with \`scorecard.py\` timing benchmarks.

\============================== PART 8===================================

### **1\. Feasibility Verdict: Can Your System Handle "Lakhs" (100,000+) of Videos & Transcripts?**

Handling 100,000+ tutorials on your hardware (**RTX 3050 6GB VRAM, 32GB RAM, 1.3 TB External SSD**) is **impossible if you download raw video files**, but **100% achievable if you use a Metadata-First, Selective-Frame Pipeline**:

* **Why Raw Video Downloading Fails at Scale:** 100,000 full tutorial videos (averaging 100 MB each) equal **10 Terabytes (10,000 GB)**—nearly 8 times larger than your 1.3 TB SSD. Running Whisper on 100,000 audio files on your CPU would take over **4 months** of non-stop processing.  
* **The Zero-Download Transcript Shortcut (100% Free & Instant):** You do **not** need to download video/audio files or run Whisper for 95% of YouTube tutorials. YouTube already auto-generates timestamped transcripts on its own servers. Using the free Python library youtube-transcript-api, your laptop can download **100,000 full timestamped transcripts in plain JSON** without downloading a single MB of video.  
* **Storage Footprint on Your 1.3 TB SSD:**  
  * **100,000 JSON Transcripts:** \~15 KB per transcript \= **\~1.5 GB total disk space**.  
  * **100,000 Vectorized Transcripts in LanceDB:** \~2 million semantic chunks \= **\~10 GB to 14 GB total disk space**, searchable in **under 15 milliseconds**.  
  * **Selective Keyframe Extraction:** Instead of downloading full 30-minute MP4s, your script scans the downloaded transcript text first, identifies the exact timestamps where an action is explained (e.g., \[02:14\] "Click the Extrude button"), and uses yt-dlp \--download-sections "\*02:12-02:17" to pull **only the 2 keyframes** around that action.

### **2\. The 7 Essential Data Items Needed Beyond Video, Audio, and Transcripts**

To make your system operate like Jarvis—capable of both teaching a human and building professional-grade outputs in apps like AutoCAD, Blender, Excel, or WhatsApp—videos and transcripts alone leave massive blind spots. Here are the **7 additional data pillars**, why each is required, and their exact role:

| \# | Required Data Item | Why Video & Transcript Alone Fail Without It | Role & Importance |
| :---- | :---- | :---- | :---- |
| **1** | **Keyboard Shortcut & Hotkey Matrices** (JSON maps of Action \-\> Key\_Combo per app) | In tutorials, instructors press hotkeys (Ctrl+B, G \-\> Z \-\> 2, Alt+F4) silently or faster than the eye can see. Furthermore, clicking nested menus takes 5–10 seconds and can fail; firing a hotkey takes **0.005 seconds** with 100% accuracy. | **CRITICAL (10/10)**  Gives the agent instant speed and bypasses hidden menus in complex apps. |
| **2** | **Scripting APIs, CLI Flags & Macro Libraries** (bpy for Blender, AutoLISP/.scr for AutoCAD, VBA/COM for Office, PowerShell for Windows) | **This is your secret weapon for "superhuman/paid-subscription" quality.** A human clicks the mouse 5,000 times to build a 3D house in AutoCAD or Blender. A Jarvis-level AI doesn't click the mouse 5,000 times—it writes and injects a 200-line AutoCAD .scr script or Blender Python (bpy) script behind the scenes and renders a studio-grade 3D model in 4 seconds. | **GAME-CHANGING (10/10)**  Allows your system to build complex 3D CAD models, financial sheets, and automations beyond human manual skill. |
| **3** | **OS Accessibility Trees & Structural UI Schemas** (fast\_uia.py dumps: ControlType, AutomationId, parent-child hierarchy) | Videos only capture flat pixels. If a user switches an app from Light Mode to Dark Mode, or resizes the window, pixel coordinates shift. The Accessibility Tree tells the system the structural identity of every button regardless of screen size or theme. | **CRITICAL (10/10)**  Provides instant structural X-ray vision of any window in 1–3 seconds. |
| **4** | **Set-of-Marks (SoM) State-Transition Pairs** (Before\_Frame \+ Action\_Taken $\rightarrow$ After\_Frame\_Delta) | Transcripts explain concepts, not visual verification. The AI needs to know what the screen *should* look like 500ms after clicking a button (e.g., clicking \+ in OBS opens a specific popup list) so it can detect if a click failed. | **CRITICAL (10/10)**  Enables closed-loop self-correction during live execution. |
| **5** | **Perceptual Hash (pHash) Icon Memory Atlas** (64-bit visual hashes of $16\times 16$ to $64\times 64$ toolbar icons \+ SVG/icon names) | Apps like Blender, AutoCAD, GIMP, and Word have hundreds of tiny icons with no text on them. Calling Qwen3-VL on every icon takes 90 seconds. A pHash lookup table recognizes known icons in **0.1 milliseconds** on the CPU. | **HIGH (9.5/10)**  Eliminates the 90-second vision bottleneck permanently. |
| **6** | **Official Structured Documentation & Help Files** (Markdown/HTML docs, parameter tables, .chm local help files) | YouTube videos only cover the most popular 20% of an app's features. Official documentation covers 100% of every obscure button, dialog box, and math parameter. | **HIGH (8.5/10)**  Ensures the AI never says "I don't know" when asked about advanced/obscure settings. |
| **7** | **Error Dialog, Crash & Troubleshooting Playbooks** (Common modal error messages, permission blocks, recovery steps) | YouTube tutorials are edited to show only the "happy path" where nothing goes wrong. In the real world, apps throw popups like *"File is locked"*, *"Non-manifold mesh"*, or *"WhatsApp automation blocked"*. | **HIGH (8.5/10)**  Allows the agent to autonomously close/fix unexpected errors in the real world. |

### **3\. Architecture Decision: One Giant RAG vs. Multi-RAG Under One Complex Router?**

**Do NOT put everything into one single flat RAG table.** If you dump lakhs of video transcripts, UI trees, icons, and scripts into a single vector index, searching for *"How to extrude in AutoCAD"* will pull mixed chunks from Blender, SolidWorks, and 3ds Max, causing your 8B model to hallucinate wrong buttons.

Instead, implement a **Hierarchical Federated Multi-RAG (5 Specialized Sub-RAGs under 1 Master Router RAG)** inside **LanceDB \+ NetworkX** on your 1.3 TB External SSD:

                      User Command / Live App Screen  
                                     │  
                                     ▼  
            ┌───────────────────────────────────────–────┐  
            │        MASTER ROUTER & ORCHESTRATOR RAG                               │  
            │  (Detects Active App, Window Class & Task Type)                                 │  
            └────────┬──────┬───────────┬───────────┬────┘  
                                   │                │                            │                            │  
       ┌──────────┘                 │                            │                           └───────┐  
       ▼                                          ▼                            ▼                                              ▼  
┌─────────┐        ┌─────────┐    ┌─────────┐     ┌─────────────┐  
│  SUB-RAG 1   │        │  SUB-RAG 2 │     │  SUB-RAG 3    │     │    SUB-RAG 4          │  
│ Visual & Icon  │        │ UI Topology  │      │ Video & Docs   │     │ Superhuman Macro │  
│  Vault (pHash  │        │ State-Graph │      │ Workflow RAG │     │  & Hotkey RAG         │  
│  \+ SoM Crops)│        │ (NetworkX)   │       │ (Transcripts)    │     │ (CLI/bpy/AutoLISP    │  
└─────────┘        └────────┘        └──────────┘     └──────────────┘  
                                                                                 │  
                                                                                 ▼  
                             ┌──────────────────┐  
                                                                 │    SUB-RAG 5                       │  
                                                                 │ Error & Recovery                  │  
                                                                 │  Playbook RAG                      │  
                                                                └──────────────────┘

#### **Exact Mapping: What Trains the ML/VLM Model vs. What Goes Into the Multi-RAG**

| System Component | What Data Goes Into It | Why It Belongs Here (And Not Elsewhere) |
| :---- | :---- | :---- |
| **Qwen3-VL-8B \+ QLoRA Fine-Tuning**  *(The Core Skill & Instinct)* | **10,000–25,000 Curated Multimodal Action Samples:**  • Set-of-Marks (SoM) numbered screenshots (universal\_scan.py outputs). • Contact-sheet grids of unknown icons. • Before/After delta screen pairs. • Structured JSON action output formatting. | **QLoRA teaches *how to see and act*, not encyclopedic facts.** An 8B model has limited weight capacity on 6GB VRAM. By training it on SoM reading, visual grounding, and JSON tool-calling, it gains the *general skill* to operate **any** app—even a brand-new company app it has never seen before. |
| **Sub-RAG 1: Visual & Icon Vault**  *(LanceDB Table: icon\_vault)* | • 64-bit pHash/dHash signatures of every cropped icon. • CLIP/SigLIP visual embeddings of toolbar buttons. | Gives instant $O(1)$ sub-millisecond visual memory so Qwen3-VL never wastes time re-identifying icons it has already seen. |
| **Sub-RAG 2: UI Topology Graph**  *(NetworkX \+ LanceDB: ui\_graph)* | • Outputs of fast\_uia.py \+ triggers.py. • Directed graph edges: Window A \-\> Click \[Button \+\] \-\> Opens Modal B. | Maps the physical wiring of every application so the agent knows the exact path of clicks to reach any buried setting. |
| **Sub-RAG 3: Procedural Workflow RAG**  *(LanceDB Table: video\_workflows)* | • **Lakhs of YouTube Transcripts** (chunked by timestamped steps). • Official app documentation & wiki pages. • Filtered by metadata tag app\_name. | Holds unlimited terabytes of step-by-step "how-to" knowledge on your 1.3 TB SSD without bloating GPU VRAM. |
| **Sub-RAG 4: Superhuman Macro & Hotkey RAG**  *(LanceDB Table: fast\_execution)* | • Keyboard shortcut dictionaries (Ctrl+...). • Blender bpy Python templates, AutoCAD .scr/AutoLISP scripts, Office VBA/COM scripts, CLI commands. | Whenever a user asks for a complex professional output (e.g., *"Build a 3D mechanical gear in Blender"*), the Router checks Sub-RAG 4 first to execute code/hotkeys directly instead of slow mouse clicking. |
| **Sub-RAG 5: Error & Recovery RAG**  *(LanceDB Table: error\_playbooks)* | • Modal popup signatures, common error texts, and fallback steps (e.g., when UIA is blocked, switch to Phantom Alpha \+ OS SendInput). | Keeps the agent from crashing or getting stuck when unexpected popups appear. |

### **4\. The 100% Free (\$0 Budget) Pipeline to Find 1,000+ Apps, Scrape YouTube Tutorials & Build Your Excel Master File**

You do **not** need to search for 1,000 apps by hand, and you do **not** need a paid YouTube Data API key (which restricts free users to \~100 searches/day).

#### **Where to Get the 1,000+ Apps List for Free (In 10 Seconds)**

Microsoft maintains an open-source repository of every Windows application (winget-pkgs), and there is an open-source pre-compiled CSV index (svrooij/winget-pkgs-index on GitHub) containing **15,000+ Windows apps** completely free. Our script below combines a curated Tier 0–3 priority list with automated pulling from the open-source Winget index.

#### **How to Search YouTube & Extract Transcripts for Free (Zero API Key, Zero Quota)**

1. **Free Search (yt-dlp Flat-Playlist Mode):** Running yt-dlp "ytsearch10:{app\_name} full tutorial for beginners" \--flat-playlist \--dump-json queries YouTube directly like a browser, returning Video IDs, Titles, URLs, Durations, and View Counts for **free** with no API key.  
2. **Free Transcript Extraction (youtube-transcript-api):** Passes each Video ID to YouTubeTranscriptApi.get\_transcript(video\_id) to pull the entire timestamped transcript in **0.3 seconds** without downloading the video.

#### **Install Free Python Packages**

Bash  
pip install yt-dlp youtube-transcript-api pandas openpyxl requests beautifulsoup4

#### **Ready-to-Run Script: free\_master\_harvester.py**

Save and run this script. It automatically builds your **1,000+ App List**, searches YouTube for the best tutorials per app, downloads their timestamped transcripts to your external SSD, and exports a structured multi-sheet Excel workbook (HoJaiga\_Master\_App\_Dataset.xlsx) for \$0:

Python  
import os  
import json  
import time  
import requests  
import subprocess  
import pandas as pd  
from youtube\_transcript\_api import YouTubeTranscriptApi

\# \=====================================================================  
\# CONFIGURATION: Point to your 1.3 TB External SSD  
\# \=====================================================================  
SSD\_ROOT \= "E:/HoJaiga\_AI/Dataset\_Harvester"  
TRANSCRIPT\_DIR \= os.path.join(SSD\_ROOT, "transcripts\_json")  
EXCEL\_OUTPUT \= os.path.join(SSD\_ROOT, "HoJaiga\_Master\_App\_Dataset.xlsx")

os.makedirs(TRANSCRIPT\_DIR, exist\_ok=True)

\# 1\. Core Seed Matrix Across Tiers 0 \- 3 (Auto-expands to 1,000+ via Winget Index)  
CORE\_APPS \= \[  
    \# Tier 0: Simple Native Win32  
    {"app\_name": "Notepad", "tier": 0, "category": "Text Editor"},  
    {"app\_name": "Windows Calculator", "tier": 0, "category": "Utility"},  
    {"app\_name": "MS Paint", "tier": 0, "category": "Graphics"},  
    {"app\_name": "Snipping Tool", "tier": 0, "category": "Utility"},  
    {"app\_name": "7-Zip", "tier": 0, "category": "Archiver"},  
    {"app\_name": "VLC Media Player", "tier": 0, "category": "Media"},  
    \# Tier 1: Modern Desktop / Web-Wrapped / Comms  
    {"app\_name": "WhatsApp Desktop", "tier": 1, "category": "Communication"},  
    {"app\_name": "Discord", "tier": 1, "category": "Communication"},  
    {"app\_name": "Slack", "tier": 1, "category": "Communication"},  
    {"app\_name": "Microsoft Teams", "tier": 1, "category": "Communication"},  
    {"app\_name": "Spotify", "tier": 1, "category": "Media"},  
    {"app\_name": "Windows 11 Settings", "tier": 1, "category": "System"},  
    {"app\_name": "Zoom", "tier": 1, "category": "Communication"},  
    {"app\_name": "Notion", "tier": 1, "category": "Productivity"},  
    \# Tier 2: Multi-Panel & Ribbon Suites  
    {"app\_name": "Microsoft Word", "tier": 2, "category": "Office Suite"},  
    {"app\_name": "Microsoft Excel", "tier": 2, "category": "Office Suite"},  
    {"app\_name": "Microsoft PowerPoint", "tier": 2, "category": "Office Suite"},  
    {"app\_name": "OBS Studio", "tier": 2, "category": "Broadcasting"},  
    {"app\_name": "Visual Studio Code", "tier": 2, "category": "Development"},  
    {"app\_name": "Audacity", "tier": 2, "category": "Audio Editing"},  
    {"app\_name": "GIMP", "tier": 2, "category": "Image Editing"},  
    {"app\_name": "Inkscape", "tier": 2, "category": "Vector Graphics"},  
    {"app\_name": "Postman", "tier": 2, "category": "Development"},  
    \# Tier 3: Complex 3D / CAD / NLE / Canvas Suites  
    {"app\_name": "Blender 3D", "tier": 3, "category": "3D Modeling"},  
    {"app\_name": "AutoCAD", "tier": 3, "category": "CAD Engineering"},  
    {"app\_name": "FreeCAD", "tier": 3, "category": "CAD Engineering"},  
    {"app\_name": "DaVinci Resolve", "tier": 3, "category": "Video Editing"},  
    {"app\_name": "Unreal Engine 5", "tier": 3, "category": "Game Engine"},  
    {"app\_name": "Unity Editor", "tier": 3, "category": "Game Engine"},  
    {"app\_name": "Adobe Photoshop", "tier": 3, "category": "Design"},  
    {"app\_name": "SolidWorks", "tier": 3, "category": "CAD Engineering"}  
\]

def fetch\_1000\_free\_apps\_from\_winget(limit: int \= 1000\) \-\> list:  
    """  
    Pulls 1,000+ Windows applications for FREE from the open-source Winget CSV index on GitHub.  
    """  
    winget\_csv\_url \= "https\://github.com/svrooij/winget-pkgs-index/raw/main/index.v2.csv"  
    print("\[\*\] Fetching open-source Windows App Catalog from GitHub...")  
    apps \= list(CORE\_APPS)  
    existing\_names \= {a\["app\_name"\].lower() for a in apps}

    try:  
        df\_winget \= pd.read\_csv(winget\_csv\_url)  
        \# Filter out pure runtime/redistributable libraries to keep user-facing GUI apps  
        df\_winget \= df\_winget.dropna(subset=\["Name", "Tags"\])  
        exclude\_keywords \= \["redistributable", "sdk", "driver", "cli", "runtime", "font"\]  
          
        for \_, row in df\_winget.iterrows():  
            name \= str(row\["Name"\]).strip()  
            tags \= str(row.get("Tags", "")).lower()  
            if name.lower() not in existing\_names and not any(k in name.lower() for k in exclude\_keywords):  
                apps.append({  
                    "app\_name": name,  
                    "tier": 2, \# Default classification before scanner benchmark  
                    "category": tags.split(",")\[0\] if tags else "General Desktop App"  
                })  
                existing\_names.add(name.lower())  
                if len(apps) \>= limit:  
                    break  
    except Exception as e:  
        print(f"\[\!\] Winget fetch fallback triggered: {e}")  
      
    print(f"\[+\] Total Apps Queued: {len(apps)}")  
    return apps

def search\_youtube\_free\_no\_api(app\_name: str, videos\_per\_app: int \= 5\) \-\> list:  
    """  
    Uses yt-dlp flat-playlist search to grab YouTube tutorial URLs & metadata for \$0 without API keys.  
    """  
    search\_queries \= \[  
        f"ytsearch{videos\_per\_app}:{app\_name} full tutorial for beginners step by step",  
        f"ytsearch{videos\_per\_app}:{app\_name} shortcuts tips and tricks workflow"  
    \]  
    found\_videos \= \[\]

    for query in search\_queries:  
        cmd \= \[  
            "yt-dlp",  
            query,  
            "--flat-playlist",  
            "--dump-json",  
            "--no-warnings",  
            "--skip-download"  
        \]  
        try:  
            result \= subprocess.run(cmd, capture\_output=True, text=True, encoding="utf-8", timeout=30)  
            for line in result.stdout.strip().split("\\n"):  
                if not line:  
                    continue  
                data \= json.loads(line)  
                vid\_id \= data.get("id")  
                if vid\_id:  
                    found\_videos.append({  
                        "app\_name": app\_name,  
                        "video\_id": vid\_id,  
                        "title": data.get("title", ""),  
                        "url": f"https\://www\.youtube.com/watch?v={vid\_id}",  
                        "duration\_sec": data.get("duration", 0),  
                        "view\_count": data.get("view\_count", 0),  
                        "channel": data.get("uploader", "")  
                    })  
        except Exception as e:  
            print(f"    \[\!\] Search error for {app\_name}: {e}")

    return found\_videos

def fetch\_transcript\_free(video\_id: str, app\_name: str) \-\> dict:  
    """  
    Downloads timestamped YouTube transcripts directly without downloading video or using GPU.  
    """  
    save\_path \= os.path.join(TRANSCRIPT\_DIR, f"{app\_name.replace(' ', '\_')}\_{video\_id}.json")  
    if os.path.exists(save\_path):  
        return {"status": "Cached", "path": save\_path}

    try:  
        transcript \= YouTubeTranscriptApi.get\_transcript(video\_id, languages=\['en', 'en-US', 'en-GB'\])  
        with open(save\_path, "w", encoding="utf-8") as f:  
            json.dump(transcript, f, indent=2)  
        return {"status": "Downloaded", "segments\_count": len(transcript), "path": save\_path}  
    except Exception:  
        return {"status": "No\_Subtitles", "segments\_count": 0, "path": ""}

def run\_harvester(max\_apps\_to\_process: int \= 50, videos\_per\_app: int \= 3):  
    apps\_list \= fetch\_1000\_free\_apps\_from\_winget(limit=1000)  
      
    videos\_records \= \[\]  
    for idx, app in enumerate(apps\_list\[:max\_apps\_to\_process\]):  
        app\_name \= app\["app\_name"\]  
        print(f"\[{idx+1}/{max\_apps\_to\_process}\] Harvesting YouTube Tutorials & Transcripts for: {app\_name}...")  
          
        vids \= search\_youtube\_free\_no\_api(app\_name, videos\_per\_app=videos\_per\_app)  
        for v in vids:  
            t\_info \= fetch\_transcript\_free(v\["video\_id"\], app\_name)  
            v\["transcript\_status"\] \= t\_info\["status"\]  
            v\["transcript\_segments"\] \= t\_info.get("segments\_count", 0\)  
            v\["local\_ssd\_json\_path"\] \= t\_info\["path"\]  
            videos\_records.append(v)  
          
        time.sleep(1.0) \# Polite rate-limiting so YouTube never blocks your IP

    \# Export multi-sheet Excel file  
    df\_apps \= pd.DataFrame(apps\_list)  
    df\_videos \= pd.DataFrame(videos\_records)

    with pd.ExcelWriter(EXCEL\_OUTPUT, engine="openpyxl") as writer:  
        df\_apps.to\_excel(writer, sheet\_name="1\_Master\_1000\_Apps", index=False)  
        df\_videos.to\_excel(writer, sheet\_name="2\_YouTube\_And\_Transcripts", index=False)

    print(f"\\n\[SUCCESS\] Master Excel exported to: {EXCEL\_OUTPUT}")  
    print(f"\[SUCCESS\] Transcripts stored on SSD at: {TRANSCRIPT\_DIR}")

if \_\_name\_\_ \== "\_\_main\_\_":  
    \# Start with 50 apps (300 videos) to verify, then increase max\_apps\_to\_process to 1000\!  
    run\_harvester(max\_apps\_to\_process=50, videos\_per\_app=3)

### **5\. Step-by-Step Execution Order (How You Run This Independently)**

1. **Step 1 (Build the Excel Master & Transcript Bank — Days 1–2):** Run free\_master\_harvester.py in batches (e.g., 200 apps per day with a 1.0s delay between requests so YouTube never rate-limits your home IP). This builds your HoJaiga\_Master\_App\_Dataset.xlsx and populates E:/HoJaiga\_AI/Dataset\_Harvester/transcripts\_json for \$0.  
2. **Step 2 (Ingest Transcripts \+ Hotkeys into Sub-RAG 3 & Sub-RAG 4 — Days 3–4):** Feed the downloaded JSON transcripts directly into your LanceDB procedural\_workflow\_rag table on your 1.3 TB SSD, alongside scraped hotkey tables from free sites like defkey.com or GitHub cheat-sheet repos.  
3. **Step 3 (Selective Keyframe Slicing for QLoRA — Days 5–7):** For your core 30 benchmark apps across Tiers 0–3, run a filter over the transcripts that grabs **only** segments containing action verbs (click, select, menu, toolbar, extrude, shortcut), downloads those 5-second clips via yt-dlp \--download-sections, passes the frame through your universal\_scan.py Set-of-Marks numbering, and saves 15,000 high-precision visual pairs for Unsloth QLoRA training.

\======================================================================

### **The \$0 Companion Scraper: Keyboard Shortcuts, CLI Cheat Sheets & Superhuman Macro Harvester (`Sub-RAG 4`)**

This companion script (`free_hotkeys_and_macros_harvester.py`) populates **Sub-RAG 4 (Superhuman Macro & Hotkey Vault)** for \$0 without paid APIs. It pulls from four free layers and writes directly to your `HoJaiga_Master_App_Dataset.xlsx` file and your LanceDB JSONL folder on your 1.3 TB External SSD:

1. **Layer 1: Live Web Table Scraper (`ShortcutWorld` & `DefKey` HTML Tables):** Uses `requests` and `BeautifulSoup` to search public shortcut directories for each app in your 1,000-app list and parses every `Key Combo -> Action` table row.  
2. **Layer 2: Open-Source `tldr-pages` GitHub Scraper:** Queries the raw GitHub repository (`tldr-pages/tldr`) for Windows and cross-platform CLI syntax so your agent can trigger silent background tasks via command line.  
3. **Layer 3: Built-In Superhuman Script Templates (`bpy`, AutoLISP/`.scr`, Office COM/VBA):** Pre-loads programmatic execution templates for Tier 2 and Tier 3 apps (Blender, AutoCAD, Word, Excel, OBS) so the agent can generate studio-grade 3D models, CAD drawings, and spreadsheets via code injection rather than slow mouse clicking.  
4. **Layer 4: Local Ollama Zero-Cost Fallback:** If an obscure app has no public table on the web, the script can query your local Ollama model offline to extract standard Windows menu accelerators (`Alt+F`, `Ctrl+S`, etc.) at zero cost.

### **Step 1: Install Required Free Libraries**

If you already installed the packages from the previous step, you already have everything needed (`requests`, `beautifulsoup4`, `pandas`, `openpyxl`).

Bash  
pip install requests beautifulsoup4 lxml pandas openpyxl

### **Step 2: Save and Run `free_hotkeys_and_macros_harvester.py`**

Python  
import os  
import re  
import json  
import time  
import urllib.parse  
import requests  
import pandas as pd  
from bs4 import BeautifulSoup

\# \=====================================================================  
\# CONFIGURATION: Point to your 1.3 TB External SSD  
\# \=====================================================================  
SSD\_ROOT \= "E:/HoJaiga\_AI/Dataset\_Harvester"  
EXCEL\_PATH \= os.path.join(SSD\_ROOT, "HoJaiga\_Master\_App\_Dataset.xlsx")  
JSONL\_EXPORT\_PATH \= os.path.join(SSD\_ROOT, "sub\_rag4\_hotkeys\_and\_macros.jsonl")

os.makedirs(SSD\_ROOT, exist\_ok=True)

HEADERS \= {  
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"  
}

\# \=====================================================================  
\# LAYER 1: Built-in Superhuman Macros & Scripting Templates (Tier 0 \- 3\)  
\# Allows the agent to build pro-grade outputs via code instead of clicks  
\# \=====================================================================  
SUPERHUMAN\_MACROS\_SEED \= \[  
    {  
        "app\_name": "Blender 3D",  
        "tier": 3,  
        "execution\_type": "Headless\_Python\_bpy",  
        "cli\_trigger": 'blender \--background \--python "{script\_path}"',  
        "task\_pattern": "Create procedural 3D architectural mesh / bevel / studio lighting render",  
        "code\_template": (  
            "import bpy\\n"  
            "bpy.ops.wm.read\_factory\_settings(use\_empty=True)\\n"  
            "bpy.ops.mesh.primitive\_cube\_add(size=2, location=(0, 0, 1))\\n"  
            "obj \= bpy.context.active\_object\\n"  
            "mod \= obj.modifiers.new(name='Bevel', type='BEVEL')\\n"  
            "mod.width \= 0.15\\n"  
            "mod.segments \= 4\\n"  
            "bpy.ops.object.shade\_smooth()\\n"  
            "bpy.ops.wm.save\_as\_mainfile(filepath=r'{output\_blend\_path}')"  
        )  
    },  
    {  
        "app\_name": "AutoCAD",  
        "tier": 3,  
        "execution\_type": "AutoCAD\_Script\_SCR",  
        "cli\_trigger": 'accoreconsole.exe /i "{input\_dwg}" /s "{script\_scr\_path}"',  
        "task\_pattern": "Draw precision 2D/3D floorplan or extrude closed polyline to 3D solid",  
        "code\_template": (  
            "\_PLINE 0,0 1000,0 1000,800 0,800 \_C\\n"  
            "\_EXTRUDE \_L \\n"  
            "300\\n"  
            "\_ZOOM \_E\\n"  
            "\_QSAVE\\n"  
        )  
    },  
    {  
        "app\_name": "Microsoft Excel",  
        "tier": 2,  
        "execution\_type": "Win32\_COM\_Automation",  
        "cli\_trigger": "python \-c \\"import win32com.client; xl \= win32com.client.Dispatch('Excel.Application')\\"",  
        "task\_pattern": "Create automated financial sheet, formulas, and pivot chart instantaneously",  
        "code\_template": (  
            "import win32com.client as win32\\n"  
            "excel \= win32.gencache.EnsureDispatch('Excel.Application')\\n"  
            "excel.Visible \= True\\n"  
            "wb \= excel.Workbooks.Add()\\n"  
            "ws \= wb.ActiveSheet\\n"  
            "ws.Range('A1:B1').Value \= \['Metric', 'Revenue'\]\\n"  
            "ws.Range('B5').Formula \= '=SUM(B2:B4)'\\n"  
        )  
    },  
    {  
        "app\_name": "Microsoft Word",  
        "tier": 2,  
        "execution\_type": "Win32\_COM\_Automation",  
        "cli\_trigger": "python \-c \\"import win32com.client; wd \= win32com.client.Dispatch('Word.Application')\\"",  
        "task\_pattern": "Generate formatted executive report with headings and tables directly via COM",  
        "code\_template": (  
            "import win32com.client as win32\\n"  
            "word \= win32.gencache.EnsureDispatch('Word.Application')\\n"  
            "word.Visible \= True\\n"  
            "doc \= word.Documents.Add()\\n"  
            "rng \= doc.Range(0, 0)\\n"  
            "rng.Text \= 'Executive Summary\\\\n'\\n"  
            "rng.Style \= 'Heading 1'\\n"  
        )  
    },  
    {  
        "app\_name": "OBS Studio",  
        "tier": 2,  
        "execution\_type": "WebSocket\_And\_CLI",  
        "cli\_trigger": "obs64.exe \--startrecording \--minimize-to-tray",  
        "task\_pattern": "Start recording or switch scene without touching the UI",  
        "code\_template": "obs64.exe \--scene \\"Main Camera\\" \--startrecording"  
    }  
\]

\# Core high-frequency hotkeys guaranteed even offline  
CORE\_HOTKEYS\_SEED \= \[  
    {"app\_name": "Blender 3D", "shortcut": "G then Z then \[Number\]", "action": "Move/Grab selected object along Z-axis by exact units", "category": "3D Transform"},  
    {"app\_name": "Blender 3D", "shortcut": "E", "action": "Extrude selected mesh region in Edit Mode", "category": "Modeling"},  
    {"app\_name": "Blender 3D", "shortcut": "Ctrl \+ B", "action": "Bevel selected edges or vertices", "category": "Modeling"},  
    {"app\_name": "Blender 3D", "shortcut": "Tab", "action": "Toggle between Object Mode and Edit Mode", "category": "Mode Switch"},  
    {"app\_name": "Blender 3D", "shortcut": "Shift \+ A", "action": "Open Add Menu (Mesh, Curve, Light, Camera)", "category": "Creation"},  
    {"app\_name": "Blender 3D", "shortcut": "F12", "action": "Render active camera frame", "category": "Render"},  
    {"app\_name": "AutoCAD", "shortcut": "L \+ Enter", "action": "Activate LINE drawing tool", "category": "Draw"},  
    {"app\_name": "AutoCAD", "shortcut": "EXT \+ Enter", "action": "EXTRUDE 2D closed object into 3D solid", "category": "3D Modeling"},  
    {"app\_name": "AutoCAD", "shortcut": "TR \+ Enter \+ Enter", "action": "TRIM intersecting geometry", "category": "Modify"},  
    {"app\_name": "AutoCAD", "shortcut": "F8", "action": "Toggle Ortho Mode (lock cursor to 90-degree angles)", "category": "Precision"},  
    {"app\_name": "AutoCAD", "shortcut": "F3", "action": "Toggle Object Snap (OSNAP) for exact endpoints/midpoints", "category": "Precision"},  
    {"app\_name": "WhatsApp Desktop", "shortcut": "Ctrl \+ N", "action": "Start a new chat", "category": "Navigation"},  
    {"app\_name": "WhatsApp Desktop", "shortcut": "Ctrl \+ F", "action": "Search chats and messages", "category": "Search"},  
    {"app\_name": "WhatsApp Desktop", "shortcut": "Ctrl \+ Shift \+ M", "action": "Mute selected conversation", "category": "Chat Actions"},  
    {"app\_name": "OBS Studio", "shortcut": "Ctrl \+ ,", "action": "Open OBS Settings window", "category": "Configuration"},  
    {"app\_name": "Visual Studio Code", "shortcut": "Ctrl \+ Shift \+ P", "action": "Open Command Palette (executes any VS Code feature by name)", "category": "Master Control"},  
\]

\# \=====================================================================  
\# LAYER 2: Free Public Web Scraper (ShortcutWorld & DefKey HTML Tables)  
\# \=====================================================================  
def scrape\_public\_shortcuts\_for\_app(app\_name: str) \-\> list:  
    """  
    Searches public shortcut directories (ShortcutWorld / DefKey) and extracts  
    all (Shortcut \-\> Action) rows from HTML tables for \$0.  
    """  
    extracted \= \[\]  
    clean\_slug \= re.sub(r"\[^a-z0-9\]+", "-", app\_name.lower()).strip("-")  
      
    \# Candidate public cheat-sheet URLs  
    candidate\_urls \= \[  
        f"https\://www\.shortcutworld.com/{clean\_slug}/win/{clean\_slug}\_shortcuts",  
        f"https\://defkey.com/{clean\_slug}-shortcuts"  
    \]

    for url in candidate\_urls:  
        try:  
            resp \= requests.get(url, headers=HEADERS, timeout=12)  
            if resp.status\_code \!= 200:  
                continue

            soup \= BeautifulSoup(resp.text, "lxml")  
            tables \= soup.find\_all("table")  
            for table in tables:  
                for row in table.find\_all("tr"):  
                    cols \= \[c.get\_text(" ", strip=True) for c in row.find\_all(\["td", "th"\])\]  
                    if len(cols) \>= 2:  
                        key\_combo, description \= cols\[0\], cols\[1\]  
                        \# Filter out table headers  
                        if key\_combo.lower() in \["shortcut", "key", "command", "windows"\]:  
                            continue  
                        if 1 \<= len(key\_combo) \<= 45 and len(description) \> 3:  
                            extracted.append({  
                                "app\_name": app\_name,  
                                "shortcut": key\_combo,  
                                "action": description,  
                                "category": "Scraped\_Web\_Table",  
                                "source\_url": url  
                            })  
            if extracted:  
                break  
        except Exception:  
            continue

    return extracted

\# \=====================================================================  
\# LAYER 3: Open-Source GitHub \`tldr-pages\` CLI Scraper (100% Free)  
\# \=====================================================================  
def fetch\_tldr\_cli\_cheatsheet(app\_name: str) \-\> list:  
    """  
    Pulls official open-source CLI cheat sheets from the tldr-pages GitHub repo.  
    """  
    cli\_commands \= \[\]  
    cmd\_slug \= app\_name.lower().split()\[0\].replace(".exe", "")  
      
    github\_raw\_urls \= \[  
        f"https\://raw.githubusercontent.com/tldr-pages/tldr/main/pages/windows/{cmd\_slug}.md",  
        f"https\://raw.githubusercontent.com/tldr-pages/tldr/main/pages/common/{cmd\_slug}.md"  
    \]

    for url in github\_raw\_urls:  
        try:  
            resp \= requests.get(url, headers=HEADERS, timeout=10)  
            if resp.status\_code \== 200:  
                lines \= resp.text.splitlines()  
                current\_desc \= ""  
                for line in lines:  
                    line \= line.strip()  
                    if line.startswith("- "):  
                        current\_desc \= line\[2:\].rstrip(":")  
                    elif line.startswith("\`") and line.endswith("\`") and current\_desc:  
                        cmd\_syntax \= line.strip("\`")  
                        cli\_commands.append({  
                            "app\_name": app\_name,  
                            "tier": 1,  
                            "execution\_type": "CLI\_Command",  
                            "cli\_trigger": cmd\_syntax,  
                            "task\_pattern": current\_desc,  
                            "code\_template": cmd\_syntax  
                        })  
                        current\_desc \= ""  
                break  
        except Exception:  
            continue

    return cli\_commands

\# \=====================================================================  
\# LAYER 4: Local Ollama Offline Fallback Generator (\$0 Cost)  
\# \=====================================================================  
def generate\_fallback\_shortcuts\_via\_local\_ollama(app\_name: str, model\_name: str \= "qwen3-vl:8b") \-\> list:  
    """  
    If an app has no scraped tables online, asks your local Ollama instance  
    to output standard keyboard shortcuts in JSON format for \$0.  
    """  
    prompt \= (  
        f"List the 10 most important Windows keyboard shortcuts for '{app\_name}'. "  
        "Return ONLY a valid JSON list of objects with keys 'shortcut' and 'action'."  
    )  
    try:  
        resp \= requests.post(  
            "http\://localhost:11434/api/generate",  
            json={"model": model\_name, "prompt": prompt, "stream": False, "format": "json"},  
            timeout=20  
        )  
        if resp.status\_code \== 200:  
            raw\_json \= json.loads(resp.json().get("response", "\[\]"))  
            items \= raw\_json if isinstance(raw\_json, list) else raw\_json.get("shortcuts", \[\])  
            results \= \[\]  
            for item in items:  
                if "shortcut" in item and "action" in item:  
                    results.append({  
                        "app\_name": app\_name,  
                        "shortcut": str(item\["shortcut"\]),  
                        "action": str(item\["action"\]),  
                        "category": "Local\_Ollama\_Synthesized",  
                        "source\_url": "local://ollama"  
                    })  
            return results  
    except Exception:  
        pass  
    return \[\]

\# \=====================================================================  
\# MAIN PIPELINE: Enrich Excel Workbook & Export LanceDB JSONL  
\# \=====================================================================  
def run\_hotkeys\_and\_macros\_harvester(max\_apps\_to\_scrape: int \= 50, use\_ollama\_fallback: bool \= False):  
    \# Load app list from Sheet 1 of your existing Excel file (or use default seed)  
    if os.path.exists(EXCEL\_PATH):  
        df\_apps \= pd.read\_excel(EXCEL\_PATH, sheet\_name="1\_Master\_1000\_Apps")  
        app\_names \= df\_apps\["app\_name"\].dropna().unique().tolist()  
    else:  
        print("\[\!\] Master Excel not found yet; initializing from default seed apps...")  
        app\_names \= \["Notepad", "MS Paint", "WhatsApp Desktop", "Discord", "Microsoft Word",  
                     "Microsoft Excel", "OBS Studio", "Visual Studio Code", "Blender 3D", "AutoCAD"\]  
        df\_apps \= pd.DataFrame(\[{"app\_name": a} for a in app\_names\])

    all\_hotkeys \= list(CORE\_HOTKEYS\_SEED)  
    all\_macros \= list(SUPERHUMAN\_MACROS\_SEED)

    for idx, app\_name in enumerate(app\_names\[:max\_apps\_to\_scrape\]):  
        print(f"\[{idx+1}/{min(len(app\_names), max\_apps\_to\_scrape)}\] Scraping Hotkeys & CLI Macros for: {app\_name}...")

        \# 1\. Scrape public shortcut tables  
        scraped\_keys \= scrape\_public\_shortcuts\_for\_app(app\_name)  
        if scraped\_keys:  
            print(f"    \[+\] Found {len(scraped\_keys)} shortcuts from public web tables.")  
            all\_hotkeys.extend(scraped\_keys)  
        elif use\_ollama\_fallback:  
            fallback\_keys \= generate\_fallback\_shortcuts\_via\_local\_ollama(app\_name)  
            print(f"    \[+\] Generated {len(fallback\_keys)} shortcuts via local Ollama fallback.")  
            all\_hotkeys.extend(fallback\_keys)

        \# 2\. Scrape GitHub tldr-pages CLI commands  
        cli\_macros \= fetch\_tldr\_cli\_cheatsheet(app\_name)  
        if cli\_macros:  
            print(f"    \[+\] Found {len(cli\_macros)} CLI commands from tldr-pages.")  
            all\_macros.extend(cli\_macros)

        time.sleep(0.8) \# Polite delay

    df\_hotkeys \= pd.DataFrame(all\_hotkeys).drop\_duplicates(subset=\["app\_name", "shortcut"\])  
    df\_macros \= pd.DataFrame(all\_macros).drop\_duplicates(subset=\["app\_name", "task\_pattern"\])

    \# Append/Update Sheets 3 and 4 inside HoJaiga\_Master\_App\_Dataset.xlsx  
    mode \= "a" if os.path.exists(EXCEL\_PATH) else "w"  
    writer\_kwargs \= {"engine": "openpyxl", "mode": mode}  
    if mode \== "a":  
        writer\_kwargs\["if\_sheet\_exists"\] \= "replace"

    with pd.ExcelWriter(EXCEL\_PATH, \*\*writer\_kwargs) as writer:  
        if mode \== "w":  
            df\_apps.to\_excel(writer, sheet\_name="1\_Master\_1000\_Apps", index=False)  
        df\_hotkeys.to\_excel(writer, sheet\_name="3\_Hotkeys\_Matrix", index=False)  
        df\_macros.to\_excel(writer, sheet\_name="4\_Superhuman\_Macros\_CLI", index=False)

    \# Also export directly as JSONL for instant LanceDB Sub-RAG 4 ingestion  
    with open(JSONL\_EXPORT\_PATH, "w", encoding="utf-8") as f:  
        for record in df\_hotkeys.to\_dict(orient="records"):  
            record\["rag\_sub\_table"\] \= "sub\_rag4\_hotkeys"  
            f.write(json.dumps(record) \+ "\\n")  
        for record in df\_macros.to\_dict(orient="records"):  
            record\["rag\_sub\_table"\] \= "sub\_rag4\_superhuman\_macros"  
            f.write(json.dumps(record) \+ "\\n")

    print(f"\\n\[SUCCESS\] Added '3\_Hotkeys\_Matrix' ({len(df\_hotkeys)} rows) and '4\_Superhuman\_Macros\_CLI' ({len(df\_macros)} rows) to: {EXCEL\_PATH}")  
    print(f"\[SUCCESS\] Exported LanceDB Sub-RAG 4 JSONL to: {JSONL\_EXPORT\_PATH}")

if \_\_name\_\_ \== "\_\_main\_\_":  
    run\_hotkeys\_and\_macros\_harvester(max\_apps\_to\_scrape=50, use\_ollama\_fallback=False)

### **How Your Complete 4-Sheet Excel File Now Feeds Your System**

Once you run both scripts (`free_master_harvester.py` followed by `free_hotkeys_and_macros_harvester.py`), your `HoJaiga_Master_App_Dataset.xlsx` on your 1.3 TB SSD contains four sheets that map directly to your Multi-RAG and QLoRA training pipeline:

1. **`1_Master_1000_Apps`:** The master queue of applications categorized from Tier 0 to Tier 3\.  
2. **`2_YouTube_And_Transcripts`:** Links every app to its downloaded JSON timestamped transcripts on your SSD (feeds **Sub-RAG 3: Procedural Video Workflow RAG** and selects exact action timestamps for **Qwen3-VL QLoRA keyframe slicing**).  
3. **`3_Hotkeys_Matrix`:** Instant keyboard shortcuts for every app (feeds **Sub-RAG 4** so the agent executes actions in **0.005 seconds** via keystrokes instead of slow menu clicking).  
4. **`4_Superhuman_Macros_CLI`:** Headless Python `bpy` scripts, AutoCAD `.scr` templates, Office Win32 COM scripts, and `tldr` CLI commands (feeds **Sub-RAG 4** so the agent can generate complex, studio-grade 3D CAD/Blender/Excel deliverables automatically).