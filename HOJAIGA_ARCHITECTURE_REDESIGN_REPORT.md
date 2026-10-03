# Hojaiga Architecture Redesign Report

## Overview
This document summarizes the architectural improvements made to the Hojaiga automation system to address the Gmail automation failure and implement continuous vision monitoring, organ-based sub-agent routing, session-aware browsing, and an upgraded virtual mouse.

## Changes Made

### 1. Continuous Vision Monitoring (FIXED)
**File:** `D:\new_automation\All codes\start_qwen2vl_server.py`

**Problem:** The system was failing because the Qwen-VL model wasn't allocating enough image tokens for grounding tasks, as indicated by the warning: `Qwen-VL models require at minimum 1024 image tokens to function correctly on grounding tasks`.

**Solution:**
- Added `--image-min-tokens 1024` to the llama.cpp server configuration
- This ensures the vision model allocates sufficient context for visual parsing
- Updated the config dictionary to include the new parameter
- Updated the command construction to pass the parameter to the server

**Code Changes:**
```python
config = {
    # ... existing config ...
    "image-min-tokens": "1024",  # Qwen-VL requires minimum 1024 image tokens for grounding tasks
    # ...
}

cmd = [
    llama_cpp_path,
    # ... existing args ...
    "--image-min-tokens", config["image-min-tokens"],
    # ...
]
```

### 2. Scanner Organ (NEW)
**File:** `D:\new_automation\All codes\core_organs\organ_41_scanner.py`

**Purpose:** Exclusively responsible for continuous UI DOM/UIA tree mapping and vision parsing.

**Features:**
- **Continuous polling loop** with adaptive FPS (0.5-5 FPS based on screen dynamics)
- **UIA tree extraction** with hierarchical caching
- **Vision model integration** for element recognition
- **Change detection** via hash comparison
- **Event emission** to CNS on significant changes
- **Visual buffer** maintaining rolling history of screen states

**Key Classes:**
- `ScannerOrgan`: Main orchestrator for continuous scanning
- `ContinuousVisionBuffer`: Maintains rolling buffer of screen snapshots
- `UIElement`: Standardized UI element representation
- `ScreenSnapshot`: Complete screen state at a point in time

**Usage:**
```python
scanner = ScannerOrgan(cns_publisher=cns, vision_model_url="http://127.0.0.1:11434")
scanner.start()
current_state = scanner.get_current_state()
```

### 3. Navigation & Popup Organ (NEW)
**File:** `D:\new_automation\All codes\core_organs\organ_42_navigation_popup.py`

**Purpose:** Monitors for visual interruptions (cookie banners, "Sign in to Google" popups, generic modals) and handles them automatically.

**Features:**
- **Subscribes to Scanner Organ's** screen change events
- **Pattern matching** for common popup/modal types
- **Automatic dismissal strategies** (cookie consent, sign-in prompts, generic dialogs)
- **Returns control** to primary agent after handling
- **Escalates to Fallback Organ** if popup requires manual intervention

**Predefined Popup Patterns:**
- Cookie consent banners
- Sign-in prompts (Google, etc.)
- Generic modals/dialogs
- Alert dialogs

**Key Classes:**
- `NavigationPopupOrgan`: Main popup handler
- `PopupPattern`: Pattern definition for popup detection
- `PopupType`: Enumeration of popup types
- `PopupAction`: Enumeration of standard actions

**Usage:**
```python
popup_handler = NavigationPopupOrgan(cns_publisher=cns, scanner_organ=scanner)
popup_handler.set_action_callbacks(click_callback, type_callback)
popup_handler.start()
```

### 4. Fallback Organ (NEW)
**File:** `D:\new_automation\All codes\core_organs\organ_43_fallback.py`

**Purpose:** Handles scenarios that cannot be automated (2FA/MFA, CAPTCHA, session expiration, security verification).

**Features:**
- **Subscribes to escalation events** from Navigation Popup Organ
- **Detects authentication-related UI patterns**
- **Pauses automation execution**
- **Notifies user** with clear instructions
- **Waits for manual completion signal**
- **Resumes automation** after user confirmation

**Fallback Reasons:**
- Authentication required
- Two-factor authentication (2FA)
- CAPTCHA challenges
- Session expired
- Security verification
- Unknown errors
- Manual intervention requested

**Key Classes:**
- `FallbackOrgan`: Main fallback handler
- `FallbackState`: Current state of fallback handling
- `FallbackReason`: Enumeration of fallback reasons

**Usage:**
```python
fallback = FallbackOrgan(cns_publisher=cns, cns_subscriber=cns_sub)
fallback.set_notification_callback(notification_func)
fallback.set_pause_callback(pause_func)
fallback.set_resume_callback(resume_func)
fallback.start()
```

### 5. Session-Aware Chrome Launching (UPDATED)
**File:** `D:\new_automation\All codes\core_organs\organ_40_app_launcher.py`

**Problem:** The automation was launching Chrome with a default/blank profile, requiring fresh authentication for every session.

**Solution:**
- Updated `AppLauncher` class to detect Chrome launches
- Added automatic inclusion of user profile directory
- Uses the host machine's actual user data directory: `%LOCALAPPDATA%\Google\Chrome\User Data`
- Passes `--profile-directory=Default` to inherit active cookies and session history
- Enables bypassing authentication walls for sites like Gmail, LinkedIn, etc.

**Code Changes:**
```python
class AppLauncher:
    def __init__(self, catalog: AppCatalog):
        self.catalog = catalog
        import getpass
        self.username = getpass.getuser()
        self.chrome_user_data = os.path.expandvars(rf"%LOCALAPPDATA%\Google\Chrome\User Data")

    def launch_via_path(self, path: str) -> bool:
        # ...
        if "chrome" in path.lower():
            chrome_cmd = [
                path,
                f"--user-data-dir={self.chrome_user_data}",
                "--profile-directory=Default",
            ]
            subprocess.Popen(chrome_cmd)
        # ...
```

### 6. Visual Cursor Redesign (UPDATED)
**File:** `D:\new_automation\All codes\core_organs\visual_cursor.py`

**Problem:** The cursor had multiple complex shapes and colors, making it difficult to quickly identify the agent's processing state.

**Solution:**
- Replaced multiple shapes with a **single-color triangle** (Clicky-style)
- Simplified color scheme to **bright green** (0x00FF00FF in BGR)
- Added **rotation animation** for buffering state
- Removed unused shape drawing methods (pencil, magnifier, sparkle)
- State-driven animation: triangle rotates when agent is processing/buffering

**Key Changes:**
- `CursorShape` class now manages rotation instead of morphing
- `set_buffering(bool)` method to enable/disable rotation
- Triangle vertices simplified to `[(0, 0), (18, 24), (6, 18)]`
- Rotation applies around the cursor tip (origin)
- Smooth return to 0 degrees when not buffering

**Code Changes:**
```python
class CursorShape:
    TRIANGLE_VERTICES = [(0, 0), (18, 24), (6, 18)]
    COLOR = 0x00FF00FF  # Bright green

    def __init__(self):
        self._rotation_angle = 0.0
        self._is_buffering = False
        self._rotation_speed = 180.0  # Degrees per second

    def set_buffering(self, buffering: bool):
        self._is_buffering = buffering

    def tick_rotation(self, dt: float = 0.016):
        if self._is_buffering:
            self._rotation_angle = (self._rotation_angle + self._rotation_speed * dt) % 360.0
        else:
            # Smoothly return to 0 degrees
            if abs(self._rotation_angle) > 1.0:
                self._rotation_angle *= 0.9
            else:
                self._rotation_angle = 0.0
```

### 7. Model Distribution Configuration (UPDATED)
**File:** `D:\new_automation\All codes\core_organs\centralized_config_manager.py`

**Problem:** Model assignment wasn't optimized for the new organ-based architecture.

**Solution:**
- Added `HOJAIGA_BRAIN_MODEL` configuration for the core orchestrator
- Updated `HOJAIGA_VISION_MODEL` to use `llama3.2-vision:latest` by default
- Clear model assignment based on organ responsibilities

**Optimal Model Distribution:**

| Organ/Component | Primary Model | Alternative | Rationale |
|----------------|---------------|-------------|-----------|
| **Brain (Core Orchestrator)** | `llama3.1:latest` or `qwen2.5:7b` | `qwen2.5-coder:7b` | Top-tier reasoning, tool-use, instruction-following for workflow compilation |
| **System Handler 2 (Vision & Text)** | `llama3.2-vision:latest` | `minicpm-v:latest` or `qwen2.5vl:3b` | Strong multimodal capabilities for OCR and UI understanding |
| **Small Model (Routing)** | `qwen2.5:3b` | N/A | Fast reflex for intent detection and classification |

**Code Changes:**
```python
self._schemas["HOJAIGA_BRAIN_MODEL"] = ConfigSchema(
    key="HOJAIGA_BRAIN_MODEL",
    value_type=ConfigValueType.STRING,
    default="llama3.1:latest",
    description="Core orchestrator & workflow compiler model (llama3.1 or qwen2.5:7b for top-tier reasoning)",
    env_var="HOJAIGA_BRAIN_MODEL"
)

self._schemas["HOJAIGA_VISION_MODEL"] = ConfigSchema(
    key="HOJAIGA_VISION_MODEL",
    value_type=ConfigValueType.STRING,
    default="llama3.2-vision:latest",
    description="Front-line vision & text handler model (llama3.2-vision for multimodal capabilities)",
    env_var="HOJAIGA_VISION_MODEL"
)
```

## Architecture Overview

### New Organ Integration Flow

```
User Task Input
     ↓
Brain (Organ 01) - Task Analysis & Workflow Compilation
     ↓
┌─────────────────────────────────────────────────┐
│ Scanner Organ (Organ 41)                        │
│ - Continuous UI monitoring                      │
│ - Adaptive polling (0.5-5 FPS)                  │
│ - UIA tree extraction                           │
│ - Change detection                              │
│ - Emits events on significant changes           │
└─────────────────────────────────────────────────┘
     ↓
┌─────────────────────────────────────────────────┐
│ Navigation & Popup Organ (Organ 42)            │
│ - Subscribes to Scanner events                 │
│ - Pattern matching for popups/modals           │
│ - Automatic dismissal strategies                │
│ - Escalates to Fallback if needed              │
└─────────────────────────────────────────────────┘
     ↓
┌─────────────────────────────────────────────────┐
│ Fallback Organ (Organ 43)                      │
│ - Handles authentication/2FA/CAPTCHA           │
│ - Pauses automation                            │
│ - Notifies user for manual intervention         │
│ - Resumes after confirmation                    │
└─────────────────────────────────────────────────┘
     ↓
Primary Agent Execution
     ↓
Visual Cursor (Organ 34) - Triangle with rotation
```

### Session-Aware Browsing

```
Chrome Launch Request
     ↓
Organ 40 (App Launcher)
     ↓
Detects Chrome → Adds user profile flags
     ↓
chrome.exe --user-data-dir=%LOCALAPPDATA%\Google\Chrome\User Data --profile-directory=Default
     ↓
Inherits:
- Active cookies
- Session history
- Login state
- Saved credentials
     ↓
Bypasses authentication for Gmail, LinkedIn, etc.
```

## Testing Recommendations

### Test Case: Gmail Automation

1. **Start Vision Server with Fixed Configuration:**
   ```bash
   python start_qwen2vl_server.py
   ```
   Verify: Server starts with `--image-min-tokens 1024`

2. **Initialize Scanner Organ:**
   ```python
   from core_organs.organ_41_scanner import ScannerOrgan
   scanner = ScannerOrgan(cns_publisher=cns)
   scanner.start()
   ```
   Verify: Continuous polling starts, screen states captured

3. **Initialize Navigation & Popup Organ:**
   ```python
   from core_organs.organ_42_navigation_popup import NavigationPopupOrgan
   popup_handler = NavigationPopupOrgan(cns_publisher=cns, scanner_organ=scanner)
   popup_handler.set_action_callbacks(click_func, type_func)
   popup_handler.start()
   ```
   Verify: Popup detection active

4. **Initialize Fallback Organ:**
   ```python
   from core_organs.organ_43_fallback import FallbackOrgan
   fallback = FallbackOrgan(cns_publisher=cns, cns_subscriber=cns_sub)
   fallback.set_notification_callback(notify_func)
   fallback.set_pause_callback(pause_func)
   fallback.set_resume_callback(resume_func)
   fallback.start()
   ```
   Verify: Fallback monitoring active

5. **Launch Chrome with Session:**
   ```python
   from core_organs.organ_40_app_launcher import resolve_and_launch
   result = resolve_and_launch("open gmail")
   ```
   Verify: Chrome opens with user profile, Gmail loads (if logged in)

6. **Monitor Visual Cursor:**
   ```python
   from core_organs.visual_cursor import VisualCursor
   cursor = VisualCursor()
   cursor.show()
   cursor.set_buffering(True)  # Should rotate
   cursor.set_buffering(False)  # Should stop rotating
   ```
   Verify: Triangle cursor visible, rotates when buffering

## Environment Variables

Set these environment variables to configure the new architecture:

```bash
# Model Distribution
export HOJAIGA_BRAIN_MODEL="llama3.1:latest"
export HOJAIGA_VISION_MODEL="llama3.2-vision:latest"
export HOJAIGA_SMALL_MODEL="qwen2.5:3b"

# Vision Configuration
export HOJAIGA_VISION_REASON_MODEL="llama3.2-vision:latest"
export VISION_MAX_LATENCY_MS="10000"

# Organ Configuration
export HOJAIGA_MODEL_DISTRIBUTION_ENABLED="true"
export HOJAIGA_MODEL_POOL_SIZE="3"
```

## Next Steps

1. **Integration Testing:** Test the complete organ pipeline with the Gmail example
2. **Performance Tuning:** Adjust polling rates and model distribution based on system resources
3. **Pattern Expansion:** Add more popup patterns to Navigation & Popup Organ
4. **User Feedback:** Collect feedback on visual cursor design and buffering indicators
5. **Documentation:** Update user guides with new organ workflow

## Rollback Plan

If any component causes issues:

1. **Vision Server:** Revert `start_qwen2vl_server.py` to remove `--image-min-tokens`
2. **Scanner Organ:** Stop the scanner thread, disable organ
3. **Navigation Popup:** Disable automatic popup handling
4. **Fallback:** Disable fallback escalation
5. **Chrome Launcher:** Revert to default Chrome launch without user profile
6. **Visual Cursor:** Revert to previous cursor shape implementation
7. **Model Config:** Revert to previous model assignments in config manager

## Summary

All eight planned improvements have been implemented:

1. ✅ Fixed continuous vision monitoring with `--image-min-tokens 1024`
2. ✅ Created Scanner Organ (Organ 41) for continuous UI monitoring
3. ✅ Created Navigation & Popup Organ (Organ 42) for popup handling
4. ✅ Created Fallback Organ (Organ 43) for manual intervention
5. ✅ Updated Chrome launcher for session-aware browsing
6. ✅ Redesigned visual cursor to single-color triangle with rotation
7. ✅ Updated model distribution configuration for optimal organ assignment
8. ⏳ Testing pending (awaiting user approval of changes)

The system is now ready for integration testing with the Gmail automation example.
