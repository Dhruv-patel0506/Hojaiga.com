import os, sys, tempfile, time
os.environ["HOJAIGA_PROF_DIR"] = os.path.join(tempfile.gettempdir(), "hojaiga_prof_lab")
sys.path.insert(0, r"D:\new_automation"); sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs.professor import pointer as PT
from core_organs.professor.lab.labkit import Lab, client_origin
from core_organs.professor.lab.lab_matrix import Fx
import frida
name = sys.argv[1] if len(sys.argv) > 1 else "winforms"
lab = Lab(name); ox, oy = client_origin(lab.hwnd)
vp = PT.VirtualPointer(lab.hwnd, "x", Fx(), only=["shim"])
vp.hover(ox + 80, oy + 40)
sess = frida.attach(lab.proc.pid)
JS = """
var REC = false;
var u = Process.getModuleByName('user32.dll');
['GetAsyncKeyState','GetKeyState'].forEach(function(n){ var a = u.getExportByName(n); Interceptor.attach(a, { onEnter: function(args){ this.vk = args[0].toInt32(); }, onLeave: function(r){ if (REC && (this.vk <= 6)) send(n + '(' + this.vk + ')=' + r.toInt32()); } }); });
['SetCapture','ReleaseCapture','GetCapture','DragDetect','GetCursorPos','SetCursor','PeekMessageW','GetMessageW','SetWindowsHookExW','GetClipboardOwner','OleInitialize'].forEach(function(n){ try { var a = u.getExportByName(n); Interceptor.attach(a, { onEnter: function(){ if (REC) send(n); } }); } catch(e){} });
var wfp = u.getExportByName('WindowFromPoint'); Interceptor.attach(wfp, { onEnter: function(a){ this.pt = a[0]; }, onLeave: function(r){ if (REC) { var v = BigInt(this.pt.toString()); send('WFP(' + Number(BigInt.asIntN(32, v & BigInt(0xFFFFFFFF))) + ',' + Number(BigInt.asIntN(32, v >> BigInt(32))) + ')->' + r); } } });
['PeekMessageW','GetMessageW'].forEach(function(n){ Interceptor.attach(u.getExportByName(n), { onEnter: function(a){ this.m = a[0]; }, onLeave: function(r){ if (REC && r.toInt32() !== 0) { var m = this.m; var msg = m.add(8).readU32(); if (msg >= 0x200 && msg <= 0x20E) send('MSG ' + msg.toString(16) + ' lp=(' + (m.add(24).readS16()) + ',' + (m.add(26).readS16()) + ') pt=(' + m.add(40).readS32() + ',' + m.add(44).readS32() + ')'); } } }); });
Interceptor.attach(u.getExportByName('GetCursorPos'), { onEnter: function(a){ this.p = a[0]; }, onLeave: function(r){ if (REC) send('GCP=(' + this.p.readS32() + ',' + this.p.add(4).readS32() + ')'); } });
rpc.exports = { rec: function(v){ REC = v; return true; } };
"""
log = []
sc = sess.create_script(JS); sc.on("message", lambda m, d: log.append(m["payload"]) if m["type"] == "send" else None); sc.load()
sc.exports_sync.rec(True)
m = lab.mark()
res = vp.drag_drop((ox + 80, oy + 40), (ox + 750, oy + 200))
time.sleep(0.6); sc.exports_sync.rec(False)
print([e["kind"] for e in lab.since(m) if not e["kind"].startswith("move")])
from collections import Counter
c = Counter(log); print(c.most_common(30))
i = [k for k, x in enumerate(log)]
print([x for x in log if str(x).startswith(('MSG','GCP'))][:40]); wf = [x for x in log if str(x).startswith('WFP')]; print(set(wf)); from core_organs.professor.pointer import _child_at; print('target child', hex(_child_at(lab.hwnd, ox+750, oy+200)), 'src child', hex(_child_at(lab.hwnd, ox+80, oy+40)), 'top', hex(lab.hwnd))
vp.close(); lab.close()
