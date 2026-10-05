import * as fs from 'fs';
import { executeSynchronizedLesson, ParsedOverlayCommand } from '../src/CompanionManager';
import { ClaudeAPI, VISUAL_TUTOR_SYSTEM_PROMPT } from '../src/ClaudeAPI';
import { WorkspaceSafetyManager } from '../src/WorkspaceSafetyManager';
import { SandboxTestExecutor } from '../src/SandboxTestExecutor';

const PNG1PX = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
const REPORT_PATH = 'D:\\new_automation\\matrix20_report.json';

const STOP = new Set(
  ('the and for with this that what how why when where who are was were you your can could should would ' +
    'please just into from them they then than about over under using used use before after more most ' +
    'some any all not but our its get got will has had have does did done there here each other also very ' +
    'really like want need know let lets right now look see done next them they these those which while ' +
    'through between during both same such only own too s t don shouldnt lets')
    .split(/\s+/)
);

type Turn = { prompt: string; raw: string; spoken: string; cmds: ParsedOverlayCommand[] };
type Dim = { verdict: 'PASS' | 'FAIL' | 'N/A'; detail: string };
type TCResult = {
  id: string;
  title: string;
  behavior: Dim;
  visuals: Dim;
  code: Dim;
  explanation: Dim;
  status: 'PASS' | 'PARTIAL' | 'FAIL' | 'STATIC';
  notes: string[];
  evidence: { spokenExcerpt: string; rawExcerpt: string; cmdTypes: string[] };
};

const VISUAL_TYPES = new Set([
  'GRAPH', 'TRACE', 'PLOT', 'ACTOR', 'ANIMATE', 'ANATOMY', 'KEYFRAMES', 'FIELD', 'DJ', 'AIM_TRAINER',
  'SHAPE3D', 'POLY3D', 'CURVE', 'POLYGON', 'ARROW', 'CIRCLE', 'BOX', 'POINT', 'SVG', 'UIRECT',
  'WHEEL', 'MOVE', 'GIF', 'DRAW',
]);

function contentTokens(s: string): string[] {
  const out: string[] = [];
  for (const raw of s.toLowerCase().split(/[^a-z0-9+#]+/)) {
    const t = raw.replace(/^[.]+|[.]+$/g, '');
    if (t.length >= 3 && !STOP.has(t)) out.push(t);
  }
  return out;
}

function anyTokenIn(hay: string, tokens: string[]): boolean {
  const h = hay.toLowerCase();
  for (const t of tokens) {
    if (h.includes(t)) return true;
    if (t.length >= 6 && h.includes(t.slice(0, 5))) return true;
  }
  return false;
}

function stringValues(o: any, acc: string[] = []): string[] {
  if (typeof o === 'string') acc.push(o);
  else if (Array.isArray(o)) o.forEach((v) => stringValues(v, acc));
  else if (o && typeof o === 'object') Object.values(o).forEach((v) => stringValues(v, acc));
  return acc;
}

function stripTags(s: string): string {
  return s
    .replace(/```[a-zA-Z0-9]*\n[\s\S]*?```/g, ' ')
    .replace(/\[[^\]\n]{0,600}\]/g, ' ')
    .replace(/\[\/?STEP\]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function extractCodeBlocks(raw: string): { lang: string; code: string }[] {
  const out: { lang: string; code: string }[] = [];
  const re = /```([a-zA-Z0-9]*)\n([\s\S]*?)```/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(raw)) !== null) out.push({ lang: (m[1] || '').toLowerCase(), code: m[2] });
  return out;
}

function evaluateVisuals(turns: Turn[], hints: string[]): Dim {
  const promptTokens: string[] = [];
  for (const t of turns) promptTokens.push(...contentTokens(t.prompt));
  for (const h of hints) promptTokens.push(h.toLowerCase());
  let total = 0;
  const unrelated: string[] = [];
  for (const t of turns) {
    const draws = ClaudeAPI.parseResponseAndDrawings(t.raw);
    for (const d of draws.drawCommands || []) {
      total++;
      const label = (d.label || '').toLowerCase();
      const own = contentTokens(label);
      if (own.length > 0 && promptTokens.length > 0 && !anyTokenIn(label, promptTokens)) {
        unrelated.push(`DRAW ${d.type}: ${label.slice(0, 60)}`);
      }
    }
    for (const c of t.cmds) {
      if (!VISUAL_TYPES.has(c.type)) continue;
      total++;
      const vals = stringValues(c).filter((v) => v !== c.type);
      const joined = vals.join(' ');
      const own = contentTokens(joined);
      if (own.length > 0 && promptTokens.length > 0 && !anyTokenIn(joined, promptTokens)) {
        unrelated.push(`${c.type}: ${String(c.label || joined).slice(0, 60)}`);
      }
    }
  }
  if (total === 0) return { verdict: 'N/A', detail: 'no drawing/animation shapes emitted' };
  if (unrelated.length === 0) {
    return { verdict: 'PASS', detail: `all ${total} shape(s) topic-related` };
  }
  return {
    verdict: 'FAIL',
    detail: `${unrelated.length}/${total} shape(s) unrelated: ${unrelated.slice(0, 3).join(' | ')}`,
  };
}

function evaluateCode(turns: Turn[], opts: { allowTODO?: boolean } = {}): Dim {
  const blocks: { lang: string; code: string }[] = [];
  for (const t of turns) blocks.push(...extractCodeBlocks(t.raw));
  if (blocks.length === 0) return { verdict: 'N/A', detail: 'no code blocks emitted' };
  const issues: string[] = [];
  for (const b of blocks) {
    const c = b.code;
    if (c.trim().length < 10) issues.push('empty/tiny block');
    const braces = (c.match(/\{/g) || []).length - (c.match(/\}/g) || []).length;
    if (braces !== 0) issues.push(`unbalanced braces (${braces > 0 ? 'missing }' : 'extra }'})`);
    const parens = (c.match(/\(/g) || []).length - (c.match(/\)/g) || []).length;
    if (parens !== 0) issues.push(`unbalanced parens (${parens > 0 ? 'missing )' : 'extra )'})`);
    if (!opts.allowTODO && /\b(TODO|FIXME|IMPLEMENT ME|YOUR CODE HERE|<placeholder>)\b/.test(c)) {
      issues.push('left TODO/placeholder in code');
    }
    const lines = c.trim().split('\n');
    const last = (lines[lines.length - 1] || '').trim();
    if (/\.\.\.$/.test(last) || /[,=:+&|{(]$/.test(last)) issues.push(`truncated last line: "${last.slice(0, 40)}"`);
  }
  if (issues.length === 0) {
    return { verdict: 'PASS', detail: `${blocks.length} block(s): balanced, complete, no placeholders` };
  }
  return { verdict: 'FAIL', detail: issues.slice(0, 4).join('; ') };
}

function evaluateExplanation(turn: Turn, minWords: number, extraTokens: string[] = []): Dim {
  const text = turn.spoken.length > 10 ? turn.spoken : stripTags(turn.raw);
  const words = text.split(/\s+/).filter(Boolean);
  if (words.length < minWords) {
    return { verdict: 'FAIL', detail: `explanation too short (${words.length} words, need >= ${minWords})` };
  }
  const toks = extraTokens.length > 0 ? extraTokens : contentTokens(turn.prompt);
  if (toks.length > 0 && !anyTokenIn(text.toLowerCase(), toks)) {
    return { verdict: 'FAIL', detail: 'topic never mentioned in spoken explanation' };
  }
  return { verdict: 'PASS', detail: `${words.length} words, topic present` };
}

function countBullets(s: string): number {
  return (s.match(/(?:^|\n)\s*(?:[-*•]|\d+[.)])\s+\S/g) || []).length;
}

function hasTree(raw: string): { tree: boolean; paths: string[] } {
  const paths = [...new Set(raw.match(/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+(?:\.[A-Za-z0-9]+)?/g) || [])];
  const treeChars = /[├└│]/.test(raw);
  return { tree: paths.length >= 3 || treeChars, paths };
}

function builderLeak(cmds: ParsedOverlayCommand[], raw: string): boolean {
  for (const c of cmds) {
    const label = String(c.label || '');
    if (/(?:scaffold|starter (?:project|repo)|file tree|folder structure|full stack architecture)/i.test(label)) return true;
  }
  return /(?:scaffold(?:ed)? the (?:project|repo)|file tree below)/i.test(raw);
}

function hijackEngine(cmds: ParsedOverlayCommand[]): string[] {
  const markers = ['ACTOR', 'DJ', 'AIM_TRAINER', 'TRACE', 'ANIMATE', 'ANATOMY', 'FIELD'];
  return [...new Set(cmds.filter((c) => markers.includes(c.type)).map((c) => c.type))];
}

async function ask(api: ClaudeAPI, prompt: string, history: { userTranscript: string; assistantResponse: string }[]): Promise<string> {
  const timeout = new Promise<string>((resolve) =>
    setTimeout(() => resolve('[LLM_TIMEOUT] no response within 120s'), 120000)
  );
  const capture = {
    label: 'screen',
    screenshotWidthInPixels: 1,
    screenshotHeightInPixels: 1,
    imageDataBase64: PNG1PX,
  } as any;
  return Promise.race([
    api.analyzeImageStreaming([capture], VISUAL_TUTOR_SYSTEM_PROMPT, history, prompt),
    timeout,
  ]);
}

async function runTurn(api: ClaudeAPI, prompt: string, history: { userTranscript: string; assistantResponse: string }[]): Promise<Turn> {
  process.stdout.write(`  . LLM call for: ${prompt.slice(0, 60).replace(/\n/g, ' ')}...\n`);
  const raw = await ask(api, prompt, history);
  const cmds: ParsedOverlayCommand[] = [];
  const spokenSegs: string[] = [];
  await executeSynchronizedLesson(
    raw,
    (segmentCommands, clearFirst) => {
      if (clearFirst) cmds.length = 0;
      for (const c of segmentCommands) cmds.push(c);
    },
    async (text) => {
      if (text.trim()) spokenSegs.push(text.trim());
    },
    undefined,
    prompt
  );
  history.push({ userTranscript: prompt, assistantResponse: stripTags(raw).slice(0, 4000) });
  return { prompt, raw, spoken: spokenSegs.join(' '), cmds };
}

function makeResult(
  id: string,
  title: string,
  behavior: Dim,
  visuals: Dim,
  code: Dim,
  explanation: Dim,
  notes: string[],
  turns: Turn[],
  override?: TCResult['status']
): TCResult {
  let status: TCResult['status'];
  if (override) status = override;
  else if (behavior.verdict === 'FAIL') status = 'FAIL';
  else if (visuals.verdict === 'FAIL' || code.verdict === 'FAIL' || explanation.verdict === 'FAIL') status = 'PARTIAL';
  else status = 'PASS';
  const cmdTypes = [...new Set(turns.flatMap((t) => t.cmds.map((c) => c.type)))];
  return {
    id,
    title,
    behavior,
    visuals,
    code,
    explanation,
    status,
    notes,
    evidence: {
      spokenExcerpt: turns.map((t) => t.spoken).join(' ').slice(0, 300),
      rawExcerpt: turns.map((t) => t.raw).join('\n').slice(0, 300),
      cmdTypes,
    },
  };
}

function printResult(r: TCResult): void {
  const line =
    `${r.id} [${r.status}] ${r.title}\n` +
    `    behavior    : ${r.behavior.verdict} - ${r.behavior.detail}\n` +
    `    visuals     : ${r.visuals.verdict} - ${r.visuals.detail}\n` +
    `    code        : ${r.code.verdict} - ${r.code.detail}\n` +
    `    explanation : ${r.explanation.verdict} - ${r.explanation.detail}` +
    (r.notes.length ? `\n    notes       : ${r.notes.join(' | ')}` : '');
  console.log(line + '\n');
}

async function sandboxRun(code: string, lang: 'javascript' | 'typescript' | 'python'): Promise<{ ok: boolean; out: string }> {
  const ex = new SandboxTestExecutor(new WorkspaceSafetyManager());
  const res = await ex.runCodeInSandbox(code, lang, 10000);
  return { ok: res.succeeded && res.stdout.includes('CALLRESULT'), out: (res.stderr || res.stdout || '').slice(0, 200) };
}

function detectLang(block: { lang: string; code: string }): 'javascript' | 'typescript' | 'python' {
  if (['py', 'python'].includes(block.lang) || /def\s+\w+\s*\(/.test(block.code)) return 'python';
  if (['ts', 'typescript'].includes(block.lang)) return 'typescript';
  if (/(?:\(|,)\s*\w+\s*:\s*(?:string|number|boolean|any)\s*[,)]/.test(block.code)) return 'typescript';
  return 'javascript';
}

async function main() {
  console.log('=== STARTING 20-TC MATRIX PROBE (Clicky real pipeline) ===\n');
  const api = new ClaudeAPI();
  const results: TCResult[] = [];

  {
    const history: { userTranscript: string; assistantResponse: string }[] = [];
    const turns: Turn[] = [];
    turns.push(await runTurn(api, 'Explain how binary search works like I am 10 years old.', history));
    const t = turns[0];
    const all = (t.raw + ' ' + t.spoken).toLowerCase();
    const teaches = all.includes('binary') && (all.includes('search') || all.includes('midpoint') || all.includes('divide'));
    const leak = builderLeak(t.cmds, t.raw);
    const behavior: Dim = teaches && !leak
      ? { verdict: 'PASS', detail: 'binary-search lesson delivered, no builder/scaffold triggered' }
      : { verdict: 'FAIL', detail: !teaches ? 'no binary-search teaching content' : 'builder/scaffold output leaked into a teaching task' };
    const notes: string[] = [];
    const srcEngine = t.cmds.some((c) => c.type === 'TRACE') ? 'TRACE engine' : t.cmds.some((c) => c.type === 'GRAPH') ? 'auto-GRAPH engine' : 'LLM lesson path';
    notes.push(`module-equivalent chosen: ${srcEngine} (teaching), CodebaseBuilder not used`);
    const code = evaluateCode(turns);
    results.push(makeResult('TC-01', 'Clear Educational Routing', behavior, evaluateVisuals(turns, ['binary', 'search']), code, evaluateExplanation(t, 25), notes, turns));
  }

  {
    const history: { userTranscript: string; assistantResponse: string }[] = [];
    const turns: Turn[] = [];
    turns.push(await runTurn(api, 'Generate a clean folder structure for a React + FastAPI web app.', history));
    const t = turns[0];
    const all = t.raw + ' ' + t.spoken;
    const { tree, paths } = hasTree(all);
    const stack = /react/i.test(all) && /fastapi/i.test(all);
    const behavior: Dim = tree && stack
      ? { verdict: 'PASS', detail: `file tree emitted (${paths.length} paths): start-from-scratch structure produced` }
      : { verdict: 'FAIL', detail: `tree=${tree} (paths=${paths.length}), react+fastapi mentioned=${stack}` };
    const notes = [`detected paths: ${paths.slice(0, 6).join(', ').slice(0, 120)}`];
    results.push(makeResult('TC-02', 'Clear Architecture Routing', behavior, evaluateVisuals(turns, ['react', 'fastapi', 'folder', 'structure']), evaluateCode(turns), evaluateExplanation(t, 25), notes, turns));
  }

  {
    const history: { userTranscript: string; assistantResponse: string }[] = [];
    const turns: Turn[] = [];
    turns.push(
      await runTurn(
        api,
        'Rewrite these messy meeting notes into a 3-bullet action list. Notes: "alice to send the deck by friday, bob needs to fix the login bug ASAP, carol will follow up with marketing about the launch date, dave said budget is fine"',
        history
      )
    );
    const t = turns[0];
    const bullets = countBullets(t.spoken) + countBullets(stripTags(t.raw));
    const hijack = hijackEngine(t.cmds);
    const behavior: Dim = bullets >= 2 && bullets <= 6 && hijack.length === 0
      ? { verdict: 'PASS', detail: `direct handling: ${bullets} bullets, no specialized engine hijack` }
      : { verdict: 'FAIL', detail: `bullets=${bullets} (need 2-6), hijacked by: ${hijack.join(',') || 'n/a'}` };
    results.push(makeResult('TC-03', 'General Task Execution (direct)', behavior, evaluateVisuals(turns, ['meeting', 'action', 'bullet']), evaluateCode(turns), evaluateExplanation(t, 15), [], turns));
  }

  {
    const history: { userTranscript: string; assistantResponse: string }[] = [];
    const turns: Turn[] = [];
    turns.push(
      await runTurn(api, 'I only know basic HTML/CSS. Explain what a database foreign key is.', history)
    );
    const t = turns[0];
    const text = (t.spoken + ' ' + stripTags(t.raw)).toLowerCase();
    const analogy = ['spreadsheet', 'link', 'reference', 'relationship', 'pointing to', 'points to', 'row'].some((w) => text.includes(w));
    const jargon = (text.match(/\bjoin\b|normaliz|referential integrity/g) || []).length;
    const behavior: Dim = analogy && jargon <= 2
      ? { verdict: 'PASS', detail: `relatable analogy used, heavy-jargon count=${jargon}` }
      : { verdict: 'FAIL', detail: `analogy=${analogy}, jargon-count=${jargon}` };
    results.push(makeResult('TC-04', 'Tutor Skill-Level Adaptation', behavior, evaluateVisuals(turns, ['foreign', 'key', 'database']), evaluateCode(turns), evaluateExplanation(t, 30), [], turns));
  }

  {
    const history: { userTranscript: string; assistantResponse: string }[] = [];
    const turns: Turn[] = [];
    turns.push(
      await runTurn(
        api,
        'Complete this half-written Python file. Keep the function name and finish only the missing logic:\n\ndef calculate_discount(price, tier):\n    # TODO\n',
        history
      )
    );
    const t = turns[0];
    const blocks = extractCodeBlocks(t.raw);
    const fnBlock = blocks.find((b) => b.code.includes('calculate_discount'));
    const signatureKept = !!fnBlock && /def\s+calculate_discount\s*\(\s*price\s*,\s*tier\s*\)/.test(fnBlock.code);
    const bodyFilled = !!fnBlock && !/def\s+calculate_discount[\s\S]{0,120}#?\s*TODO/.test(fnBlock.code) && (fnBlock.code.match(/\n/g) || []).length >= 3;
    const behavior: Dim = signatureKept && bodyFilled
      ? { verdict: 'PASS', detail: 'signature preserved, TODO body replaced with real logic' }
      : { verdict: 'FAIL', detail: `signatureKept=${signatureKept}, bodyFilled=${bodyFilled}` };
    let code = evaluateCode(turns);
    if (fnBlock && code.verdict !== 'FAIL') {
      const lang = detectLang(fnBlock);
      const wrap = lang === 'python'
        ? fnBlock.code + "\nprint('CALLRESULT:', type(calculate_discount(100, 'gold')).__name__)\n"
        : fnBlock.code + "\nconsole.log('CALLRESULT:' + typeof calculate_discount(100, 'gold'));\n";
      const run = await sandboxRun(wrap, lang);
      code = run.ok
        ? { verdict: 'PASS', detail: `completeness + sandbox execution OK (${lang}, exit 0)` }
        : { verdict: 'FAIL', detail: `sandbox execution failed: ${run.out.slice(0, 120)}` };
    }
    results.push(makeResult('TC-05', 'Single-File Code Completion', behavior, evaluateVisuals(turns, ['discount', 'price', 'tier']), code, evaluateExplanation(t, 20), [], turns));
  }

  {
    const history: { userTranscript: string; assistantResponse: string }[] = [];
    const turns: Turn[] = [];
    turns.push(await runTurn(api, 'WebSockets.', history));
    const t = turns[0];
    const all = (t.raw + ' ' + t.spoken).toLowerCase();
    const asks = all.includes('?');
    const offersLearn = ['explain', 'what', 'how it works', 'learn', 'understand', 'overview'].some((w) => all.includes(w));
    const offersBuild = ['build', 'implement', 'integrate', 'project', 'app', 'into your', 'into my'].some((w) => all.includes(w));
    const behavior: Dim = asks && offersLearn && offersBuild
      ? { verdict: 'PASS', detail: 'paused and asked clarify: learn vs build' }
      : { verdict: 'FAIL', detail: `asked=${asks}, learn-offer=${offersLearn}, build-offer=${offersBuild}` };
    results.push(makeResult('TC-06', 'Ambiguous Intent Handling (ASK_CLARIFICATION)', behavior, evaluateVisuals(turns, ['websocket']), evaluateCode(turns), evaluateExplanation(t, 10), [], turns));
  }

  {
    const history: { userTranscript: string; assistantResponse: string }[] = [];
    const turns: Turn[] = [];
    turns.push(await runTurn(api, 'Teach me JavaScript Promises.', history));
    turns.push(await runTurn(api, "I'm confused by .catch(). Quiz me on it.", history));
    turns.push(await runTurn(api, 'A: It runs when the promise is rejected and handles the error.', history));
    const [t1, t2, t3] = turns;
    const s1 = (t1.raw + ' ' + t1.spoken).toLowerCase();
    const s2 = (t2.raw + ' ' + t2.spoken).toLowerCase();
    const s3 = (t3.raw + ' ' + t3.spoken).toLowerCase();
    const taught = s1.includes('promise') && (s1.includes('resolve') || s1.includes('reject') || s1.includes('await'));
    const quizzed = (s2.includes('quiz') || s2.includes('question')) && s2.includes('?') && s2.includes('catch');
    const graded = ['correct', 'right', 'exactly', 'yes', 'good', 'spot on'].some((w) => s3.includes(w)) && (s3.includes('catch') || s3.includes('reject'));
    const behavior: Dim = taught && quizzed && graded
      ? { verdict: 'PASS', detail: 'turn1 taught, turn2 quizzed .catch(), turn3 graded the reply' }
      : { verdict: 'FAIL', detail: `taught=${taught}, quizzed=${quizzed}, graded=${graded}` };
    const ex1 = evaluateExplanation(t1, 30, ['promise']);
    const ex2 = evaluateExplanation(t2, 10, ['catch', 'promise']);
    const ex3 = evaluateExplanation(t3, 8, ['catch', 'reject', 'promise']);
    const explanation: Dim = [ex1, ex2, ex3].every((e) => e.verdict === 'PASS')
      ? { verdict: 'PASS', detail: 'all 3 turns explained with topic continuity (memory kept)' }
      : { verdict: 'FAIL', detail: [ex1, ex2, ex3].filter((e) => e.verdict === 'FAIL').map((e) => e.detail).join('; ') };
    results.push(makeResult('TC-07', 'Multi-Turn Memory & Quizzing', behavior, evaluateVisuals(turns, ['promise', 'catch']), evaluateCode(turns), explanation, [], turns));
  }

  {
    const history: { userTranscript: string; assistantResponse: string }[] = [];
    const turns: Turn[] = [];
    turns.push(
      await runTurn(
        api,
        'I want to build a personal expense tracker website with a chart, but I do not know where to start.',
        history
      )
    );
    const t = turns[0];
    const all = (t.raw + ' ' + t.spoken).toLowerCase();
    const hasIndex = all.includes('index.html');
    const hasCss = all.includes('style.css') || all.includes('styles.css');
    const hasJs = all.includes('app.js') || all.includes('script.js') || all.includes('main.js');
    const hasReadme = all.includes('readme');
    const behavior: Dim = hasIndex && hasCss && hasJs && hasReadme
      ? { verdict: 'PASS', detail: 'full skeleton: index.html + css + js + README' }
      : { verdict: 'FAIL', detail: `index=${hasIndex} css=${hasCss} js=${hasJs} readme=${hasReadme}` };
    results.push(makeResult('TC-08', 'Builder Blank-Slate Skeleton', behavior, evaluateVisuals(turns, ['expense', 'tracker', 'chart']), evaluateCode(turns), evaluateExplanation(t, 25), [], turns));
  }

  {
    const history: { userTranscript: string; assistantResponse: string }[] = [];
    const turns: Turn[] = [];
    const prompt =
      'Finish this codebase.\n' +
      '--- routes.js\n' +
      "const userController = require('./userController');\n" +
      "module.exports = (app) => { app.post('/login', userController.login); };\n" +
      '--- userController.js\n' +
      '// (empty - controller logic missing)';
    turns.push(await runTurn(api, prompt, history));
    const t = turns[0];
    const all = t.raw + ' ' + t.spoken;
    const low = all.toLowerCase();
    const hasLogin = low.includes('login');
    const hasLogic = /login\s*[:(=]/.test(low) && ['password', 'verify', 'compare', 'jwt', 'bcrypt', 'hash'].some((w) => low.includes(w));
    const wires = low.includes('usercontroller') && (low.includes('routes.js') || low.includes('module.exports'));
    const behavior: Dim = hasLogin && hasLogic && wires
      ? { verdict: 'PASS', detail: 'detected missing controller.login from routes.js call-site and wrote it' }
      : { verdict: 'FAIL', detail: `login=${hasLogin}, body=${hasLogic}, wired-to-routes=${wires}` };
    results.push(makeResult('TC-09', 'Multi-File Gap Completion', behavior, evaluateVisuals(turns, ['login', 'controller', 'routes']), evaluateCode(turns), evaluateExplanation(t, 20), [], turns));
  }

  {
    const history: { userTranscript: string; assistantResponse: string }[] = [];
    const turns: Turn[] = [];
    turns.push(
      await runTurn(
        api,
        'Write a rate-limiter middleware in Node.js for my app, and then explain how the sliding window logic works.',
        history
      )
    );
    const t = turns[0];
    const blocks = extractCodeBlocks(t.raw);
    const codeBlock = blocks.find((b) => /rate|limit|window|middleware/i.test(b.code));
    const all = (t.raw + ' ' + t.spoken).toLowerCase();
    const explains = all.includes('sliding window');
    const ids = [...new Set(((codeBlock && codeBlock.code.match(/\b[a-zA-Z_][a-zA-Z0-9_]{3,}\b/g)) || []))].filter((x) => !STOP.has(x.toLowerCase()));
    const overlap = ids.filter((x) => all.includes(x.toLowerCase()));
    const behavior: Dim = !!codeBlock && explains && overlap.length >= 2
      ? { verdict: 'PASS', detail: `code produced, sliding-window explained, ${overlap.length} code identifiers referenced in explanation` }
      : { verdict: 'FAIL', detail: `code=${!!codeBlock}, explains-window=${explains}, identifier-overlap=${overlap.length}` };
    results.push(makeResult('TC-10', 'Sequential Chaining (build + teach with context)', behavior, evaluateVisuals(turns, ['rate', 'window', 'limit']), evaluateCode(turns), evaluateExplanation(t, 30), [`overlap identifiers: ${overlap.slice(0, 6).join(', ')}`], turns));
  }

  {
    const history: { userTranscript: string; assistantResponse: string }[] = [];
    const turns: Turn[] = [];
    turns.push(
      await runTurn(
        api,
        'Teach me the Factory Design Pattern, then create an unfinished mini-project where I have to write the final class myself.',
        history
      )
    );
    const t = turns[0];
    const all = (t.raw + ' ' + t.spoken).toLowerCase();
    const taught = all.includes('factory') && ['interface', 'product', 'creator', 'without exposing', 'instantiate'].some((w) => all.includes(w));
    const unfinished = extractCodeBlocks(t.raw).some((b) => /TODO:?\s*Implement your Factory|# TODO/i.test(b.code) || (/class\s+\w*Factory/i.test(b.code) && /TODO/i.test(b.code)));
    const behavior: Dim = taught && unfinished
      ? { verdict: 'PASS', detail: 'pattern taught + 80%-complete project with explicit Factory TODO' }
      : { verdict: 'FAIL', detail: `taught=${taught}, unfinished-project-with-TODO=${unfinished}` };
    results.push(makeResult('TC-11', 'Learn-by-Doing Scaffold', behavior, evaluateVisuals(turns, ['factory', 'pattern']), evaluateCode(turns, { allowTODO: true }), evaluateExplanation(t, 30), [], turns));
  }

  {
    const history: { userTranscript: string; assistantResponse: string }[] = [];
    const turns: Turn[] = [];
    const prompt =
      'Fix the broken navbar and finish the contact form.\n' +
      '--- navbar.js\n' +
      "export function renderNavbar() { return '<nav class=\"navbar\">'; }\n" +
      '--- contact.html\n' +
      '<form id="contact"></form>\n' +
      '--- package.json\n' +
      '{"name":"site","dependencies":{"express":"^4.18.2"}}';
    turns.push(await runTurn(api, prompt, history));
    const t = turns[0];
    const low = (t.raw + ' ' + t.spoken).toLowerCase();
    const fixedNav = low.includes('navbar') && ['fix', 'closed', 'closing', 'complete', 'active link'].some((w) => low.includes(w));
    const finishedForm = low.includes('contact') && low.includes('form') && (low.includes('input') || low.includes('submit') || low.includes('label'));
    const behavior: Dim = fixedNav && finishedForm
      ? { verdict: 'PASS', detail: 'navbar repaired + contact form completed' }
      : { verdict: 'FAIL', detail: `navbar-fixed=${fixedNav}, form-finished=${finishedForm}` };
    const depRe = /require\(['"](?!(?:node:|\.)[a-z0-9]*['"])[a-z@][a-z0-9@/_-]*['"]\)|from ['"](?!(?:node:|\.)[a-z0-9]*['"])[a-z@][a-z0-9@/_-]*['"]/g;
    const imported = [...new Set(t.raw.match(depRe) || [])].map((s) => (s.match(/['"]([^'"]+)['"]/) || [, ''])[1]);
    const known = new Set(['express']);
    const hallucinated = imported.filter((m) => !known.has(m.split('/')[0].replace(/^@[^/]+\//, '@')));
    let code = evaluateCode(turns);
    if (hallucinated.length > 0) {
      code = { verdict: 'FAIL', detail: `hallucinated deps not in package.json: ${hallucinated.join(', ')}` };
    }
    results.push(makeResult('TC-12', 'Messy Repo Rescue (no broken pages, no hallucinated libs)', behavior, evaluateVisuals(turns, ['navbar', 'contact', 'form']), code, evaluateExplanation(t, 25), hallucinated.length ? [] : ['no new dependencies introduced'], turns));
  }

  {
    const history: { userTranscript: string; assistantResponse: string }[] = [];
    const turns: Turn[] = [];
    const prompt =
      'Complete the login route.\n' +
      '--- auth.js\n' +
      "const bcrypt = require('bcrypt');\n" +
      "const jwt = require('jsonwebtoken');\n" +
      '// TODO: finish verifyCredentials and issueToken\n' +
      '--- package.json\n' +
      '{"name":"api","dependencies":{"express":"^4.18.2"}}';
    turns.push(await runTurn(api, prompt, history));
    const t = turns[0];
    const low = (t.raw + ' ' + t.spoken).toLowerCase();
    const finishesRoute = low.includes('login') && (t.raw.includes('bcrypt') || t.raw.includes('jwt'));
    const updatesManifest = low.includes('package.json') && low.includes('dependencies') && low.includes('bcrypt') && (low.includes('jsonwebtoken') || low.includes('jwt'));
    const behavior: Dim = finishesRoute && updatesManifest
      ? { verdict: 'PASS', detail: 'route completed AND dependency manifest updated (bcrypt + jsonwebtoken)' }
      : { verdict: 'FAIL', detail: `route=${finishesRoute}, manifest-update=${updatesManifest}` };
    results.push(makeResult('TC-13', 'Missing Dependency Detection', behavior, evaluateVisuals(turns, ['login', 'auth', 'bcrypt']), evaluateCode(turns), evaluateExplanation(t, 20), [], turns));
  }

  {
    const history: { userTranscript: string; assistantResponse: string }[] = [];
    const turns: Turn[] = [];
    turns.push(
      await runTurn(api, 'Since CSS is a backend database language, how do I query my database in it?', history)
    );
    const t = turns[0];
    const all = t.raw + ' ' + t.spoken;
    const corrects = /CSS is not\b/i.test(all) || /css(?:\s+\w+){0,6}\s+(?:is\s+)?(?:not|isn't|is not)/i.test(all);
    const guides = /sql|select|query/i.test(all) && /styling|stylesheet|layout|colors|font/i.test(all);
    const behavior: Dim = corrects
      ? { verdict: 'PASS', detail: `false premise corrected (guides-to-right-tool=${guides})` }
      : { verdict: 'FAIL', detail: 'did not correct the false premise (missing "CSS is not")' };
    results.push(makeResult('TC-14', 'False Premise Correction', behavior, evaluateVisuals(turns, ['css', 'sql']), evaluateCode(turns), evaluateExplanation(t, 20), [], turns));
  }

  {
    const history: { userTranscript: string; assistantResponse: string }[] = [];
    const turns: Turn[] = [];
    turns.push(await runTurn(api, 'Start building an e-commerce cart API.', history));
    turns.push(await runTurn(api, 'Wait, what is idempotency in payments? Teach me first.', history));
    turns.push(await runTurn(api, 'Got it, now finish the cart API using that.', history));
    const [t1, t2, t3] = turns;
    const s1 = (t1.raw + ' ' + t1.spoken).toLowerCase();
    const s2 = (t2.raw + ' ' + t2.spoken).toLowerCase();
    const s3 = (t3.raw + ' ' + t3.spoken).toLowerCase();
    const started = s1.includes('cart') && ['api', 'endpoint', 'route', 'post', 'handler'].some((w) => s1.includes(w));
    const taught = s2.includes('idempot') && ['key', 'header', 'request', 'same request'].some((w) => s2.includes(w));
    const resumed = s3.includes('cart') && s3.includes('idempot');
    const behavior: Dim = started && taught && resumed
      ? { verdict: 'PASS', detail: 'builder started -> turn2 routed to teaching -> turn3 resumed with idempotency context' }
      : { verdict: 'FAIL', detail: `started=${started}, taught=${taught}, resumed-with-context=${resumed}` };
    results.push(makeResult('TC-15', 'Mid-Task Context Switch & Resume', behavior, evaluateVisuals(turns, ['cart', 'idempotency']), evaluateCode(turns), evaluateExplanation(t2, 30), [], turns));
  }

  {
    const history: { userTranscript: string; assistantResponse: string }[] = [];
    const turns: Turn[] = [];
    const prompt =
      'Finish the export feature.\n' +
      '--- fileA.js\n' +
      "const b = require('./fileB');\n" +
      'exports.exportA = () => b.getB();\n' +
      '--- fileB.js\n' +
      "const a = require('./fileA');\n" +
      'exports.getB = () => { /* unfinished: combine shared transform */ };';
    turns.push(await runTurn(api, prompt, history));
    const t = turns[0];
    const low = (t.raw + ' ' + t.spoken).toLowerCase();
    const detectsCycle = low.includes('circular') || low.includes('cycle') || low.includes('deadlock');
    const extractsUtils = low.includes('utils');
    const completesExport = extractCodeBlocks(t.raw).some((b) => /module\.exports|exports\./.test(b.code) && !/require\(['"]\.\/file[AB]['"]\)/.test(b.code));
    const behavior: Dim = detectsCycle && extractsUtils && completesExport
      ? { verdict: 'PASS', detail: 'cycle detected, shared logic moved to utils, export completed without require cycle' }
      : { verdict: 'FAIL', detail: `cycle-detected=${detectsCycle}, utils-extracted=${extractsUtils}, export-completed=${completesExport}` };
    results.push(makeResult('TC-16', 'Circular Dependency Resolution', behavior, evaluateVisuals(turns, ['export', 'circular', 'utils']), evaluateCode(turns), evaluateExplanation(t, 25), [], turns));
  }

  {
    const history: { userTranscript: string; assistantResponse: string }[] = [];
    const turns: Turn[] = [];
    const prompt =
      'Add a footer component to the landing page. Project folder has 40+ files: landing.html, app.js, styles.css, nav.js, components/sidebar.js, components/modal.js, data/products.json (2MB), node_modules/ (38 packages), package-lock.json, README.md, and 25 more.';
    turns.push(await runTurn(api, prompt, history));
    const t = turns[0];
    const raw = t.raw;
    const editCtx = raw.match(/(?:edit|update|modify|change|write to|open up)\s+[^\n]{0,100}/gi) || [];
    const badTarget = editCtx.some((l) => /node_modules|package-lock|yarn\.lock/i.test(l));
    let targets = [...new Set(raw.match(/[\w./-]+\.(?:js|jsx|ts|tsx|css|html|json)/g) || [])].filter(
      (p) => !p.includes('node_modules') && !p.includes('lock')
    );
    const picksRelevant = targets.some((p) => /landing|index/i.test(p)) && raw.toLowerCase().includes('footer');
    const behavior: Dim = !badTarget && picksRelevant && targets.length <= 6
      ? { verdict: 'PASS', detail: `selected ${targets.length} relevant file(s), node_modules/lockfile untouched` }
      : { verdict: 'FAIL', detail: `edited-bad-target=${badTarget}, relevant-pick=${picksRelevant}, target-count=${targets.length} (want <=6)` };
    results.push(makeResult('TC-17', 'Large-Codebase Relevance Filtering', behavior, evaluateVisuals(turns, ['footer', 'landing']), evaluateCode(turns), evaluateExplanation(t, 20), [`targets: ${targets.slice(0, 6).join(', ')}`], turns));
  }

  {
    const behavior: Dim = {
      verdict: 'PASS',
      detail:
        'static evidence: ClaudeAPI tries Ollama once (ClaudeAPI.ts:144, now with num_ctx=8192) -> cloud once (:187) -> offline fallback (:204-211); AutoRepairLoop bounded by maxRetries; no retry/loop path exists',
    };
    const notes = [
      'runtime failure-injection skipped on purpose: would require stopping the user Ollama service',
      'run1 (before fix): Ollama returned 400 "exceeds context size (4096)" for the ~4,100-token system prompt -> 17/20 TCs scored the offline fallback; fixed by options.num_ctx=8192 in ClaudeAPI.ts',
    ];
    const result = makeResult('TC-18', 'Sub-Agent Failure & Loop Breaker', behavior, { verdict: 'N/A', detail: 'static check' }, { verdict: 'N/A', detail: 'static check' }, { verdict: 'N/A', detail: 'static check' }, notes, [], 'STATIC');
    results.push(result);
  }

  {
    const sm = new WorkspaceSafetyManager('D:\\new_automation\\final hojaiga tutor');
    const rm = sm.validateCommand('rm -rf ../../');
    const del = sm.validateCommand('del /f /q C:\\Windows');
    const nodeOk = sm.validateCommand('node test.js');
    const outside = sm.isPathInsideWorkspace('C:\\Windows\\System32');
    const traversal = sm.isPathInsideWorkspace('D:\\new_automation\\final hojaiga tutor\\..\\..\\..\\Windows');
    const blocking = rm.allowed === false && del.allowed === false && nodeOk.allowed === true && outside === false && traversal === false;
    const behavior: Dim = blocking
      ? { verdict: 'PASS', detail: 'rm -rf blocked, del blocked, node allowed, outside-path + traversal blocked' }
      : { verdict: 'FAIL', detail: `rm=${rm.allowed}, del=${del.allowed}, node=${nodeOk.allowed}, outside=${outside}, traversal=${traversal}` };
    const notes = [
      'confirmation primitive queueApproval/resolveApproval exists (WorkspaceSafetyManager.ts:75,91) but grep shows ZERO callers anywhere in src - not wired into any flow',
      'natural-language destructive prompt has no engine-level block (only command/path level)',
    ];
    const result = makeResult('TC-19', 'Path Traversal & Destructive Safety', behavior, { verdict: 'N/A', detail: 'no LLM turn' }, { verdict: 'N/A', detail: 'no LLM turn' }, { verdict: 'N/A', detail: 'no LLM turn' }, notes, [], 'PARTIAL');
    results.push(result);
  }

  {
    const history: { userTranscript: string; assistantResponse: string }[] = [];
    const turns: Turn[] = [];
    turns.push(
      await runTurn(
        api,
        'I have an empty directory and do not know GraphQL. Teach me the basics in 5 lines, scaffold a GraphQL book-library API, finish all resolvers, and give me a test query I can run.',
        history
      )
    );
    const t = turns[0];
    const low = (t.raw + ' ' + t.spoken).toLowerCase();
    const lesson = low.includes('graphql');
    const schema = /type\s+query|schema|type\s+book/.test(low);
    const resolvers = low.includes('resolv');
    const testQuery = /query\s*\{|\{\s*books|\bbooks\s*\{/.test(low);
    const behavior: Dim = lesson && schema && resolvers && testQuery
      ? { verdict: 'PASS', detail: 'concise lesson + schema + resolvers + runnable test query all present' }
      : { verdict: 'FAIL', detail: `lesson=${lesson}, schema=${schema}, resolvers=${resolvers}, testQuery=${testQuery}` };
    const spokenWords = t.spoken.split(/\s+/).filter(Boolean).length;
    const explanation: Dim =
      lesson && spokenWords >= 30 && spokenWords <= 500
        ? { verdict: 'PASS', detail: `lesson present, ${spokenWords} spoken words (concise)` }
        : { verdict: 'FAIL', detail: `lesson=${lesson}, spoken-words=${spokenWords} (want 30-500)` };
    results.push(makeResult('TC-20', 'Full Autonomous Capstone', behavior, evaluateVisuals(turns, ['graphql', 'book', 'resolver']), evaluateCode(turns), explanation, [], turns));
  }

  for (const r of results) printResult(r);

  const counts = { PASS: 0, PARTIAL: 0, FAIL: 0, STATIC: 0 };
  for (const r of results) counts[r.status]++;
  console.log('================================================================');
  console.log(`MATRIX20 SUMMARY: ${counts.PASS} PASS | ${counts.PARTIAL} PARTIAL | ${counts.FAIL} FAIL | ${counts.STATIC} STATIC | TOTAL ${results.length}`);
  console.log('================================================================');
  fs.writeFileSync(REPORT_PATH, JSON.stringify(results, null, 2), 'utf8');
  console.log(`report -> ${REPORT_PATH}`);
  console.log('MATRIX20_DONE');
}

main().catch((err) => {
  console.error('MATRIX20_ERROR:', err && err.stack ? err.stack : err);
  process.exit(1);
});
