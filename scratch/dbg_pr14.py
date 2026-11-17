import sys, json
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes", "D:/new_automation/All codes/core_organs"]
import si_tests_professor as T
from core_organs.professor import synth
from core_organs.professor.teacher import Conversation, Teacher
img, truth, _ = synth.render_app("light", 1.0)
sm, _ = T._scan_offline(img, 1.0)
pic = T._el(sm, truth, "Picture")
print("pic id", pic.id, "label", pic.label, "elements", len(sm.elements), "named", len(sm.named()))
fake = T.FakeLlama()
plan = {"mode": "lesson", "title": "x", "speech": "x", "steps": []}
fake.text_reply = lambda req: json.dumps(plan)
t = Teacher(T._scripted_brain(fake))
les = t.plan("How do I insert a picture?", sm, Conversation())
prompt = next(r for r in fake.requests if r["messages"][0]["role"] == "system")["messages"][-1]["content"]
print(len(prompt), "INVENTORY" in prompt, "LEARNER SAYS" in prompt, f"#{pic.id} " in prompt)
i = prompt.find("INVENTORY"); print(prompt[i:i+900])
print("----")
for r in fake.requests:
    print(r["messages"][0]["role"], "|", str(r["messages"][0]["content"])[:120].replace("\n", " "), "||", str(r["messages"][-1]["content"])[:100].replace("\n", " "))
