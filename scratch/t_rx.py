import sys, re
sys.path[:0] = ['D:/new_automation', 'D:/new_automation/All codes']
from core_organs.professor.adapters import chromium as C
p = C.SAFE_PAGE_RX.pattern
print(len(p), [hex(ord(c)) for c in p if ord(c) < 32 or ord(c) > 126][:5])
print(p[-80:])
print(re.search(r"^chrome://(settings)", "chrome://settings/"), C.SAFE_PAGE_RX.match("chrome://settings/"))
