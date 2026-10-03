const { app, BrowserWindow } = require('electron');
const fs = require('fs');
app.whenReady().then(async () => {
  const cm = require('D:/new_automation/final hojaiga tutor/dist/CompanionManager.js');
  const r = {};

  // --- parsers: all 5 new tags ---
  const kf = cm.parseVisualTagsFromText('[KEYFRAMES:circle:0,90,320,0,0.6->0.5,285,170,180,1.4->1,470,320,360,0.6:Energy Curve:cyan] moving').commands[0];
  r.kf = JSON.stringify({ t: kf.type, shape: kf.shape, n: kf.keyframes.length, last: kf.keyframes[2], loop: kf.loop, spoken: 'moving' });
  const gr = cm.parseVisualTagsFromText('[GRAPH:Sun->Plants|Plants->Herbivores|Herbivores->Carnivores:Food Chain:cyan] graph').commands[0];
  r.graph = JSON.stringify({ t: gr.type, nodes: gr.nodes, edges: gr.edges.length, label: gr.label });
  const tr = cm.parseVisualTagsFromText('[TRACE:42,15,8,99,23:swap=1,2:ptr=1:Bubble Sort Pass:yellow] trace').commands[0];
  r.trace = JSON.stringify({ t: tr.type, v: tr.values, swap: tr.swapIndices, ptr: tr.pointerIndex });
  const fd = cm.parseVisualTagsFromText('[FIELD:gas:temp=80:Kinetic Theory:orange] field').commands[0];
  r.field = JSON.stringify({ t: fd.type, kind: fd.fieldType, intensity: fd.intensity });
  const dj = cm.parseVisualTagsFromText('[DJ:lofi:84:Lo-Fi Beat:purple] music').commands[0];
  r.dj = JSON.stringify({ t: dj.type, genre: dj.genre, bpm: dj.bpm, root: dj.chordRoot });

  // --- dispatcher: IN PLACE, no replacement, once per type ---
  const a1 = [{ type: 'BOARD', x: 60, y: 60, w: 760, h: 440, label: 'Sort' }, { type: 'WRITE', x: 700, y: 200, label: 'n', color: 'white' }, { type: 'BOX', x: 1, y: 1, w: 10, h: 10, label: 'crude' }];
  const same = cm.enrichUniversalCapabilities('explain bubble sort step by step', a1) === a1;
  r.traceInPlace = same;
  r.traceTypes = a1.map(c => c.type).join(',');
  cm.enrichUniversalCapabilities('explain bubble sort step by step', a1);
  r.traceOnce = a1.filter(c => c.type === 'TRACE').length === 1;
  r.traceKeptBoard = a1.some(c => c.type === 'BOARD');

  const a2 = [{ type: 'WRITE', x: 700, y: 200, label: 'n', color: 'white' }];
  cm.enrichUniversalCapabilities('make a flowchart of the water cycle', a2);
  r.graphDerived = JSON.stringify({ types: a2.map(c => c.type).join(','), nodes: (a2.find(c => c.type === 'GRAPH') || {}).nodes });

  const a3 = [{ type: 'WRITE', x: 700, y: 200, label: 'n', color: 'white' }];
  cm.enrichUniversalCapabilities('explain kinetic theory of gas particles', a3);
  r.fieldGas = (a3.find(c => c.type === 'FIELD') || {}).fieldType;
  const a3b = [{ type: 'WRITE', x: 700, y: 200, label: 'n', color: 'white' }];
  cm.enrichUniversalCapabilities('draw magnetic field lines around a bar magnet', a3b);
  r.fieldMagnetic = (a3b.find(c => c.type === 'FIELD') || {}).fieldType;

  const a4 = [{ type: 'WRITE', x: 700, y: 200, label: 'n', color: 'white' }];
  cm.enrichUniversalCapabilities('play some lofi beats for studying', a4);
  r.djInjected = JSON.stringify((a4.find(c => c.type === 'DJ') || {}), null, 0).slice(0, 120);

  const a5 = [{ type: 'WRITE', x: 700, y: 200, label: 'n', color: 'white' }, { type: 'CIRCLE', x: 300, y: 300, r: 40, label: 'crude' }];
  cm.enrichUniversalCapabilities('analyze my squat posture form check', a5);
  const act = a5.find(c => c.type === 'ACTOR');
  r.biomech = JSON.stringify({ types: a5.map(c => c.type).join(','), action: act && act.action, protractor: act && act.showProtractor });
  cm.enrichUniversalCapabilities('analyze my squat posture form check', a5);
  r.biomechOnce = a5.filter(c => c.type === 'ACTOR').length === 1;

  // --- regressions through the same dispatcher+ensure chain ---
  const w = [{ type: 'WRITE', label: 'n' }];
  cm.ensureMotionAnimationForPrompt('show a wheel rolling', w);
  r.wheel = w[0].type;
  const pool = [{ type: 'BOX', x: 1, y: 1, w: 10, h: 10, label: 'c' }];
  cm.ensureMotionAnimationForPrompt('the skeleton sits on the pool edge ready to dive', pool);
  r.pool = pool.map(c => c.type).join(',');
  const heart = [];
  cm.ensureMotionAnimationForPrompt('human heart anatomy', heart);
  r.heart = heart.map(c => c.type).join(',');

  // --- lesson: TRACE injected once, step1 clean ---
  const steps = [];
  await cm.executeSynchronizedLesson(
    '[STEP]compare the first pair[WRITE:700,200:Step 1: swap if out of order][BOX:200,200,150,200:crude][/STEP][STEP]move the pointer right[WRITE:700,300:Step 2: next pair][/STEP]',
    (cmds) => { steps.push(cmds.map(c => c.type).join(',')); },
    async () => {},
    undefined,
    'walk me through bubble sort'
  );
  r.lessonStep0 = steps[0];
  r.lessonStep1 = steps[1];
  console.log('PART1 ' + JSON.stringify(r, null, 1));

  // ================= overlay render tests =================
  const win = new BrowserWindow({ width: 1522, height: 754, show: true,
    webPreferences: { nodeIntegration: true, contextIsolation: false } });
  await win.loadFile('D:/new_automation/final hojaiga tutor/public/overlay.html');
  const mkNotes = (n) => Array.from({ length: n }, (_, i) => ({ type: 'WRITE', x: 700, y: 150 + i * 70, label: 'Step ' + (i + 1) + ': keep the explanation on the right side', color: 'white' }));
  const checkFn = (rectKey) => `(function(){
    const d = activeCommands.find(c=>c.type==='${rectKey}') || activeCommands.find(c=>c.type==='${rectKey}');
    const notesC = activeCommands.filter(c=>c.type==='WRITE');
    const hit=(a,b)=>!(a.x+a.w<=b.x||b.x+b.w<=a.x||a.y+a.h<=b.y||b.y+b.h<=a.y);
    const rects = activeCommands.filter(c=>c._kfRect||c._gRect||c._traceRect||c._fieldRect||c._djRect||c._actorRect).map(c=>c._kfRect||c._gRect||c._traceRect||c._fieldRect||c._djRect||c._actorRect);
    let diagramOverlaps = 0;
    for (let i=0;i<rects.length;i++) for (let j=i+1;j<rects.length;j++) if (hit(rects[i],rects[j])) diagramOverlaps++;
    const noteOverlaps = notesC.reduce((s,n)=>s+rects.filter(rr=>hit({x:n.x,y:n.y,w:n.cardW,h:n.cardH}, rr)).length,0);
    return JSON.stringify({
      type: d&&d.type, rect: rects[0] && [Math.round(rects[0].x),Math.round(rects[0].y),Math.round(rects[0].w),Math.round(rects[0].h)],
      diagramOverlaps, noteOverlaps,
      zoneViolations: notesC.filter(n=>n.x<540).length,
      stillLooping: animationFrameId !== null
    });
  })()`;

  const run = async (name, cmds, extra) => {
    await win.webContents.executeJavaScript(`window.ClickyOverlay.addCommands(${JSON.stringify(cmds)}, true); window.ClickyOverlay.setSubtitle('${name} demo'); 'ok';`);
    await new Promise(res => setTimeout(res, 1100));
    const s1 = await win.webContents.capturePage();
    await new Promise(res => setTimeout(res, 450));
    const s2 = await win.webContents.capturePage();
    const b1 = s1.toBitmap(), b2 = s2.toBitmap();
    let diff = 0;
    for (let i = 0; i < b1.length; i += 4) if (b1[i]!==b2[i] || b1[i+1]!==b2[i+1] || b1[i+2]!==b2[i+2]) diff++;
    await new Promise(res => setTimeout(res, 3600));
    const info = await win.webContents.executeJavaScript(checkFn('X'));
    console.log(name + ' DIFF=' + diff + ' ' + info);
    if (extra) console.log(name + '_EXTRA ' + (await win.webContents.executeJavaScript(extra)));
    const img = await win.webContents.capturePage();
    fs.writeFileSync('C:/Users/dhruv/AppData/Local/Temp/opencode/overlay_' + name + '.png', img.toPNG());
  };

  const board = { type: 'BOARD', x: 60, y: 60, w: 760, h: 440, label: 'Universal Engines' };

  await run('keyframes', [board,
    { type: 'KEYFRAMES', shape: 'circle', keyframes: [{t:0,x:90,y:320,rot:0,scale:0.6},{t:0.5,x:285,y:170,rot:180,scale:1.4},{t:1,x:470,y:320,rot:360,scale:0.6}], label: 'Energy Curve Ride', color: 'cyan', loop: true },
    ...mkNotes(4)]);

  await run('graph', [board,
    { type: 'GRAPH', nodes: ['Sun','Plants','Herbivores','Carnivores'], edges: [{from:'Sun',to:'Plants'},{from:'Plants',to:'Herbivores'},{from:'Herbivores',to:'Carnivores'}], nodePositions: {}, label: 'Food Chain', color: 'cyan', loop: true },
    { type: 'TRACE', values: ['42','15','8','99','23'], swapIndices: [0,1], pointerIndex: 1, label: 'Bubble Sort Pass 1', color: 'yellow', loop: true },
    ...mkNotes(4)],
    `(function(){ const g=activeCommands.find(c=>c.type==='GRAPH'); const t=activeCommands.find(c=>c.type==='TRACE');
      const inside = Object.values(g.nodePositions).every(p=>p.x>0&&p.x<g._gRect.w&&p.y>0&&p.y<g._gRect.h);
      const hit=(a,b)=>!(a.x+a.w<=b.x||b.x+b.w<=a.x||a.y+a.h<=b.y||b.y+b.h<=a.y);
      return JSON.stringify({ nodesInsideRect: inside, graphTraceOverlap: hit(g._gRect, t._traceRect) }); })()`);

  await run('field', [board,
    { type: 'FIELD', fieldType: 'gas', intensity: 80, label: 'Kinetic Theory of Gases', color: 'orange', loop: true },
    ...mkNotes(4)]);

  await run('dj', [board,
    { type: 'DJ', genre: 'lofi', bpm: 84, chordRoot: 261.63, label: 'Lo-Fi Study Beat', color: 'purple', loop: true },
    ...mkNotes(4)],
    `JSON.stringify({ audioRunning: DJAudio.timer !== null, genre: DJAudio.genre, bpm: DJAudio.bpm })`);

  // DJ stops on clear
  await win.webContents.executeJavaScript(`window.ClickyOverlay.clear(); 'ok';`);
  await new Promise(res => setTimeout(res, 300));
  console.log('DJ_STOPPED ' + (await win.webContents.executeJavaScript(`JSON.stringify({ audioStopped: DJAudio.timer === null })`)));

  // biomechanics protractor actor
  await run('biomech', [board,
    { type: 'ACTOR', action: 'sprint', pov: '3rd', x1: 125, y1: 315, x2: 435, y2: 315, cx: 275, cy: 315, showProtractor: true, label: 'Biomechanics Rig', color: 'green', loop: true },
    ...mkNotes(4)],
    `JSON.stringify({ hasActor: !!activeCommands.find(c=>c.type==='ACTOR'), protractor: (activeCommands.find(c=>c.type==='ACTOR')||{}).showProtractor })`);

  console.log('shots saved');
  app.exit(0);
});
