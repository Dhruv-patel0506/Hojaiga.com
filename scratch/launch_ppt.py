import sys, time
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import universal_scan as us
lh=us.launch_hidden("powerpoint", timeout_s=40.0, fast=True)
print({k:v for k,v in lh.items() if k in("hwnd","launched","status","why")})
