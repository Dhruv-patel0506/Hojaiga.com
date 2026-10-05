const { app, BrowserWindow } = require('electron');
const fs = require('fs');
app.whenReady().then(async () => {
  const cm = require('D:/new_automation/final hojaiga tutor/dist/CompanionManager.js');
  const r = {};

  // --- parser: ACTOR tag, all POVs ---
  const a = cm.parseVisualTagsFromText('[ACTOR:sprint:3rd:120,315->445,315:Sprinting Figure:cyan] watch this sprint');
  const ac = a.commands[0];
  r.actorParse = JSON.stringify({ t: ac.type, act: ac.action, pov: ac.pov, x1: ac.x1, y1: ac.y1, x2: ac.x2, y2: ac.y2, label: ac.label, loop: ac.loop, spoken: a.spokenText });
  const b = cm.parseVisualTagsFromText('[ACTOR:wave:2nd::Wave From Front:cyan] wave');
  r.pov2nd = JSON.stringify({ pov: b.commands[0].pov, act: b.commands[0].action, x1: b.commands[0].x1, x2: b.commands[0].x2 });
  const c = cm.parseVisualTagsFromText('[ACTOR:swim:1st::Swimming POV:cyan] swim');
  r.pov1st = c.commands[0].pov;

  // --- detectActorScene: hijack prompt resolves to ACTOR, not anatomy ---
  const hijack = 'the skeleton sits right on the pool\'s edge, ready to dive in';
  r.hijackDetect = JSON.stringify(cm.detectActorScene(hijack));
  r.heartDetect = cm.detectActorScene('teach me how the heart pumps blood');       // strong organ -> null
  r.waveDetect = cm.detectActorScene('teach me wave motion in physics');           // physics wave -> null
  r.runDetect = cm.detectActorScene('run the sorting algorithm');                  // no human/scene -> null
  r.humanRunDetect = JSON.stringify(cm.detectActorScene('show me someone running across the track'));

  // --- biology must NOT hijack the scene prompt ---
  const hijackArr = [{ type:'BOX', x:1,y:1,w:10,h:10, label:'crude' }, { type:'WRITE', x:700, y:200, label:'note', color:'white' }];
  r.hijackBioRefused = cm.ensureBiologyDiagramForPrompt(hijack, hijackArr) === false;
  r.hijackNoAnatomy = !hijackArr.some(x => x.type === 'ANATOMY');

  // --- ACTOR injection: strips crude, keeps notes/board/plot/animate, once ---
  const scene = [
    { type:'BOARD', x:60, y:60, w:760, h:440, label:'Dive Prep' },
    { type:'POLYGON', points:[{x:1,y:1},{x:2,y:2},{x:3,y:3}], label:'crude', color:'red' },
    { type:'CIRCLE', x:300, y:400, r:40, label:'crude', color:'red' },
    { type:'WRITE', x:700, y:200, label:'Step 1: bend knees', color:'white' },
    { type:'PLOT', expr:'x^2', xMin:-3, xMax:3, x:100, y:150, w:300, h:250, color:'cyan' },
    { type:'ANIMATE', preset:'wheel', x1:110, y1:310, x2:460, y2:310, r:54, label:'w', color:'cyan', loop:true },
  ];
  r.sceneActorInjected = cm.ensureActionActorForPrompt(hijack, scene);
  r.sceneTypes = scene.map(x => x.type).join(',');
  cm.ensureActionActorForPrompt(hijack, scene);
  r.noDuplicateActor = scene.filter(x => x.type === 'ACTOR').length === 1;
  r.actorAction = (scene.find(x => x.type === 'ACTOR') || {}).action;

  // --- regression: organ prompt still -> anatomy; wheel still -> animate ---
  const organ = [];
  cm.ensureMotionAnimationForPrompt('human heart anatomy', organ);
  r.organViaMotion = organ.map(x => x.type).join(',');
  const wheel = [{ type:'WRITE', label:'n' }];
  cm.ensureMotionAnimationForPrompt('show a wheel rolling', wheel);
  r.wheelStillWorks = wheel[0].type === 'ANIMATE';
  const poolViaMotion = [{ type:'BOX', x:1,y:1,w:10,h:10, label:'crude' }, { type:'WRITE', x:700, y:300, label:'note', color:'white' }];
  cm.ensureMotionAnimationForPrompt(hijack, poolViaMotion);
  r.poolViaMotion = poolViaMotion.map(x => x.type).join(',');

  // --- full lesson over the hijack prompt: ACTOR once, crude gone both steps ---
  const steps = [];
  await cm.executeSynchronizedLesson(
    '[STEP]you crouch at the edge[WRITE:700,200:Step 1: bend knees][BOX:200,200,150,200:crude torso][CIRCLE:300,400,40:crude leg:red][/STEP][STEP]you push off and dive[WRITE:700,300:Step 2: streamline][POLYGON:10,10->20,10->20,20->10,20:crude head:red][/STEP]',
    (cmds) => { steps.push(cmds.map(x => x.type).join(',')); },
    async () => {},
    undefined,
    hijack
  );
  r.lessonStep0 = steps[0];
  r.lessonStep1 = steps[1];
  r.lessonActorOnce = steps.filter(s => s.includes('ACTOR')).length === 1;
  console.log('PART1 ' + JSON.stringify(r, null, 1));

  // --- overlay render test ---
  const win = new BrowserWindow({ width: 1522, height: 754, show: true,
    webPreferences: { nodeIntegration: true, contextIsolation: false } });
  await win.loadFile('D:/new_automation/final hojaiga tutor/public/overlay.html');
  const notes = [];
  for (let i = 1; i <= 5; i++) notes.push({ type:'WRITE', x:700, y:150+i*70, label:'Step '+i+': streamlining reduces drag through the water', color:'white' });
  const cmds = [
    { type:'BOARD', x:60, y:60, w:760, h:440, label:'Dive Technique' },
    { type:'ACTOR', action:'dive', pov:'3rd', x1:120, y1:315, x2:445, y2:315, cx:275, cy:315, label:'Diving Into Pool', color:'cyan', loop:true },
    ...notes
  ];
  await win.webContents.executeJavaScript(`window.ClickyOverlay.addCommands(${JSON.stringify(cmds)}, true); window.ClickyOverlay.setSubtitle('you push off the ledge'); 'ok';`);
  await new Promise(res => setTimeout(res, 1200));
  const shotA = await win.webContents.capturePage();
  await new Promise(res => setTimeout(res, 500));
  const shotB = await win.webContents.capturePage();
  const b1 = shotA.toBitmap(), b2 = shotB.toBitmap();
  let diff = 0;
  for (let i = 0; i < b1.length; i += 4) if (b1[i]!==b2[i] || b1[i+1]!==b2[i+1] || b1[i+2]!==b2[i+2]) diff++;

  await new Promise(res => setTimeout(res, 4500));
  const late = await win.webContents.executeJavaScript(`(function(){
    const actor = activeCommands.find(c=>c.type==='ACTOR');
    const notesC = activeCommands.filter(c=>c.type==='WRITE');
    const hit=(a,b)=>!(a.x+a.w<=b.x||b.x+b.w<=a.x||a.y+a.h<=b.y||b.y+b.h<=a.y);
    const ar = actor._actorRect;
    const overlaps = notesC.filter(n=>hit({x:n.x,y:n.y,w:n.cardW,h:n.cardH}, {x:ar.x,y:ar.y,w:ar.w,h:ar.h})).length;
    return JSON.stringify({
      stillLooping: animationFrameId !== null,
      actorRect: [Math.round(ar.x),Math.round(ar.y),Math.round(ar.w),Math.round(ar.h)],
      dx: actor._actDx, dy: actor._actDy,
      noteActorOverlaps: overlaps,
      zoneViolations: notesC.filter(n=>n.x<540).length,
      voidActive: document.getElementById('infinite-void').classList.contains('active')
    });
  })()`);
  console.log('DIFF_PIXELS ' + diff);
  console.log('LATE ' + late.replace(/\},/g,'},\n'));
  const img = await win.webContents.capturePage();
  fs.writeFileSync('C:/Users/dhruv/AppData/Local/Temp/opencode/overlay_actor1.png', img.toPNG());

  // --- 1st PERSON POV on a fresh overlay ---
  await win.webContents.executeJavaScript(`window.ClickyOverlay.clear();
    window.ClickyOverlay.addCommands([
      { type:'BOARD', x:60, y:60, w:760, h:440, label:'Swim POV' },
      { type:'ACTOR', action:'swim', pov:'1st', x1:120, y1:315, x2:445, y2:315, cx:285, cy:295, label:'Swimming POV', color:'cyan', loop:true }
    ], true); 'ok';`);
  await new Promise(res => setTimeout(res, 3500));
  const povOk = await win.webContents.executeJavaScript(`(function(){
    const s = activeCommands.find(c=>c.type==='ACTOR');
    return JSON.stringify({ has: !!s, pov: s.pov, cx: s.cx, rect: s && [Math.round(s._actorRect.x),Math.round(s._actorRect.y),Math.round(s._actorRect.w),Math.round(s._actorRect.h)], stillLooping: animationFrameId !== null });
  })()`);
  console.log('POV1ST ' + povOk);
  const img2 = await win.webContents.capturePage();
  fs.writeFileSync('C:/Users/dhruv/AppData/Local/Temp/opencode/overlay_actor_pov1.png', img2.toPNG());

  // --- regression: anatomy still renders after ACTOR merge ---
  await win.webContents.executeJavaScript(`window.ClickyOverlay.clear();
    window.ClickyOverlay.addCommands([
      { type:'BOARD', x:60, y:60, w:760, h:440, label:'Nervous System' },
      { type:'ANATOMY', system:'nervous', cx:285, cy:315, scale:1, label:'Human NERVOUS System', color:'cyan', loop:true }
    ], true); 'ok';`);
  await new Promise(res => setTimeout(res, 3500));
  const anatOk = await win.webContents.executeJavaScript(`(function(){
    const s = activeCommands.find(c=>c.type==='ANATOMY');
    return JSON.stringify({ has: !!s, rect: s && [Math.round(s._anatRect.x),Math.round(s._anatRect.y),Math.round(s._anatRect.w),Math.round(s._anatRect.h)], stillLooping: animationFrameId !== null });
  })()`);
  console.log('ANATOMY_REGRESSION ' + anatOk);
  console.log('shots saved');
  app.exit(0);
});
