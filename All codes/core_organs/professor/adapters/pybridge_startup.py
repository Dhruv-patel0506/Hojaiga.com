# This file runs INSIDE the application (an embedded Python with a start-up script flag); it is read as text by professor.adapters.script_bridge and never imported.
import bpy, json, os, re, socket, time, traceback, types, contextlib
PORT, TOKEN = __PORT__, "__TOKEN__"
SANDBOX = r"__SANDBOX__"
SANDBOX = os.path.abspath(SANDBOX) if SANDBOX else ""
_srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
_srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
_srv.bind(("127.0.0.1", PORT)); _srv.listen(4); _srv.setblocking(False)

# This instance is a throw-away one: a setting the run changes must never reach the person's own preferences file.
try:
    bpy.context.preferences.use_preferences_save = False
except Exception:
    pass

# The application opens its temporary editors (Preferences, file browser, render result) in WINDOWS of their own by default. This instance is parked where the person cannot see it: every such editor is
# made to open inside the one window instead (a new window would appear on the person's screen). Found by the property names, not by listing editors.
try:
    _view = bpy.context.preferences.view
    for _p in _view.bl_rna.properties:
        if _p.identifier.endswith("_display_type") and _p.type == "ENUM" and getattr(_view, _p.identifier) == "WINDOW":
            _ids = [i.identifier for i in _p.enum_items]
            for _want in ("SCREEN", "AREA", "NONE"):
                if _want in _ids:
                    setattr(_view, _p.identifier, _want)
                    break
except Exception:
    pass

# Commands that would open another window on the person's screen, close this one or leave the application: never run through this bridge.
REFUSED_OPS = re.compile(r"(?:^|\.)(?:window_new|window_new_main|window_close|window_fullscreen_toggle|area_dupli|area_detach|quit_blender|revert_mainfile|recover_last_session|recover_auto_save|app_template_install)$")


def _inside(path):
    """A file path is acceptable only inside the run's sandbox folder (everything the run reads or writes lives there)."""
    try:
        return bool(SANDBOX) and os.path.commonpath([os.path.abspath(str(path)), SANDBOX]) == SANDBOX
    except Exception:
        return False


def _view3d():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                region = next((r for r in area.regions if r.type == "WINDOW"), None)
                return {"window": win, "screen": win.screen, "area": area, "region": region}
    return None


def _registry():
    out = []
    for mod in dir(bpy.ops):
        if mod.startswith("_"):
            continue
        sub = getattr(bpy.ops, mod)
        for name in dir(sub):
            if name.startswith("_"):
                continue
            try:
                rna = getattr(sub, name).get_rna_type()
                out.append({"id": mod + "." + name, "label": rna.name, "desc": (rna.description or "")[:200], "module": mod})
            except Exception:
                pass
    return out


class _P:
    """What layout.operator() returns: an object whose properties can be assigned and read without effect."""
    def __setattr__(s, k, v): pass
    def __getattr__(s, k): return None


class _Rec:
    """A stand-in for a UI layout: records what a menu's / panel's draw() would show - commands with their on-screen text, submenus, PROPERTIES (the struct and the property drawn), the sections
    (collapsible sub-panels) they sit in - without drawing anything."""
    def __init__(self, sink, trail=()):
        self.sink = sink
        self.trail = tuple(trail)
        self.operator_context = "INVOKE_DEFAULT"
        self.enabled = True
        self.active = True
        self.use_property_split = False
        self.use_property_decorate = False

    def operator(self, op, text=None, icon=None, **kw):
        self.sink.append(("op", op, text))
        return _P()

    def menu(self, name, text=None, **kw):
        self.sink.append(("menu", name, text))

    def operator_menu_enum(self, op, prop, text=None, **kw):
        self.sink.append(("op", op, text))

    def prop(self, data, prop, text=None, **kw):
        self.sink.append(("prop", data, prop, text, self.trail))

    def prop_menu_enum(self, data, prop, text=None, **kw):
        self.sink.append(("prop", data, prop, text, self.trail))

    def prop_search(self, data, prop, search_data=None, search_prop=None, text=None, **kw):
        self.sink.append(("prop", data, prop, text, self.trail))

    def props_enum(self, data, prop):
        self.sink.append(("prop", data, prop, None, self.trail))

    def prop_enum(self, data, prop, value, text=None, **kw):
        self.sink.append(("prop_enum", data, prop, value, text, self.trail))

    def label(self, text="", **kw):
        self.sink.append(("label", text, self.trail))

    def template_ID(self, data, prop, *a, **kw):
        self.sink.append(("prop", data, prop, kw.get("text"), self.trail))

    def template_ID_tabs(self, data, prop, *a, **kw):
        self.sink.append(("prop", data, prop, kw.get("text"), self.trail))

    def template_ID_preview(self, data, prop, *a, **kw):
        self.sink.append(("prop", data, prop, kw.get("text"), self.trail))

    def template_any_ID(self, data, prop, type_prop=None, text=None, **kw):
        self.sink.append(("prop", data, prop, text, self.trail))

    def panel(self, idname, default_closed=False):
        head = _Rec([], self.trail)
        body = _Rec(self.sink, self.trail)
        body_trail_holder = {}

        class _Head(_Rec):
            def label(s, text="", **kw):
                if text and not body_trail_holder:
                    body_trail_holder["t"] = text
                    body.trail = self.trail + (text,)

            def prop(s, data, prop, text=None, **kw):
                if not body_trail_holder:
                    body_trail_holder["t"] = text or str(prop)
                    body.trail = self.trail + (text or str(prop),)
                self.sink.append(("prop", data, prop, text, self.trail))
        return _Head([], self.trail), body

    def panel_prop(self, data, prop):
        return _Rec(self.sink, self.trail)

    def __getattr__(self, name):
        if name in ("row", "column", "box", "split", "column_flow", "grid_flow", "menu_pie"):
            return lambda *a, **k: _Rec(self.sink, self.trail)
        return lambda *a, **k: None


def _menus():
    """Every menu class: its on-screen label, and the commands / submenus its draw() lists (label as shown)."""
    out = {}
    for name in dir(bpy.types):
        cls = getattr(bpy.types, name, None)
        try:
            if not (isinstance(cls, type) and issubclass(cls, bpy.types.Menu) and cls is not bpy.types.Menu):
                continue
        except Exception:
            continue
        sink = []
        fake = type("F", (), {})()
        fake.layout = _Rec(sink)
        fake.bl_label = getattr(cls, "bl_label", name)
        try:
            cls.draw(fake, bpy.context)
        except Exception:
            pass
        items = []
        for rec in sink:
            kind, ident, text = rec[0], rec[1], rec[2]
            if kind == "op":
                try:
                    mod, opn = ident.split(".", 1)
                    lab = text or getattr(getattr(bpy.ops, mod), opn).get_rna_type().name
                except Exception:
                    lab = text or ident
                items.append({"kind": "op", "id": ident, "label": lab})
            elif kind == "menu":
                sub = getattr(bpy.types, ident, None)
                items.append({"kind": "menu", "id": ident, "label": text or getattr(sub, "bl_label", ident)})
        if items:
            out[name] = {"label": getattr(cls, "bl_label", name), "items": items}
    return out


# ------------------------------------------------------------------------------------------------------------- properties: the settings a guide names (not operators)
_PROPS = {}                                    # key -> (struct, property identifier)
_PROP_KEYS = {}                                # (struct pointer, identifier) -> key


class _Fake:
    """Stands in for a panel instance: its draw() sees .layout and can call the panel class's own helper methods."""
    def __init__(self, cls, layout):
        self.__dict__["_cls"] = cls
        self.__dict__["layout"] = layout
        self.__dict__["bl_label"] = getattr(cls, "bl_label", "")

    def __getattr__(self, n):
        f = getattr(self.__dict__["_cls"], n)
        return types.MethodType(f, self) if isinstance(f, types.FunctionType) else f

    def __setattr__(self, n, v):
        self.__dict__[n] = v


class _Stub:
    """An area / region stand-in for the global bars (top bar, status bar), which are not areas of the screen but whose drawing code reads context.area."""
    show_menus = True
    ui_type = ""
    type = ""

    def __getattr__(self, n):
        return None


class _Ctx:
    """The real context, except that a missing area / region is a stub (read by the drawing code of global bars)."""
    def __getattr__(self, n):
        v = getattr(bpy.context, n, None)
        if v is None and n in ("area", "region"):
            return _Stub()
        return v


def _enum_names(owner, ident):
    try:
        return {i.identifier.lower(): i.name for i in owner.bl_rna.properties[ident].enum_items}
    except Exception:
        return {}


def _editor_name(space_type):
    try:
        for i in bpy.types.Area.bl_rna.properties["type"].enum_items:
            if i.identifier == space_type:
                return i.name
    except Exception:
        pass
    return space_type.replace("_", " ").title()


def _tab_names(space_type):
    if space_type == "PREFERENCES":
        return _enum_names(bpy.types.Preferences, "active_section")
    if space_type == "PROPERTIES":
        return _enum_names(bpy.types.SpaceProperties, "context")
    return {}


def _id_collection(pr):
    """For a pointer property to a data-block type (WorkSpace, Camera, Material, World ...): the collection of bpy.data that holds those data-blocks, else None."""
    try:
        want = pr.fixed_type.identifier
        for q in bpy.data.bl_rna.properties:
            if q.type == "COLLECTION" and q.fixed_type is not None and q.fixed_type.identifier == want:
                return getattr(bpy.data, q.identifier)
    except Exception:
        pass
    return None


def _prop_entry(data, ident, text):
    props = data.bl_rna.properties
    if ident not in props:
        return None
    pr = props[ident]
    if pr.type == "COLLECTION":
        return None
    if pr.type == "POINTER":
        coll = _id_collection(pr)
        if coll is None or pr.is_readonly:
            return None
        ptr = 0
        try:
            ptr = data.as_pointer()
        except Exception:
            pass
        key = _PROP_KEYS.get((ptr, ident)) if ptr else None
        fresh = key is None
        if fresh:
            key = "p%d" % (len(_PROPS) + 1)
            _PROPS[key] = (data, ident)
            if ptr:
                _PROP_KEYS[(ptr, ident)] = key
        cur = getattr(data, ident)
        return {"key": key, "id": ident, "label": text or pr.name, "ui_name": pr.name, "type": "ENUM", "readonly": False, "desc": (pr.description or "")[:160],
                "struct": data.bl_rna.identifier, "fresh": fresh, "items": [{"id": b.name, "label": b.name} for b in list(coll)[:80]], "value": getattr(cur, "name", None)}
    ptr = 0
    try:
        ptr = data.as_pointer()
    except Exception:
        pass
    key = _PROP_KEYS.get((ptr, ident)) if ptr else None
    fresh = key is None
    if fresh:
        key = "p%d" % (len(_PROPS) + 1)
        _PROPS[key] = (data, ident)
        if ptr:
            _PROP_KEYS[(ptr, ident)] = key
    ent = {"key": key, "id": ident, "label": text or pr.name, "ui_name": pr.name, "type": pr.type, "readonly": bool(pr.is_readonly), "desc": (pr.description or "")[:160],
           "struct": data.bl_rna.identifier, "fresh": fresh}
    if pr.type == "ENUM":
        try:
            ent["items"] = [{"id": i.identifier, "label": i.name} for i in list(pr.enum_items)[:80]]
        except Exception:
            ent["items"] = []
    try:
        val = getattr(data, ident)
        ent["value"] = list(val) if (hasattr(val, "__len__") and not isinstance(val, str)) else val
        if isinstance(ent["value"], set):
            ent["value"] = sorted(ent["value"])
        if not isinstance(ent["value"], (bool, int, float, str, list, type(None))):
            ent["value"] = str(ent["value"])
    except Exception:
        ent["value"] = None
    return ent


def _override_for(space_type, region_type="WINDOW"):
    """A context in which a panel of this editor can be drawn: the window's area of that kind and its region of the panel's kind; any area when the window has none (Preferences panels)."""
    fallback = None
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            reg = next((r for r in area.regions if r.type == region_type), None) or next((r for r in area.regions if r.type == "WINDOW"), None)
            if reg is None:
                continue
            if area.type == space_type:
                return {"window": win, "screen": win.screen, "area": area, "region": reg}
            if fallback is None:
                fallback = {"window": win, "screen": win.screen, "area": area, "region": reg}
    return fallback or {}


def _panels(max_panels=1500):
    """Every property a panel draws, with WHERE it is drawn: editor > tab > parent panels > sections. This is how a guide names a setting ('Preferences > Interface > Translation > Language')."""
    out = []
    classes = []
    for name in dir(bpy.types):
        cls = getattr(bpy.types, name, None)
        try:
            if isinstance(cls, type) and issubclass(cls, bpy.types.Panel) and cls is not bpy.types.Panel and hasattr(cls, "bl_space_type"):
                classes.append(cls)
        except Exception:
            continue
    by_id = {getattr(c, "bl_idname", c.__name__): c for c in classes}

    def lineage(cls):
        names, c, guard = [], cls, 0
        while c is not None and guard < 6:
            names.insert(0, getattr(c, "bl_label", "") or "")
            c = by_id.get(getattr(c, "bl_parent_id", ""))
            guard += 1
        return [n for n in names if n]
    n = [0]

    def draw_pass(cls_list):
        for cls in cls_list:
            if n[0] >= max_panels:
                return
            st = getattr(cls, "bl_space_type", "")
            if st not in ("PREFERENCES", "PROPERTIES", "VIEW_3D", "IMAGE_EDITOR", "NODE_EDITOR", "SEQUENCE_EDITOR", "CLIP_EDITOR", "TEXT_EDITOR", "OUTLINER", "FILE_BROWSER"):
                continue
            sink = []
            ov = _override_for(st, getattr(cls, "bl_region_type", "WINDOW"))
            cm = bpy.context.temp_override(**ov) if ov else contextlib.nullcontext()
            with cm:
                try:
                    if hasattr(cls, "poll") and not cls.poll(bpy.context):
                        continue
                except Exception:
                    pass
                fake = _Fake(cls, _Rec(sink))
                try:
                    cls.draw(fake, bpy.context)
                except Exception as exc:
                    if len(_ERRORS) < 12:
                        _ERRORS.append("%s: %s: %s" % (getattr(cls, "__name__", "?"), type(exc).__name__, str(exc)[:80]))
            n[0] += 1
            tabs = _tab_names(st)
            ctx = getattr(cls, "bl_context", "") or ""
            tab = tabs.get(str(ctx).lower(), "") or (str(ctx).replace("_", " ").title() if ctx else "")
            base = [_editor_name(st)] + ([tab] if tab else []) + ([getattr(cls, "bl_category", "")] if (st == "VIEW_3D" and getattr(cls, "bl_category", "")) else []) + lineage(cls)
            for rec in sink:
                if rec[0] == "prop":
                    _k, data, ident, text, trail = rec
                    try:
                        ent = _prop_entry(data, ident, text)
                    except Exception:
                        ent = None
                    if ent and ent["fresh"]:
                        ent["path"] = base + [t for t in trail if t and t not in base]
                        ent.pop("fresh", None)
                        out.append(ent)
    header_cls = []
    for name in dir(bpy.types):
        cls = getattr(bpy.types, name, None)
        try:
            if isinstance(cls, type) and issubclass(cls, bpy.types.Header) and cls is not bpy.types.Header and hasattr(cls, "bl_space_type"):
                header_cls.append(cls)
        except Exception:
            continue

    def draw_headers():
        for cls in header_cls:
            st = getattr(cls, "bl_space_type", "")
            areas = [(win, area) for win in bpy.context.window_manager.windows for area in win.screen.areas if area.type == st]
            if areas:
                win, area = areas[0]
                runs = [("region", reg) for reg in [r for r in area.regions if r.type == "HEADER"][:3]]
            else:                                                                           # the top bar / status bar are global: not an area of the screen; their halves are drawn by name
                runs = [("part", n) for n in ("draw_left", "draw_center", "draw_right") if hasattr(cls, n)]
            for how, what in runs:
                sink = []
                cm = bpy.context.temp_override(window=win, screen=win.screen, area=area, region=what) if how == "region" else contextlib.nullcontext()
                with cm:
                    try:
                        if how == "region" and hasattr(cls, "poll") and not cls.poll(bpy.context):
                            continue
                    except Exception:
                        pass
                    try:
                        fk = _Fake(cls, _Rec(sink))
                        if how == "region":
                            cls.draw(fk, bpy.context)
                        else:
                            getattr(cls, what)(fk, _Ctx())
                    except Exception as exc:
                        if len(_ERRORS) < 12:
                            _ERRORS.append("%s: %s: %s" % (getattr(cls, "__name__", "?"), type(exc).__name__, str(exc)[:80]))
                base = [_editor_name(st)]
                for rec in sink:
                    if rec[0] == "prop":
                        _k, data, ident, text, trail = rec
                        try:
                            ent = _prop_entry(data, ident, text)
                        except Exception:
                            ent = None
                        if ent and ent["fresh"]:
                            ent["path"] = base + [t for t in trail if t and t not in base]
                            ent.pop("fresh", None)
                            out.append(ent)
    draw_headers()
    # every editor's TYPE menu (the first button of its header: 3D Viewport, Video Sequencer, Shader Editor ...) is a setting of the area; the header template that draws it is not recordable
    seen_types = set()
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type in seen_types:
                continue
            seen_types.add(area.type)
            try:
                ent = _prop_entry(area, "ui_type", "Editor Type")
            except Exception:
                ent = None
            if ent and ent["fresh"]:
                ent["path"] = [_editor_name(area.type), "Editor Type"]
                ent.pop("fresh", None)
                out.append(ent)
    pref_cls = [c for c in classes if getattr(c, "bl_space_type", "") == "PREFERENCES"]
    draw_pass([c for c in classes if getattr(c, "bl_space_type", "") != "PREFERENCES"])
    # the Preferences panels draw only for the section that is open (their poll asks the preferences): open each section in turn, then put the original one back
    prefs = bpy.context.preferences
    try:
        sections = [i.identifier for i in prefs.bl_rna.properties["active_section"].enum_items]
        orig = prefs.active_section
    except Exception:
        sections, orig = [], None
    for sec in sections:
        try:
            prefs.active_section = sec
        except Exception:
            continue
        draw_pass(pref_cls)
    if orig is not None:
        try:
            prefs.active_section = orig
        except Exception:
            pass
    return out


_ERRORS = []


def _coerce(pr, value):
    """The property's own type from what a guide says ('on', '1.5', 'English', 'Python')."""
    t = pr.type
    if t == "POINTER":
        coll = _id_collection(pr)
        if coll is None:
            raise ValueError("not a data-block choice")
        v = str(value).strip()
        for b in coll:
            if b.name == v or b.name.lower() == v.lower():
                return b
        for b in coll:
            if v and (v.lower() in b.name.lower() or b.name.lower() in v.lower()):
                return b
        raise ValueError("no data-block named %r (there are: %s)" % (v, ", ".join(b.name for b in list(coll)[:12])))
    if t == "BOOLEAN":
        if isinstance(value, str):
            v = value.strip().lower()
            if v in ("1", "true", "on", "yes", "enable", "enabled", "checked"):
                return True
            if v in ("0", "false", "off", "no", "disable", "disabled", "unchecked"):
                return False
            raise ValueError("not a yes / no value: %r" % value)
        return bool(value)
    if t == "INT":
        return int(float(value))
    if t == "FLOAT":
        return float(value)
    if t == "STRING":
        return str(value)
    if t == "ENUM":
        v = str(value).strip()
        items = list(pr.enum_items)
        for i in items:
            if i.identifier == v:
                return i.identifier
        low = v.lower()
        for i in items:
            if i.name.lower() == low or i.identifier.lower() == low:
                return i.identifier
        for i in items:
            if low and (low in i.name.lower() or i.name.lower() in low):
                return i.identifier
        raise ValueError("no choice named %r (choices: %s)" % (v, ", ".join(i.name for i in items[:12])))
    raise ValueError("a %s property cannot be set from a value" % t)


def _rna_get(key):
    data, ident = _PROPS[key]
    val = getattr(data, ident)
    return list(val) if (hasattr(val, "__len__") and not isinstance(val, str)) else val


def _rna_set(key, value):
    if key not in _PROPS:
        return {"ok": False, "note": "unknown property key"}
    data, ident = _PROPS[key]
    pr = data.bl_rna.properties[ident]
    if pr.is_readonly:
        return {"ok": False, "note": "'%s' is read-only" % pr.name}
    try:
        new = _coerce(pr, value)
    except Exception as exc:
        return {"ok": False, "note": "%s: %s" % (type(exc).__name__, str(exc)[:160])}
    old = getattr(data, ident)
    try:
        setattr(data, ident, new)
    except Exception as exc:
        return {"ok": False, "note": "%s: %s" % (type(exc).__name__, str(exc)[:160])}
    now = getattr(data, ident)
    if pr.type == "POINTER":
        old, now = getattr(old, "name", old), getattr(new, "name", new)                 # a data-block choice (workspace, camera ...) is applied when the application next processes events: report the requested one
    return {"ok": True, "note": "%s: %r -> %r" % (pr.name, old, now), "changed": old != now, "value": now if isinstance(now, (bool, int, float, str)) else str(now)}


# ------------------------------------------------------------------------------------------------------------- operators
def _op(op_id):
    mod, name = op_id.split(".", 1)
    return mod, getattr(getattr(bpy.ops, mod), name)


def _path_props(rna):
    return [p.identifier for p in rna.properties if p.type == "STRING" and p.subtype in ("FILE_PATH", "DIR_PATH", "FILE_NAME")]


def _fileinfo(op_id):
    """Does this command take a file? Which types, and does it read or write? (Run without a path it would open the application's OWN file browser - drawn in its window, not a system dialog.)"""
    mod, op = _op(op_id)
    rna = op.get_rna_type()
    pp = _path_props(rna)
    if not pp:
        return {"path_props": []}
    exts = []
    for p in rna.properties:
        if p.identifier == "filename_ext" and p.default:
            exts.append(str(p.default).lstrip("."))
        if p.identifier == "filter_glob" and p.default:
            exts += [g.strip().lstrip("*.").lower() for g in str(p.default).split(";") if g.strip().startswith("*.")]
    if not exts and ("mainfile" in op_id or "blend" in (rna.name or "").lower()):
        exts = ["blend"]                                                          # the application's own document type has no filename_ext on its Open / Save commands
    low = (op_id + " " + rna.name).lower()
    direction = "save" if re.search(r"save|export|write", low) else "open"
    return {"path_props": pp, "exts": [e for e in dict.fromkeys(exts) if e], "direction": direction, "label": rna.name}


def _execute(op_id, props=None):
    if REFUSED_OPS.search(op_id):
        return {"ok": False, "refused": True, "note": "refused: '%s' would open another window on the person's screen, close the application or discard the run's document" % op_id}
    mod, op = _op(op_id)
    props = dict(props or {})
    rna = op.get_rna_type()
    pp = _path_props(rna)
    for k, v in props.items():
        if k in pp and not _inside(v):
            return {"ok": False, "note": "refused: '%s' is outside the run's sandbox folder" % v}
    if pp and not any(k in props for k in pp):
        return {"ok": False, "needs_path": True, "path_props": pp, "note": "needs a file path (called without one the application opens its own file browser)"}
    ov = _view3d() if mod in ("view3d", "object", "mesh", "transform", "sculpt", "paint") else None
    cm = bpy.context.temp_override(**ov) if ov is not None else contextlib.nullcontext()
    with cm:
        try:
            if not op.poll():
                return {"ok": False, "precondition": True, "note": "not available in the current state (its poll() is False): it needs something that is not there yet - an earlier operation, a selection, an object of the right kind or another mode"}
        except Exception:
            pass
        return {"ok": True, "note": str(op(**props))}


def _polls(ids):
    """{command id: can it run in the application's current state?} - a command whose poll() is False needs something that is not there yet (an object, a selection, another mode, an earlier operation)."""
    out = {}
    ov = _view3d()
    for op_id in ids[:900]:
        try:
            mod, op = _op(op_id)
            cm = bpy.context.temp_override(**ov) if (ov is not None and mod in ("view3d", "object", "mesh", "transform", "sculpt", "paint")) else contextlib.nullcontext()
            with cm:
                out[op_id] = bool(op.poll())
        except Exception:
            out[op_id] = True
    return out


def _layout():
    """Where things are, in WINDOW pixels from the top-left (what a virtual pointer needs): every window's size, every area and its main region, and for the 3D view the pixel of each object."""
    out = []
    from bpy_extras import view3d_utils
    for win in bpy.context.window_manager.windows:
        areas = []
        for area in win.screen.areas:
            reg = next((r for r in area.regions if r.type == "WINDOW"), None)
            a = {"type": area.type, "x": area.x, "y": win.height - area.y - area.height, "w": area.width, "h": area.height}
            if reg is not None:
                a["region"] = {"x": reg.x, "y": win.height - reg.y - reg.height, "w": reg.width, "h": reg.height}
                if area.type == "VIEW_3D":
                    r3d = area.spaces.active.region_3d
                    objs = {}
                    for o in bpy.context.view_layer.objects:
                        p = view3d_utils.location_3d_to_region_2d(reg, r3d, o.matrix_world.translation)
                        if p is not None:
                            objs[o.name] = [round(reg.x + p.x), round(win.height - (reg.y + p.y))]
                    a["objects_px"] = objs
            areas.append(a)
        out.append({"w": win.width, "h": win.height, "areas": areas})
    return out


def _gesture(kind):
    ov = _view3d()
    if ov is None:
        return False, "no 3D view in this window"
    with bpy.context.temp_override(**ov):
        if kind == "orbit":
            bpy.ops.view3d.view_orbit(angle=0.35, type="ORBITRIGHT")
        elif kind == "pan":
            try:
                bpy.ops.view3d.view_pan(type="PANRIGHT")
            except Exception:
                r3d = ov["area"].spaces.active.region_3d
                r3d.view_location.x += 0.5 * max(1.0, r3d.view_distance / 10.0)
        elif kind == "zoom":
            bpy.ops.view3d.zoom(delta=1)
        else:
            return False, "no scripted form of '%s'" % kind
    return True, "view3d " + kind


_MODE_KEYMAP = {"OBJECT": "Object Mode", "EDIT_MESH": "Mesh", "POSE": "Pose", "EDIT_ARMATURE": "Armature", "SCULPT": "Sculpt", "PAINT_WEIGHT": "Weight Paint", "PAINT_VERTEX": "Vertex Paint",
                "PAINT_TEXTURE": "Image Paint", "EDIT_CURVE": "Curve", "EDIT_CURVES": "Curves", "EDIT_TEXT": "Font", "EDIT_LATTICE": "Lattice", "EDIT_METABALL": "Metaball", "PARTICLE": "Particle",
                "EDIT_SURFACE": "Curve", "EDIT_GREASE_PENCIL": "Grease Pencil Edit Mode"}
_KEY_ALIAS = {"del": "delete", "ret": "enter", "return": "enter", "esc": "escape", "back_space": "backspace", "space": "space", "page_up": "pageup", "page_down": "pagedown",
              "up_arrow": "up", "down_arrow": "down", "left_arrow": "left", "right_arrow": "right", "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
              "seven": "7", "eight": "8", "nine": "9", "control": "ctrl"}


def _canon(chord):
    parts = [p.strip().lower().replace(" ", "_") for p in str(chord).split("+") if p.strip()]
    mods = {_KEY_ALIAS.get(p, p) for p in parts[:-1]} & {"ctrl", "alt", "shift", "oskey"}
    key = _KEY_ALIAS.get(parts[-1], parts[-1]) if parts else ""
    return mods, key


def _key_resolve(chord):
    """The command the ACTIVE keymaps bind to a chord in the application's current state: the current mode's keymap first, then the 3D viewport's, then the screen / window ones (the
    order the application itself looks them up in). A chord that opens a menu or starts an interactive transform is reported, not run: it needs a choice / a gesture value."""
    want_mods, want_key = _canon(chord)
    if not want_key:
        return {"ok": False, "note": "no key"}
    kc = bpy.context.window_manager.keyconfigs.active or bpy.context.window_manager.keyconfigs.default
    order = [_MODE_KEYMAP.get(bpy.context.mode, ""), "Object Non-modal", "3D View", "3D View Generic", "Frames", "Screen", "Window"]
    first = None
    for name in [n for n in order if n]:
        km = kc.keymaps.get(name)
        if km is None:
            continue
        for kmi in km.keymap_items:
            if not kmi.active or not kmi.idname or kmi.map_type != "KEYBOARD" or kmi.value in ("DOUBLE_CLICK", "CLICK_DRAG", "RELEASE"):
                continue
            if _KEY_ALIAS.get(kmi.type.lower(), kmi.type.lower()) != want_key:
                continue
            if any((m in want_mods) != bool(f) for m, f in (("ctrl", kmi.ctrl), ("alt", kmi.alt), ("shift", kmi.shift), ("oskey", kmi.oskey)) if f != -1):
                continue
            props = {}
            try:
                for p in kmi.properties.bl_rna.properties:
                    if p.identifier != "rna_type" and kmi.properties.is_property_set(p.identifier):
                        val = getattr(kmi.properties, p.identifier)
                        props[p.identifier] = val if isinstance(val, (str, int, float, bool)) else (list(val) if hasattr(val, "__len__") and not isinstance(val, str) else str(val))
            except Exception:
                pass
            kind = "menu" if kmi.idname.startswith(("wm.call_menu", "wm.call_panel", "wm.call_menu_pie")) else ("interactive" if kmi.idname.startswith(("transform.", "view3d.rotate", "view3d.move", "view3d.zoom")) else "command")
            hit = {"ok": True, "id": kmi.idname, "props": props, "keymap": name, "mode": bpy.context.mode, "kind": kind}
            try:                                                   # a binding whose command cannot run here belongs to another editor (Ctrl+Z of the asset browser): the next binding is the live one
                mod, op = _op(kmi.idname)
                ov = _view3d()
                with (bpy.context.temp_override(**ov) if ov is not None else contextlib.nullcontext()):
                    can = bool(op.poll())
            except Exception:
                can = True
            if can:
                return hit
            first = first or dict(hit, poll=False)
    if first:
        return first                                               # bound, but its precondition is not met now (no object selected ...): the caller hears it as a precondition
    return {"ok": False, "note": "no active keymap of the current state binds %s" % chord, "mode": bpy.context.mode}


_ELEMENT_WORDS = ("vertex", "vertices", "edge", "edges", "face", "faces", "element", "elements")


def _select_object(kind):
    """A guide step that works on 'an object' / 'a mesh' / 'the camera' / 'mesh elements': one of the scene's own objects of that kind is selected and made active (inside edit mode: all of
    the elements). None of that kind -> needs_object (the caller creates one with the application's own Add command and asks again)."""
    k = (kind or "object").lower().strip()
    mode = bpy.context.mode
    if any(w in k for w in _ELEMENT_WORDS) or (mode.startswith("EDIT") and k in ("object", "objects", "")):
        if mode == "EDIT_MESH":
            ov = _view3d()
            with (bpy.context.temp_override(**ov) if ov is not None else contextlib.nullcontext()):
                return {"ok": True, "note": "all elements selected: " + str(bpy.ops.mesh.select_all(action="SELECT"))}
        k = "mesh"
    want = {"mesh": "MESH", "meshes": "MESH", "camera": "CAMERA", "light": "LIGHT", "lamp": "LIGHT", "armature": "ARMATURE", "bone": "ARMATURE", "bones": "ARMATURE", "curve": "CURVE",
            "text": "FONT", "font": "FONT", "empty": "EMPTY", "lattice": "LATTICE", "surface": "SURFACE", "metaball": "META", "grease pencil": "GREASEPENCIL", "volume": "VOLUME"}
    typ = next((t for w, t in want.items() if w in k), "")
    objs = [o for o in bpy.context.view_layer.objects if (not typ or o.type == typ or (typ == "GREASEPENCIL" and o.type.startswith("GP")))]
    if not objs:
        return {"ok": False, "needs_object": True, "note": "no %s in the scene" % (typ.lower() or "object")}
    if mode != "OBJECT" and bpy.context.view_layer.objects.active is not None and bpy.context.view_layer.objects.active in objs:
        return {"ok": True, "note": "the active %s is already being edited" % objs[0].type.lower()}
    o = next((x for x in objs if x.type == "MESH"), objs[0]) if not typ else objs[0]
    for x in bpy.context.view_layer.objects:
        x.select_set(False)
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    return {"ok": True, "note": "selected and made active: %s (%s)" % (o.name, o.type.lower())}


def _state():
    v = _view3d()
    r3d = v["area"].spaces.active.region_3d if v else None
    return {"ok": True, "view": [round(x, 4) for x in r3d.view_rotation] + [round(r3d.view_distance, 4)] if r3d else None,
            "objects": len(bpy.data.objects), "mode": bpy.context.mode, "pan": [round(c, 4) for c in r3d.view_location] if r3d else None,
            "selected": sorted(o.name for o in bpy.context.view_layer.objects if o.select_get()),
            "active": getattr(bpy.context.view_layer.objects.active, "name", ""),
            "locations": {o.name: [round(c, 3) for c in o.location] for o in bpy.context.view_layer.objects},
            "file": bpy.data.filepath, "dirty": bool(bpy.data.is_dirty)}


def _scene():
    """The document's contents as measurements (read only): every object with its kind, transform, size in world units, mesh counts, materials, modifiers, parent and its world bounding box."""
    from mathutils import Vector
    objs = []
    for o in bpy.context.view_layer.objects:
        d = {"name": o.name, "type": o.type, "loc": [round(c, 4) for c in o.location], "rot": [round(c, 4) for c in o.rotation_euler], "scale": [round(c, 4) for c in o.scale],
             "dims": [round(c, 4) for c in o.dimensions], "parent": o.parent.name if o.parent else "", "mods": [m.name for m in o.modifiers],
             "mats": [s.material.name for s in o.material_slots if s.material], "visible": bool(o.visible_get())}
        if o.type == "MESH" and o.data is not None:
            d["verts"], d["faces"] = len(o.data.vertices), len(o.data.polygons)
        try:
            cs = [o.matrix_world @ Vector(c) for c in o.bound_box]
            d["bbox"] = [[round(min(c[i] for c in cs), 4) for i in range(3)], [round(max(c[i] for c in cs), 4) for i in range(3)]]
        except Exception:
            pass
        objs.append(d)
    return {"ok": True, "objects": objs, "mode": bpy.context.mode, "file": bpy.data.filepath, "dirty": bool(bpy.data.is_dirty), "units": bpy.context.scene.unit_settings.system}


def _scene_restore(prior):
    """Put the document back to an earlier `_scene()` dump: objects that were not there are removed, the others get their transform back and lose modifiers that were not there (a rollback)."""
    want = {o["name"]: o for o in prior.get("objects", [])}
    removed, reset = [], []
    if bpy.context.mode != "OBJECT":
        with contextlib.suppress(Exception):
            bpy.ops.object.mode_set(mode="OBJECT")
    for o in list(bpy.context.view_layer.objects):
        if o.name not in want:
            gone = o.name
            bpy.data.objects.remove(o, do_unlink=True)
            removed.append(gone)
            continue
        w = want[o.name]
        o.location, o.rotation_euler, o.scale = w["loc"], w["rot"], w["scale"]
        for m in list(o.modifiers):
            if m.name not in w.get("mods", []):
                o.modifiers.remove(m)
        reset.append(o.name)
    return {"ok": True, "removed": removed, "reset": reset}


def _shot(path, names=None):
    """The 3D view as a picture inside the run's sandbox (the window is not needed on screen)."""
    if not _inside(path):
        return {"ok": False, "note": "refused: outside the run's sandbox folder"}
    ov = _view3d()
    if ov is None:
        return {"ok": False, "note": "no 3D view"}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sc = bpy.context.scene
    old = (sc.render.filepath, sc.render.image_settings.file_format)
    try:
        sc.render.image_settings.file_format = "PNG"
        sc.render.filepath = path
        with bpy.context.temp_override(**ov):
            picked = [bpy.data.objects[n] for n in (names or []) if n in bpy.data.objects]
            if picked:                                                         # frame the built object itself, not the whole scene with its camera and light
                for o in bpy.context.view_layer.objects:
                    o.select_set(False)
                for o in picked:
                    o.select_set(True)
                bpy.ops.view3d.view_selected()
                for o in picked:
                    o.select_set(False)
            else:
                bpy.ops.view3d.view_all(center=False)
            bpy.ops.render.opengl(write_still=True, view_context=True)
        return {"ok": os.path.isfile(path), "path": path}
    finally:
        sc.render.filepath, sc.render.image_settings.file_format = old


def _batch_add(items):
    """Many parts in one request: each item is the application's own add command with its settings (op, props), then a name, a colour (one material per colour) and a collection."""
    ov = _view3d()
    mats, made, failed = {}, [], []
    for it in items:
        try:
            op_id = it["op"]
            if REFUSED_OPS.search(op_id):
                failed.append([it.get("name", ""), "refused"])
                continue
            mod, op = _op(op_id)
            cm = bpy.context.temp_override(**ov) if ov is not None else contextlib.nullcontext()
            with cm:
                op(**dict(it.get("props") or {}))
            o = bpy.context.view_layer.objects.active
            if o is None:
                failed.append([it.get("name", ""), "no object"])
                continue
            if it.get("name"):
                o.name = str(it["name"])[:60]
            rgba = it.get("rgba")
            if rgba and o.type == "MESH":
                key = tuple(round(float(c), 3) for c in rgba)
                if key not in mats:
                    m = bpy.data.materials.new("hojaiga_%d" % len(mats))
                    m.diffuse_color = list(key) + [1.0] * (4 - len(key))
                    mats[key] = m
                o.data.materials.clear()
                o.data.materials.append(mats[key])
            cn = it.get("collection")
            if cn:
                coll = bpy.data.collections.get(cn)
                if coll is None:
                    coll = bpy.data.collections.new(cn)
                    bpy.context.scene.collection.children.link(coll)
                for c in list(o.users_collection):
                    c.objects.unlink(o)
                coll.objects.link(o)
            made.append(o.name)
        except Exception as exc:
            failed.append([it.get("name", ""), type(exc).__name__ + ": " + str(exc)[:80]])
    return {"ok": True, "made": made, "failed": failed, "materials": len(mats)}


def _view_shot(path, collections=None, hide=None, view="iso", frame=None, only=None):
    """A picture of the 3D view: the named collections hidden for the shot (a roof lifted off), the view turned to look from above or from the south-east, framed on the named collections."""
    if not _inside(path):
        return {"ok": False, "note": "refused: outside the run's sandbox folder"}
    ov = _view3d()
    if ov is None:
        return {"ok": False, "note": "no 3D view"}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    import math
    from mathutils import Euler
    sc = bpy.context.scene
    old = (sc.render.filepath, sc.render.image_settings.file_format)
    hidden = []
    hidden_objs = []
    try:
        if only:                                                                   # a picture of THESE objects alone: everything else is hidden for the shot (an earlier model standing in the scene is not part of this one)
            keep = set(only)
            for o in bpy.context.view_layer.objects:
                if o.name not in keep and not o.hide_viewport:
                    o.hide_viewport = True
                    hidden_objs.append(o)
        for cn in hide or []:
            c = bpy.data.collections.get(cn)
            if c is not None and not c.hide_viewport:
                c.hide_viewport = True
                hidden.append(c)
        r3d = ov["area"].spaces.active.region_3d
        with bpy.context.temp_override(**ov):
            if view in ("top", "front", "side"):
                bpy.ops.view3d.view_axis(type={"top": "TOP", "front": "BACK", "side": "RIGHT"}[view])
            else:
                r3d.view_perspective = "PERSP"
                pitch, yaw = {"iso": (62, 35), "south": (62, 20), "steep": (30, 18), "iso_front": (62, 145), "low_front": (80, 160)}.get(view, (62, 35))                       # degrees from the vertical, and turn
                r3d.view_rotation = Euler((math.radians(pitch), 0, math.radians(yaw)), "XYZ").to_quaternion()
            objs = []
            for cn in frame or []:
                c = bpy.data.collections.get(cn)
                if c is not None:
                    objs += list(c.objects)
                elif bpy.data.objects.get(cn) is not None:                           # a loose part (a design built without collections) is framed by its own name
                    objs.append(bpy.data.objects[cn])
            for o in bpy.context.view_layer.objects:
                o.select_set(False)
            for o in objs:
                if not o.hide_viewport:
                    o.select_set(True)
            if objs:
                bpy.ops.view3d.view_selected()
            else:
                bpy.ops.view3d.view_all(center=False)
            for o in bpy.context.view_layer.objects:
                o.select_set(False)
            sc.render.image_settings.file_format = "PNG"
            sc.render.filepath = path
            bpy.ops.render.opengl(write_still=True, view_context=True)
        return {"ok": os.path.isfile(path), "path": path}
    finally:
        for c in hidden + hidden_objs:
            c.hide_viewport = False
        sc.render.filepath, sc.render.image_settings.file_format = old


def _serve():
    try:
        conn, _ = _srv.accept()
    except BlockingIOError:
        return 0.05
    try:
        conn.settimeout(20.0)
        buf = b""
        while True:                                                                  # a long request (a batch of parts) arrives in pieces; the client closes its side when done
            piece = conn.recv(1 << 16)
            if not piece:
                break
            buf += piece
        req = json.loads(buf.decode("utf-8"))
        if req.get("token") != TOKEN:
            conn.sendall(b'{"ok": false, "error": "bad token"}'); return 0.05
        what = req.get("what")
        if what == "ping":
            res = {"ok": True, "version": bpy.app.version_string}
        elif what == "registry":
            res = {"ok": True, "items": _registry()}
        elif what == "menus":
            res = {"ok": True, "menus": _menus()}
        elif what == "panels":
            res = {"ok": True, "props": _panels(), "errors": list(_ERRORS)}
        elif what == "polls":
            res = {"ok": True, "polls": _polls(list(req.get("ids", [])))}
        elif what == "rna_get":
            res = {"ok": True, "value": _rna_get(req.get("key", ""))}
        elif what == "rna_set":
            res = _rna_set(req.get("key", ""), req.get("value"))
        elif what == "fileinfo":
            res = {"ok": True, **_fileinfo(req.get("id", ""))}
        elif what == "save_copy":
            path = req.get("path", "")
            if not _inside(path):
                res = {"ok": False, "note": "refused: outside the run's sandbox folder"}
            else:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                res = {"ok": True, "note": str(bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)), "path": path}
        elif what == "keymap":
            keys = {}
            kc = bpy.context.window_manager.keyconfigs.active or bpy.context.window_manager.keyconfigs.default
            for km in kc.keymaps:
                for kmi in km.keymap_items:
                    if not kmi.active or not kmi.idname or kmi.map_type not in ("KEYBOARD", "MOUSE"):
                        continue
                    mods = [m for m, on in (("Ctrl", kmi.ctrl), ("Alt", kmi.alt), ("Shift", kmi.shift), ("OSKey", kmi.oskey)) if on is True or on == 1]
                    keys.setdefault(kmi.idname, [])
                    chord = "+".join(mods + [kmi.type.title() if len(kmi.type) > 1 else kmi.type])
                    if chord not in [c for c, _ in keys[kmi.idname]]:
                        keys[kmi.idname].append((chord, km.name))
                    if kmi.idname.startswith("wm.call_menu"):                       # a key that opens a menu: filed under the menu's own class name
                        try:
                            mname = "menu:" + str(kmi.properties.name)
                            keys.setdefault(mname, [])
                            if chord not in [c for c, _ in keys[mname]]:
                                keys[mname].append((chord, km.name))
                        except Exception:
                            pass
            res = {"ok": True, "keys": keys}
        elif what == "select_object":
            res = _select_object(req.get("kind", ""))
        elif what == "key_resolve":
            res = _key_resolve(req.get("chord", ""))
        elif what == "gesture":
            ok, note = _gesture(req.get("kind", ""))
            res = {"ok": ok, "note": note}
        elif what == "execute":
            res = _execute(req.get("id", ""), req.get("props"))
        elif what == "state":
            res = _state()
        elif what == "batch_add":
            res = _batch_add(req.get("items") or [])
        elif what == "view_shot":
            res = _view_shot(req.get("path", ""), None, req.get("hide"), req.get("view", "iso"), req.get("frame"), req.get("only"))
        elif what == "scene":
            res = _scene()
        elif what == "paint":
            o = bpy.data.objects.get(req.get("name", ""))
            if o is None or o.type != "MESH":
                res = {"ok": False, "note": "no such mesh object"}
            else:
                col = [float(c) for c in (list(req.get("rgba") or [0.8, 0.8, 0.8]) + [1.0])[:4]]
                mat = bpy.data.materials.new("hojaiga_" + o.name)
                mat.diffuse_color = col
                try:
                    mat.use_nodes = True
                    bsdf = mat.node_tree.nodes.get("Principled BSDF")
                    if bsdf is not None:
                        bsdf.inputs["Base Color"].default_value = col
                except Exception:
                    pass
                o.data.materials.clear()
                o.data.materials.append(mat)
                if req.get("rename"):
                    o.name = str(req["rename"])[:60]
                res = {"ok": True, "note": "material " + mat.name, "name": o.name}
        elif what == "open_file":
            path = req.get("path", "")
            if not _inside(path) or not os.path.isfile(path):
                res = {"ok": False, "note": "refused or missing: only a file inside the run's sandbox folder can be opened"}
            else:
                res = {"ok": True, "note": str(bpy.ops.wm.open_mainfile(filepath=path)), "file": path}
        elif what == "scene_restore":
            res = _scene_restore(req.get("prior") or {})
        elif what == "shot":
            res = _shot(req.get("path", ""), req.get("names"))
        elif what == "op_props":
            _m, _o = _op(req.get("id", ""))
            res = {"ok": True, "props": [{"name": p.identifier, "type": p.type, "default": (list(p.default_array) if getattr(p, "is_array", False) and p.type in ("FLOAT", "INT", "BOOLEAN") else (p.default if p.type in ("FLOAT", "INT", "BOOLEAN", "STRING") else None)),
                                          "enum": [e.identifier for e in p.enum_items] if p.type == "ENUM" else None, "desc": (p.description or "")[:100]}
                                         for p in _o.get_rna_type().properties if p.identifier != "rna_type"]}
        elif what == "layout":
            res = {"ok": True, "layout": _layout()}
        else:
            res = {"ok": False, "error": "unknown request"}
    except Exception as exc:
        res = {"ok": False, "error": type(exc).__name__ + ": " + str(exc)[:200]}
    try:
        conn.sendall(json.dumps(res, default=str).encode("utf-8"))
    finally:
        conn.close()
    return 0.02


bpy.app.timers.register(_serve, persistent=True)
