// professor.inproc agent -- runs INSIDE an application the run launched itself (never the person's own processes).
// It makes the polling APIs an application uses to learn "where is the mouse / which buttons are down / which modifiers" answer with the VIRTUAL pointer's state
// while a gesture is being delivered, so that an app which ignores posted window messages because it cross-checks them against the real cursor now sees one consistent pointer.
// The person's physical cursor and keyboard are never read or changed by this agent. Everything is addressed through rpc.exports (synchronous, ordered).
'use strict';
var S = { on: false, kb: false, x: 0, y: 0, btn: 0, mods: 0, win: ptr('0') };
var KEYS = {};                                                       // virtual key -> down?, from the WM_KEYDOWN / WM_KEYUP messages the application dequeues (posted ones included)           // btn: 1 left, 2 right, 4 middle, 8 x1, 16 x2   mods: 1 shift, 2 ctrl, 4 alt, 8 win
var hooked = [], failed = [], calls = {};
var u32 = Process.getModuleByName('user32.dll');
function addr(name) { try { return u32.getExportByName(name); } catch (e) { return null; } }
function hook(name, ret, args, fn, needs) {                              // needs: 'ptr' = answers only while the virtual POINTER is on; default = pointer or keyboard
  var a = addr(name);
  if (!a) { failed.push(name); return; }
  var orig = new NativeFunction(a, ret, args);
  calls[name] = 0;
  try {
    Interceptor.replace(a, new NativeCallback(function () {
      calls[name]++;
      var av = Array.prototype.slice.call(arguments);
      if (needs === 'ptr' ? !S.on : (!S.on && !S.kb)) return orig.apply(null, av);
      try { return fn.apply(null, [orig].concat(av)); } catch (e) { return orig.apply(null, av); }
    }, ret, args));
    hooked.push(name);
  } catch (e) { failed.push(name + ':' + e); }
}
var VKBTN = { 0x01: 1, 0x02: 2, 0x04: 4, 0x05: 8, 0x06: 16 };
var MODBIT = { 0x10: 1, 0xA0: 1, 0xA1: 1, 0x11: 2, 0xA2: 2, 0xA3: 2, 0x12: 4, 0xA4: 4, 0xA5: 4, 0x5B: 8, 0x5C: 8 };
var MODKEYS = { 1: [0x10, 0xA0, 0xA1], 2: [0x11, 0xA2, 0xA3], 4: [0x12, 0xA4, 0xA5], 8: [0x5B, 0x5C] };
function vkDown(vk) {                                                 // true / false when the virtual state decides, null when it does not speak for this key
  if (S.on && (vk in VKBTN)) return (S.btn & VKBTN[vk]) !== 0;
  var bit = MODBIT[vk];
  if (bit !== undefined && (S.on || S.kb)) {                          // a modifier: what the virtual pointer holds, or a key the application saw go down - never the person's own keyboard
    if (S.mods & bit) return true;
    return MODKEYS[bit].some(function (k) { return KEYS[k] === true; });
  }
  if (S.kb && KEYS[vk] !== undefined) return KEYS[vk] === true;
  return null;
}
hook('GetCursorPos', 'int', ['pointer'], function (o, p) { p.writeS32(S.x); p.add(4).writeS32(S.y); return 1; }, 'ptr');
hook('GetPhysicalCursorPos', 'int', ['pointer'], function (o, p) { p.writeS32(S.x); p.add(4).writeS32(S.y); return 1; }, 'ptr');
hook('GetCursorInfo', 'int', ['pointer'], function (o, p) { var r = o(p); if (r) { p.add(16).writeS32(S.x); p.add(20).writeS32(S.y); } return r; }, 'ptr');
hook('GetMessagePos', 'uint32', [], function (o) { return (((S.y & 0xFFFF) << 16) | (S.x & 0xFFFF)) >>> 0; }, 'ptr');
hook('GetAsyncKeyState', 'int16', ['int'], function (o, vk) { var d = vkDown(vk); if (d === null) return o(vk); return d ? -32768 : 0; });
hook('GetKeyState', 'int16', ['int'], function (o, vk) { var d = vkDown(vk); if (d === null) return o(vk); return d ? -32768 : 0; });
hook('GetKeyboardState', 'int', ['pointer'], function (o, p) {
  var r = o(p);
  if (r) { [0x01, 0x02, 0x04, 0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5].forEach(function (vk) { var d = vkDown(vk); if (d !== null) p.add(vk).writeU8(d ? 0x80 : 0); }); }
  return r;
});
// ---- safety: an application that moves or confines the cursor itself (a 3D editor wrapping the pointer during an endless drag, a game centring it) must never move THE PERSON'S cursor.
// These are swallowed for as long as the agent is loaded; the virtual pointer follows the position the application asked for.
function guard(name, ret, args, fn) {
  var a = addr(name);
  if (!a) return;
  calls[name] = 0;
  try { Interceptor.replace(a, new NativeCallback(function () { calls[name]++; return fn.apply(null, Array.prototype.slice.call(arguments)); }, ret, args)); hooked.push(name); }
  catch (e) { failed.push(name + ':' + e); }
}
guard('SetCursorPos', 'int', ['int', 'int'], function (x, y) { S.x = x; S.y = y; return 1; });
guard('SetPhysicalCursorPos', 'int', ['int', 'int'], function (x, y) { S.x = x; S.y = y; return 1; });
guard('ClipCursor', 'int', ['pointer'], function (r) { return 1; });
guard('mouse_event', 'void', ['uint32', 'uint32', 'uint32', 'uint32', 'pointer'], function () { });
(function () {                                                      // SendInput: a call carrying any MOUSE input is swallowed (it would act on the person's desktop); keyboard-only calls pass through
  var a = addr('SendInput');
  if (!a) return;
  var orig = new NativeFunction(a, 'uint32', ['uint32', 'pointer', 'int']);
  calls['SendInput'] = 0;
  try {
    Interceptor.replace(a, new NativeCallback(function (n, p, cb) {
      calls['SendInput']++;
      var mouse = false;
      for (var i = 0; i < n; i++) { if (p.add(i * cb).readU32() === 0) { mouse = true; break; } }
      return mouse ? n : orig(n, p, cb);
    }, 'uint32', ['uint32', 'pointer', 'int']));
    hooked.push('SendInput');
  } catch (e) { failed.push('SendInput:' + e); }
})();
// WindowFromPoint at (or within 2 px of) the virtual pointer answers with the window the virtual pointer is over: a toolkit that checks "is the mouse really over my window?" before it
// accepts a wheel / move (WPF) gets the answer even while the window is parked where no monitor shows it.
(function () {
  var a = addr('WindowFromPoint');
  if (!a) return;
  var orig = new NativeFunction(a, 'pointer', ['int64']);
  calls['WindowFromPoint'] = 0;
  try {
    Interceptor.replace(a, new NativeCallback(function (pt) {
      calls['WindowFromPoint']++;
      if (S.on && !S.win.isNull()) {
        var x = Number(BigInt.asIntN(32, BigInt(pt) & BigInt(0xFFFFFFFF))), y = Number(BigInt.asIntN(32, BigInt(pt) >> BigInt(32)));
        if (Math.abs(x - S.x) <= 2 && Math.abs(y - S.y) <= 2) return S.win;
      }
      return orig(pt);
    }, 'pointer', ['int64']));
    hooked.push('WindowFromPoint');
  } catch (e) { failed.push('WindowFromPoint:' + e); }
})();
// MSG.pt: the system stamps a dequeued mouse message with the screen position of the cursor when it was generated; for a POSTED message that is not the position it carries. Code that
// takes the pointer from msg.pt (OLE's drag-and-drop loop does) is given the position the message itself names, converted exactly as the system would: client coordinates -> screen.
(function () {
  var cts = null;
  try { cts = new NativeFunction(addr('ClientToScreen'), 'int', ['pointer', 'pointer']); } catch (e) { return; }
  var tmp = Memory.alloc(8);
  ['PeekMessageW', 'PeekMessageA', 'GetMessageW', 'GetMessageA'].forEach(function (n) {
    var a = addr(n);
    if (!a) return;
    try {
      Interceptor.attach(a, {
        onEnter: function (args) { this.m = args[0]; },
        onLeave: function (r) {
          if (r.toInt32() <= 0) return;
          var m = this.m, msg = m.add(8).readU32();
          if (msg === 0x100 || msg === 0x104) { KEYS[m.add(16).readU32() & 0xFF] = true; return; }
          if (msg === 0x101 || msg === 0x105) { KEYS[m.add(16).readU32() & 0xFF] = false; return; }
          if (!S.on) return;
          var lx = m.add(24).readS16(), ly = m.add(26).readS16();
          if ((msg >= 0x200 && msg <= 0x209) || (msg >= 0x20B && msg <= 0x20D)) {
            tmp.writeS32(lx); tmp.add(4).writeS32(ly);
            if (cts(m.readPointer(), tmp)) { m.add(36).writeS32(tmp.readS32()); m.add(40).writeS32(tmp.add(4).readS32()); }
          } else if (msg === 0x20A || msg === 0x20E || (msg >= 0xA0 && msg <= 0xAD)) { m.add(36).writeS32(lx); m.add(40).writeS32(ly); }
        }
      });
      hooked.push(n + '.pt');
    } catch (e) { failed.push(n + ':' + e); }
  });
})();
rpc.exports = {
  kb: function (on) { S.kb = !!on; if (!on) { KEYS = {}; } return true; },
  set: function (on, x, y, btn, mods, win) { S.on = !!on; S.x = x | 0; S.y = y | 0; S.btn = btn | 0; S.mods = mods | 0; S.win = ptr(String(win || 0)); return true; },
  // the guard's self-test: ask THIS process to move the cursor; the caller checks that the person's cursor did not go there
  selftest: function (x, y) { var f = new NativeFunction(addr('SetCursorPos'), 'int', ['int', 'int']); return f(x, y); },
  state: function () { return { s: { on: S.on, x: S.x, y: S.y, btn: S.btn, mods: S.mods, win: S.win.toString() }, hooked: hooked, failed: failed, calls: calls }; }
};
