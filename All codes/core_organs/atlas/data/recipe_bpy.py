"""
Atlas introspection recipe for hosts that embed a Python API named `bpy` (run INSIDE the host, headless, by atlas.introspect):

    <exe> -b --factory-startup --python recipe_bpy.py -- <out.json>

READ-ONLY: it never opens a file, changes a scene, or touches user preferences (--factory-startup). It reports what the program's own runtime says it has:
operators (idname, label, description, properties), menus (REPLAYED against a recording layout -> the real menu -> operator structure), panels, headers,
workspaces, editor types, object modes, the RNA data model (struct -> properties) and event hooks.
"""
import json
import sys
import time
import types

import bpy

T0 = time.time()
OUT = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "atlas_bpy.json"
BUDGET = {"ops": 25.0, "menus": 40.0, "panels": 25.0, "rna": 20.0}
res = {"recipe": "bpy", "version": bpy.app.version_string, "background": bpy.app.background, "binary": bpy.app.binary_path, "errors": []}


def guard(name, fn):
    try:
        t = time.time()
        res[name] = fn()
        res.setdefault("timings", {})[name] = round(time.time() - t, 2)
    except Exception as e:  # noqa: BLE001
        res["errors"].append(f"{name}: {type(e).__name__}: {str(e)[:160]}")


def operators():
    out, n = {}, 0
    t_end = time.time() + BUDGET["ops"]
    for cat in sorted(c for c in dir(bpy.ops) if not c.startswith("_")):
        mod = getattr(bpy.ops, cat)
        items = []
        for op in sorted(o for o in dir(mod) if not o.startswith("_")):
            if time.time() > t_end:
                break
            try:
                rna = getattr(mod, op).get_rna_type()
                props = []
                for p in rna.properties:
                    if p.identifier == "rna_type":
                        continue
                    props.append([p.identifier, p.type, (p.description or "")[:70]])
                    if len(props) >= 14:
                        break
                items.append({"id": f"{cat}.{op}", "name": rna.name, "desc": (rna.description or "")[:200], "props": props})
                n += 1
            except Exception:  # noqa: BLE001
                items.append({"id": f"{cat}.{op}", "name": op, "desc": "", "props": []})
        out[cat] = items
    res["ops_count"] = n
    return out


class Rec:
    """A layout that RECORDS what a menu/panel draws instead of drawing it."""

    def __init__(self, sink, depth=0):
        self.__dict__["_sink"] = sink
        self.__dict__["_depth"] = depth

    def __getattr__(self, name):
        sink = self.__dict__["_sink"]

        def call(*a, **k):
            text = k.get("text", "")
            if name in ("operator", "operator_menu_enum", "operator_enum", "operator_context_set"):
                if name == "operator":
                    sink.append({"t": "op", "id": a[0] if a else "", "text": text})
                else:
                    sink.append({"t": "op", "id": a[0] if a else "", "text": text, "enum": a[1] if len(a) > 1 else ""})
            elif name == "menu":
                sink.append({"t": "menu", "id": a[0] if a else "", "text": text})
            elif name == "prop":
                sink.append({"t": "prop", "id": a[1] if len(a) > 1 else "", "text": text})
            elif name == "label":
                sink.append({"t": "label", "text": text})
            elif name == "separator":
                sink.append({"t": "sep"})
            elif name in ("prop_menu_enum", "props_enum", "prop_enum", "prop_search"):
                sink.append({"t": "prop", "id": a[1] if len(a) > 1 else "", "text": text})
            if name in ("row", "column", "box", "split", "grid_flow", "column_flow", "menu_pie", "template_list"):
                return Rec(sink)
            return Rec(sink)
        return call

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def replay(cls):
    sink = []
    holder = types.SimpleNamespace(layout=Rec(sink), bl_label=getattr(cls, "bl_label", ""), bl_idname=getattr(cls, "bl_idname", ""))
    try:
        cls.draw(holder, bpy.context)
    except Exception:  # noqa: BLE001  (a menu that needs a live context is recorded as far as it got)
        pass
    return sink


def menus():
    out = {}
    t_end = time.time() + BUDGET["menus"]
    subs = list(bpy.types.Menu.__subclasses__())
    for cls in subs:
        if time.time() > t_end:
            break
        idn = getattr(cls, "bl_idname", cls.__name__)
        draw = replay(cls)
        out[idn] = {"label": getattr(cls, "bl_label", ""), "items": draw[:120], "n_items": len(draw)}
    res["menus_count"] = len(subs)
    return out


def panels():
    out = []
    t_end = time.time() + BUDGET["panels"]
    for cls in bpy.types.Panel.__subclasses__():
        rec = {"id": getattr(cls, "bl_idname", cls.__name__), "label": getattr(cls, "bl_label", ""), "space": getattr(cls, "bl_space_type", ""), "region": getattr(cls, "bl_region_type", ""),
               "context": getattr(cls, "bl_context", ""), "category": getattr(cls, "bl_category", "")}
        if time.time() < t_end:
            d = replay(cls)
            rec["props"] = [x["id"] for x in d if x.get("t") == "prop" and x.get("id")][:20]
            rec["ops"] = [x["id"] for x in d if x.get("t") == "op" and x.get("id")][:20]
        out.append(rec)
    res["panels_count"] = len(out)
    return out


def headers():
    return [{"id": getattr(c, "bl_idname", c.__name__), "space": getattr(c, "bl_space_type", ""), "items": replay(c)[:60]} for c in bpy.types.Header.__subclasses__()]


STRUCTS = ["Scene", "Object", "Mesh", "Material", "Camera", "Light", "World", "Collection", "Action", "Armature", "Curve", "Image", "Text", "Sound", "Texture", "NodeTree", "Modifier", "Constraint",
           "RenderSettings", "ToolSettings", "Brush", "ParticleSystem", "Library", "WindowManager", "Screen", "Area", "Region", "Space", "Gizmo", "Macro", "Operator"]


def rna():
    out = {}
    t_end = time.time() + BUDGET["rna"]
    for name in STRUCTS:
        if time.time() > t_end:
            break
        st = getattr(bpy.types, name, None)
        if st is None:
            continue
        props = []
        for p in st.bl_rna.properties:
            if p.identifier == "rna_type":
                continue
            props.append([p.identifier, p.type, (p.description or "")[:60]])
            if len(props) >= 140:
                break
        out[name] = {"n": len(st.bl_rna.properties), "props": props}
    return out


def enums():
    def en(struct, prop):
        try:
            return [[i.identifier, i.name] for i in getattr(bpy.types, struct).bl_rna.properties[prop].enum_items]
        except Exception:  # noqa: BLE001
            return []
    return {"area_types": en("Area", "type"), "object_modes": en("Object", "mode"), "object_types": en("Object", "type"), "modifier_types": en("Modifier", "type"), "shading": en("View3DShading", "type"),
            "render_engines": en("RenderSettings", "engine"), "transform_orientation": en("TransformOrientationSlot", "type")}


def hooks():
    out = {}
    for k in dir(bpy.app.handlers):
        v = getattr(bpy.app.handlers, k, None)
        if not k.startswith("_") and isinstance(v, list):
            out[k] = len(v)
    return out


def paths():
    out = {}
    try:
        out["script_paths"] = list(bpy.utils.script_paths())
    except Exception:  # noqa: BLE001
        pass
    try:
        import addon_utils
        mods = [m.__name__ for m in addon_utils.modules()]
        out["bundled_addons"] = mods[:200]
        out["bundled_addons_count"] = len(mods)
    except Exception as e:  # noqa: BLE001
        out["addon_error"] = str(e)[:100]
    return out


guard("operators", operators)
guard("menus", menus)
guard("panels", panels)
guard("headers", headers)
guard("rna", rna)
guard("enums", enums)
guard("hooks", hooks)
guard("paths", paths)
res["workspaces"] = list(bpy.data.workspaces.keys())
res["seconds"] = round(time.time() - T0, 1)
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(res, fh)
print("ATLAS_RECIPE_DONE", OUT, res["seconds"])
