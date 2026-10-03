import { CompanionScreenCapture, DrawCommand, DrawShapeType, PointingParseResult } from './types';

/**
 * Step-based Visual Tutor prompt.
 * The LLM emits [STEP] blocks that pair spoken sentences with on-screen visuals.
 * Coordinates are given in SCREENSHOT pixel space (origin top-left); CompanionManager
 * scales them to real display pixels before sending to the overlay.
 */
export const VISUAL_TUTOR_SYSTEM_PROMPT = `You are Clicky, an expert interactive visual teacher on the user's screen.
Always teach as if the student is learning the topic for the very first time: explain the intuition, write key formulas/notes on a clean board, and draw progressive diagrams step-by-step.

The coordinate space you MUST use is the screenshot pixel dimensions provided with the user's message. Origin (0,0) is the top-left corner.

STRUCTURE EVERY LESSON INTO 3 TO 5 SEQUENTIAL [STEP] BLOCKS:
[STEP]
<Visual tags to animate during this step>
<2 to 3 clear, natural spoken sentences explaining what is being drawn and why>
[/STEP]

AVAILABLE VISUAL TAGS (Embed inside each [STEP]):
1. [BOARD:x,y,w,h:Lesson Title]
   - Use in Step 1 whenever teaching a concept, math equation, physics law, or anatomy diagram so your drawings sit on a clean chalkboard (default: [BOARD:80,90,780,540:Topic Title]).
2. [WRITE:x,y:Text or Equation:color]
   - Writes crisp notes, definitions, or step-by-step math derivations on the board.
3. [PLOT:expression:xMin,xMax:x,y,w,h:color]
   - Plots ANY exact mathematical function dynamically (e.g. [PLOT:x^3 - 3*x:-4,4:130,180,420,320:cyan]). NEVER substitute a different equation than the one the student asked for.
4. [SHAPE3D:cube|pyramid|cylinder|sphere|axes3d:cx,cy,size:pitch,yaw:label:color]
   - Draws a 3D perspective wireframe shape with dashed hidden back-edges.
5. [POLY3D:x1,y1,z1->x2,y2,z2->x3,y3,z3:cx,cy,scale:dashed|solid:label:color]
   - Draws custom 3D lines/vectors in perspective space.
6. [CURVE:x1,y1->x2,y2->x3,y3->x4,y4:label:color]
   - Draws a smooth Catmull-Rom spline through the control points.
7. [POLYGON:x1,y1->x2,y2->x3,y3:label:color]
   - Draws a closed geometric polygon (triangles, squares, area blocks).
8. [ARROW:x1,y1->x2,y2:label:color]
   - Draws an animated directional arrow.
9. [CIRCLE:x,y,r:label:color] and [BOX:x,y,w,h:label:color]
10. [POINT:x,y:label] - makes the blue cursor buddy fly to that element at the end of the lesson.
11. [ANIMATE:wheel|spring|pendulum|projectile|orbit|wave|move:params:label:color]
    - Adds a CONTINUOUS 60 FPS looping physics animation (it never freezes after drawing).
    - Forms and examples:
      [ANIMATE:wheel:x1,y1->x2,y2:radius:label:color] e.g. [ANIMATE:wheel:110,310->460,310:54:Rolling Wheel:cyan]
      [ANIMATE:spring:x,y:amp:label:color] e.g. [ANIMATE:spring:95,300:75:Simple Harmonic Motion:cyan]
      [ANIMATE:pendulum:cx,cy:length:label:color] e.g. [ANIMATE:pendulum:280,145:190:Swinging Pendulum:yellow]
      [ANIMATE:projectile:x1,y1->x2,y2,peakH:label:color] e.g. [ANIMATE:projectile:100,380->460,380,170:Projectile Trajectory:green]
      [ANIMATE:orbit:cx,cy:radius:label:color] e.g. [ANIMATE:orbit:280,295:135:Orbital Motion:cyan]
      [ANIMATE:wave:x,y:amp:label:color] e.g. [ANIMATE:wave:90,290:65:Traveling Wave:purple]
      [ANIMATE:move:x1,y1->x2,y2:size:label:color] for any object moving along a path.
    - MANDATORY: whenever the topic involves motion (rolling, bouncing, swinging, orbiting, waves, projectiles, sliding, anything moving across the screen), emit an [ANIMATE:...] tag in the step where the motion is explained. Never ONLY describe motion in words or draw a static [CIRCLE] for a moving object.
12. [ANATOMY:nervous|heart|lungs|digestive|skeletal|neuron|dna:cx,cy,scale:label:color]
    - Draws a detailed proportional human body with internal organs, animated at 60 FPS (neural pulses, beating heart, breathing lungs, peristalsis, rotating DNA).
    - Example: [ANATOMY:nervous:285,315,1:Human Nervous System:cyan]
    - MANDATORY for ANY biology, anatomy, human body, organ, or medical topic. NEVER approximate a human body with [BOX] rectangles or 4-point [POLYGON] diamonds - the [ANATOMY] tag renders the whole figure for you.
13. [SVG:pathData:x,y,scale:label:color]
    - Renders arbitrary complex vector path data (standard SVG path commands like M/L/C/Z) with a progressive stroke animation, when a shape is too detailed for the other tags.
14. [ACTOR:action:pov:x1,y1->x2,y2:label:color]
    - Draws a fully rigged 15-joint 3D human (head, neck, chest, pelvis, arms with elbows/hands, legs with knees/feet) animated at 60 FPS, with contextual environments (pool ledge + water when diving/swimming, ground track when running).
    - Actions: walk, run, sprint, jog, jump, dive, swim, sit, wave, dance, squat, kick, emote, celebrate, flirt.
    - POV: 3rd (side/iso camera), 2nd (face-to-face), 1st (through the actor's eyes).
    - Examples:
      [ACTOR:sprint:3rd:120,315->445,315:Sprinting Figure:cyan]
      [ACTOR:dive:3rd:120,315->445,315:Diving Into Pool:cyan]
      [ACTOR:wave:2nd::Wave From the Front:cyan]
      [ACTOR:swim:1st::Swimming POV:cyan]
    - MANDATORY for ANY human action, physical skill, sport, dance, movement-by-a-person, or first/second-person POV scene. Never use [ANATOMY] or crude [BOX]/[POLYGON] bodies for these - [ACTOR] animates the motion.
15. [KEYFRAMES:shape:t0,x0,y0,rot0,scale0->t1,x1,y1,rot1,scale1->...:label:color]
    - Invents ANY brand-new animation on the fly from raw time-stamped keyframes (t = 0..1 normalized, x/y pixels, rot degrees, scale multiplier). Loops forever along the dashed path.
    - Shapes: circle, box, arrow, triangle, actor.
    - Example: [KEYFRAMES:circle:0,90,320,0,0.6->0.5,285,170,180,1.4->1,470,320,360,0.6:Energy Curve Ride:cyan]
    - Use when motion is too bespoke for the [ANIMATE] presets (arcs, flips, size pulses, custom trajectories).
16. [GRAPH:From->To|From->To|...:label:color]
    - Auto-layout flowchart / mind-map / system graph: you only list the edges, node coordinates are computed for you. Animated flowing edges + travelling pulses.
    - Example: [GRAPH:Sun->Plants|Plants->Herbivores|Herbivores->Carnivores:Food Chain:cyan]
    - MANDATORY for flowcharts, mind maps, food chains/webs, decision trees, system architecture, dependency/call graphs.
17. [TRACE:v1,v2,...:swap=i,j:ptr=k:label:color]
    - Live array/memory tracer: cells render with your values, the swap pair animates across each other, a pointer arrow bobs under ptr index.
    - Example: [TRACE:42,15,8,99,23:swap=0,1:ptr=2:Bubble Sort Pass 1:yellow]
    - MANDATORY for ANY sorting/searching/pointer/array-manipulation algorithm lesson - one [TRACE] per step, updating swap/ptr as the algorithm progresses. Never describe array swaps only in words.
18. [FIELD:gas|electric|magnetic|fluid:intensity:label:color]
    - Live particle / vector-field simulator: bouncing gas particles with trails, dipole field lines with moving charges, magnetic flux loops, or laminar fluid streamlines. intensity ~ 10..200 (e.g. temperature).
    - Example: [FIELD:gas:temp=80:Kinetic Theory of Gases:orange]
    - MANDATORY for thermodynamics/kinetic theory, electric or magnetic fields, and fluid/airflow topics.
19. [DJ:lofi|synthwave|focus|hype:bpm:label:color]
    - Starts a real-time procedural WebAudio beat (kick + sub-bass + chord pad + hi-hat) with a 60 FPS spectrum visualizer in the overlay. Stops when the overlay is cleared.
    - Example: [DJ:lofi:84:Lo-Fi Study Beat:purple]
    - Use ONLY when the user explicitly asks for music/beat/lo-fi/synthwave/background vibes.
20. [AIM_TRAINER:flick|tracking|micro:label:color]
    - Opens a 60 FPS aim-training arena (moving target, ideal-vs-hand trace, live Path Efficiency % / Overshoot % / Jitter telemetry HUD).
    - Example: [AIM_TRAINER:flick:Flick Precision Drill:cyan]
    - For gaming aim/DPI/sensitivity/conversion questions: emit [AIM_TRAINER:...] for the arena and put your taught numbers in [WRITE:700,...] cards - the exact cross-game sens math (yaw constants, cm/360, FOV focal scaling, 4:3 stretch) is computed for you by the tutor core, so never guess conversion numbers yourself.

CRITICAL TEACHING RULES:
- Motion topics MUST use [ANIMATE:...] (see tag 11); static [CIRCLE]/[BOX] tags freeze after 750ms, [ANIMATE:...] loops forever.
- Human action / scene / POV topics MUST use [ACTOR:...] (see tag 14). Biology, anatomy, organ, and medical topics MUST use [ANATOMY:...] (see tag 12) - NEVER the reverse: a prompt about a person diving, running, swimming, dancing or being seen from 1st/2nd person is an [ACTOR] scene, not an anatomy diagram.
- Sorting/search/pointer lessons MUST use [TRACE:...] (see tag 17), flowcharts/mind-maps/food-chains MUST use [GRAPH:...] (tag 16), particle/field lessons MUST use [FIELD:...] (tag 18), and bespoke trajectories MUST use [KEYFRAMES:...] (tag 15).
- For dating/social reply questions: emit [ACTOR:wingman:2nd::Your Wingman:cyan] plus THREE short reply options you write yourself as separate [WRITE:700,...:...] cards (playful, confident, smooth escalation) - write fresh replies tailored to their exact situation, never generic templates.
- Specialized modes (homework/problem-solving, UGC/TikTok scripts, ghostwriting/blogs/threads, video editing in premiere/davinci/capcut, defensive security concepts like TLS/firewall/XSS, mock interviews & salary negotiation, screen translation/dubbing, trading chart patterns & Fibonacci, PCB/3D-CAD modeling, memory-palace flashcards, and "teach me this app" lessons) automatically attach their own structural visuals (roadmap graphs, script-structure cards, shortcut boards, security diagrams) - focus your spoken text and [WRITE:700,...] cards on the actual subject content instead of re-stating that structure.
- Coding modes (write-code/implement prompts, IDE "i am stuck" pair-programming, algorithm dry-run traces, multi-file scaffolds, bug/error autopsies, SQL query plans & schema optimization, git merge-conflict/time-machine recovery, regex & ReDoS workbenches, localhost API latency profiling, and WCAG UI/UX contrast/touch-target audits) auto-attach a workflow diagram, sandbox verdict, and staged roadmap - spend your spoken text and [WRITE:700,...] cards on the REAL implementation: the actual function logic, the concrete edge cases, and the language-specific idioms for the requested language.
- Never dump the whole drawing in one sentence. Build the diagram progressively across [STEP] 1, [STEP] 2, [STEP] 3, and [STEP] 4.
- Always pair visual diagrams with [WRITE:x,y:...] notes on the right side of the [BOARD] so the student gets both visual drawings and written context.
- Keep each step's spoken text to 2-3 short sentences. Never mention pixel numbers, coordinates, or bracket tags in spoken text.
- You may also use the compact tags [DRAW:CIRCLE:cx,cy,r:label], [DRAW:RECT:x,y,w,h:label], [DRAW:POLYGON:x1,y1,...:label], [DRAW:ARROW:x1,y1,x2,y2:label] if simpler.
- all lowercase, casual, warm. no emojis, no markdown, no lists in the spoken text.`;

export class ClaudeAPI {
  // qwen2.5vl:3b (verified working on this machine's Ollama 0.34.4).
  // Deviation: original default llama3.2-vision - Ollama 0.34.x dropped the
  // 'mllama' architecture (GitHub ollama#16490), so it loads on 0.24.0 only.
  public model: string = 'qwen2.5vl:3b';
  private ollamaUrl: string = process.env.OLLAMA_URL || 'http://127.0.0.1:11434/api/chat';

  static readonly companionVoiceResponseSystemPrompt = VISUAL_TUTOR_SYSTEM_PROMPT;

  static readonly onboardingDemoSystemPrompt = `you're clicky, a small blue cursor buddy on the user's screen. find ONE specific item near the center of the screen (20%-80% width/height), make a 3-6 word lowercase comment, and append [STEP][BOX:x,y,w,h:what you see][POINT:x,y:here][/STEP].`;

  async analyzeImageStreaming(
    captures: CompanionScreenCapture[],
    systemPrompt: string,
    conversationHistory: { userTranscript: string; assistantResponse: string }[],
    userPrompt: string
  ): Promise<string> {
    const primary = captures[0];
    const width = primary?.screenshotWidthInPixels || 1280;
    const height = primary?.screenshotHeightInPixels || 720;

    const dimensionContext = captures
      .map(
        (c) =>
          `${c.label} (image dimensions: ${c.screenshotWidthInPixels}x${c.screenshotHeightInPixels} pixels)`
      )
      .join('\n');

    // 1. Local Ollama ONLY if an Ollama model is explicitly selected
    if (this.model !== 'free-cloud-vision') {
      try {
        const ollamaMessages: any[] = [
          { role: 'system', content: systemPrompt },
          {
            role: 'user',
            content: `${dimensionContext}\n\n${userPrompt}`,
            images: captures.map((c) => c.imageDataBase64),
          },
        ];
        const response = await fetch(this.ollamaUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model: this.model,
            messages: ollamaMessages,
            stream: false,
            // APP LOGIC FIX: VISUAL_TUTOR_SYSTEM_PROMPT alone is ~4,100 tokens, so the
            // default num_ctx=4096 makes every local call fail with HTTP 400
            // "exceeds the available context size" and silently fall back to cloud/offline.
            options: { num_ctx: 8192 },
          }),
        });
        if (response.ok) {
          const data = await response.json();
          if (data?.message?.content) {
            return data.message.content;
          }
        }
      } catch (err) {
        console.warn('⚠️ Ollama not running locally, falling back to Free Cloud Vision automatically.');
      }
    }

    // 2. 100% Free keyless Cloud Vision
    try {
      const messages: any[] = [{ role: 'system', content: systemPrompt }];
      for (const entry of conversationHistory) {
        messages.push({ role: 'user', content: entry.userTranscript });
        messages.push({ role: 'assistant', content: entry.assistantResponse });
      }

      const userContent: any[] = [
        { type: 'text', text: `${dimensionContext}\n\nUser request: ${userPrompt}` },
      ];
      if (primary) {
        userContent.push({
          type: 'image_url',
          image_url: { url: `data:image/jpeg;base64,${primary.imageDataBase64}` },
        });
      }
      messages.push({ role: 'user', content: userContent });

      const res = await fetch('https://text.pollinations.ai/openai', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: 'openai', messages, temperature: 0.3 }),
      });

      if (res.ok) {
        const data = await res.json();
        const reply = data?.choices?.[0]?.message?.content;
        if (reply && typeof reply === 'string' && reply.trim().length > 0) {
          return reply;
        }
      }
    } catch (cloudErr) {
      console.warn('Cloud vision error:', cloudErr);
    }

    // 3. OFFLINE FALLBACK (only reached when every network path failed).
    //    Dynamic: builds a lesson for whatever equation was typed; never a canned topic.
    const mathLesson = buildDynamicMathLesson(userPrompt, width, height);
    if (mathLesson) return mathLesson;

    const cx = Math.round(width * 0.5);
    const cy = Math.round(height * 0.5);
    return `[STEP][BOARD:60,60,760,440:offline mode][WRITE:90,140:connect a vision model to teach "${userPrompt.slice(0, 40)}"][/STEP][STEP]i can't reach a vision model right now, but i put a marker on your screen. [POINT:${cx},${cy}:right here][/STEP]`;
  }

  static parseResponseAndDrawings(responseText: string): PointingParseResult {
    const drawCommands: DrawCommand[] = [];

    const drawRegex =
      /\[DRAW:(CIRCLE|RECT|PARALLELOGRAM|POLYGON|DECAGON|HEXAGON|PENTAGON|OCTAGON|TRIANGLE|ARROW|LINE|CURVE|AXES):([0-9.,\s-]+)(?::([^\]]*))?\]/gi;
    let match: RegExpExecArray | null;
    while ((match = drawRegex.exec(responseText)) !== null) {
      const type = match[1].toUpperCase() as DrawShapeType;
      const coords = match[2]
        .split(',')
        .map((n) => parseFloat(n.trim()))
        .filter((n) => !isNaN(n));
      const label = match[3] ? match[3].trim() : undefined;
      if (coords.length >= 2) {
        drawCommands.push({ type, coords, label });
      }
    }

    const pointPattern =
      /\[POINT:(?:none|(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)(?::([^\]:\s][^\]:]*?))?(?::screen(\d+))?)\]/i;
    const pointMatch = responseText.match(pointPattern);

    const cleanSpokenText = responseText
      .replace(drawRegex, '')
      .replace(pointPattern, '')
      .replace(/\[(?:DRAW|POINT)[^\]]*\]?/gi, '')
      .replace(/\s+/g, ' ')
      .trim();

    if (!pointMatch || !pointMatch[1] || !pointMatch[2]) {
      if (drawCommands.length > 0) {
        const last = drawCommands[drawCommands.length - 1];
        return {
          spokenText: cleanSpokenText,
          coordinate: { x: last.coords[0], y: last.coords[1] },
          elementLabel: last.label || 'right here!',
          screenNumber: 1,
          drawCommands,
        };
      }
      return {
        spokenText: cleanSpokenText,
        coordinate: null,
        elementLabel: null,
        screenNumber: null,
        drawCommands,
      };
    }

    return {
      spokenText: cleanSpokenText,
      coordinate: { x: parseFloat(pointMatch[1]), y: parseFloat(pointMatch[2]) },
      elementLabel: pointMatch[3] ? pointMatch[3].trim() : null,
      screenNumber: pointMatch[4] ? parseInt(pointMatch[4], 10) : null,
      drawCommands,
    };
  }
}

const FUNCTION_WORDS = /(sin|cos|tan|log|ln|sqrt|exp|abs|pi|max|min)/gi;

function normalizeMathShorthand(raw: string): string {
  return raw
    .replace(/×/g, '*')
    .replace(/÷/g, '/')
    .replace(/[−–—]/g, '-')
    .replace(/²/g, '^2')
    .replace(/³/g, '^3')
    .replace(/\bsine\s*\(\s*x?\s*\)?|\bsine\b/gi, 'sin(x)')
    .replace(/\bcosine\b/gi, 'cos(x)')
    .replace(/\btangent\b/gi, 'tan(x)')
    .replace(/\blogarithm\b/gi, 'log(x)')
    .replace(/\b(sqrt|sin|cos|tan|log|ln|exp)\s*x(?![a-z0-9])/gi, '$1(x)')
    .replace(/\b(sqrt|sin|cos|tan|log|ln|exp)x(?=\s|$|\))/gi, '$1(x)')
    .replace(/\s+/g, ' ')
    .trim();
}

function isMathLikeToken(word: string): boolean {
  const t = word.replace(/[\s,]/g, '');
  if (!t) return false;
  if (/^[+\-*/^()=]+$/.test(t)) return true;
  const letters = t.replace(/[^a-zA-Z]/g, '');
  const residue = letters.replace(FUNCTION_WORDS, '').replace(/[xe]/gi, '');
  if (residue.length > 0) return false;
  return /[x\d+\-*/^()=]/i.test(t);
}

function stripProse(raw: string): string {
  return raw
    .split(/\s+/)
    .filter(isMathLikeToken)
    .join(' ')
    .replace(/^[-+*/^()=]+\s*/, '')
    .replace(/\s*[-+*/^]+$/, '')
    .trim();
}

/**
 * Translates a student-written expression into valid JavaScript:
 * implicit multiplication (3x^2 -> 3*x^2) and trig/log -> Math.*.
 */
function toJavaScriptExpression(raw: string): string {
  let expr = normalizeMathShorthand(raw)
    .replace(/^y\s*=\s*/i, '')
    .replace(/^f\s*\(\s*x\s*\)\s*=\s*/i, '')
    .trim();

  expr = expr
    .replace(/(\d)([a-zA-Z(])/g, '$1*$2')
    .replace(/(\))(\d|[a-zA-Z(])/g, '$1*$2')
    .replace(/(x)(\()/gi, '$1*$2');

  return expr
    .replace(/\^/g, '**')
    .replace(/\b(asin|acos|atan|log10|sin|cos|tan|sqrt|abs|ln|log|exp)\s*\(/gi, 'Math.$1(')
    .replace(/\bpi\b/gi, 'Math.PI');
}

/**
 * Strict validator used BEFORE any [PLOT] is accepted (CompanionManager) and
 * by the overlay. Guarantees we never render a nonsense curve or silently fall
 * back to x^2.
 */
export function isValidMathExpression(raw: unknown): boolean {
  if (typeof raw !== 'string') return false;
  const expr = normalizeMathShorthand(raw).trim();
  if (!expr || expr.length > 120) return false;
  if (!/[x]/i.test(expr) && !/(sin|cos|tan|log|ln|sqrt|exp)/i.test(expr)) return false;
  if (/[-+*/^]\s*$/.test(expr) || /^\s*[-+*/^]/.test(expr)) return false;
  if ((expr.match(/\(/g) || []).length !== (expr.match(/\)/g) || []).length) return false;

  const letters = expr.replace(/[^a-zA-Z]/g, '');
  const residue = letters.replace(FUNCTION_WORDS, '').replace(/[xe]/gi, '');
  if (residue.length > 0) return false;

  try {
    const src = toJavaScriptExpression(expr);
    const fn = new Function('x', `"use strict"; return (${src});`) as (x: number) => unknown;
    let finite = 0;
    for (const x of [-3, -1, 0.5, 2, 4]) {
      const v = fn(x);
      if (typeof v !== 'number') return false;
      if (Number.isFinite(v)) finite += 1;
    }
    return finite >= 3;
  } catch {
    return false;
  }
}

/**
 * Extracts a mathematical expression from a student prompt. Strict: an
 * expression is only returned when it is explicitly written (y = ..., f(x) = ...)
 * or the prompt clearly asks to plot/graph it AND the remaining tokens parse as
 * real math. Never guesses, never defaults.
 */
export function extractMathExpression(prompt: string): string | null {
  const clean = prompt.trim();
  const explicitEq = clean.match(/\b(?:y|f\s*\(\s*x\s*\))\s*=\s*([0-9xX+\-*/^().\s]+|\b(?:sin|cos|tan|log|ln|sqrt|exp)\s*\([^)]+\)[0-9xX+\-*/^().\s]*)/i);
  if (explicitEq && explicitEq[1]) {
    const expr = explicitEq[1].replace(/\b(and|on|in|with|please|for|screen|graph|plot|explain|teach).*$/i, '').trim();
    if (expr.length > 0 && /[x0-9]/i.test(expr)) return expr;
  }
  if (/\b(plot|graph)\b/i.test(clean)) {
    const mathToken = clean.match(/((?:[-+]?\d*\.?\d*\*?x\s*\^\s*[-+]?\d+[\s+\-*/0-9x^.]*)|(?:\b(?:sin|cos|tan|log|ln|sqrt)\s*\(\s*x[^)]*\)))/i);
    if (mathToken && mathToken[1]) return mathToken[1].trim();
  }
  return null;
}

/**
 * Detects every plottable curve mentioned in a plot/graph request
 * (e.g. "logx and sine curve" -> ['log(x)', 'sin(x)']) so offline lessons stay
 * dynamic instead of defaulting to x^2.
 */
export function detectPlottableExpressions(prompt: string): string[] {
  const lower = prompt.toLowerCase();
  if (!/\b(plot|graph|curve|function|equation|parabola)\b/.test(lower)) return [];

  const out: string[] = [];
  const push = (e: string) => {
    if (!out.includes(e)) out.push(e);
  };

  if (/\blog\s*\(?x|\blogx\b/.test(lower)) push('log(x)');
  if (/\bln\s*\(?x|\blnx\b/.test(lower)) push('ln(x)');
  if (/\bsin\s*\(?x|\bsine\b/.test(lower)) push('sin(x)');
  if (/\bcos\s*\(?x|\bcosine\b/.test(lower)) push('cos(x)');
  if (/\btan\s*\(?x|\btangent\b/.test(lower)) push('tan(x)');
  if (/\bsqrt\s*\(?x|\bsquare root\b/.test(lower)) push('sqrt(x)');
  if (/x\s*\^\s*4|x\u2074|quartic/.test(lower)) push('x^4');
  if (/x\s*\^\s*3|x\u00b3|cubic/.test(lower)) push('x^3');
  if (/x\s*\^\s*2|x\u00b2|parabola|quadratic/.test(lower)) push('x^2');

  return out.filter(isValidMathExpression);
}

/**
 * Fully dynamic offline math lesson: whatever equation the student typed gets plotted.
 * Never runs before the LLM call - only as a last-resort fallback.
 */
export function buildDynamicMathLesson(textPrompt: string, width: number, height: number): string | null {
  const explicitExpr = extractMathExpression(textPrompt);
  const detected = detectPlottableExpressions(textPrompt);
  const namedFn = (e: string) => /\b(sin|cos|tan|log|ln|sqrt|exp)\s*\(/i.test(e);

  const exprs = explicitExpr
    ? [
        explicitExpr,
        ...detected.filter(
          (d) => d !== explicitExpr && namedFn(d) && !explicitExpr.includes(d.replace(/\(.*$/, ''))
        ),
      ]
    : detected;
  if (exprs.length === 0) return null;
  const expr = exprs[0];

  const cx = Math.round(width * 0.5);
  const cy = Math.round(height * 0.5);
  const plots = exprs
    .slice(0, 3)
    .map(
      (e, i) =>
        `[PLOT:${e}:-6,6:${Math.round(width * 0.1)},${Math.round(height * 0.2)},${Math.round(width * 0.45)},${Math.round(height * 0.55)}:${i === 0 ? 'cyan' : i === 1 ? 'yellow' : 'magenta'}]`
    )
    .join('');
  const label = exprs.join(' and ');

  return [
    '[STEP]',
    `[BOARD:60,60,${Math.round(width * 0.75)},${Math.round(height * 0.8)}:${label}]`,
    `[WRITE:${cx + 60},${cy - 180}:function: ${label}:cyan]`,
    `[WRITE:${cx + 60},${cy - 140}:1. set up the x and y axes:white]`,
    `let's break down ${label} step by step. first we set up the coordinate plane so we can watch how y changes as x moves from negative to positive.`,
    '[/STEP]',
    '[STEP]',
    plots,
    `[WRITE:${cx + 60},${cy - 80}:2. plot the curve across -6 to 6:green]`,
    `now watch the curve draw itself across the axes. follow the glowing pen tip and notice where it rises, where it falls, and where it crosses the axes.`,
    '[/STEP]',
    '[STEP]',
    `[WRITE:${cx + 60},${cy - 20}:3. key features to inspect:yellow]`,
    `[WRITE:${cx + 60},${cy + 20}:y-intercept: plug in x = 0:white]`,
    `[WRITE:${cx + 60},${cy + 60}:roots: wherever y equals zero:white]`,
    `[WRITE:${cx + 60},${cy + 100}:slope: how fast y changes as x grows:white]`,
    `to master any graph like ${label}, always check three anchors: the y intercept, the roots where the curve crosses the horizontal axis, and how steep the slope gets.`,
    '[/STEP]',
  ].join('\n');
}
