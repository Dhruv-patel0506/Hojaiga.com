import sys, json
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor.ml import get_learner
from core_organs.professor import history as HS
h = HS.library()
L = get_learner()
print("history:", json.dumps(h.stats(), indent=1)[:700])
print("learner attach:", L.attach(h, catch_up=True))
rep = L.report()
print(json.dumps(rep, indent=1, default=str)[:3500])
