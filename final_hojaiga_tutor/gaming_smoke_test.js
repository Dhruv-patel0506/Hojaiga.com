const { app, BrowserWindow } = require('electron');
const fs = require('fs');
app.whenReady().then(async () => {
  const cm = require('D:/new_automation/final hojaiga tutor/dist/CompanionManager.js');
  const gm = require('D:/new_automation/final hojaiga tutor/dist/GamingAimAndSensEngine.js');
  const r = {};

  // --- Section 2: converter reference math ---
  const c1 = gm.CrossGameSensConverter.convert({ sourceGameKey: 'cs2', targetGameKey: 'valorant', sourceSens: 1.0, dpi: 800 });
  r.raw360 = c1.targetSensRaw360;                     // 1.0*0.022*800/(0.07*800) = 0.3143
  r.raw360Ok = Math.abs(c1.targetSensRaw360 - 0.3143) < 0.0005;
  const c2 = gm.CrossGameSensConverter.convert({ sourceGameKey: 'valorant', targetGameKey: 'valorant', sourceSens: 0.35, dpi: 800 });
  r.fovIdentity = Math.abs(c2.targetSensFovMatched - c2.targetSensRaw360) < 1e-9;  // same game => fovScale 1
  r.cm360 = c2.cmPer360;                               // 0.35@800 valorant => ~46.65 cm
  r.cmOk = c2.cmPer360 > 45 && c2.cmPer360 < 48;
  r.aimStyle = c2.aimStyleClassification;             // >45 => Low-Sens Arm Aim
  const c3 = gm.CrossGameSensConverter.convert({ sourceGameKey: 'cs2', targetGameKey: 'valorant', sourceSens: 1.0, dpi: 800, sourceStretched43: true });
  r.stretch43 = Math.abs(c3.targetSensStretchedAdjusted - c3.targetSensFovMatched * (4 / 3)) < 2e-4;  // toFixed(4) rounding
  const c4 = gm.CrossGameSensConverter.convert({ sourceGameKey: 'cs2', targetGameKey: 'valorant', sourceSens: 1.0, dpi: 800, sourceFov: 106.26, targetFov: 106.26 });
  r.fovEqual = Math.abs(c4.targetSensFovMatched - c4.targetSensRaw360) < 1e-9;      // equal FOVs => scale 1

  // --- game detection order (direction must follow prompt, not DB order) ---
  r.games1 = gm.detectMentionedGames('convert cs2 to valorant').join(',');   // cs2,valorant
  r.games2 = gm.detectMentionedGames('my counter-strike sens in overwatch').join(',');
  r.games3 = gm.detectMentionedGames('marvel rivals flicking').join(',');

  // --- Section 3: analyzer on synthetic traces ---
  const straight = Array.from({ length: 11 }, (_, i) => ({ x: i * 10, y: 0, t: i * 20 }));
  const a1 = gm.MousePrecisionAnalyzer.analyzeHandTrace(straight, { x: 0, y: 0 }, { x: 100, y: 0 }, 800);
  r.straight = JSON.stringify({ eff: a1.pathEfficiencyPct, over: a1.overshootPct, jit: a1.jitterPx, mult: a1.recommendedSensMultiplier });
  const over = [...Array.from({ length: 11 }, (_, i) => ({ x: i * 15, y: 0, t: i * 20 })), { x: 150, y: 0, t: 240 }, { x: 100, y: 0, t: 300 }];
  const a2 = gm.MousePrecisionAnalyzer.analyzeHandTrace(over, { x: 0, y: 0 }, { x: 100, y: 0 }, 800);
  r.overshoot = JSON.stringify({ over: a2.overshootPct, mult: a2.recommendedSensMultiplier, dx: a2.recommendedDpi });
  const wobble = Array.from({ length: 41 }, (_, i) => ({ x: i * 10, y: (i % 2 ? 20 : -20), t: i * 12.5 }));
  const a3 = gm.MousePrecisionAnalyzer.analyzeHandTrace(wobble, { x: 0, y: 0 }, { x: 400, y: 0 }, 800);
  r.wobble = JSON.stringify({ eff: a3.pathEfficiencyPct, jit: a3.jitterPx, mult: a3.recommendedSensMultiplier, dpi: a3.recommendedDpi });

  // --- Section 4: IN-PLACE dispatch, never replaces model commands ---
  const cmds = [
    { type: 'BOARD', x: 60, y: 60, w: 760, h: 440, label: 'Aim Lab' },
    { type: 'WRITE', x: 700, y: 200, label: 'teaching note', color: 'white' },
    { type: 'BOX', x: 200, y: 200, w: 100, h: 80, label: 'crude target', color: 'red' },
  ];
  const sameRef = cm.enrichUniversalCapabilities('convert my 1.0 sens from cs2 to valorant at 800 dpi, i play 4:3 stretched', cmds) === cmds;
  r.gamingInPlace = sameRef;
  r.gamingTypes = cmds.map(c => c.type).join(',');
  const trainer = cmds.find(c => c.type === 'AIM_TRAINER');
  r.trainer = JSON.stringify({ mode: trainer && trainer.drillMode, dpi: trainer && trainer.dpi, cm: trainer && trainer.cmPer360 });
  r.sourceCard = (cmds.find(c => c.type === 'WRITE' && /Counter-Strike/.test(c.label)) || {}).label;
  cm.enrichUniversalCapabilities('convert my 1.0 sens from cs2 to valorant at 800 dpi, i play 4:3 stretched', cmds);
  r.gamingOnce = cmds.filter(c => c.type === 'AIM_TRAINER').length === 1;
  r.boardKept = cmds.some(c => c.type === 'BOARD');

  const untouched = [{ type: 'WRITE', x: 700, y: 200, label: 'n', color: 'white' }];
  r.nonGamingUntouched = cm.enrichUniversalCapabilities('teach me the quadratic formula', untouched) === untouched && untouched.length === 1;

  // --- lesson: AIM_TRAINER once, step1 clean ---
  const steps = [];
  await cm.executeSynchronizedLesson(
    '[STEP]flick to the first target[WRITE:700,200:Step 1: crosshair placement][BOX:200,200,150,200:crude target][/STEP][STEP]reset your hand[WRITE:700,300:Step 2: micro adjust][/STEP]',
    (cmds2) => { steps.push(cmds2.map(c => c.type).join(',')); },
    async () => {},
    undefined,
    'aim training flick drill in valorant'
  );
  r.lessonStep0 = steps[0];
  r.lessonStep1 = steps[1];
  r.lessonOnce = steps.filter(s => s.includes('AIM_TRAINER')).length === 1;

  // --- regressions through the same dispatcher chain ---
  const w2 = [{ type: 'WRITE', label: 'n' }];
  cm.ensureMotionAnimationForPrompt('show a wheel rolling', w2);
  r.wheel = w2[0].type;
  const pool = [{ type: 'BOX', x: 1, y: 1, w: 10, h: 10, label: 'c' }];
  cm.ensureMotionAnimationForPrompt('the skeleton sits on the pool edge ready to dive', pool);
  r.pool = pool.map(c => c.type).join(',');
  const heart = [];
  cm.ensureMotionAnimationForPrompt('human heart anatomy', heart);
  r.heart = heart.map(c => c.type).join(',');
  const dj = [{ type: 'WRITE', label: 'n' }];
  cm.enrichUniversalCapabilities('play some lofi beats', dj);
  r.dj = dj.map(c => c.type).join(',');
  console.log('PART1 ' + JSON.stringify(r, null, 1));

  // ================= overlay render =================
  const win = new BrowserWindow({ width: 1522, height: 754, show: true,
    webPreferences: { nodeIntegration: true, contextIsolation: false } });
  await win.loadFile('D:/new_automation/final hojaiga tutor/public/overlay.html');
  const notes = [];
  for (let i = 1; i <= 4; i++) notes.push({ type: 'WRITE', x: 700, y: 150 + i * 70, label: 'Step ' + i + ': keep the drill notes on the right', color: 'white' });
  const cmds2 = [
    { type: 'BOARD', x: 60, y: 60, w: 760, h: 440, label: 'Aim & Sensitivity Lab' },
    { type: 'AIM_TRAINER', drillMode: 'flick', dpi: 800, sourceSens: 0.35, targetSens: 0.3333, cmPer360: 46.65, label: 'Live FLICK Precision Drill', color: 'cyan', loop: true },
    ...notes,
  ];
  await win.webContents.executeJavaScript(`window.ClickyOverlay.addCommands(${JSON.stringify(cmds2)}, true); window.ClickyOverlay.setSubtitle('flick drill'); 'ok';`);
  await new Promise(res => setTimeout(res, 1100));
  const s1 = await win.webContents.capturePage();
  await new Promise(res => setTimeout(res, 450));
  const s2 = await win.webContents.capturePage();
  const b1 = s1.toBitmap(), b2 = s2.toBitmap();
  let diff = 0;
  for (let i = 0; i < b1.length; i += 4) if (b1[i] !== b2[i] || b1[i + 1] !== b2[i + 1] || b1[i + 2] !== b2[i + 2]) diff++;
  await new Promise(res => setTimeout(res, 3600));
  const late = await win.webContents.executeJavaScript(`(function(){
    const a = activeCommands.find(c=>c.type==='AIM_TRAINER');
    const notesC = activeCommands.filter(c=>c.type==='WRITE');
    const hit=(x,y)=>!(x.x+x.w<=y.x||y.x+y.w<=x.x||x.y+x.h<=y.y||y.y+y.h<=x.y);
    const ar = a._aimRect;
    const overlaps = notesC.filter(n=>hit({x:n.x,y:n.y,w:n.cardW,h:n.cardH}, ar)).length;
    return JSON.stringify({
      rect: [Math.round(ar.x),Math.round(ar.y),Math.round(ar.w),Math.round(ar.h)],
      noteAimOverlaps: overlaps,
      zoneViolations: notesC.filter(n=>n.x<540).length,
      stillLooping: animationFrameId !== null
    });
  })()`);
  console.log('DIFF_PIXELS ' + diff);
  console.log('LATE ' + late);
  const img = await win.webContents.capturePage();
  fs.writeFileSync('C:/Users/dhruv/AppData/Local/Temp/opencode/overlay_aim.png', img.toPNG());
  console.log('shots saved');
  app.exit(0);
});
