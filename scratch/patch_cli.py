p = r"D:\new_automation\All codes\core_organs\hojaiga_atlas.py"
s = open(p, encoding="utf-8").read()
s = s.replace('''    python hojaiga_atlas.py gestures <app>                   the gesture atlas (measured + published)''','''    python hojaiga_atlas.py howto   <app> "<goal>"           step-by-step routes through the scanned UI ("insert a picture")
    python hojaiga_atlas.py explain <app> "<control>"        one control: where it is, what it opens, shortcut, state
    python hojaiga_atlas.py overview <app>                   the application section by section
    python hojaiga_atlas.py manual  <app>                    write the full generated user manual (Markdown)
    python hojaiga_atlas.py gestures <app>                   the gesture atlas (measured + published)''',1)
s = s.replace("from core_organs.atlas import scanner, architect,", "from core_organs.atlas import teach, manual, uimap, scanner, architect,",1)
s = s.replace('''    if cmd == "gestures":''','''    if cmd == "howto":
        r = teach.howto(C.app_key_of(pos[0]), " ".join(pos[1:]), use_model="--no-model" not in argv)
        if as_json:
            _out(r, True)
        else:
            print(r["answer"])
        return 0
    if cmd == "explain":
        _out(teach.explain(C.app_key_of(pos[0]), " ".join(pos[1:])), as_json)
        return 0
    if cmd == "overview":
        _out(teach.overview(C.app_key_of(pos[0])), as_json)
        return 0
    if cmd == "manual":
        print(manual.write(C.app_key_of(pos[0]), pos[0]))
        return 0
    if cmd == "gestures":''',1)
open(p, "w", encoding="utf-8").write(s)
print("cli patched")
