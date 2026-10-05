const { app } = require('electron');
app.whenReady().then(async () => {
  const cm = require('D:/new_automation/final hojaiga tutor/dist/CompanionManager.js');
  const perStep = [];
  await cm.executeSynchronizedLesson(
    '[STEP]this is about a swinging pendulum, here are notes[WRITE:700,200:Step 1: pendulum basics][/STEP][STEP]the period depends on length[WRITE:700,300:Step 2: T = 2pi sqrt(L/g)][/STEP]',
    (cmds) => { perStep.push(cmds.map(x => x.type + (x.preset ? ':' + x.preset : '')).join(',')); },
    async () => {},
    undefined,
    'explain a pendulum swinging back and forth'
  );
  // also: model DID emit an animate tag itself -> no duplicate injection
  const perStep2 = [];
  await cm.executeSynchronizedLesson(
    '[STEP]watch this wheel[ANIMATE:wheel:110,310->460,310:54:Rolling Wheel:cyan][/STEP][STEP]now the notes[WRITE:700,300:note][/STEP]',
    (cmds) => { perStep2.push(cmds.map(x => x.type + (x.preset ? ':' + x.preset : '')).join(',')); },
    async () => {},
    undefined,
    'show a wheel rolling'
  );
  console.log(JSON.stringify({ stepInjected: perStep, modelTagNoDupe: perStep2 }, null, 1));
  app.exit(0);
});
