import sys
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs.desktop_grounding import literal_typed_text as L

COMPOSE_GOALS = [
    "type the current date",
    "type your name in the box",
    "write today's date at the top",
    "type a short note about the trip",
    "enter the total of 3 and 4",
    "type hello",
    "type the word hello three times",
]
for g in COMPOSE_GOALS:
    print(repr(g), "->", repr(L(g)))
