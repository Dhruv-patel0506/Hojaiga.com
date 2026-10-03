const { app, BrowserWindow } = require('electron');
const fs = require('fs');
app.whenReady().then(async () => {
  // ---- TEST 1: parser + motion guarantee (main process, compiled JS) ----
  const cm = require('D:/new_automation/final hojaiga tutor/dist/CompanionManager.js');
  const results = {};

  const a = cm.parseVisualTagsFromText('[ANIMATE:wheel:110,310->460,310:54:Rolling Wheel:cyan] watch it roll');
  const wheel = a.commands.find(c => c.type === 'ANIMATE');
  results.wheelParse = JSON.stringify({ preset: wheel.preset, x1: wheel.x1, x2: wheel.x2, r: wheel.r, label: wheel.label, color: wheel.color, loop: wheel.loop, spoken: a.spokenText });

  const b = cm.parseVisualTagsFromText('[ANIMATE:projectile:100,380->460,380,170:Projectile Trajectory:green] and it flies');
  const proj = b.commands.find(c => c.type === 'ANIMATE');
  results.projParse = JSON.stringify({ preset: proj.preset, peakH: proj.peakH, x2: proj.x2 });

  const c = cm.parseVisualTagsFromText('[WHEEL:100,300->500,300:60:Rolling Wheel:yellow] legacy form');
  const legacy = c.commands[0];
  results.legacyWheel = JSON.stringify({ preset: legacy.preset, r: legacy.r, x2: legacy.x2, label: legacy.label });

  const d = cm.parseVisualTagsFromText('[ANIMATE:pendulum:280,145:190:Swinging Pendulum:yellow][ANIMATE:orbit:280,295:135:Orbit:cyan][ANIMATE:wave:90,290:65:Wave:purple][ANIMATE:spring:95,300:75:SHM:cyan][ANIMATE:move:110,300->450,300:42:Moving Block:cyan] multi');
  results.multi = d.commands.map(x => x.type + '/' + x.preset).join(',');

  // prose-only step about motion -> injection
  const prose = [ { type: 'WRITE', x: 700, y: 200, label: 'notes', color: 'white' } ];
  cm.ensureMotionAnimationForPrompt('animate a wheel rolling across the screen', prose);
  results.injectWheel = prose.map(x => x.type + (x.preset ? ':' + x.preset : '')).join(',');

  // already has ANIMATE -> untouched
  const hasAnim = [ { type: 'ANIMATE', preset: 'wave' } ];
  const before = JSON.stringify(hasAnim);
  cm.ensureMotionAnimationForPrompt('roll a wheel', hasAnim);
  results.noDoubleInject = before === JSON.stringify(hasAnim);

  // no motion words -> untouched
  const noMotion = [ { type: 'WRITE', label: 'x' } ];
  cm.ensureMotionAnimationForPrompt('explain quadratic functions', noMotion);
  results.noMotionNoInject = noMotion.length === 1;

  // full lesson flow: model emitted prose only, prompt about pendulum
  let sentCount = 0;
  await cm.executeSynchronizedLesson(
    '[STEP]this is about a swinging pendulum, here are notes[WRITE:700,200:Step 1: pendulum basics][/STEP][STEP]the period depends on length[WRITE:700,300:Step 2: T = 2pi sqrt(L/g)][/STEP]',
    (cmds, clearFirst) => { sentCount++; results.lessonStep0 = cmds.map(x => x.type + (x.preset ? ':' + x.preset : '')).join(','); },
    async () => {},
    undefined,
    'explain a pendulum swinging back and forth'
  );
  results.lessonStepsSent = sentCount;

  console.log(JSON.stringify(results, null, 1));

  // ---- TEST 2: overlay 60 FPS loop ----
  const win = new BrowserWindow({ width: 1522, height: 754, show: true,
    webPreferences: { nodeIntegration: true, contextIsolation: false } });
  await win.loadFile('D:/new_automation/final hojaiga tutor/public/overlay.html');
  const notes = [];
  for (let i = 1; i <= 6; i++) notes.push({ type:'WRITE', x:700, y:150+i*60, label:'Step '+i+': substitute values into the equation and simplify', color:'white' });
  const cmds = [
    { type:'BOARD', x:60, y:60, w:760, h:440, label:'Motion of a rolling wheel' },
    { type:'ANIMATE', preset:'wheel', x1:110, y1:310, x2:460, y2:310, r:54, label:'Rolling Wheel (No-Slip Motion)', color:'cyan', loop:true },
    ...notes
  ];
  await win.webContents.executeJavaScript(`window.ClickyOverlay.addCommands(${JSON.stringify(cmds)}, true); window.ClickyOverlay.setSubtitle('watch the wheel roll'); 'ok';`);

  await new Promise(r => setTimeout(r, 600));
  const mid = await win.webContents.executeJavaScript(`(function(){
    const img1 = document.getElementById('overlay-canvas').toDataURL('image/png').length;
    return JSON.stringify({ t:'a', img1, anim: !!window.__rafCheck });
  })()`);
  const shot1 = await win.webContents.capturePage();
  await new Promise(r => setTimeout(r, 500));
  const shot2 = await win.webContents.capturePage();
  const b1 = shot1.toBitmap(), b2 = shot2.toBitmap();
  let diffPixels = 0;
  for (let i = 0; i < b1.length; i += 4) {
    if (b1[i] !== b2[i] || b1[i+1] !== b2[i+1] || b1[i+2] !== b2[i+2]) diffPixels++;
  }

  await new Promise(r => setTimeout(r, 5000));
  const late = await win.webContents.executeJavaScript(`(function(){
    const rect = activeCommands.find(c=>c.type==='ANIMATE');
    const notesC = activeCommands.filter(c=>c.type==='WRITE');
    const hit=(a,b)=>!(a.x+a.w<=b.x||b.x+b.w<=a.x||a.y+a.h<=b.y||b.y+b.h<=a.y);
    const ar = {x:rect._animRect.x,y:rect._animRect.y,w:rect._animRect.w,h:rect._animRect.h};
    const overlaps = notesC.filter(n=>hit({x:n.x,y:n.y,w:n.cardW,h:n.cardH}, ar)).length;
    return JSON.stringify({
      stillLooping: animationFrameId !== null,
      loopFlag: rect.loop === true,
      animRect: [Math.round(ar.x),Math.round(ar.y),Math.round(ar.w),Math.round(ar.h)],
      noteAnimateOverlaps: overlaps,
      zoneViolations: notesC.filter(n=>n.x<540).length,
      voidActive: document.getElementById('infinite-void').classList.contains('active')
    });
  })()`);
  console.log('MID ' + mid);
  console.log('DIFF_PIXELS ' + diffPixels);
  console.log('LATE ' + late.replace(/\},/g,'},\n'));
  const img = await win.webContents.capturePage();
  fs.writeFileSync('C:/Users/dhruv/AppData/Local/Temp/opencode/overlay_anim1.png', img.toPNG());
  console.log('shot saved');
  app.exit(0);
});
