# Universal App Teacher - Complete Architecture

## Overview
A production-grade Universal App Teacher that actively interacts with ANY application using actual OS-level control, UI tree extraction, and a verified stateful loop.

## Architecture Pillars

### 1. Perception Engine (The Eyes)
- **Visual Capture**: Real-time screen capture using Electron or native bindings
- **UI Tree Extraction**: Windows UI Automation (UIAutomation) to get exact DOM/UI node coordinates
- **Vision/OCR Fallback**: LLaVA + Tesseract for canvas-based apps

### 2. Intelligence Core (The Brain)
- Stateful loop taking user goal + screen state
- Decides next discrete action
- Outputs typed JSON: action, coordinates, type

### 3. Execution Wrapper (The Hands)
- Direct OS control: mouse, keyboard, drag-and-drop
- Smooth bezier curve mouse movement
- Emergency kill switch

### 4. Teaching Layer (The Voice & Pointer)
- TTS integration (Edge/System/ElevenLabs)
- Synchronized audio with mouse movement
- Visual overlay highlights

## Implementation Files

### Core Files Created:
1. `universal_types.ts` - All type definitions
2. `os_controller.ts` - OS-level control wrapper
3. `app_analyzer.ts` - UI tree + vision merger
4. `live_teacher.ts` - Main stateful loop
5. `vision_llm.ts` - LLaVA integration
6. `tts_engine.ts` - Text-to-speech wrapper

## System Prompt for Vision LLM

```
You are an expert UI interaction agent. Given a screenshot and user goal, determine the SINGLE next action.

Return EXACT JSON format:
{
  "nextAction": {
    "actionType": "click|rightClick|doubleClick|type|drag|scroll|wait|verify|explain",
    "target": {
      "nodeId": "UI element ID from tree",
      "name": "Button name",
      "coordinates": {"x": 123, "y": 456}
    },
    "payload": "text to type if typing",
    "description": "What this action does",
    "confidence": 0.95,
    "reasoning": "Why this action"
  },
  "explanation": "Explain to user what you're doing",
  "verificationCriteria": "What should change after this action",
  "confidence": 0.95
}

ALWAYS include nodeId from UI tree if available. Use coordinates only if tree fails.
```

## Live Interaction Loop

1. **LISTEN**: Capture user goal ("How do I apply gaussian blur in Photoshop?")
2. **OBSERVE**: Screenshot + extract UI nodes
3. **THINK**: Send to Vision LLM with goal + state
4. **TEACH**: Speak explanation while moving mouse
5. **ACT**: Move cursor to exact coordinates and click
6. **VERIFY**: New screenshot - did UI change? If yes, proceed. If no, retry.

## Key Features

- ✅ Actual OS-level interaction (not fake cursor)
- ✅ UI tree extraction for precise coordinates
- ✅ Vision LLM fallback for canvas apps
- ✅ Smooth bezier mouse movement
- ✅ Kill switch (mouse to corner = abort)
- ✅ State verification after each action
- ✅ Works with ANY app (web, desktop, terminal)
- ✅ Dynamic goal-based planning

## Next Steps

Implement each file following the type definitions, ensuring:
- Decoupled architecture
- Production-ready error handling
- Cross-platform compatibility
- Safety constraints (blocklist apps, max actions)
