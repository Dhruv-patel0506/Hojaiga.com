const { app, BrowserWindow } = require('electron');
const fs = require('fs');
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1522, height: 754, show: true,
    webPreferences: { nodeIntegration: true, contextIsolation: false } });
  await win.loadFile('D:/new_automation/final hojaiga tutor/public/overlay.html');
  const notes = [];
  for (let i = 1; i <= 14; i++) notes.push({ type:'WRITE', x:700, y:150+i*40, label:'Step '+i+': substitute values into the equation and simplify carefully', color: i%3===0?'gray':'white' });
  const cmds = [
    { type:'BOX', x:160, y:300, w:150, h:90, label:'Force F' },
    ...notes,
    { type:'CIRCLE', x:300, y:430, r:42, label:'normal N' },
    { type:'CIRCLE', x:300, y:560, r:42, label:'ground' },
    { type:'PLOT', expr:'x^3 - 3*x', xMin:-4, xMax:4, x:130, y:180, w:420, h:330, color:'cyan' },
    { type:'SHAPE3D', shapeType:'cube', cx:430, cy:600, size:70, label:'block', color:'yellow' },
    { type:'BOARD', x:60, y:60, w:760, h:440, label:'Motion of a block on a horizontal surface' },
    { type:'PLOT', expr:'sine curve', xMin:-6, xMax:6, x:200, y:200, w:300, h:200 }
  ];
  await win.webContents.executeJavaScript(`window.ClickyOverlay.addCommands(${JSON.stringify(cmds)}, true); window.ClickyOverlay.setSubtitle('now watch the curve draw itself'); 'ok';`);
  await new Promise(r => setTimeout(r, 4800));
  const res = await win.webContents.executeJavaScript(`(function(){
    const rect = c => {
      if (c.type==='WRITE') return {n:'NOTE:'+c.label.slice(0,7), x:c.x, y:c.y, w:c.cardW, h:c.cardH, note:true};
      if (c.type==='BOX') return {n:'BOX', x:c.x, y:c.y, w:c.w, h:c.h};
      if (c.type==='PLOT') return {n:'PLOT:'+c.expr, x:c.x, y:c.y, w:c.w, h:c.h};
      if (c.type==='CIRCLE') return {n:'CIRCLE:'+c.label, x:c.x-c.r, y:c.y-c.r, w:c.r*2, h:c.r*2};
      if (c.type==='SHAPE3D') return {n:'SHAPE3D', x:c.cx-c.size-20, y:c.cy-c.size-20, w:c.size*2+40, h:c.size*2+40};
      return null;
    };
    const items = activeCommands.map(rect).filter(Boolean);
    const hit=(a,b)=>!(a.x+a.w<=b.x||b.x+b.w<=a.x||a.y+a.h<=b.y||b.y+b.h<=a.y);
    const overlaps=[];
    for (let i=0;i<items.length;i++) for (let j=i+1;j<items.length;j++)
      if (hit(items[i],items[j])) overlaps.push(items[i].n+' x '+items[j].n);
    const notesC = items.filter(i=>i.note);
    const shapes = items.filter(i=>!i.note);
    const noteShape=[];
    for (const a of notesC) for (const b of shapes) if (hit(a,b)) noteShape.push(a.n+' x '+b.n);
    const pills = activeCommands.filter(c=>c._pillRect).map(c=>c._pillRect);
    let pillOverlaps=0;
    for (let i=0;i<pills.length;i++) for (let j=i+1;j<pills.length;j++) if (hit(pills[i],pills[j])) pillOverlaps++;
    const notePill = [];
    for (const a of notesC) for (const b of pills) if (hit(a,b)) notePill.push(a.n);
    return JSON.stringify({
      vw:window.innerWidth, vh:window.innerHeight,
      totalItems: items.length, overlaps, noteShape,
      zoneViolations: notesC.filter(c=>c.x<540).map(c=>c.n),
      columns: [...new Set(notesC.map(c=>Math.round(c.x)))].sort((a,b)=>a-b),
      pills: pills.length, pillOverlaps, notePill,
      invalidPlotDropped: !activeCommands.some(c=>c.type==='PLOT'&&c.expr==='sine curve'),
      darkColorsFixed: activeCommands.filter(c=>c.type==='WRITE').every(c=>c.color==='#f8fafc'),
      voidActive: document.getElementById('infinite-void').classList.contains('active'),
      cubeSize: (activeCommands.find(c=>c.type==='SHAPE3D')||{}).size
    });
  })()`);
  console.log(res.replace(/\},/g,'},\n'));
  const img = await win.webContents.capturePage();
  fs.writeFileSync('C:/Users/dhruv/AppData/Local/Temp/opencode/overlay_shot6.png', img.toPNG());
  console.log('shot saved');

  // --- File 29 prompt bar: hidden at boot, shown on click-through-off IPC,
  //     submit -> overlay:submit-prompt then returns to click-through ---
  const { ipcMain } = require('electron');
  let submittedText = null;
  let clickThroughReply = null;
  ipcMain.handle('overlay:submit-prompt', async (_e, text) => { submittedText = text; return true; });
  ipcMain.on('overlay:set-click-through', (_e, v) => { clickThroughReply = v; });

  const bar0 = JSON.parse(await win.webContents.executeJavaScript(`(function(){
    const bar = document.getElementById('prompt-bar');
    return JSON.stringify({ exists: !!bar, hiddenAtBoot: !bar.classList.contains('interactive') });
  })()`));

  win.webContents.send('overlay:click-through-changed', false);
  await new Promise(r => setTimeout(r, 250));
  const bar1 = JSON.parse(await win.webContents.executeJavaScript(`(function(){
    const bar = document.getElementById('prompt-bar');
    const input = document.getElementById('prompt-input');
    return JSON.stringify({
      shown: bar.classList.contains('interactive'),
      pointerEvents: getComputedStyle(bar).pointerEvents,
      focused: document.activeElement === input
    });
  })()`));

  await win.webContents.executeJavaScript(`(function(){
    const bar = document.getElementById('prompt-bar');
    const input = document.getElementById('prompt-input');
    input.value = 'teach me gravity with a diagram';
    bar.dispatchEvent(new Event('submit'));
    return 'submitted';
  })()`);
  await new Promise(r => setTimeout(r, 400));

  win.webContents.send('overlay:click-through-changed', true);
  await new Promise(r => setTimeout(r, 250));
  const bar2 = JSON.parse(await win.webContents.executeJavaScript(`(function(){
    const bar = document.getElementById('prompt-bar');
    const input = document.getElementById('prompt-input');
    return JSON.stringify({
      hiddenAgain: !bar.classList.contains('interactive'),
      inputCleared: input.value === ''
    });
  })()`));

  console.log('PROMPTBAR ' + JSON.stringify({
    bootHidden: bar0.exists && bar0.hiddenAtBoot,
    interactiveShown: bar1.shown && bar1.pointerEvents === 'auto' && bar1.focused,
    submitForwarded: submittedText === 'teach me gravity with a diagram',
    clickThroughReturned: clickThroughReply === true,
    hiddenAfter: bar2.hiddenAgain && bar2.inputCleared
  }));

  app.exit(0);
});
