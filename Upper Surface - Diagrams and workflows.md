# **1\. HOJAIGA MASTER ARCHITECTURE(before adding 20 files but above master architecture includes all the files and everything in depth)**

                                          USER  
                                             │  
                                             ▼  
                              ┌─────────────────────────┐  
                              │   Interface Layer       │  
                              │  (CLI / GUI / API)      │  
                              └────────────┬────────────┘  
                                           │  
                                           ▼  
                              ┌─────────────────────────┐  
                              │         BRAIN           │  
                              │  Planning • Reasoning   │  
                              │ Decision • Reflection   │  
                              └────────────┬────────────┘  
                                           │  
                                           ▼  
                    ┌───────────────────────────────────────────┐  
                    │          CENTRAL NERVOUS SYSTEM           │  
                    │ Event Bus • Session Bus • Socket Manager  │  
                    │ Pipeline Manager • Router • Scheduler     │  
                    └────────────┬───────────────┬──────────────┘  
                                 │               │  
         ┌───────────────────────┼───────────────┼─────────────────────────┐  
         │                       │               │                         │  
         ▼                       ▼               ▼                         ▼  
 ┌──────────────┐       ┌──────────────┐  ┌──────────────┐        ┌──────────────┐  
 │    Memory    │       │  Knowledge   │  │ Controllers  │        │  Learning    │  
 └──────────────┘       └──────────────┘  └──────────────┘        └──────────────┘  
                                 │               │  
                                 └───────┬───────┘  
                                         ▼  
                               ┌─────────────────────┐  
                               │    Automation       │  
                               └─────────┬───────────┘  
                                         ▼  
                               ┌─────────────────────┐  
                               │      Agents         │  
                               └─────────┬───────────┘  
                                         ▼  
                               ┌─────────────────────┐  
                               │   Infrastructure    │  
                               └─────────┬───────────┘  
                                         ▼  
                               ┌─────────────────────┐  
                               │      Security       │  
                               └─────────┬───────────┘  
                                         ▼  
                               ┌─────────────────────┐  
                               │    Integration      │  
                               └─────────────────────┘  
---

# **2\. COMPLETE EXECUTION FLOW**

User

↓

Interface

↓

Brain

↓

CNS

↓

Controllers

↓

Automation

↓

Agents

↓

Execution

↓

Validation

↓

Learning

↓

Memory

↓

Knowledge

↓

Logs

↓

Reports

↓

User  
---

# **3\. BRAIN LIFECYCLE**

Task Received  
      │  
      ▼  
Check Brain Runtime  
      │  
      ▼  
Already Running?  
   │         │  
 Yes        No  
   │         │  
   │    Start llama.cpp  
   │         │  
   │         ▼  
   │   Load Qwen3 Model  
   │         │  
   └────────►│  
             ▼  
      Brain Ready  
             │  
             ▼  
      Execute Task  
             │  
             ▼  
      Grace Period  
             │  
             ▼  
 New Task?  
   │        │  
 Yes       No  
  │         │  
  └────────►Shutdown Brain  
            │  
            ▼  
      Free GPU Memory  
---

# **4\. LOCAL LLM ARCHITECTURE**

                Brain

                   │

                   ▼

            Model Manager

                   │

        ┌──────────┴──────────┐  
        │                     │  
        ▼                     ▼  
 Model Verification      Model Loader  
        │                     │  
        └──────────┬──────────┘  
                   ▼  
              llama.cpp  
                   │  
                   ▼  
            Qwen3 8B Model  
                   │  
                   ▼  
          Local HTTP API  
                   │  
                   ▼  
                Brain  
---

# **5\. EXTERNAL PLUGIN ARCHITECTURE**

External Plugin  
       │  
       ▼  
┌────────────────────┐  
│ Extension Gateway  │  
└────────────────────┘  
       │  
       ▼  
┌────────────────────┐  
│ Security Validator │  
└────────────────────┘  
       │  
       ▼  
┌────────────────────┐  
│ Compatibility Check│  
└────────────────────┘  
       │  
       ▼  
┌────────────────────┐  
│ Sandbox Test Run   │  
└────────────────────┘  
       │  
       ▼  
┌────────────────────┐  
│ Pending Attachment │  
└────────────────────┘  
       │  
User Reviews & Approves  
       │  
       ▼  
┌────────────────────┐  
│ Connected Socket   │  
└────────────────────┘  
       │  
       ▼  
Used by Automation  
---

# **6\. SOCKET ARCHITECTURE**

Organ A

   │

Public Socket

   │

Authentication

   │

Validation

   │

Version Check

   │

Pipeline

   │

Authentication

   │

Validation

   │

Public Socket

   │

Organ B  
---

# **7\. PIPELINE ARCHITECTURE**

Source Organ  
      │  
      ▼  
Serialize Data  
      │  
      ▼  
Validate Contract  
      │  
      ▼  
Encrypt (Optional)  
      │  
      ▼  
Pipeline  
      │  
      ▼  
Deserialize  
      │  
      ▼  
Validate  
      │  
      ▼  
Destination Organ  
---

# **8\. PLAYWRIGHT \+ CDP ARCHITECTURE**

Automation

      │

      ▼

Browser Manager

      │

      ▼

Playwright

      │

      ▼

Chrome DevTools Protocol

      │

      ▼

Chrome Browser

      │

      ▼

Tabs

Windows

Downloads

Uploads

Network

DOM

JavaScript  
---

# **9\. WINDOWS GUI AUTOMATION**

Automation  
      │  
      ▼  
GUI Manager  
      │  
      ▼  
Desktop Session  
      │  
      ▼  
Main Window  
      │  
      ▼  
Child Window Detector  
      │  
      ▼  
Focused Window  
      │  
      ▼  
UI Tree Reader  
      │  
      ▼  
Action Executor  
---

# **10\. KNOWLEDGE FLOW**

User Input

      │

      ▼

Brain

      │

      ▼

Knowledge Search

      │

      ▼

Memory Lookup

      │

      ▼

Controllers

      │

      ▼

Automation

      │

      ▼

Execution

      │

      ▼

Learning

      │

      ▼

Knowledge Updated  
---

# **11\. n8n WORKFLOW**

Trigger

   │

   ▼

Brain

   │

   ▼

Decision

   │

   ▼

Controllers

   │

   ▼

Automation

   │

   ▼

Execution

   │

   ▼

Validation

   │

Retry?──────No──────────►Report

 │

Yes

 │

 ▼

Retry Execution  
---

# **12\. STORAGE ARCHITECTURE**

                SSD (Runtime)

          Config

          Cache

          Session

          Temp Files

          Active Logs

                 │

                 ▼

          External HDD

          Models

          Knowledge

          History

          Archives

          Reports

          Datasets

          Backups  
---

# **13\. SECURITY LAYER**

User Request

      │

      ▼

Authentication

      │

      ▼

Permission Check

      │

      ▼

Policy Validation

      │

      ▼

Law Validation

      │

      ▼

Security Sandbox

      │

      ▼

Execution Approval

      │

      ▼

Automation  
---

# **14\. BOOT SEQUENCE**

Launch

   │

   ▼

Load Configuration

   │

   ▼

Initialize Infrastructure

   │

   ▼

Initialize CNS

   │

   ▼

Initialize Memory

   │

   ▼

Initialize Knowledge

   │

   ▼

Brain Standby

   │

   ▼

Wait for Tasks  
---

# **15\. SHUTDOWN SEQUENCE**

Task Complete

      │

      ▼

Flush Memory

      │

      ▼

Save History

      │

      ▼

Close Sessions

      │

      ▼

Stop Brain

      │

      ▼

Release GPU

      │

      ▼

Archive Logs

      │

      ▼

Idle State  
—------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# **Diagram 1 — Master Architecture (Hojaiga v0.9)**

                                       ┌────────────────────────────┐  
                                        │         USER INPUT         │  
                                        │ Text • Voice • Image • PDF │  
                                        │ Video • Files • URL • etc  │  
                                        └─────────────┬──────────────┘  
                                                      │  
                                                      ▼  
                                     ┌────────────────────────────────┐  
                                     │       INPUT NORMALIZER         │  
                                     │ Universal Input Translator     │  
                                     └────────────────┬───────────────┘  
                                                      │  
                                                      ▼  
                     ┌────────────────────────────────────────────────────┐  
                     │                    BRAIN (LLM)                     │  
                     │                                                    │  
                     │ • Global Reasoning                                │  
                     │ • Critical Thinking                               │  
                     │ • Long-term Intelligence                          │  
                     │ • Strategic Planning                              │  
                     └─────────────────┬──────────────────────────────────┘  
                                       │  
                                       │  
               ┌───────────────────────┼─────────────────────────┐  
               │                       │                         │  
               ▼                       ▼                         ▼  
      ┌────────────────┐     ┌──────────────────┐      ┌─────────────────┐  
      │ Model Runtime  │     │ Reasoning Gateway│      │ Memory System   │  
      │ Model Router   │     │ Local Reasoners  │      │ Working         │  
      │ Provider Mgmt  │     │ Escalation       │      │ Environment     │  
      │ Offline/Online │     │ Confidence       │      │ Knowledge       │  
      └────────────────┘     └──────────────────┘      └─────────────────┘  
                                       │  
                                       ▼  
                   ┌──────────────────────────────────────────┐  
                   │     CENTRAL NERVOUS SYSTEM (CNS)         │  
                   │           ORCHESTRATOR                   │  
                   └─────────────────┬────────────────────────┘  
                                     │  
          ┌──────────────────────────┼─────────────────────────────┐  
          │                          │                             │  
          ▼                          ▼                             ▼  
 ┌────────────────┐       ┌─────────────────────┐        ┌─────────────────┐  
 │Domain Control  │──────▶│Environment Control  │───────▶│Execution Control│  
 │(Skills)        │       │(Resources/Body)     │        │(Motor System)   │  
 └────────────────┘       └─────────────────────┘        └─────────────────┘  
                                     │  
                                     ▼  
                    ┌──────────────────────────────────────┐  
                    │     REAL WORLD / TOOLS / SYSTEMS     │  
                    │ Browser │ Terminal │ Files │ APIs    │  
                    │ Desktop │ Cloud │ Local │ Database  │  
                    └──────────────────────────────────────┘

──────────────────────────────────────────────────────────────────────────────

Cross Cutting Systems

• Self Healing  
• Logging  
• Security  
• Communication Bus  
• State Manager  
• Plugin System  
• Universal Laws  
---

# **Diagram 2 — Domain Controller**

                    DOMAIN CONTROLLER  
                   (WHAT TO DO)

                         │  
 ┌───────────────────────┼────────────────────────┐  
 │                       │                        │  
 ▼                       ▼                        ▼

Browser          Coding Controller         GUI Controller

Document         Communication             Data

Research         Planning                  Creativity

Automation

Think of these as **Departments inside a company.**

Each department is an expert.

None of them knows how to execute.

They only know HOW TO THINK.

---

# **Diagram 3 — Environment Controller**

                 ENVIRONMENT CONTROLLER  
                      (BODY)

                     Resource Manager  
                            │  
 ┌──────────────┬────────────┼───────────────┬────────────┐  
 │              │            │               │            │  
 ▼              ▼            ▼               ▼            ▼

Vision       Audio       Video         Runtime       Memory

                                  Browser Sessions  
                                  VM  
                                  Containers

             App Scanner  
             Desktop Scanner  
             Web Scanner  
             OCR

             File System

             Network

             Device Manager

             Window Manager

             Security

             Logging

             State

             Environment Memory

Notice something?

Nothing here makes decisions.

Everything here exposes capabilities.

---

# **Diagram 4 — Execution Controller**

             EXECUTION CONTROLLER  
             (Heart \+ Motor System)

                    Scheduler  
                        │  
                        ▼  
                 Action Planner  
                        │  
                        ▼  
                 Task Executor  
                        │  
                        ▼  
              Synchronization Manager  
                        │  
                        ▼  
                 Validation Manager  
                        │  
          ┌─────────────┴──────────────┐  
          ▼                            ▼

     Retry Manager             Rollback Manager  
          │                            │  
          └─────────────┬──────────────┘  
                        ▼  
                Progress Tracker  
                        │  
                        ▼  
               Completion Manager

Notice again...

No reasoning.

Only execution.

---

# **Diagram 5 — Communication Architecture**

                 EVENT BUS

          Controller A  
                │  
                ▼

         Publish Event  
                │  
                ▼

        Message Queue

                │  
                ▼

        Event Router

                │  
     ┌──────────┼──────────┐  
     ▼          ▼          ▼

 Controller B Controller C Controller D

        ACK  
        Retry  
        Timeout  
        Priority  
        Cancel

Nobody directly calls each other.

Everything speaks through events.

---

# **Diagram 6 — Human Analogy**

                HUMAN

Brain  
↓

Central Nervous System

↓

Skills (Domain Controllers)

↓

Body (Environment)

↓

Heart \+ Muscles (Execution)

↓

Hands / Eyes / Tools

↓

Real World

──────────────────────────────

Self Healing  
        ↑

Memory  
        ↑

Learning

──────────────────────────────

Everything connected through nerves  
(Event Bus)  
---

# **Diagram 7 — Future n8n Blueprint**

Trigger

↓

Input Normalizer

↓

Compiler

↓

Brain

↓

Orchestrator

↓

Domain Selector

↓

Environment Allocator

↓

Execution Engine

↓

Verification

↓

Report

↓

Self Healing

↓

Knowledge Update  
---

Brain

↓

CNS

↓

Domain

↓

Environment

↓

Execution

I actually think we're **missing one crucial layer** between the Brain and the CNS:

Brain

↓

Compiler

↓

CNS

↓

Domain

↓

Environment

↓

Execution  
—------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

Absolutely. Before we write a single line of code, these diagrams should become the **official blueprint** of Hojaiga. Every `.md` file, every Claude project, and every implementation should derive from these.

---

# **Diagram 1 — Hojaiga Architecture Blueprint (Human Topology)**

This is the **master blueprint**.

                                        👤 USER  
                                            │  
                   Text │ Voice │ Image │ Video │ Files  
                                            │  
                                            ▼  
═══════════════════════════════════════════════════════════════════════════════  
                           🧠 BRAIN (Mind)  
═══════════════════════════════════════════════════════════════════════════════

 • Intent Recognition  
 • Multi-modal Understanding  
 • Task Compilation  
 • Critical Thinking  
 • Strategy Planning  
 • Tool Knowledge  
 • Domain Knowledge  
 • Memory Retrieval  
 • Creativity  
 • Reflection  
 • Risk Analysis  
 • Learning  
 • Policy Generation

                            │  
            Compiled Execution Plan \+ Policies  
                            ▼

═══════════════════════════════════════════════════════════════════════════════  
                    🧬 CNS (Central Nervous System)  
═══════════════════════════════════════════════════════════════════════════════

 ┌─────────────────────────────────────────────────────────────────────┐  
 │ Session Manager                                                     │  
 │ Shared Session Memory                                               │  
 │ Scheduler                                                           │  
 │ Queue Manager                                                       │  
 │ Dependency Resolver                                                 │  
 │ Agent Manager                                                       │  
 │ Policy Engine                                                       │  
 │ Lightweight Reasoner (Rule Engine)                                  │  
 │ Resource Coordinator                                                │  
 │ Handshake Manager                                                   │  
 └─────────────────────────────────────────────────────────────────────┘

              │  
              │ Intelligence / Session Bus  
              │  
              ├───────────────────────────────────────────────┐  
              │                                               │  
              ▼                                               ▼

     Event Bus                                   Elevation Waiting Room  
 (Broadcast Communication)                     (Unknown / Complex Tasks)

              │                                               │  
              │                                               ▼  
              │                                     Brain Consultation  
              │                                               │  
              └───────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════  
                    CONTROLLER HIERARCHY (Inheritance)  
═══════════════════════════════════════════════════════════════════════════════

                 DOMAIN CONTROLLER (Grandfather)  
                           │  
       Defines Goals │ Policies │ Permissions │ Objectives  
                           │  
                           ▼

             ENVIRONMENT CONTROLLER (Father)  
                           │  
     Resources │ Memory │ Browser │ Vision │ Audio │ Files │ APIs  
                           │  
                           ▼

             EXECUTION CONTROLLER (Child)  
                           │  
    Action Planner │ Validator │ Retry │ Executor │ Spawn  
                           │  
                           ▼

═══════════════════════════════════════════════════════════════════════════════  
                  TEMPORARY EXECUTION WORKERS  
═══════════════════════════════════════════════════════════════════════════════

 Browser Worker  
 Python Worker  
 OCR Worker  
 Vision Worker  
 GUI Worker  
 Coding Worker  
 Research Worker  
 Validation Worker  
 Reporting Worker

(Spawn → Execute → Destroy)

═══════════════════════════════════════════════════════════════════════════════  
                  LONG TERM EVOLUTION  
═══════════════════════════════════════════════════════════════════════════════

 Self Healing Engine

        │

 Root Cause Analysis

        │

 Policy Improvement

        │

 Knowledge Expansion

        │

 Cognitive Growth Engine

        │

 Future Hojaiga Versions  
---

# **Diagram 2 — n8n Workflow**

This is the implementation flow.

User Input  
      │  
      ▼  
Input Gateway  
      │  
      ▼  
─────────────────────────────────────  
Brain  
─────────────────────────────────────

Intent Recognition

↓

Compilation

↓

Critical Thinking

↓

Planning

↓

Tool Selection

↓

Execution Plan

─────────────────────────────────────  
            │  
            ▼

─────────────────────────────────────  
             CNS  
─────────────────────────────────────

Session Manager

↓

Scheduler

↓

Queue Manager

↓

Agent Manager

↓

Policy Engine

↓

Controller Routing

            │  
            ▼

─────────────────────────────────────  
 Controller Stack  
─────────────────────────────────────

Domain Controller

↓

Environment Controller

↓

Execution Controller

↓

Spawn Worker

↓

Worker Executes

↓

Validation

↓

Report

            │  
            ▼

Task Finished?

───────────────  
YES  
───────────────

↓

Return Output

↓

Idle

↓

Self Healing

↓

Cognitive Growth

───────────────  
NO  
───────────────

↓

Retry Policy?

↓

YES

↓

Retry

↓

Success

↓

Return

───────────────

NO

↓

Elevation Waiting Room

↓

Brain

↓

New Strategy

↓

Continue Execution  
---

# **Diagram 3 — Human Analogy Blueprint**

This explains **why** each subsystem exists.

               HUMAN BODY

                    │

─────────────────────────────────────  
BRAIN  
─────────────────────────────────────

Human  
• Thinks  
• Learns  
• Plans  
• Imagines  
• Understands

Hojaiga  
• Intent  
• Compilation  
• Planning  
• Knowledge  
• Reasoning  
• Creativity

─────────────────────────────────────  
CNS  
─────────────────────────────────────

Human  
• Sends nerve signals  
• Coordinates movement  
• Synchronizes body

Hojaiga  
• Scheduler  
• Session Memory  
• Queue  
• Agent Routing  
• Controller Coordination

─────────────────────────────────────  
DOMAIN CONTROLLER  
─────────────────────────────────────

Human

Long-term objectives

"Cook dinner"

Hojaiga

Mission

Policies

Goal

Success criteria

─────────────────────────────────────  
ENVIRONMENT CONTROLLER  
─────────────────────────────────────

Human

Eyes

Hands

Kitchen

Tools

Hojaiga

Browser

Filesystem

Vision

Audio

Terminal

Memory

APIs

─────────────────────────────────────  
EXECUTION CONTROLLER  
─────────────────────────────────────

Human

Moves muscles

Uses fingers

Acts

Hojaiga

Planner

Executor

Validator

Retry

Spawn Workers

─────────────────────────────────────  
TEMPORARY WORKERS  
─────────────────────────────────────

Human

Finger movement

Eye focus

Walking

Hojaiga

Browser Worker

OCR Worker

Python Worker

Research Worker

Coding Worker

GUI Worker

─────────────────────────────────────  
SELF HEALING  
─────────────────────────────────────

Human

Learns from mistakes

Hojaiga

Root Cause Analysis

Policy Updates

Knowledge Updates

─────────────────────────────────────  
COGNITIVE GROWTH  
─────────────────────────────────────

Human

Toddler

↓

Child

↓

Teenager

↓

Adult

↓

Expert

↓

Teacher

Hojaiga

Version 1

↓

Version 2

↓

Version 3

↓

Version 4

↓

Version 5

↓

Designs Version 6  
—------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

HOJAIGA/  
│  
├── README.md  
├── LICENSE  
├── requirements.txt  
├── pyproject.toml  
├── launcher.py  
├── config.yaml  
│  
├───────────────────────────────────────────────  
│  
├── docs/  
│   │  
│   ├── 00\_PROJECT\_VISION.md  
│   ├── 01\_HUMAN\_TOPOLOGY.md  
│   ├── 02\_SYSTEM\_DIAGRAM.md  
│   ├── 03\_N8N\_WORKFLOW.md  
│   ├── 04\_CONTROLLER\_ARCHITECTURE.md  
│   ├── 05\_MEMORY\_ARCHITECTURE.md  
│   ├── 06\_POLICIES.md  
│   ├── 07\_UNIVERSAL\_LAWS.md  
│   ├── 08\_FOUNDATIONAL\_LAWS.md  
│   ├── 09\_SELF\_HEALING.md  
│   ├── 10\_COGNITIVE\_GROWTH.md  
│   ├── 11\_CHECKPOINTS.md  
│   ├── 99\_EVOLUTION\_ROADMAP.md  
│  
├───────────────────────────────────────────────  
│  
├── brain/  
│   │  
│   ├── compiler/  
│   ├── planner/  
│   ├── reasoning/  
│   ├── creativity/  
│   ├── reflection/  
│   ├── tool\_knowledge/  
│   ├── domain\_knowledge/  
│   ├── memory\_access/  
│   ├── policy\_generation/  
│   └── learning/  
│  
├───────────────────────────────────────────────  
│  
├── cns/  
│   │  
│   ├── session\_manager/  
│   ├── shared\_memory/  
│   ├── scheduler/  
│   ├── queue\_manager/  
│   ├── dependency\_manager/  
│   ├── agent\_manager/  
│   ├── handshake/  
│   ├── policy\_engine/  
│   ├── lightweight\_reasoner/  
│   ├── capability\_registry/  
│   ├── event\_bus/  
│   ├── session\_bus/  
│   └── elevation\_room/  
│  
├───────────────────────────────────────────────  
│  
├── controllers/  
│   │  
│   ├── domain/  
│   │      ├── creativity/  
│   │      ├── coding/  
│   │      ├── research/  
│   │      ├── browser/  
│   │      ├── planning/  
│   │      └── ...  
│   │  
│   ├── environment/  
│   │      ├── browser/  
│   │      ├── filesystem/  
│   │      ├── vision/  
│   │      ├── audio/  
│   │      ├── terminal/  
│   │      ├── api/  
│   │      ├── memory/  
│   │      └── resources/  
│   │  
│   └── execution/  
│          ├── planner/  
│          ├── executor/  
│          ├── validator/  
│          ├── retry/  
│          ├── monitor/  
│          └── worker\_spawn/  
│  
├───────────────────────────────────────────────  
│  
├── agents/  
│   │  
│   ├── permanent/  
│   └── temporary/  
│  
├───────────────────────────────────────────────  
│  
├── memory/  
│   │  
│   ├── working/  
│   ├── environment/  
│   ├── knowledge/  
│   ├── experience/  
│   └── policies/  
│  
├───────────────────────────────────────────────  
│  
├── execution/  
│   │  
│   ├── browser/  
│   ├── python/  
│   ├── terminal/  
│   ├── filesystem/  
│   ├── gui/  
│   ├── api/  
│   ├── vision/  
│   ├── audio/  
│   └── reporting/  
│  
├───────────────────────────────────────────────  
│  
├── self\_healing/  
│  
├── cognitive\_growth/  
│  
├── paradigms/  
│  
├── prompts/  
│  
├── logs/  
│  
├── cache/  
│  
├── checkpoints/  
│  
├── tests/  
│  
└── tools/  
