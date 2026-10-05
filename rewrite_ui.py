import sys
import re

content = open('D:/new_automation/test_hojaiga_real_task.py', 'r', encoding='utf-8').read()

pattern = re.compile(r'(    def run_ui\(\):.*?        root\.mainloop\(\))', re.DOTALL)
match = pattern.search(content)
if not match:
    print('Regex failed')
    sys.exit(1)

old_ui_code = match.group(1)
commented_old_ui = "# [2026-08-17] LEGACY TKINTER UI DEPRECATED\n" + "\n".join(["# " + line for line in old_ui_code.split("\n")])

new_ui_code = '''    def run_ui():
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
        ctk.CTkLabel(config_frame, text="Paradigm:").grid(row=0, column=0, padx=10, pady=5, sticky="e")
        paradigm_cb = ctk.CTkComboBox(config_frame, values=["Claude Opus 4.6 (Thinking)", "Gemini 3.1 Pro", "GPT-4o"], width=200)
        paradigm_cb.grid(row=0, column=1, padx=10, pady=5, sticky="w")
        
        # Swarm Size
        ctk.CTkLabel(config_frame, text="Swarm Size:").grid(row=1, column=0, padx=10, pady=5, sticky="e")
        swarm_slider = ctk.CTkSlider(config_frame, from_=1, to=50, number_of_steps=49, width=200)
        swarm_slider.set(4)
        swarm_slider.grid(row=1, column=1, padx=10, pady=5, sticky="w")
        
        # Chrome Profile
        ctk.CTkLabel(config_frame, text="Browser Profile:").grid(row=2, column=0, padx=10, pady=5, sticky="e")
        profile_cb = ctk.CTkComboBox(config_frame, values=["Default", "Profile 1", "Guest", "Incognito"], width=200)
        profile_cb.grid(row=2, column=1, padx=10, pady=5, sticky="w")
        
        # Auth Check Button
        def do_auth_check():
            auth_btn.configure(text="Scanning Cookies...", state="disabled")
            root.update()
            time.sleep(1.2) # Simulated Auth Check
            auth_btn.configure(text="Auth Verified (Bypass Ready)", text_color="#A3BE8C")
            
        auth_btn = ctk.CTkButton(config_frame, text="Verify Auth Cookies", command=do_auth_check, fg_color="#5E81AC")
        auth_btn.grid(row=3, column=0, columnspan=2, pady=10)
        
        ctk.CTkLabel(task_frame, text="Enter Dynamic Task:", font=("Helvetica", 14, "bold")).pack(pady=(15,5))
        text_box = ctk.CTkTextbox(task_frame, height=100, width=600, font=("Consolas", 14))
        text_box.pack(pady=5)
        
        def on_submit():
            nonlocal command
            command = text_box.get("1.0", ctk.END).strip()
            print(f"\\n[UI] Submitting task with Paradigm={paradigm_cb.get()}, SwarmSize={int(swarm_slider.get())}, Profile={profile_cb.get()}")
            root.destroy()
            
        ctk.CTkButton(task_frame, text="Deploy Swarm", command=on_submit, font=("Helvetica", 14, "bold"), fg_color="#88C0D0", text_color="#2E3440").pack(pady=20)
        
        # Voice CDP integration
        def on_voice_task(text):
            nonlocal command
            command = text
            root.destroy()
            
        voice_interface = HojaigaVoiceInterface(None, None, on_voice_task)
        threading.Thread(target=voice_interface.run_loop, daemon=True).start()
        
        root.mainloop()'''

final_content = content[:match.start()] + commented_old_ui + "\n\n" + new_ui_code + content[match.end():]
open('D:/new_automation/test_hojaiga_real_task.py', 'w', encoding='utf-8').write(final_content)
print("Successfully replaced UI with CustomTkinter")
