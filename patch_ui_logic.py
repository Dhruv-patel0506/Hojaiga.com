import sys
import re

with open('D:/new_automation/test_hojaiga_real_task.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Replace the Paradigm list and Swarm Size tooltip
paradigm_old = 'paradigm_cb = ctk.CTkComboBox(config_frame, values=["Auto Mode", "Agentic Chatroom", "Verification Loop"], width=200)'
paradigm_new = 'paradigm_cb = ctk.CTkComboBox(config_frame, values=["Parallel Web Automation", "Agent Chatroom", "Stochastic Consensus", "Verification Loop", "Video To Action", "Deterministic Lead Gen", "Research & Write"], width=200)'
content = content.replace(paradigm_old, paradigm_new)

# 2. Update the on_submit logic to NOT destroy root, but just withdraw the main window
# and set an asyncio event.
on_submit_old = '''        def on_submit():
            nonlocal command
            command = text_box.get("1.0", ctk.END).strip()
            print(f"\\n[UI] Submitting task with Paradigm={paradigm_cb.get()}, SwarmSize={int(swarm_slider.get())}, Profile={profile_cb.get()}")
            root.destroy()'''

on_submit_new = '''        # Global status box for orchestrator updates
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
        
        # Attach to global so the orchestrator can update it if needed, or just let the main loop update it
        global sys_status_update
        def sys_status_update(msg):
            status_label.configure(text=msg)
            if not status_window.winfo_ismapped():
                status_window.deiconify()

        def on_submit():
            nonlocal command
            command = text_box.get("1.0", ctk.END).strip()
            print(f"\\n[UI] Submitting task with Paradigm={paradigm_cb.get()}, SwarmSize={int(swarm_slider.get())}, Profile={profile_cb.get()}")
            root.withdraw() # Hide main window, keep event loop alive for floating pill and status box!
            # Notify main loop
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(task_ready_event.set)
            except:
                pass'''
content = content.replace(on_submit_old, on_submit_new)

# 3. Modify the await asyncio.to_thread(run_ui) logic
blocking_old = '''    print("\\nWaiting for user to enter task in the UI...")
    await asyncio.to_thread(run_ui)
    
    if not command:'''

blocking_new = '''    print("\\nWaiting for user to enter task in the UI...")
    global task_ready_event
    task_ready_event = asyncio.Event()
    
    import threading
    ui_thread = threading.Thread(target=run_ui, daemon=True)
    ui_thread.start()
    
    await task_ready_event.wait()
    sys_status_update("[CNS] Task Dispatched to Organ 01 (Brain)\\nState: COMPILING")
    
    if not command:'''
content = content.replace(blocking_old, blocking_new)

with open('D:/new_automation/test_hojaiga_real_task.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("UI patched successfully.")
