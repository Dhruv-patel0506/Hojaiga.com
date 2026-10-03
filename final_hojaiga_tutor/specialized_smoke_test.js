const { app, BrowserWindow } = require('electron');
const fs = require('fs');
app.whenReady().then(async () => {
  const cm = require('D:/new_automation/final hojaiga tutor/dist/CompanionManager.js');
  const scanner = require('D:/new_automation/final hojaiga tutor/dist/DynamicAppScannerAndTeacher.js');
  const safetyMod = require('D:/new_automation/final hojaiga tutor/dist/WorkspaceSafetyManager.js');
  const sandboxMod = require('D:/new_automation/final hojaiga tutor/dist/SandboxTestExecutor.js');
  const repairMod = require('D:/new_automation/final hojaiga tutor/dist/AutoRepairLoopEngine.js');
  const bridgeMod = require('D:/new_automation/final hojaiga tutor/dist/HojaigaIntegrationBridge.js');
  const hwMod = require('D:/new_automation/final hojaiga tutor/dist/HomeworkSocraticTutor.js');
  const ugcMod = require('D:/new_automation/final hojaiga tutor/dist/UGCContentEngine.js');
  const ghostMod = require('D:/new_automation/final hojaiga tutor/dist/GhostwritingEngine.js');
  const videoMod = require('D:/new_automation/final hojaiga tutor/dist/ProVideoEditorDirector.js');
  const cyberMod = require('D:/new_automation/final hojaiga tutor/dist/CyberDefenseTutorEngine.js');
  const r = {};

  // --- detection predicates (no cross-collisions) ---
  r.detect = {
    cyber: cyberMod.CyberDefenseTutorEngine.isSecurityConceptPrompt('explain how a firewall and tls encryption protect a network'),
    cyberNeg: cyberMod.CyberDefenseTutorEngine.isSecurityConceptPrompt('teach me quadratic formula'),
    hw: hwMod.HomeworkSocraticTutor.isHomeworkPrompt('help me solve this homework problem 3'),
    ugc: ugcMod.UGCContentEngine.isUGCPrompt('write a tiktok ugc script for my skincare product'),
    ghost: ghostMod.GhostwritingEngine.isGhostwritePrompt('ghostwrite a twitter thread about startups'),
    video: videoMod.ProVideoEditorDirector.isVideoEditPrompt('teach me premiere color grading'),
    videoNeg: videoMod.ProVideoEditorDirector.isVideoEditPrompt('explain how a firewall works'),
    nle: videoMod.detectNle('davinci resolve color grading'),
  };

  // --- routeSpecializedEngines: IN-PLACE merge, model commands preserved ---
  const cyberCmds = [{ type: 'WRITE', x: 700, y: 200, label: 'model note kept', color: 'white' }];
  const cyberRef = await cm.routeSpecializedEngines('explain how a firewall and tls encryption protect a network', cyberCmds, true);
  r.cyberRouted = cyberRef === true;
  r.cyberInPlace = cyberCmds.length > 1 && cyberCmds.some(c => c.type === 'GRAPH') && cyberCmds.some(c => c.label === 'model note kept');
  r.cyberBoard = cyberCmds.some(c => c.type === 'BOARD');
  const before = cyberCmds.length;
  await cm.routeSpecializedEngines('explain how a firewall and tls encryption protect a network', cyberCmds, false);
  r.cyberIdempotent = cyberCmds.length === before;

  const hwCmds = [{ type: 'WRITE', label: 'model note', color: 'white' }];
  await cm.routeSpecializedEngines('help me solve this homework problem 3', hwCmds, true);
  r.hwGraph = hwCmds.some(c => c.type === 'GRAPH') && hwCmds.some(c => c.label === 'model note');

  const ugcCmds = [];
  await cm.routeSpecializedEngines('write a tiktok ugc script for my skincare product', ugcCmds, true);
  r.ugcActor = ugcCmds.some(c => c.type === 'ACTOR') && ugcCmds.some(c => /HOOK/.test(c.label || ''));

  const ghostCmds = [];
  await cm.routeSpecializedEngines('ghostwrite a twitter thread about startups', ghostCmds, true);
  r.ghostGraph = ghostCmds.some(c => c.type === 'GRAPH') && ghostCmds.some(c => /Edit/.test(c.label || ''));

  const videoCmds = [];
  const vStart = Date.now();
  await cm.routeSpecializedEngines('teach me premiere color grading', videoCmds, true);
  r.videoMs = Date.now() - vStart;
  r.videoDj = videoCmds.some(c => c.type === 'DJ') && videoCmds.some(c => /Ctrl\+M/.test(c.label || ''));

  const appCmds = [];
  await cm.routeSpecializedEngines('How do i use Notepad', appCmds, true);
  r.appScan = appCmds.length > 0 && appCmds.every(c => ['BOARD', 'UIRECT', 'WRITE'].includes(c.type));
  r.appUiRectOrFallback = appCmds.some(c => c.type === 'UIRECT') || appCmds.some(c => c.type === 'WRITE');
  const walkSort = [{ type: 'WRITE', label: 'model note', color: 'white' }];
  const walkSortRouted = await cm.routeSpecializedEngines('walk me through bubble sort', walkSort, true);
  r.walkSortNotRouted = walkSortRouted === false && walkSort.length === 1;
  const walkApp = [];
  const walkAppRouted = await cm.routeSpecializedEngines('walk me through the app', walkApp, true);
  r.walkAppRouted = walkAppRouted === true && walkApp.length > 0;

  const noneCmds = [{ type: 'WRITE', label: 'plain' }];
  const noneRouted = await cm.routeSpecializedEngines('teach me the quadratic formula', noneCmds, true);
  r.noFalseMatch = noneRouted === false && noneCmds.length === 1;

  // --- File 2: WorkspaceSafetyManager ---
  const safe = new safetyMod.WorkspaceSafetyManager();
  r.blockRm = safe.validateCommand('rm -rf C:\\Windows').allowed === false;
  r.allowNode = safe.validateCommand('node test.js').allowed === true;
  r.unknownApproval = safe.validateCommand('curl http://evil').allowed === false;
  r.pathIn = safe.isPathInsideWorkspace('D:\\new_automation\\final hojaiga tutor\\src\\a.ts') === true;
  r.pathOut = safe.isPathInsideWorkspace('C:\\Users\\dhruv\\evil.js') === false;
  const req = safe.queueApproval('FILE_WRITE', 'D:\\new_automation\\x.ts', 'test');
  r.approval = safe.getPendingApprovals().length === 1 && safe.resolveApproval(req.id, true) === true && safe.getPendingApprovals().length === 0;

  // --- File 3: SandboxTestExecutor ---
  const sbx = new sandboxMod.SandboxTestExecutor(safe);
  const run1 = await sbx.runCodeInSandbox('console.log(40+2)', 'node');
  r.sbxOut = run1.stdout.trim();
  r.sbxOk = run1.succeeded === true && r.sbxOut === '42';
  const run2 = await sbx.runCodeInSandbox('process.exit(3)', 'node');
  r.sbxExit = run2.succeeded === false && run2.exitCode === 3;
  const sbxCmds = sbx.buildSandboxOverlay(run1, 'Demo Run');
  r.sbxOverlay = sbxCmds.length >= 2 && sbxCmds[0].type === 'BOARD';

  // --- File 4: AutoRepairLoopEngine (corrupted regex must be fixed) ---
  const fix = repairMod.AutoRepairLoopEngine.applyDeterministicSyntaxFix('console.log(2+2');
  r.repairFixed = fix.fixedCode === 'console.log(2+2)';
  r.repairSummary = fix.summary.includes('Auto-fixed');
  const loop = await repairMod.AutoRepairLoopEngine.runAutoRepairLoop('console.log(2+2', 'node', sbx);
  r.repairRun = loop.run.succeeded === true && loop.run.stdout.trim() === '4';
  r.repairCmds = loop.commands.length >= 2;

  // --- File 5: HojaigaIntegrationBridge (temp registry, wiped per run) ---
  const regPath = 'C:/Users/dhruv/AppData/Local/Temp/opencode/hojaiga_registry_test.json';
  try { fs.unlinkSync(regPath); } catch {}
  const bridge = new bridgeMod.HojaigaIntegrationBridge(regPath);
  const cap = bridge.registerCapability({ name: 'Aim Trainer', engine: 'GamingAimAndSensEngine', description: 'Aim drills' });
  const sched = bridge.scheduleLesson('TLS basics', '0 9 * * 1', Date.now() + 3600000);
  r.bridgeCaps = bridge.listCapabilities().length === 1 && cap.id.startsWith('cap_');
  r.bridgeSched = bridge.getDueSchedules().length === 0 && bridge.reschedule(sched.id, Date.now() - 1000) && bridge.getDueSchedules().length === 1;
  r.bridgeDesc = bridge.describeAsCommands()[0].type === 'BOARD';

  // --- File 11: InterviewCoachEngine ---
  const iv = require('D:/new_automation/final hojaiga tutor/dist/InterviewCoachEngine.js');
  r.ivDetect = iv.InterviewCoachEngine.isInterviewPrompt('run a mock interview, system design round') === true;
  const ivCmds = [];
  await cm.routeSpecializedEngines('run a mock interview for a system design round', ivCmds, true);
  r.ivRouted = ivCmds.some(c => c.type === 'GRAPH') && ivCmds.some(c => c.type === 'BOARD');
  r.ivNoFakeTelemetry = !ivCmds.some(c => /Speech Telemetry/.test(c.label || ''));
  const ivTelCmds = [];
  await cm.routeSpecializedEngines('mock interview: um so i would basically load balance um the queue and like scale horizontally after that', ivTelCmds, true);
  r.ivTelCard = ivTelCmds.some(c => /Speech Telemetry/.test(c.label || ''));
  const negCmds = [];
  await cm.routeSpecializedEngines('help me negotiate a salary counter offer', negCmds, true);
  r.ivNeg = negCmds.some(c => /Counter-Offer/.test(c.label || ''));
  const tel = iv.InterviewCoachEngine.analyzeSpeechTranscript('um so i would basically load balance um the queue and like scale horizontally', 45);
  r.telOk = tel.fillerCount >= 4 && tel.clarityScore < 100 && tel.pacingWpm > 0;

  // --- File 12: LiveScreenTranslator ---
  const tr = require('D:/new_automation/final hojaiga tutor/dist/LiveScreenTranslator.js');
  r.trDetect = tr.LiveScreenTranslator.isTranslationPrompt('translate this app to spanish') === true;
  r.trNoBareLang = tr.LiveScreenTranslator.isTranslationPrompt('teach me thermodynamics in hindi') === false;
  r.trDubThis = tr.LiveScreenTranslator.isTranslationPrompt('dub this') === true;
  r.trLang = tr.LiveScreenTranslator.detectTargetLanguage('dub this in japanese') === 'japanese';
  r.trLabel = tr.LiveScreenTranslator.translateLabel('File', 'hindi').indexOf('फ़ाइल') >= 0;
  const trCmds = [];
  await cm.routeSpecializedEngines('translate this screen to spanish', trCmds, true);
  r.trRouted = trCmds.some(c => c.type === 'BOARD');
  r.trUsesUiRect = !trCmds.some(c => c.type === 'BOX') && trCmds.some(c => c.type === 'UIRECT');

  // --- File 13: ChartPatternTutor ---
  const ch = require('D:/new_automation/final hojaiga tutor/dist/ChartPatternTutor.js');
  const fib = ch.ChartPatternTutor.calculateFibonacciLevels(25200, 24400);
  r.fibOk = Math.abs(fib.level500 - 24800) < 0.01 && Math.abs(fib.level618 - 24705.6) < 0.01 && Math.abs(fib.level382 - 24894.4) < 0.01;
  const chCmds = [];
  await cm.routeSpecializedEngines('candlestick breakout fibonacci support and resistance 25200 24400', chCmds, true);
  r.chartRouted = chCmds.some(c => /Golden Pocket/.test(c.label || '')) && chCmds.some(c => c.type === 'WRITE');
  r.chartBoard = /24400/.test((chCmds.find(c => c.type === 'BOARD') || {}).label || '');

  // --- File 14: HardwareSchematicTutor ---
  const hwS = require('D:/new_automation/final hojaiga tutor/dist/HardwareSchematicTutor.js');
  r.hwPcbDetect = hwS.HardwareSchematicTutor.isHardwareOrCADPrompt('check this pcb schematic for i2c pullups') === true;
  r.hwCadDetect = hwS.HardwareSchematicTutor.isHardwareOrCADPrompt('blender quad topology bevel workflow') === true;
  const pcbCmds = [];
  await cm.routeSpecializedEngines('check this pcb schematic for i2c pullups', pcbCmds, true);
  r.pcbRouted = pcbCmds.some(c => /Signal Integrity/.test(c.label || '')) && pcbCmds.some(c => c.type === 'GRAPH');
  const cadCmds = [];
  await cm.routeSpecializedEngines('blender quad topology and bevel modifiers', cadCmds, true);
  r.cadRouted = cadCmds.some(c => /CAD/.test(c.label || ''));

  // --- File 15: MemoryPalaceEngine (temp deck for math, root deck via router) ---
  try { fs.unlinkSync('C:/Users/dhruv/AppData/Local/Temp/opencode/memory_palace_deck.json'); } catch {}
  try { fs.unlinkSync('D:/new_automation/final hojaiga tutor/memory_palace_deck.json'); } catch {}
  try { fs.unlinkSync('D:/new_automation/final hojaiga tutor/hojaiga_registry.json'); } catch {}
  const mpMod = require('D:/new_automation/final hojaiga tutor/dist/MemoryPalaceEngine.js');
  r.mpDetect = mpMod.MemoryPalaceEngine.isMemoryPalacePrompt('build a memory palace for thermodynamics') === true;
  const mpTemp = new mpMod.MemoryPalaceEngine('C:/Users/dhruv/AppData/Local/Temp/opencode');
  const cards = mpTemp.createSpatialLociForTopic('french revolution dates');
  r.mpCards = cards.length === 4 && mpTemp.cardCount === 4;
  const dupCards = mpTemp.createSpatialLociForTopic('french revolution dates');
  r.mpDedup = dupCards.length === 4 && mpTemp.cardCount === 4;
  const g1 = mpTemp.recordSM2Review(cards[0].id, 5);
  r.mpSm2Pass1 = g1.intervalDays === 6;
  const g2 = mpTemp.recordSM2Review(cards[0].id, 5);
  r.mpSm2Pass2 = g2.intervalDays === 16 && g2.easeFactor > 2.5;
  const g3 = mpTemp.recordSM2Review(cards[1].id, 1);
  r.mpSm2Fail = g3.intervalDays === 1 && g3.easeFactor < 2.5 && g3.easeFactor >= 1.3;
  const mpCmds = [];
  await cm.routeSpecializedEngines('build a memory palace for french revolution dates', mpCmds, true);
  r.mpRouted = mpCmds.some(c => c.type === 'GRAPH') && mpCmds.filter(c => c.type === 'WRITE').length >= 4;

  // --- File 16: PolyglotVisualArchitectCoder ---
  const pc = require('D:/new_automation/final hojaiga tutor/dist/PolyglotVisualArchitectCoder.js');
  r.pgDetect = pc.PolyglotVisualArchitectCoder.isCodingIntentPrompt('build a function in python for this payload') === true;
  r.pgLangRust = pc.PolyglotVisualArchitectCoder.detectLanguage('write this in rust') === 'rust';
  r.pgLangJava = pc.PolyglotVisualArchitectCoder.detectLanguage('build a function in java') === 'java';
  r.pgLangJs = pc.PolyglotVisualArchitectCoder.detectLanguage('code this in javascript now') === 'javascript';
  const pgCmds = [];
  await cm.routeSpecializedEngines('build a function in python that filters empty payload items', pgCmds, true);
  r.pgRouted = pgCmds.some(c => /Polyglot Visual Architect \[PYTHON\]/.test(c.label || '')) && pgCmds.some(c => c.type === 'GRAPH');
  r.pgSandbox = pgCmds.some(c => /VERIFIED PASS/.test(c.label || ''));
  const pgJs = [];
  await cm.routeSpecializedEngines('code this in javascript a guarded intent handler', pgJs, true);
  r.pgJs = pgJs.some(c => /VERIFIED PASS/.test(c.label || ''));
  const pgTs = [];
  await cm.routeSpecializedEngines('write code in typescript a rate limiter function', pgTs, true);
  r.pgTs = pgTs.some(c => /VERIFIED PASS/.test(c.label || ''));

  // --- File 17: LiveIDEPairProgrammer ---
  const ip = require('D:/new_automation/final hojaiga tutor/dist/LiveIDEPairProgrammer.js');
  r.ideDetect = ip.LiveIDEPairProgrammer.isIDEPairPrompt('i am stuck with async fetch in vscode') === true;
  r.ideCat = ip.LiveIDEPairProgrammer.classifyStuckPoint('my await promise keeps failing') === 'ASYNC_FLOW';
  const ideCmds = [];
  await cm.routeSpecializedEngines('i am stuck with this async fetch flow, pair program with me', ideCmds, true);
  r.ideRouted = ideCmds.some(c => /Pair Programmer/.test(c.label || '')) && ideCmds.some(c => c.type === 'GRAPH');
  r.ideNoBox = !ideCmds.some(c => c.type === 'BOX');

  // --- File 20: BugRootCauseAutopsyEngine ---
  const ba = require('D:/new_automation/final hojaiga tutor/dist/BugRootCauseAutopsyEngine.js');
  r.bugDetect = ba.BugRootCauseAutopsyEngine.isBugAutopsyPrompt('why is this failing with typeerror') === true;
  const bugCmds = [];
  await cm.routeSpecializedEngines('typeerror cannot read property of undefined, why is this failing', bugCmds, true);
  r.bugRouted = bugCmds.some(c => /Null \/ Undefined/.test(c.label || '')) && bugCmds.some(c => /WHY IT BROKE/.test(c.label || ''));

  // --- File 18: VisualAlgorithmStepDebugger ---
  const vd = require('D:/new_automation/final hojaiga tutor/dist/VisualAlgorithmStepDebugger.js');
  r.algoDetect = vd.VisualAlgorithmStepDebugger.isAlgorithmTracePrompt('dry run this sliding window two pointer') === true;
  const algoCmds = [];
  await cm.routeSpecializedEngines('step through and trace this sliding window, big o analysis please', algoCmds, true);
  r.algoRouted = algoCmds.some(c => /State Transition Trace/.test(c.label || '')) &&
    algoCmds.filter(c => c.type === 'WRITE').length >= 5 &&
    algoCmds.some(c => /Complexity Proof/.test(c.label || ''));

  // --- File 19: FullStackScaffoldAndVerifyEngine ---
  const fsEng = require('D:/new_automation/final hojaiga tutor/dist/FullStackScaffoldAndVerifyEngine.js');
  r.fsDetect = fsEng.FullStackScaffoldAndVerifyEngine.isArchitectureScaffoldPrompt('scaffold a multi-file microservice for OrderService') === true;
  try { fs.rmSync('C:/Users/dhruv/AppData/Local/Temp/opencode/scaffold_ws', { recursive: true, force: true }); } catch {}
  const fsInst = new fsEng.FullStackScaffoldAndVerifyEngine(new safetyMod.WorkspaceSafetyManager('C:/Users/dhruv/AppData/Local/Temp/opencode/scaffold_ws'));
  const plan = fsInst.planVerifiedFeatureArchitecture('Order');
  r.fsPlan = plan.length === 4 && plan.every(f => f.relativePath.indexOf('src/generated/') === 0);
  const wr = fsInst.writeVerifiedScaffoldToDisk('C:/Users/dhruv/AppData/Local/Temp/opencode/scaffold_ws', plan);
  r.fsWrite = wr.writtenFiles.length === 4 && wr.blockedFiles.length === 0;
  const br = fsInst.writeVerifiedScaffoldToDisk('C:/Users/dhruv', [{ relativePath: 'evil.ts', layer: 'TYPES', responsibility: '', codeContent: 'x' }]);
  r.fsBlocked = br.blockedFiles.length === 1;
  const fsCmds = [];
  await cm.routeSpecializedEngines('scaffold a multi-file microservice for OrderService', fsCmds, true);
  r.fsRouted = fsCmds.some(c => /Full-Stack Visual Architect/.test(c.label || '')) && fsCmds.filter(c => c.type === 'WRITE').length >= 4;

  // --- Files 21-25: SQL / Git / Regex / API latency / UI-UX critic ---
  const sqlMod = require('D:/new_automation/final hojaiga tutor/dist/SQLQueryPlanAndSchemaVisualizer.js');
  r.sqlDetect = sqlMod.SQLQueryPlanAndSchemaVisualizer.isSQLVisualizerPrompt('optimize query plan and b-tree index for postgres orders') === true;
  const sqlRep = sqlMod.SQLQueryPlanAndSchemaVisualizer.verifyAndOptimizeSQL('delete from stale orders');
  r.sqlDestructive = sqlRep.hasDestructiveUnboundedMutation === true && sqlRep.verificationWarnings.some(w => /CRITICAL/.test(w));
  const sqlRep2 = sqlMod.SQLQueryPlanAndSchemaVisualizer.verifyAndOptimizeSQL('select * from orders like "%active"');
  r.sqlSelectStar = sqlRep2.verificationWarnings.length >= 2 && sqlRep2.hasDestructiveUnboundedMutation === false;
  const sqlCmds = [];
  await cm.routeSpecializedEngines('optimize query plan and b-tree index for postgres orders', sqlCmds, true);
  r.sqlRouted = sqlCmds.some(c => /Visual SQL Architect/.test(c.label || '')) && sqlCmds.some(c => c.type === 'GRAPH') && sqlCmds.some(c => c.type === 'BOARD');

  const gitMod = require('D:/new_automation/final hojaiga tutor/dist/GitTimeMachineAndConflictResolver.js');
  r.gitDetect = gitMod.GitTimeMachineAndConflictResolver.isGitPrompt('help me resolve a git rebase merge conflict safely') === true;
  r.gitDetectNeg = gitMod.GitTimeMachineAndConflictResolver.isGitPrompt('teach me quadratic formula') === false;
  const gitState = await gitMod.GitTimeMachineAndConflictResolver.inspectWorkspaceGitState('D:/new_automation/final hojaiga tutor');
  r.gitInspect = typeof gitState.branchName === 'string' && gitState.branchName.length > 0 && typeof gitState.dirtyFilesCount === 'number' && Array.isArray(gitState.conflictedFiles);
  const gitCmds = [];
  await cm.routeSpecializedEngines('resolve this merge conflict in git rebase', gitCmds, true);
  r.gitRouted = gitCmds.some(c => /Git Time-Machine/.test(c.label || '')) && gitCmds.some(c => c.type === 'GRAPH') && gitCmds.some(c => /stash push/.test(c.label || ''));

  const rxMod = require('D:/new_automation/final hojaiga tutor/dist/RegexAndParserVisualWorkbench.js');
  r.rxDetect = rxMod.RegexAndParserVisualWorkbench.isRegexPrompt('build a regex pattern to extract email addresses') === true;
  const rxEmail = rxMod.RegexAndParserVisualWorkbench.synthesizeAndVerifyPattern('extract email addresses');
  r.rxEmail = rxEmail.isReDoSSafe === true && rxEmail.matchedSamples.length === 2 && rxEmail.rejectedSamples.length === 2;
  const rxUrl = rxMod.RegexAndParserVisualWorkbench.synthesizeAndVerifyPattern('extract url from text');
  r.rxUrl = rxUrl.patternSource.includes('https') && rxUrl.matchedSamples.length === 2 && rxUrl.rejectedSamples.length === 2;
  const rxVer = rxMod.RegexAndParserVisualWorkbench.synthesizeAndVerifyPattern('semver version matching');
  r.rxVer = rxVer.patternSource.includes('major') && rxVer.matchedSamples.length === 2 && rxVer.rejectedSamples.length === 2;
  const rxCmds = [];
  await cm.routeSpecializedEngines('build a regex pattern to extract email addresses', rxCmds, true);
  r.rxRouted = rxCmds.some(c => /Regex & Parser Visual Workbench/.test(c.label || '')) && rxCmds.some(c => c.type === 'GRAPH');

  const apiMod = require('D:/new_automation/final hojaiga tutor/dist/APILoadAndLatencySimulator.js');
  r.apiDetect = apiMod.APILoadAndLatencySimulator.isLoadSimulatorPrompt('benchmark api p95 latency on http://127.0.0.1:3000/health') === true;
  r.apiRateNarrow = apiMod.APILoadAndLatencySimulator.isLoadSimulatorPrompt('write code for a rate limiter function') === false;
  r.apiLocalhostGuard = apiMod.APILoadAndLatencySimulator.isSafeLocalhostUrl('http://127.0.0.1:3000/x') === true &&
    apiMod.APILoadAndLatencySimulator.isSafeLocalhostUrl('http://example.com') === false;
  let apiThrew = false;
  try { await apiMod.APILoadAndLatencySimulator.measureLocalEndpoint('http://example.com', 2); } catch { apiThrew = true; }
  r.apiExternalBlocked = apiThrew;
  const apiTel = await apiMod.APILoadAndLatencySimulator.measureLocalEndpoint('http://127.0.0.1:3000/health', 4);
  r.apiPercentiles = apiTel.samplesCount === 4 && apiTel.p50Ms >= 2 && apiTel.p99Ms >= apiTel.p50Ms && apiTel.bottleneckDiagnosis.length > 10;
  const apiCmds = [];
  await cm.routeSpecializedEngines('benchmark api p95 latency on http://127.0.0.1:3000/health', apiCmds, true);
  r.apiRouted = apiCmds.some(c => /API Latency/.test(c.label || '')) && apiCmds.some(c => c.type === 'GRAPH');
  const rateCmds = [];
  await cm.routeSpecializedEngines('write code for a rate limiter function', rateCmds, true);
  r.apiRateGoesToPolyglot = rateCmds.some(c => /Polyglot Visual Architect/.test(c.label || ''));

  const uxMod = require('D:/new_automation/final hojaiga tutor/dist/UIUXAccessibilityAndDesignCritic.js');
  r.uxDetect = uxMod.UIUXAccessibilityAndDesignCritic.isUIUXCriticPrompt('run a wcag contrast ratio and tailwind ui audit') === true;
  const uxRatio = uxMod.UIUXAccessibilityAndDesignCritic.computeHexContrastRatio('#38BDF8', '#0F172A');
  r.uxRatio = uxRatio > 4.5 && uxRatio < 12;
  const uxCmds = [];
  await cm.routeSpecializedEngines('run a wcag contrast ratio and tailwind ui audit #38BDF8 #0F172A', uxCmds, true);
  r.uxRouted = uxCmds.some(c => /WCAG Critic/.test(c.label || '')) && uxCmds.filter(c => c.type === 'WRITE').length >= 3 && uxCmds.some(c => c.type === 'BOARD');
  r.uxUiRectOnly = !uxCmds.some(c => c.type === 'BOX') && uxCmds.filter(c => c.type === 'UIRECT').every(c => c.x >= 0 && c.y >= 0 && c.w > 0 && c.h > 0);
  const uxRatioCard = uxCmds.find(c => /WCAG 2.1 VERIFICATION/.test(c.label || ''));
  r.uxRatioCard = !!uxRatioCard && uxRatioCard.label.includes(uxRatio + ':1');

  // --- full lesson integration: inject once, model commands survive ---
  const steps = [];
  await cm.executeSynchronizedLesson(
    '[STEP]firewalls filter traffic[WRITE:700,200:Step 1: default deny][BOX:100,100,50,40:crude][/STEP][STEP]now tls handshakes[WRITE:700,300:Step 2: encrypt][/STEP]',
    (cmds) => { steps.push(cmds.map(c => c.type).join(',')); },
    async () => {},
    undefined,
    'explain how a firewall and tls encryption protect a network'
  );
  r.lessonStep0 = steps[0];
  r.lessonStep1 = steps[1];
  r.lessonOnce = (steps[0].match(/GRAPH/g) || []).length === 1 && !steps[1].includes('GRAPH');
  r.lessonModelKept = steps[0].includes('WRITE');

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

  // ================= overlay render: cyber GRAPH + absolute UIRECT =========
  const win = new BrowserWindow({ width: 1522, height: 754, show: true,
    webPreferences: { nodeIntegration: true, contextIsolation: false } });
  await win.loadFile('D:/new_automation/final hojaiga tutor/public/overlay.html');
  const cmds2 = [
    { type: 'BOARD', label: 'Cyber Defense (Blue Team) • TLS Handshake / Encryption' },
    { type: 'GRAPH', showLegend: true, color: 'cyan',
      nodes: [
        { id: 'client', label: 'ClientHello', color: 'cyan' },
        { id: 'server', label: 'ServerHello + Cert', color: 'green' },
        { id: 'keys', label: 'Key Exchange', color: 'yellow' },
        { id: 'session', label: 'Encrypted Session', color: 'orange' },
      ],
      edges: [
        { from: 'client', to: 'server', label: 'offer suites', color: 'cyan' },
        { from: 'server', to: 'keys', label: 'certificate', color: 'green' },
        { from: 'keys', to: 'session', label: 'session keys', color: 'yellow' },
      ],
      nodePositions: {} },
    { type: 'WRITE', x: 700, y: 150, label: 'Step 1: TLS: authenticate, derive session keys, encrypt.', color: 'green' },
    { type: 'WRITE', x: 700, y: 330, label: 'Step 2: attack view vs defense view at each hop.', color: 'cyan' },
    { type: 'UIRECT', x: 120, y: 220, w: 160, h: 44, label: 'Step 3: Click "New Document" [Button]', color: 'cyan' },
    { type: 'UIRECT', x: 900, y: 470, w: 150, h: 60, label: 'Step 4: right-side control [Slider]', color: 'yellow' },
  ];
  await win.webContents.executeJavaScript(`window.ClickyOverlay.addCommands(${JSON.stringify(cmds2)}, true); window.ClickyOverlay.setSubtitle('specialized engines'); 'ok';`);
  await new Promise(res => setTimeout(res, 4600));
  const late = await win.webContents.executeJavaScript(`(function(){
    const g = activeCommands.find(c=>c.type==='GRAPH');
    const ui = activeCommands.filter(c=>c.type==='UIRECT');
    const notesC = activeCommands.filter(c=>c.type==='WRITE');
    const hit=(x,y)=>!(x.x+x.w<=y.x||y.x+y.w<=x.x||x.y+x.h<=y.y||y.y+y.h<=x.y);
    const gr = g && g._gRect;
    return JSON.stringify({
      graphRect: gr ? [Math.round(gr.x),Math.round(gr.y),Math.round(gr.w),Math.round(gr.h)] : null,
      graphNoteOverlaps: gr ? notesC.filter(n=>hit({x:n.x,y:n.y,w:n.cardW,h:n.cardH}, gr)).length : -1,
      zoneViolations: notesC.filter(n=>n.x<540).length,
      uirect1: ui[0] ? [Math.round(ui[0].x),Math.round(ui[0].y),Math.round(ui[0].w),Math.round(ui[0].h)] : null,
      uirect2: ui[1] ? [Math.round(ui[1].x),Math.round(ui[1].y)] : null,
      uiPills: ui.filter(c=>c._pillRect).length,
      nodeKeys: g ? Object.keys(g.nodePositions).join(',') : null,
      stillLooping: animationFrameId !== null
    });
  })()`);
  console.log('LATE ' + late);
  const img = await win.webContents.capturePage();
  fs.writeFileSync('C:/Users/dhruv/AppData/Local/Temp/opencode/overlay_specialized.png', img.toPNG());
  console.log('shot saved');
  // cleanup test-generated app data so the workspace stays pristine
  try { fs.unlinkSync('D:/new_automation/final hojaiga tutor/memory_palace_deck.json'); } catch {}
  try { fs.unlinkSync('D:/new_automation/final hojaiga tutor/hojaiga_registry.json'); } catch {}
  try { fs.unlinkSync('C:/Users/dhruv/AppData/Local/Temp/opencode/memory_palace_deck.json'); } catch {}
  try { fs.rmSync('C:/Users/dhruv/AppData/Local/Temp/opencode/scaffold_ws', { recursive: true, force: true }); } catch {}
  app.exit(0);
});
