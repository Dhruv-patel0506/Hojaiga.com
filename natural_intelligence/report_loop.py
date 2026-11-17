import time, subprocess
while True:
    try: subprocess.run([r"D:\new_automation\venv\Scripts\python.exe", "ni_report.py"], cwd=r"D:\new_automation\natural_intelligence", capture_output=True, creationflags=0x08000000, timeout=900)
    except Exception: pass
    time.sleep(1800)
