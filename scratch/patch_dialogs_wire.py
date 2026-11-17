import ast
import io

R = "D:/new_automation/All codes/core_organs/professor/"


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:100]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


# ------------------------------------------------------------------------------------------------ guide_steps
patch(R + "knowledge/guide_steps.py", [
    ('GROUNDED_HOW = ("path", "label", "chord", "typed", "key", "group", "optional")', 'GROUNDED_HOW = ("path", "label", "chord", "typed", "key", "group", "optional", "dialog")'),
    ('HUMAN_STEP_RX = [', '''SANDBOX_FILES = False                      # set by a run that owns a sandbox (professor.dialogs): choosing / saving a file is then done by the dialog handler on files the run made itself
HUMAN_STEP_RX = ['''),
    ('''    for rx, why in HUMAN_STEP_RX:
        if rx.search(st.raw or ""):
            return Grounded(st, None, 0.0, "human", why)''', '''    for rx, why in HUMAN_STEP_RX:
        if rx.search(st.raw or ""):
            if SANDBOX_FILES and "never chooses the user's own files" in why:
                return Grounded(st, None, 0.8, "dialog", "done by the dialog handler: a file the Professor generated in its sandbox is chosen (never one of the person's own files)")
            return Grounded(st, None, 0.0, "human", why)'''),
])

# ------------------------------------------------------------------------------------------------ executor
patch(R + "executor.py", [
    ("import json\nimport re\nimport time\n", "import json\nimport os\nimport re\nimport time\n"),
    ('''FIELD_ROLES = {"field", "edit", "text_field"}
''', '''FIELD_ROLES = {"field", "edit", "text_field"}
# a verb that sounds destructive but only changes the DOCUMENT the run created (Delete, Remove background, Clear) may be performed in a throw-away document of an editor; one that touches the system, an account,
# files, history, or that would end the application itself (close / exit) may not. Categories of wording and of application kind - no application names.
STRONG_UNSAFE_RX = re.compile(r"(?i)\\b(uninstall|shut ?down|restart|reboot|kill|terminate|wipe|purge|factory|reset all|format|sign ?out|log ?out|exit|quit|empty|close)\\b")
DOC_OBJECT_RX = re.compile(r"(?i)\\b(account|profile|history|data|cookies?|cache|passwords?|saved|files?|folders?|drive|disk|apps?|applications?|everything|device|windows?|system|browsing|all|tabs?)\\b")
DOC_EDITOR_ARCHETYPES = {"document_text", "raster_editor", "canvas_layout", "spreadsheet_data", "code_ide", "spatial_3d", "temporal_media"}
'''),
    ('''        self.deny: Optional["re.Pattern"] = None                  # an application-level policy''', '''        self.dialogs: Any = None                                  # professor.dialogs.DialogDriver: file dialogs (sandbox files), message boxes, print dialogs
        self.clip: Any = None                                     # professor.dialogs.ClipboardGuard: the person's clipboard is saved before a run writes to it and put back after
        self.sandbox: Any = None                                  # professor.dialogs.Sandbox: the only place a dialog may read from / write to
        self.dialog_log: List[Dict[str, Any]] = []
        self._file_followups = 0                                  # file-dialog steps of the guide that follow a dialog the handler already completed
        self.deny: Optional["re.Pattern"] = None                  # an application-level policy'''),
    ('''        if hum and cls == "sensitive" and self.allow is not None and self.allow.search(v.label):
            hum = False''', '''        if hum and cls == "sensitive" and self.allow is not None and self.allow.search(v.label):
            hum = False
        if hum and cls == "unsafe" and self._doc_local(v):
            hum = False                                                   # 'Remove background' / 'Delete' in a throw-away document of an editor'''),
    ('''            elif g.how == "human":
                s = Step(0, st.raw, None, "", [], "unknown", safety="sensitive", need_human=True, note=g.note, source="guide", cite=gp["cite"], target=st.target)''',
     '''            elif g.how == "dialog":
                s = Step(0, st.raw, None, "", [], "dialog", safety="safe", routes=["dialog: sandbox file"], expected="the file dialog is completed with a file of the run's sandbox", source="guide", cite=gp["cite"],
                         note=g.note, target=st.target)
            elif g.how == "human":
                s = Step(0, st.raw, None, "", [], "unknown", safety="sensitive", need_human=True, note=g.note, source="guide", cite=gp["cite"], target=st.target)'''),
    # ---- the loop: dialogs of the previous step, file-dialog steps
    ('''        for si, st in enumerate(list(rep.steps)):
            t0 = time.time()
            if st.kind == "unknown" and st.source == "guide" and not rep.dry_run and st.goal:''', '''        for si, st in enumerate(list(rep.steps)):
            t0 = time.time()
            if self.dialogs is not None and not rep.dry_run:
                if si > 0 and not self._is_file_step(st):
                    self._auto_dialogs(rep)                                       # a dialog the previous step opened (a message box, a print dialog, a file chooser) is dealt with before this step looks at the screen
                if self._is_file_step(st):
                    dres = self._file_step(st)
                    if dres is not None:
                        rep.results.append(dres)
                        if dres.status != "done":
                            rep.stopped = f"step {st.index + 1} ('{dres.verb}'): {dres.summary}"
                            break
                        continue
            if st.kind == "unknown" and st.source == "guide" and not rep.dry_run and st.goal:'''),
    # ---- copy / paste preparation
    ('''            routes = self.routes_for(v, st.text) if v else []
            if st.prefer:''', '''            if self.clip is not None and v is not None and not rep.dry_run:
                ck = f"{v.label} {v.shortcut}"
                if COPY_RX.search(ck):
                    self.clip.begin()                                                  # the person's clipboard is saved BEFORE the application overwrites it
                elif PASTE_RX.search(ck):
                    cnote = self._prepare_paste(st, v)
                    if cnote.startswith("refused"):
                        rep.results.append(StepResult(st.index, label, "refused", summary=cnote, ms=int((time.time() - t0) * 1000)))
                        rep.stopped = f"step {st.index + 1} ('{label}'): {cnote}"
                        break
            routes = self.routes_for(v, st.text) if v else []
            if st.prefer:'''),
    ('''            if v is not None and result.status == "done":
                self._last_verb = v
            if self._sticky is not None:''', '''            if v is not None and result.status == "done":
                self._last_verb = v
                if self.clip is not None and COPY_RX.search(f"{v.label} {v.shortcut}"):
                    self.clip.touch()                                                  # what is on the clipboard now is the run's own
            if self._sticky is not None:'''),
    ('''        rep.ok = bool(rep.results) and not rep.stopped and all(r.status in ("done", "dry_run") for r in rep.results) and len(rep.results) == len(rep.steps)
        rep.seconds = round(time.time() - t_start, 2)
        return rep''', '''        if self.dialogs is not None and not rep.dry_run:
            self._auto_dialogs(rep)                                                  # a dialog the LAST step opened
        rep.ok = bool(rep.results) and not rep.stopped and all(r.status in ("done", "dry_run") for r in rep.results) and len(rep.results) == len(rep.steps)
        rep.seconds = round(time.time() - t_start, 2)
        return rep

    # ---- dialogs, files, clipboard
    def _doc_local(self, v: Verb) -> bool:
        """May this 'unsafe'-sounding verb be performed here? Only a verb that changes the document of a throw-away editor session, and says nothing about files, accounts, the system or closing."""
        if not (self.owned and self.sandboxed and self.archetype in DOC_EDITOR_ARCHETYPES):
            return False
        text = v.label + " " + " ".join(v.path[-1:])
        return not (STRONG_UNSAFE_RX.search(text) or DOC_OBJECT_RX.search(v.label))

    @staticmethod
    def _is_file_step(st: Step) -> bool:
        from .dialogs import FILE_STEP_RX
        return st.kind == "dialog" or (st.source == "guide" and st.kind in ("unknown", "verb") and bool(FILE_STEP_RX.search(st.goal or "")))

    def _file_step(self, st: Step) -> Optional[StepResult]:
        """A step of the guide that belongs to a file dialog ('choose the image', 'type a name', 'click Save'): while a file dialog is open the handler completes it with a sandbox file; once it has been
        completed, the guide's remaining dialog steps are satisfied by it. A step that merely SOUNDS like a file step, with no dialog around, goes on as an ordinary step."""
        t0 = time.time()
        label = st.verb or st.goal[:60]
        if self.dialogs.pending():
            handled = self.dialogs.settle(max_s=10.0, intent="accept")
            if handled:
                self._file_followups = 3
                self.dialog_log += handled
                ok = all(h.get("ok") for h in handled)
                return StepResult(st.index, label, "done" if ok else "no_effect", route="dialog-driver", effect="dialog_closed" if ok else "dialog_stuck",
                                  summary="; ".join(f"{h['kind']}: " + "; ".join(h["steps"])[:140] for h in handled)[:420], ms=int((time.time() - t0) * 1000))
        if self._file_followups > 0:
            self._file_followups -= 1
            return StepResult(st.index, label, "done", route="dialog-driver", effect="already", summary="the file dialog was already completed with a sandbox file by the dialog handler", ms=0)
        if st.kind == "dialog":
            return StepResult(st.index, label, "no_effect", summary="the manual speaks of a file dialog here, but none is open", ms=int((time.time() - t0) * 1000))
        return None

    def _auto_dialogs(self, rep: ExecReport) -> None:
        """Whatever dialog the last step left open (file chooser, message box, print dialog) is handled by policy; the result of that step says so."""
        if self.dialogs is None or not self.dialogs.pending():
            return
        handled = self.dialogs.settle(max_s=8.0, intent="accept")
        if not handled:
            return
        self.dialog_log += handled
        if any(h["kind"] in ("file_open", "file_save", "folder") for h in handled):
            self._file_followups = 3
        note = " | dialog handled: " + "; ".join(f"{h['kind']} '{h['title'][:30]}': " + "; ".join(h["steps"])[:120] for h in handled)
        if rep.results:
            rep.results[-1].summary = (rep.results[-1].summary + note)[:700]

    def _prepare_paste(self, st: Step, v: Verb) -> str:
        """A paste step needs something on the clipboard. What the run itself copied stays; otherwise a fixture (text, or a picture where the context is graphical) is placed - after the person's own
        clipboard has been saved. A clipboard that cannot be put back is never overwritten."""
        from .dialogs import IMAGE_CONTEXT_RX, ClipboardBusy
        try:
            if self.clip.has_run_content():
                return "the clipboard holds what this run copied"
            ctx = f"{st.goal} {v.label} {' '.join(v.path)} {self.archetype}"
            if self.sandbox is not None and (IMAGE_CONTEXT_RX.search(ctx) or self.archetype in ("raster_editor", "canvas_layout")):
                p = self.sandbox.fixture("image", ["png"])
                self.clip.put_image(p)
                return f"the clipboard now holds a fixture picture ({os.path.basename(p)}); the person's clipboard is put back afterwards"
            self.clip.put_text("Hojaiga clipboard fixture text")
            return "the clipboard now holds fixture text; the person's clipboard is put back afterwards"
        except ClipboardBusy as exc:
            return "refused: " + str(exc)
        except Exception as exc:
            return f"refused: clipboard not usable ({type(exc).__name__})"'''),
    ("from .knowledge.guide_steps import GROUNDED_HOW\n", "from .knowledge.guide_steps import GROUNDED_HOW\nfrom .dialogs import COPY_RX, PASTE_RX\n"),
])

# ------------------------------------------------------------------------------------------------ apprun
patch(R + "apprun.py", [
    ('''# in an application that holds the user's own account or data (navigate mode)''', '''DENY_WORDS = ["save", "save as", "save all", "export", "print", "publish", "share", "send", "email", "upload", "sign in", "log ?in", "sign out", "log ?out", "uninstall", "delete", "erase", "format",
              "restore defaults", "reset"]


def deny_rx(sandbox_files: bool, doc_editor: bool) -> "re.Pattern":
    """What is never done without a human. With a file sandbox (professor.dialogs) saving and exporting are safe - the dialog is forced into the sandbox; in a throw-away editor document deleting /
    erasing a selection harms nothing. Printing, publishing, sharing, sending, uploading and sign-in stay human."""
    drop = set()
    if sandbox_files:
        drop |= {"save", "save as", "save all", "export"}
    if doc_editor:
        drop |= {"delete", "erase"}
    return re.compile(r"\\b(" + "|".join(w for w in DENY_WORDS if w not in drop) + r")\\b", re.I)


# in an application that holds the user's own account or data (navigate mode)'''),
    ('''        self.ex.deny = NAV_FORBID_RX if self.spec.mode == "navigate" else DENY_RX
        self.ex.sandboxed = bool(self.guard is not None and (self.guard.tmp_dirs or self.guard.report.get("backed_up")))          # throw-away state: settings-like verbs are harmless here''',
     '''        self.ex.sandboxed = bool(self.guard is not None and (self.guard.tmp_dirs or self.guard.report.get("backed_up")))          # throw-away state: settings-like verbs are harmless here
        # popups, file dialogs and the clipboard: a sandbox folder of the run's own, a driver that completes dialogs with files in it, a clipboard guard that gives the person's clipboard back
        try:
            from . import dialogs as DG
            from .knowledge import guide_steps as GS
            self.sandbox = DG.Sandbox(self.spec.key, self.stamp)
            self.dialogs = DG.DialogDriver(self.fx, self.hwnd, self.sandbox, baseline=self._popups0, history=self.history, toolkit=ds.profile.family, log=self.say)
            self.dialogs.start_watch()
            self.clip = DG.ClipboardGuard()
            self.ex.dialogs, self.ex.clip, self.ex.sandbox = self.dialogs, self.clip, self.sandbox
            GS.SANDBOX_FILES = True
        except Exception as exc:
            self.say("dialog handling unavailable: " + type(exc).__name__)
        self.ex.deny = NAV_FORBID_RX if self.spec.mode == "navigate" else deny_rx(self.dialogs is not None, self.arch.get("id") in DOC_EDITOR_ARCHETYPES)'''),
    ('''        self._surf = 0
        self._no_reveal = False''', '''        self._surf = 0
        self._no_reveal = False
        self.sandbox: Any = None
        self.dialogs: Any = None
        self.clip: Any = None'''),
    ('''        if self.fx is not None:
            self.report["focus_returns"] = getattr(self.fx, "focus_returns", None)''', '''        if self.fx is not None:
            self.report["focus_returns"] = getattr(self.fx, "focus_returns", None)
        try:
            handled = (self.ex.dialog_log if self.ex is not None else []) or []
            self.report["dialogs"] = {"handled": [{k: h.get(k) for k in ("kind", "title", "ok", "steps", "path", "saved")} for h in handled[:40]], "count": len(handled),
                                      "sandbox": self.sandbox.summary() if self.sandbox is not None else {},
                                      "clipboard": self.clip.end() if self.clip is not None else "not used"}
            if self.dialogs is not None:
                self.dialogs.stop_watch()
        except Exception:
            pass'''),
    ('''    def _teardown(self) -> None:
        """Close the owned instance and release its state (used when the run must start over)."""
        from core_organs.atlas import scanner as SC''', '''    def _teardown(self) -> None:
        """Close the owned instance and release its state (used when the run must start over)."""
        from core_organs.atlas import scanner as SC
        with contextlib.suppress(Exception):
            if self.dialogs is not None:
                self.dialogs.stop_watch()
            if self.clip is not None:
                self.clip.end()'''),
])
patch(R + "apprun.py", [("from .executor import Executor, milestone_checker", "from .executor import Executor, milestone_checker, DOC_EDITOR_ARCHETYPES")])
print("ok")
