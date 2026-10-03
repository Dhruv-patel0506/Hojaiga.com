const { app, BrowserWindow } = require('electron');
const fs = require('fs');
app.whenReady().then(async () => {
  const cm = require('D:/new_automation/final hojaiga tutor/dist/CompanionManager.js');
  const r = {};

  // --- parser ---
  const a = cm.parseVisualTagsFromText('[ANATOMY:nervous:285,315,1:Human Nervous System:cyan] the nervous system');
  const anat = a.commands[0];
  r.anatomyParse = JSON.stringify({ t: anat.type, sys: anat.system, cx: anat.cx, scale: anat.scale, label: anat.label, loop: anat.loop, spoken: a.spokenText });
  const s = cm.parseVisualTagsFromText('[SVG:M10 80 C 40 10, 65 10, 95 80 S 150 150, 180 80:120,200,1:Curve:cyan] drawn');
  const svg = s.commands[0];
  r.svgParse = JSON.stringify({ t: svg.type, d: (svg.d||'').slice(0,20), cx: svg.cx, label: svg.label, spoken: s.spokenText });

  // --- biology upgrade: crude boxes stripped, notes kept ---
  const crude = [
    { type:'BOARD', x:60, y:60, w:760, h:440, label:'Human Nervous System' },
    { type:'POLYGON', points:[{x:1,y:1},{x:2,y:2},{x:3,y:3},{x:4,y:4}], label:'head diamond', color:'red' },
    { type:'BOX', x:200, y:200, w:150, h:200, label:'torso', color:'red' },
    { type:'CIRCLE', x:300, y:400, r:40, label:'leg', color:'red' },
    { type:'WRITE', x:700, y:200, label:'Step 1: neurons carry signals', color:'white' },
    { type:'WRITE', x:700, y:300, label:'Step 2: brain coordinates', color:'white' },
    { type:'PLOT', expr:'x^2', xMin:-3, xMax:3, x:100, y:150, w:300, h:250, color:'cyan' },
  ];
  const ok = cm.ensureBiologyDiagramForPrompt('explain the human nervous system', crude);
  r.bioReturnsTrue = ok;
  r.afterBio = crude.map(c => c.type + (c.system ? ':' + c.system : '')).join(',');
  r.notesPreserved = crude.filter(c => c.type==='WRITE').length;
  r.plotPreserved = crude.some(c => c.type==='PLOT');
  r.boardPreserved = crude.some(c => c.type==='BOARD');
  // idempotent: second call must not duplicate
  cm.ensureBiologyDiagramForPrompt('explain the human nervous system', crude);
  r.noDuplicateAnatomy = crude.filter(c => c.type==='ANATOMY').length === 1;

  // system detection
  const systems = {};
  for (const [prompt, want] of [['teach me the heart and circulation','heart'],['how do lungs breathe','lungs'],['digestive system steps','digestive'],['human skeleton bones','skeletal'],['how a neuron fires','neuron'],['dna replication','dna']]) {
    const arr = [];
    cm.ensureBiologyDiagramForPrompt(prompt, arr);
    systems[prompt] = (arr.find(c=>c.type==='ANATOMY')||{}).system;
  }
  r.systems = JSON.stringify(systems);

  // non-bio prompt untouched; motion prompt still injects ANIMATE (not anatomy)
  const plain = [{ type:'WRITE', label:'x' }];
  r.nonBioUntouched = (cm.ensureBiologyDiagramForPrompt('teach me excel vlookup', plain) === false) && plain.length === 1;
  const motion = [{ type:'WRITE', label:'n' }];
  cm.ensureMotionAnimationForPrompt('show a wheel rolling', motion);
  r.motionStillWorks = motion[0].type === 'ANIMATE';
  // bio prompt through ensureMotion -> anatomy, not animate
  const bioViaMotion = [{ type:'BOX', x:1,y:1,w:10,h:10, label:'crude' }];
  cm.ensureMotionAnimationForPrompt('human heart anatomy', bioViaMotion);
  r.bioViaMotion = bioViaMotion.map(c=>c.type).join(',');

  // --- full lesson: model emitted crude boxes only ---
  const steps = [];
  await cm.executeSynchronizedLesson(
    '[STEP]this is the human nervous system[WRITE:700,200:Step 1: brain and nerves][BOX:200,200,150,200:crude torso][POLYGON:10,10->20,10->20,20->10,20:crude head:red][/STEP][STEP]signals travel down the spine[WRITE:700,300:Step 2: action potentials][CIRCLE:300,400,40:crude leg:red][/STEP]',
    (cmds) => { steps.push(cmds.map(c=>c.type+(c.system?':'+c.system:'')).join(',')); },
    async () => {},
    undefined,
    'teach me the human nervous system'
  );
  r.lessonStep0 = steps[0];
  r.lessonStep1 = steps[1];
  console.log('PART1 ' + JSON.stringify(r, null, 1));

  // --- overlay render test ---
  const win = new BrowserWindow({ width: 1522, height: 754, show: true,
    webPreferences: { nodeIntegration: true, contextIsolation: false } });
  await win.loadFile('D:/new_automation/final hojaiga tutor/public/overlay.html');
  const notes = [];
  for (let i = 1; i <= 5; i++) notes.push({ type:'WRITE', x:700, y:150+i*70, label:'Step '+i+': neurons transmit electrochemical signals through the body', color:'white' });
  const cmds = [
    { type:'BOARD', x:60, y:60, w:760, h:440, label:'Human Nervous System' },
    { type:'ANATOMY', system:'nervous', cx:285, cy:315, scale:1, label:'Human NERVOUS System', color:'cyan', loop:true },
    ...notes
  ];
  await win.webContents.executeJavaScript(`window.ClickyOverlay.addCommands(${JSON.stringify(cmds)}, true); window.ClickyOverlay.setSubtitle('signals fire from the brain'); 'ok';`);
  await new Promise(res => setTimeout(res, 1200));
  const shotA = await win.webContents.capturePage();
  await new Promise(res => setTimeout(res, 500));
  const shotB = await win.webContents.capturePage();
  const b1 = shotA.toBitmap(), b2 = shotB.toBitmap();
  let diff = 0;
  for (let i = 0; i < b1.length; i += 4) if (b1[i]!==b2[i] || b1[i+1]!==b2[i+1] || b1[i+2]!==b2[i+2]) diff++;

  await new Promise(res => setTimeout(res, 4000));
  const late = await win.webContents.executeJavaScript(`(function(){
    const anat = activeCommands.find(c=>c.type==='ANATOMY');
    const notesC = activeCommands.filter(c=>c.type==='WRITE');
    const hit=(a,b)=>!(a.x+a.w<=b.x||b.x+b.w<=a.x||a.y+a.h<=b.y||b.y+b.h<=a.y);
    const ar = anat._anatRect;
    const overlaps = notesC.filter(n=>hit({x:n.x,y:n.y,w:n.cardW,h:n.cardH}, {x:ar.x,y:ar.y,w:ar.w,h:ar.h})).length;
    return JSON.stringify({
      stillLooping: animationFrameId !== null,
      animRect: [Math.round(ar.x),Math.round(ar.y),Math.round(ar.w),Math.round(ar.h)],
      scale: +anat.scale.toFixed(2),
      noteAnatomyOverlaps: overlaps,
      zoneViolations: notesC.filter(n=>n.x<540).length,
      voidActive: document.getElementById('infinite-void').classList.contains('active')
    });
  })()`);
  console.log('DIFF_PIXELS ' + diff);
  console.log('LATE ' + late.replace(/\},/g,'},\n'));
  const img = await win.webContents.capturePage();
  fs.writeFileSync('C:/Users/dhruv/AppData/Local/Temp/opencode/overlay_anatomy1.png', img.toPNG());

  // --- SVG render test on a fresh overlay ---
  await win.webContents.executeJavaScript(`window.ClickyOverlay.clear();
    window.ClickyOverlay.addCommands([
      { type:'BOARD', x:60, y:60, w:760, h:440, label:'Vector Path Demo' },
      { type:'SVG', d:'M 60 300 C 160 80, 340 80, 440 300 S 620 520, 700 300', cx:250, cy:250, scale:1, label:'Bezier Curve', color:'cyan', loop:true }
    ], true); 'ok';`);
  await new Promise(res => setTimeout(res, 300));
  const svgOk = await win.webContents.executeJavaScript(`(function(){
    const s = activeCommands.find(c=>c.type==='SVG');
    return JSON.stringify({ hasSvg: !!s, rect: s && [Math.round(s._anatRect.x),Math.round(s._anatRect.y),Math.round(s._anatRect.w),Math.round(s._anatRect.h)], len: s && s._pathLen });
  })()`);
  console.log('SVG ' + svgOk);
  await new Promise(res => setTimeout(res, 900));
  const img2 = await win.webContents.capturePage();
  fs.writeFileSync('C:/Users/dhruv/AppData/Local/Temp/opencode/overlay_svg1.png', img2.toPNG());
  console.log('shots saved');
  app.exit(0);
});
