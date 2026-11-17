from core_organs.professor.harvest import Catalog
cat = Catalog.load("calculator")
for v in cat.verbs:
    print(repr(v.label), v.desc)
