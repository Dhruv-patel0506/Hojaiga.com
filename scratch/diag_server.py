import sys, json
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import vision_server as VS
print("health:", VS._health())
print("llama_processes:", VS.llama_processes())
print("pid file:", VS._PID_FILE, VS._read_pid())
import psutil
for p in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
    n = (p.info["name"] or "").lower()
    cl = " ".join(p.info["cmdline"] or [])
    if "llama" in n or "llama-server" in cl:
        print("proc:", p.info["pid"], n, cl[:140])
