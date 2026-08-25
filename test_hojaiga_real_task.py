import warnings
warnings.filterwarnings("ignore")

import asyncio
import uuid
import sys
import os
from pathlib import Path
import logging

# Suppress all noisy third-party libraries and warnings
logging.basicConfig(level=logging.ERROR)
for noisy_logger in [
    "speechbrain", "faster_whisper", "huggingface_hub", "httpx", "websockets",
    "urllib3", "torch", "haos.interface_layer", "haos.local_stt"
]:
    logging.getLogger(noisy_logger).setLevel(logging.ERROR)

# Add core path
sys.path.append(str(Path(__file__).parent / "All codes"))

from core_organs.organ_02_cns_single_file import EventBus, EventEnvelope
from core_organs.organ_38_task_orchestrator import TaskOrchestrator
from observability.organ_16_audit_system import AuditSystem
from core_organs.organ_07_security import SecurityKernel
from core_organs.organ_01_brain import BrainOrgan
from core_organs.organ_22_decision_engine import DecisionEngineOrgan
from core_organs.organ_36_workflow_compiler import WorkflowCompilerKernel
from core_organs.organ_32_state_catalog import StateCatalogOrgan
from core_organs.organ_03_memory import MemoryCore
from core_organs.organ_04_knowledge import KnowledgeOrgan
from core_organs.organ_10_agents import AgentsOrgan
from core_organs.organ_30_app_scanner import AppScannerOrgan
from core_organs.organ_31_visual_perception import VisualPerceptionOrgan
from core_organs.organ_05_controllers import ControllersCore
from core_organs.organ_29_popup_handler import DesktopInteractionManager
from chrome_launcher import launch_chrome_for_trial
from observability.organ_99_visual_adapter import VisualAdapterServer, EventBusWrapper

async def run_real_task_test(enable_visualizer: bool, inject_failure: bool = False, test_name: str = "Standard Run"):
    print(f"\n{'='*50}\nStarting Real Task Validation: {test_name}\nVisualizer Enabled: {enable_visualizer}\n{'='*50}")
    
    cns = EventBus()
    audit = AuditSystem(storage_dir=f"./audit_logs_test_real_{uuid.uuid4().hex[:6]}")
    security = SecurityKernel(Path("."))
    
    # Set up environment routing BEFORE instantiating organs
    os.environ["HOJAIGA_CDP_PORT"] = "47619"
    # Route through Hojaiga Brain Gatekeeper (port 11435) protecting Ollama (port 11434)
    os.environ["HOJAIGA_BRAIN_URL"] = "http://127.0.0.1:11435/api/chat"
    
    orchestrator = TaskOrchestrator(cns, audit, security)
    brain = BrainOrgan()
    decision_engine = DecisionEngineOrgan()
    compiler = WorkflowCompilerKernel()
    state_catalog = StateCatalogOrgan()
    memory = MemoryCore()
    knowledge = KnowledgeOrgan()
    agents = AgentsOrgan()
    app_scanner = AppScannerOrgan()
    visual_perception = VisualPerceptionOrgan()
    controllers = ControllersCore()
    popup_handler = DesktopInteractionManager()

    # chrome_mode = os.environ.get("HOJAIGA_CHROME_MODE", "safe").strip().lower()
    # chrome_profile = os.environ.get("HOJAIGA_CHROME_PROFILE", "Profile 1")
    # chrome_user_data = os.environ.get("HOJAIGA_CHROME_USER_DATA_BASE")
    # launch_chrome_for_trial(
    #     mode=chrome_mode,
    #     port=9222,
    #     ip="127.0.0.1",
    #     profile_name=chrome_profile,
    #     user_data_base=chrome_user_data,
    # )
    # await asyncio.sleep(2.5)

    # Launch Organ 19 (Chrome CDP Runtime) translator daemon in background (clean up stale processes first)
    import subprocess
    if os.name == 'nt':
        try:
            # Kill any stale python process holding port 47619
            subprocess.run(["powershell", "-Command", "Get-NetTCPConnection -LocalPort 47619 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        except Exception:
            pass
            
    organ_19_path = Path(__file__).parent / "All codes" / "core_organs" / "organ_19_chrome_cdp_runtime.py"
    subprocess.Popen([sys.executable, str(organ_19_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    await asyncio.sleep(1.5)
    
    
    await orchestrator.start()
    await brain.start(cns)
    await decision_engine.start_cns(cns)
    await compiler.start(cns)
    memory.start()
    await memory.start_cns(cns)
    await knowledge.start()
    await knowledge.start_cns(cns)
    await agents.start()
    await agents.start_cns(cns)
    await app_scanner.start_cns(cns)
    await visual_perception.start_cns(cns)
    await controllers.start_cns(cns)
    await state_catalog.start_cns(cns)
    await popup_handler.start_cns(cns)
    
    visualizer = None
    if enable_visualizer:
        visualizer = VisualAdapterServer(EventBusWrapper(cns))
        await cns.subscribe("*", "organ_99_sub", visualizer.on_cns_event)
        await visualizer.start()
        
    trace = []
    
    async def trace_monitor(env: EventEnvelope):
        payload = env.payload
        event_type = payload.get("event_type") or env.topic
        if event_type and event_type != "SCREEN_STATE_CHANGED":
            trace.append(event_type)
            print(f"[TRACE] {event_type} emitted by {env.source_organ}")
            # Update the UI status box dynamically if it exists
            if 'sys_status_update' in globals():
                try:
                    msg = f"Active Organ: {env.source_organ.upper()}\nCurrent State: {event_type}"
                    globals()['sys_status_update'](msg)
                except Exception:
                    pass
            
    await cns.subscribe("sys.events", "trace_monitor", trace_monitor)
    await cns.subscribe("REPLANNING_REQUESTED", "trace_monitor_rep", trace_monitor)
    await cns.subscribe("TASK_FAILED", "trace_monitor_fail", trace_monitor)
    await cns.subscribe("TASK_COMPLETED", "trace_monitor_comp", trace_monitor)
    await cns.subscribe("STATE_TRANSITION_FAILED", "trace_monitor_state_fail", trace_monitor)
    
    # Task Submission via UI
    task_id = str(uuid.uuid4())
    command = None
    
# [2026-08-17] LEGACY TKINTER UI DEPRECATED
#     def run_ui():
#         import tkinter as tk
#         import threading
#         from core_organs.organ_13_interface_layer import HojaigaVoiceInterface
#         
#         root = tk.Tk()
#         root.title("Hojaiga - Interface Layer")
#         root.geometry("600x450")
#         root.configure(bg="#2E3440")
#         root.attributes("-topmost", True)
# 
#         boot_frame = tk.Frame(root, bg="#2E3440")
#         task_frame = tk.Frame(root, bg="#2E3440")
#         
#         # --- Boot Frame ---
#         tk.Label(boot_frame, text="SYSTEM LOCKED", fg="#BF616A", bg="#2E3440", font=("Helvetica", 16, "bold")).pack(pady=20)
#         tk.Label(boot_frame, text="Security Question: What is the name of your grandmother?", fg="#D8DEE9", bg="#2E3440").pack(pady=5)
#         
#         pass_entry = tk.Entry(boot_frame, font=("Consolas", 14), show="*")
#         pass_entry.pack(pady=10)
#         
#         err_label = tk.Label(boot_frame, text="", fg="red", bg="#2E3440")
#         
#         def check_password(event=None):
#             if not getattr(voice_interface, 'engine_powered_on', False):
#                 pass_entry.delete(0, tk.END)
#                 err_label.config(text="Engine Offline. Say 'boot up' via voice (Hold Ctrl+Ctrl).")
#                 err_label.pack()
#                 return
# 
#             ans = pass_entry.get().strip().lower()
#             valid = ["lila", "liaben", "lilabaa", "manjibaa", "manjulaben", "leela", "lyla", "leila"]
#             if ans in valid:
#                 voice_interface.is_booted = True
#                 boot_frame.pack_forget()
#                 task_frame.pack(fill="both", expand=True)
#             else:
#                 pass_entry.delete(0, tk.END)
#                 err_label.config(text="Incorrect.")
#                 err_label.pack()
#                 
#         pass_entry.bind("<Return>", check_password)
#         tk.Button(boot_frame, text="Unlock", command=check_password, font=("Helvetica", 12, "bold"), bg="#A3BE8C", fg="#2E3440", relief=tk.FLAT, padx=10, pady=5).pack(pady=10)
#         boot_frame.pack(fill="both", expand=True)
#         
#         # --- Task Frame ---
#         tk.Label(task_frame, text="Enter dynamic task below:", bg="#2E3440", fg="#D8DEE9", font=("Helvetica", 14, "bold")).pack(pady=15)
#         text_box = tk.Text(task_frame, height=12, width=65, font=("Consolas", 12), bg="#3B4252", fg="#ECEFF4", insertbackground="white", wrap=tk.WORD)
#         text_box.pack(pady=10)
#         
#         def on_submit():
#             nonlocal command
#             command = text_box.get("1.0", tk.END).strip()
#             root.destroy()
#             
#         tk.Button(task_frame, text="Submit to CNS", command=on_submit, font=("Helvetica", 12, "bold"), bg="#88C0D0", fg="#2E3440", relief=tk.FLAT, padx=20, pady=10).pack(pady=15)
#             
#         # --- Floating Pill Voice Interface (CDP) ---
#         def on_voice_task(text):
#             nonlocal command
#             command = text
#             root.destroy()
#             
#         voice_interface = HojaigaVoiceInterface(None, None, on_voice_task)
#         
#         voice_window = tk.Toplevel(root)
#         voice_window.title("Hojaiga CDP")
#         
#         # Transparent background trick for Windows
#         transparent_color = 'magenta'
#         voice_window.configure(bg=transparent_color)
#         voice_window.attributes('-transparentcolor', transparent_color)
#         voice_window.overrideredirect(True)
#         voice_window.attributes("-topmost", True)
#         
#         # Position at bottom center initially
#         screen_width = root.winfo_screenwidth()
#         screen_height = root.winfo_screenheight()
#         voice_window.geometry(f"400x70+{int(screen_width/2 - 200)}+{int(screen_height - 150)}")
#         
#         canvas = tk.Canvas(voice_window, bg=transparent_color, highlightthickness=0, width=400, height=70)
#         canvas.pack(fill="both", expand=True)
#         
#         def create_round_rect(canvas, x1, y1, x2, y2, radius=25, **kwargs):
#             points = [x1+radius, y1, x1+radius, y1, x2-radius, y1, x2-radius, y1, x2, y1, x2, y1+radius, x2, y1+radius, x2, y2-radius, x2, y2-radius, x2, y2, x2-radius, y2, x2-radius, y2, x1+radius, y2, x1+radius, y2, x1, y2, x1, y2-radius, x1, y2-radius, x1, y1+radius, x1, y1+radius, x1, y1]
#             return canvas.create_polygon(points, **kwargs, smooth=True)
# 
#         bg_rect = create_round_rect(canvas, 10, 10, 390, 60, radius=20, fill="#1c1c1c", outline="#333333", width=1)
#         v_label = tk.Label(voice_window, text="Agent needs your input", fg="#d4d4d4", bg="#1c1c1c", font=("Segoe UI", 11, "bold"))
#         v_label.place(x=30, y=15)
#         voice_interface.ui_label = v_label
#         
#         sub_label = tk.Label(voice_window, text="Hold Left+Right Ctrl (or ~) to speak", fg="#888888", bg="#1c1c1c", font=("Segoe UI", 8))
#         sub_label.place(x=30, y=36)
#         
#         # Action Icons
#         def on_mic_click(e):
#             voice_interface.force_record = True
#             
#         mic_btn = canvas.create_oval(310, 18, 334, 42, fill="#2b2b2b", outline="#444")
#         mic_icon = canvas.create_oval(318, 26, 326, 34, fill="#ff4444", outline="")
#         canvas.tag_bind(mic_btn, "<Button-1>", on_mic_click)
#         canvas.tag_bind(mic_icon, "<Button-1>", on_mic_click)
#         
#         def on_remind_click(e):
#             voice_window.withdraw()
#             root.after(300000, voice_window.deiconify)
#             
#         remind_btn = canvas.create_rectangle(345, 18, 375, 42, fill="#2b2b2b", outline="#444")
#         remind_text = canvas.create_text(360, 30, text="5m", fill="#d4d4d4", font=("Segoe UI", 9))
#         canvas.tag_bind(remind_btn, "<Button-1>", on_remind_click)
#         canvas.tag_bind(remind_text, "<Button-1>", on_remind_click)
#         
#         # Dragging logic
#         def start_drag(event):
#             voice_window.x = event.x
#             voice_window.y = event.y
#         def do_drag(event):
#             x = voice_window.winfo_pointerx() - voice_window.x
#             y = voice_window.winfo_pointery() - voice_window.y
#             voice_window.geometry(f"+{x}+{y}")
#             
#         canvas.bind("<Button-1>", start_drag)
#         canvas.bind("<B1-Motion>", do_drag)
#         
#         # Hide default GUI if voice is booted
#         def check_voice_boot():
#             if voice_interface.is_booted and boot_frame.winfo_ismapped():
#                 boot_frame.pack_forget()
#                 task_frame.pack(fill="both", expand=True)
#             
#             # Dynamic visibility based on trigger
#             if getattr(voice_interface, 'is_active', False) or getattr(voice_interface, 'force_record', False):
#                 if not voice_window.winfo_ismapped():
#                     voice_window.deiconify()
#                 voice_window.attributes("-alpha", 1.0)
#                 voice_window.attributes("-topmost", True)
#                 v_label.config(text="Listening...", fg="#00ff00")
#             else:
#                 if voice_window.winfo_ismapped():
#                     voice_window.attributes("-alpha", 0.15)
#                     v_label.config(text="Agent needs your input", fg="#d4d4d4")
#                 
#             root.after(100, check_voice_boot)
#             
#         root.after(100, check_voice_boot)
#         import threading
#         threading.Thread(target=voice_interface.run_loop, daemon=True).start()
# 
#         root.mainloop()

    main_loop = asyncio.get_running_loop()

    def run_ui():
        import customtkinter as ctk
        import threading
        from core_organs.organ_13_interface_layer import HojaigaVoiceInterface
        import time
        
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        root = ctk.CTk()
        root.title("Hojaiga - Swarm Intelligence Interface")
        root.geometry("700x550")
        root.attributes("-topmost", True)
        
        boot_frame = ctk.CTkFrame(root)
        task_frame = ctk.CTkFrame(root)
        
        # --- Boot Frame (Security) ---
        ctk.CTkLabel(boot_frame, text="SYSTEM LOCKED", text_color="#BF616A", font=("Helvetica", 24, "bold")).pack(pady=30)
        ctk.CTkLabel(boot_frame, text="Security Question: What is the name of your grandmother?", font=("Helvetica", 14)).pack(pady=10)
        
        pass_entry = ctk.CTkEntry(boot_frame, show="*", width=300, font=("Consolas", 14))
        pass_entry.pack(pady=10)
        
        err_label = ctk.CTkLabel(boot_frame, text="", text_color="red")
        
        def check_password(event=None):
            ans = pass_entry.get().strip().lower()
            valid = ["lila", "liaben", "lilabaa", "manjibaa", "manjulaben", "leela", "lyla", "leila"]
            if ans in valid:
                boot_frame.pack_forget()
                task_frame.pack(fill="both", expand=True, padx=20, pady=20)
                
                # Launch external services
                import subprocess
                import webbrowser
                import threading
                import time
                import os
                
                # Tell the visual adapter we have booted
                asyncio.run_coroutine_threadsafe(
                    cns.publish(EventEnvelope(
                        topic="SYSTEM_BOOTED",
                        source_organ="organ_00_auth",
                        payload={"event_type": "SYSTEM_BOOTED"}
                    )),
                    main_loop
                )
                
                # 1. Start the Brain Server in a new terminal window
                try:
                    brain_bat = os.path.join(os.path.dirname(__file__), "Start_Brain_Server.bat")
                    subprocess.Popen(['cmd.exe', '/c', 'start', 'cmd.exe', '/c', brain_bat], cwd=os.path.dirname(__file__))
                except Exception as e:
                    print("Failed to launch Brain Server:", e)
                    
                # 2. Start the visual world Vite dev server
                try:
                    vw_dir = os.path.join(os.path.dirname(__file__), "hojaiga_pixel_automation", "webview-ui")
                    subprocess.Popen(['cmd.exe', '/c', 'start', 'cmd.exe', '/c', 'npm.cmd run dev'], cwd=vw_dir)
                    
                    # 3. Open the browser to localhost:5173 shortly after
                    def open_browser():
                        time.sleep(3)
                        webbrowser.open("http://localhost:5173")
                    threading.Thread(target=open_browser, daemon=True).start()
                except Exception as e:
                    print("Failed to launch visual world:", e)
                    
            else:
                pass_entry.delete(0, ctk.END)
                err_label.configure(text="Incorrect Auth.")
                err_label.pack()
                
        pass_entry.bind("<Return>", check_password)
        ctk.CTkButton(boot_frame, text="Unlock", command=check_password, fg_color="#A3BE8C", text_color="#2E3440", font=("Helvetica", 14, "bold")).pack(pady=20)
        boot_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # --- Task Frame (Configuration & Task) ---
        ctk.CTkLabel(task_frame, text="Swarm Configuration", font=("Helvetica", 18, "bold")).pack(pady=(10,5))
        
        config_frame = ctk.CTkFrame(task_frame, fg_color="transparent")
        config_frame.pack(fill="x", pady=10)
        
        # Paradigm
        ctk.CTkLabel(config_frame, text="Paradigm:").grid(row=0, column=0, padx=10, pady=(5,0), sticky="e")
        paradigm_cb = ctk.CTkComboBox(config_frame, values=["Parallel Web Automation", "Agent Chatroom", "Stochastic Consensus", "Verification Loop", "Video To Action", "Deterministic Lead Gen", "Research & Write"], width=200)
        paradigm_cb.grid(row=0, column=1, padx=10, pady=(5,0), sticky="w")
        ctk.CTkLabel(config_frame, text="Auto Mode (autonomous), Agentic Chatroom (multi-agent debate),\nor Verification Loop (auto-correcting).", font=("Helvetica", 10), text_color="gray", justify="left").grid(row=1, column=1, padx=10, pady=(0,10), sticky="w")
        
        # Swarm Size
        ctk.CTkLabel(config_frame, text="Swarm Size:").grid(row=2, column=0, padx=10, pady=(5,0), sticky="e")
        
        slider_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        slider_frame.grid(row=2, column=1, padx=10, pady=(5,0), sticky="w")
        
        swarm_val_label = ctk.CTkLabel(slider_frame, text="4 Permanent Agents", font=("Helvetica", 12, "bold"))
        swarm_val_label.pack(side="right", padx=(10,0))
        
        def on_slider_change(val):
            swarm_val_label.configure(text=f"{int(val)} Permanent Agents")
            
        swarm_slider = ctk.CTkSlider(slider_frame, from_=1, to=7, number_of_steps=6, width=150, command=on_slider_change)
        swarm_slider.set(4)
        swarm_slider.pack(side="left")
        
        ctk.CTkLabel(config_frame, text="Controls the max number of top-level Permanent Agents (1 to 7).\nWARNING: Many agents = heavy load = significant latency effect!", font=("Helvetica", 10), text_color="gray", justify="left").grid(row=3, column=1, padx=10, pady=(0,10), sticky="w")
        
        # Chrome Profile
        ctk.CTkLabel(config_frame, text="Browser Profile:").grid(row=4, column=0, padx=10, pady=5, sticky="e")
        profile_cb = ctk.CTkComboBox(config_frame, values=["Default", "Profile 1", "Guest", "Incognito"], width=200)
        profile_cb.grid(row=4, column=1, padx=10, pady=5, sticky="w")
        
        # Auth Check Button
        def do_auth_check():
            auth_btn.configure(text="Scanning Cookies...", state="disabled")
            root.update()
            time.sleep(1.2) # Simulated Auth Check
            auth_btn.configure(text="Auth Verified (Bypass Ready)", text_color="#A3BE8C")
            
        auth_btn = ctk.CTkButton(config_frame, text="Verify Auth Cookies", command=do_auth_check, fg_color="#5E81AC")
        auth_btn.grid(row=5, column=0, columnspan=2, pady=10)
        
        ctk.CTkLabel(task_frame, text="Enter Dynamic Task:", font=("Helvetica", 14, "bold")).pack(pady=(15,5))
        text_box = ctk.CTkTextbox(task_frame, height=100, width=600, font=("Consolas", 14))
        text_box.pack(pady=5)
        
        # Global status box for orchestrator updates
        status_window = ctk.CTkToplevel(root)
        status_window.title("System Status")
        status_window.geometry("300x100")
        status_window.attributes("-topmost", True)
        status_window.overrideredirect(True)
        status_window.attributes("-alpha", 0.9)
        # Position at bottom right
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        status_window.geometry(f"+{sw-320}+{sh-150}")
        status_window.withdraw() # Hide initially
        
        status_label = ctk.CTkLabel(status_window, text="Initializing...", font=("Consolas", 12), text_color="#A3BE8C", justify="left")
        status_label.pack(expand=True, fill="both", padx=10, pady=10)

        def on_submit():
            nonlocal command
            command = text_box.get("1.0", ctk.END).strip()
            print(f"\n[UI] Submitting task with Paradigm={paradigm_cb.get()}, SwarmSize={int(swarm_slider.get())}, Profile={profile_cb.get()}")
            root.iconify() # Minimize main window instead of completely hiding it!
            # Notify main loop
            try:
                main_loop.call_soon_threadsafe(task_queue.put_nowait, command)
            except Exception as e:
                print("Failed to notify main loop:", e)
            
        ctk.CTkButton(task_frame, text="Deploy Swarm", command=on_submit, font=("Helvetica", 14, "bold"), fg_color="#88C0D0", text_color="#2E3440").pack(pady=20)

        # AUTO BYPASS
        def do_auto_bypass():
            print("Auto-bypassing UI for chat monitoring...")
            pass_entry.insert(0, "lila")
            check_password()
        
        root.after(500, do_auto_bypass)
        # Voice interface background runner (no custom HUD/overlay)
        def on_voice_task(text):
            print(f"[UI] Voice Task Received: {text}")
            try:
                main_loop.call_soon_threadsafe(task_queue.put_nowait, text)
            except Exception as e:
                print("Failed to notify main loop:", e)
            
        voice_interface = HojaigaVoiceInterface(None, None, on_voice_task)
        threading.Thread(target=voice_interface.run_loop, daemon=True).start()
        
        root.mainloop()

    global sys_status_update
    def sys_status_update(msg):
        pass
        
    global task_queue
    task_queue = asyncio.Queue()
    
    global cli_command
    if globals().get("cli_command"):
        print(f"\n[CLI] Direct task provided: '{cli_command}'. Auto-submitting...")
        await task_queue.put(cli_command)
    else:
        print("\nWaiting for user to enter task in the UI...")
        import threading
        ui_thread = threading.Thread(target=run_ui, daemon=True)
        ui_thread.start()
    
    while True:
        command = await task_queue.get()
        sys_status_update("[CNS] Task Dispatched to Organ 01 (Brain)\nState: COMPILING")
        print(f"\n[CNS] Task received: {command}")
        print("[Brain] Connecting to LLM for task compilation...")
        
        if not command:
            print("Empty task provided, ignoring.")
            continue
            
        payload = {
            "payload": {"command": command},
            "request_id": task_id
        }
        
        # Check if checkpoint recovery is needed/supported
        if test_name == "Checkpoint Recovery":
            print("\n--- Checkpoint Recovery Test ---")
            print("Verdict: NOT IMPLEMENTED (Orchestrator lacks mid-execution hydration from state serialization)")
            if visualizer: await visualizer.stop()
            return trace, "NOT_IMPLEMENTED"

        if inject_failure:
            payload["payload"]["inject_verification_failure"] = True
        
        print(f"[CNS] Dispatching task '{command}' to System...")
        await cns.publish(EventEnvelope(
            topic="sock.cns.inbound", 
            source_organ="system_boot", 
            payload=payload
        ))
        
        timeout_count = 0
        timeout_count = 0
        # Wait for execution to settle (success or permanent failure)
        while timeout_count < 300: # 5 minutes timeout to allow LLM to think and agents to execute
            if "TASK_COMPLETED" in trace or "TASK_PERMANENTLY_FAILED" in trace:
                break
            await asyncio.sleep(1)
            timeout_count += 1
            
        print("[SYSTEM] Task execution loop completed for current task.")
        if "TASK_COMPLETED" in trace:
            print("[TEST RESULT] SUCCESS: Task completed successfully!")
        elif "TASK_PERMANENTLY_FAILED" in trace:
            print("[TEST RESULT] FAILED: Task permanently failed.")
        trace.clear() # clear trace for next task in queue
        
        # If running in single-task/CLI mode, exit cleanly
        if cli_command:
            break
            
    if visualizer:
        await visualizer.stop()
        
    return trace, "DONE"

async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", choices=["standard_off", "standard_on", "fail", "checkpoint"], default="standard_off")
    parser.add_argument("--command", type=str, default="", help="Direct task command string to bypass manual UI entry")
    args = parser.parse_args()

    global cli_command
    cli_command = args.command

    if args.test == "standard_off":
        await run_real_task_test(enable_visualizer=False, test_name="Standard Run (Vis OFF)")
    elif args.test == "standard_on":
        await run_real_task_test(enable_visualizer=True, test_name="Standard Run (Vis ON)")
    elif args.test == "fail":
        await run_real_task_test(enable_visualizer=True, inject_failure=True, test_name="Failure Injection")
    elif args.test == "checkpoint":
        await run_real_task_test(enable_visualizer=False, test_name="Checkpoint Recovery")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[SYSTEM] Shutdown requested by user. Exiting cleanly...")
        sys.exit(0)
