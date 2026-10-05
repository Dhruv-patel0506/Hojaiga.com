import { screen } from 'electron';
import { ClaudeAPI, VISUAL_TUTOR_SYSTEM_PROMPT, isValidMathExpression } from './ClaudeAPI';
// APP LOGIC FIX: re-export so consumers (tests, lesson chain) can import the
// math extractor from its public facade without reaching into ClaudeAPI.
export { extractMathExpression } from './ClaudeAPI';
import { EdgeNeuralTTSClient } from './EdgeNeuralTTSClient';
import { WindowsNativeTTSProvider } from './WindowsNativeWrappers';
import { CompanionScreenCaptureUtility } from './CompanionScreenCaptureUtility';
import { OverlayWindowManager } from './OverlayWindowManager';
import { MenuBarPanelManager } from './MenuBarPanelManager';
import { GlobalPushToTalkShortcutMonitor, ShortcutTransition } from './GlobalPushToTalkShortcutMonitor';
import { BuddyDictationManager } from './BuddyDictationManager';
import { ClickyAnalytics } from './ClickyAnalytics';
import { CompanionVoiceState } from './types';
import { enrichGamingAimForPrompt } from './GamingAimAndSensEngine';
import { DynamicAppScannerAndTeacher } from './DynamicAppScannerAndTeacher';
import { HomeworkSocraticTutor } from './HomeworkSocraticTutor';
import { UGCContentEngine } from './UGCContentEngine';
import { GhostwritingEngine } from './GhostwritingEngine';
import { ProVideoEditorDirector } from './ProVideoEditorDirector';
import { CyberDefenseTutorEngine } from './CyberDefenseTutorEngine';
import { InterviewCoachEngine } from './InterviewCoachEngine';
import { LiveScreenTranslator } from './LiveScreenTranslator';
import { ChartPatternTutor } from './ChartPatternTutor';
import { HardwareSchematicTutor } from './HardwareSchematicTutor';
import { MemoryPalaceEngine } from './MemoryPalaceEngine';
import { HojaigaIntegrationBridge } from './HojaigaIntegrationBridge';
import { PolyglotVisualArchitectCoder } from './PolyglotVisualArchitectCoder';
import { LiveIDEPairProgrammer } from './LiveIDEPairProgrammer';
import { VisualAlgorithmStepDebugger } from './VisualAlgorithmStepDebugger';
import { FullStackScaffoldAndVerifyEngine } from './FullStackScaffoldAndVerifyEngine';
import { BugRootCauseAutopsyEngine } from './BugRootCauseAutopsyEngine';
import { SQLQueryPlanAndSchemaVisualizer } from './SQLQueryPlanAndSchemaVisualizer';
import { GitTimeMachineAndConflictResolver } from './GitTimeMachineAndConflictResolver';
import { RegexAndParserVisualWorkbench } from './RegexAndParserVisualWorkbench';
import { APILoadAndLatencySimulator } from './APILoadAndLatencySimulator';
import { UIUXAccessibilityAndDesignCritic } from './UIUXAccessibilityAndDesignCritic';
import { createTeacherAgent, createDynamicAppTeacher, createActionExplorer } from './vision_platform/index';

export interface ParsedOverlayCommand {
  type: string;
  [key: string]: any;
}

export interface ParsedVisualTags {
  spokenText: string;
  commands: ParsedOverlayCommand[];
  point: { x: number; y: number; label: string | null } | null;
}

const REGULAR_POLYGON_SIDES: Record<string, number> = {
  DECAGON: 10,
  OCTAGON: 8,
  HEXAGON: 6,
  PENTAGON: 5,
  TRIANGLE: 3,
};

function num(v: string | undefined, fallback: number): number {
  const n = parseFloat(String(v));
  return Number.isFinite(n) ? n : fallback;
}

function parsePairs(body: string, dims: number): { x: number; y: number; z?: number }[] {
  return body
    .split('->')
    .map((pair) => {
      const parts = pair.split(',').map((p) => parseFloat(p.trim()));
      if (dims === 3) {
        return { x: parts[0] || 0, y: parts[1] || 0, z: parts[2] || 0 };
      }
      return { x: parts[0] || 0, y: parts[1] || 0 };
    })
    .filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));
}

function regularPolygonPoints(cx: number, cy: number, r: number, sides: number) {
  const pts: { x: number; y: number }[] = [];
  for (let i = 0; i < sides; i++) {
    const angle = (i * 2 * Math.PI) / sides - Math.PI / 2;
    pts.push({ x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) });
  }
  return pts;
}

/**
 * Parses every visual tag the tutor system prompt can emit (plus the legacy
 * [DRAW:...] vocabulary) into overlay commands, and returns the spoken text
 * with ALL bracket tags stripped so TTS never reads coordinates aloud.
 */
export function parseVisualTagsFromText(rawSegment: string): ParsedVisualTags {
  const commands: ParsedOverlayCommand[] = [];
  let point: ParsedVisualTags['point'] = null;

  const normalized = rawSegment.replace(/\[\s*([A-Z0-9_]+)\s*:/gi, (_, tag) => `[${tag.toUpperCase()}:`);
  const tagRegex = /\[([A-Z0-9_]+):([^\]]+)\]/gi;
  let match: RegExpExecArray | null;

  while ((match = tagRegex.exec(normalized)) !== null) {
    const tag = match[1].toUpperCase();
    const body = match[2].trim();
    const parts = body.split(':');

    if (tag === 'BOARD') {
      const [x, y, w, h] = (parts[0] || '80,80,840,520').split(',').map(Number);
      commands.push({
        type: 'BOARD',
        x: x || 80,
        y: y || 80,
        w: w || 840,
        h: h || 520,
        label: parts.slice(1).join(':') || '',
      });
    } else if (tag === 'WRITE' || tag === 'TEXT' || tag === 'LABEL') {
      const [x, y] = (parts[0] || '520,180').split(',').map(Number);
      const colorCandidate = parts.length > 2 ? parts[parts.length - 1] : undefined;
      const textContent = parts.length > 2 ? parts.slice(1, -1).join(':') : parts[1] || '';
      commands.push({ type: 'WRITE', x: x || 520, y: y || 180, label: textContent, color: colorCandidate });
    } else if (tag === 'PLOT') {
      const expr = (parts[0] || '').trim();
      // Strict gate: never plot an unvalidated expression, never default to x^2.
      if (!isValidMathExpression(expr)) continue;
      const [xMin, xMax] = (parts[1] || '-6,6').split(',').map(Number);
      const [x, y, w, h] = (parts[2] || '120,150,400,360').split(',').map(Number);
      commands.push({
        type: 'PLOT',
        expr,
        xMin: Number.isFinite(xMin) ? xMin : -6,
        xMax: Number.isFinite(xMax) ? xMax : 6,
        x: x || 120,
        y: y || 150,
        w: w || 400,
        h: h || 360,
        color: parts[3] || 'cyan',
      });
    } else if (tag === 'SHAPE3D') {
      const shapeType = parts[0] || 'cube';
      const [cx, cy, size] = (parts[1] || '320,340,100').split(',').map(Number);
      const [pitch, yaw] = (parts[2] || '0.42,0.65').split(',').map(Number);
      commands.push({
        type: 'SHAPE3D',
        shapeType,
        cx: cx || 320,
        cy: cy || 340,
        size: size || 100,
        pitch: Number.isFinite(pitch) ? pitch : 0.42,
        yaw: Number.isFinite(yaw) ? yaw : 0.65,
        label: parts[3] || '',
        color: parts[4] || 'yellow',
      });
    } else if (tag === 'POLY3D') {
      const points3D = parsePairs(parts[0] || '', 3);
      const [cx, cy, scale] = (parts[1] || '320,340,90').split(',').map(Number);
      commands.push({
        type: 'POLY3D',
        points3D,
        cx: cx || 320,
        cy: cy || 340,
        scale: scale || 90,
        dashed: (parts[2] || '').toLowerCase() === 'dashed',
        label: parts[3] || '',
        color: parts[4] || 'cyan',
      });
    } else if (tag === 'CURVE' || tag === 'POLYGON') {
      commands.push({
        type: tag,
        points: parsePairs(parts[0] || '', 2),
        label: parts[1] || '',
        color: parts[2] || (tag === 'CURVE' ? 'green' : 'cyan'),
      });
    } else if (tag === 'ARROW' || tag === 'LINE') {
      const pts = parsePairs(parts[0] || '', 2);
      if (pts.length >= 2) {
        commands.push({
          type: 'ARROW',
          x1: pts[0].x,
          y1: pts[0].y,
          x2: pts[1].x,
          y2: pts[1].y,
          label: parts[1] || '',
          color: parts[2] || 'red',
        });
      }
    } else if (tag === 'BOX' || tag === 'RECT') {
      const [x, y, w, h] = (parts[0] || '200,200,120,80').split(',').map(Number);
      commands.push({ type: 'BOX', x, y, w, h, label: parts[1] || '', color: parts[2] || 'cyan' });
    } else if (tag === 'CIRCLE' || tag === 'BEACON') {
      const [x, y, r] = (parts[0] || '300,300,32').split(',').map(Number);
      commands.push({ type: 'CIRCLE', x, y, r: r || 32, label: parts[1] || '', color: parts[2] || 'yellow' });
    } else if (tag === 'POINT') {
      if (!/^none/i.test(parts[0] || '')) {
        const [x, y] = (parts[0] || '').split(',').map(Number);
        if (Number.isFinite(x) && Number.isFinite(y)) {
          point = { x, y, label: parts[1] || null };
        }
      }
    } else if (tag === 'DRAW') {
      // Legacy vocabulary -> new commands
      const type = (parts[0] || '').toUpperCase();
      const coords = (parts[1] || '')
        .split(',')
        .map((n) => parseFloat(n.trim()))
        .filter((n) => Number.isFinite(n));
      const label = parts[2] || '';

      if (type === 'CIRCLE' && coords.length >= 3) {
        commands.push({ type: 'CIRCLE', x: coords[0], y: coords[1], r: coords[2], label, color: 'red' });
      } else if (type === 'RECT' && coords.length >= 4) {
        commands.push({ type: 'BOX', x: coords[0], y: coords[1], w: coords[2], h: coords[3], label, color: 'red' });
      } else if (type === 'PARALLELOGRAM' && coords.length >= 4) {
        const [x, y, w, h] = coords;
        const skew = coords[4] !== undefined ? coords[4] : 60;
        commands.push({
          type: 'POLYGON',
          points: [
            { x: x + skew, y },
            { x: x + w + skew, y },
            { x: x + w, y: y + h },
            { x, y: y + h },
          ],
          label,
          color: 'red',
        });
      } else if (type === 'ARROW' && coords.length >= 4) {
        commands.push({
          type: 'ARROW',
          x1: coords[0],
          y1: coords[1],
          x2: coords[2],
          y2: coords[3],
          label,
          color: 'red',
        });
      } else if (type === 'CURVE' && coords.length >= 4) {
        commands.push({ type: 'CURVE', points: parsePairs((parts[1] || '').trim(), 2), label, color: 'cyan' });
      } else if (type === 'AXES' && coords.length >= 4) {
        const [ox, oy, w, h] = coords;
        commands.push({
          type: 'CURVE',
          points: [
            { x: ox - w * 0.25, y: oy },
            { x: ox + w * 0.85, y: oy },
          ],
          label: '',
          color: 'white',
        });
        commands.push({
          type: 'CURVE',
          points: [
            { x: ox, y: oy - h * 0.6 },
            { x: ox, y: oy + h * 0.6 },
          ],
          label: '',
          color: 'white',
        });
      } else if (REGULAR_POLYGON_SIDES[type] && coords.length >= 3) {
        commands.push({
          type: 'POLYGON',
          points: regularPolygonPoints(coords[0], coords[1], coords[2], REGULAR_POLYGON_SIDES[type]),
          label,
          color: 'blue',
        });
      } else if (type === 'POLYGON' && coords.length >= 6) {
        commands.push({ type: 'POLYGON', points: parsePairs(parts[1] || '', 2), label, color: 'red' });
      }
    } else if (tag === 'ANIMATE' || tag === 'WHEEL' || tag === 'MOVE' || tag === 'GIF') {
      // Continuous 60 FPS looping motion primitives ([ANIMATE:...] renders forever,
      // unlike static shapes which freeze after their 750ms draw-in).
      //   [ANIMATE:wheel:110,310->460,310:54:Rolling Wheel:cyan]
      //   [ANIMATE:spring:95,300:75:Simple Harmonic Motion:cyan]
      //   [ANIMATE:pendulum:280,145:190:Swinging Pendulum:yellow]
      //   [ANIMATE:projectile:100,380->460,380,170:Projectile Trajectory:green]
      //   [ANIMATE:orbit:280,295:135:Orbital Motion:cyan]
      //   [ANIMATE:wave:90,290:65:Traveling Wave:purple]
      //   [ANIMATE:move:110,300->450,300:42:Moving Block:cyan]
      //   [WHEEL:x1,y1->x2,y2:r:label:color] (compact legacy form)
      const isLegacyWheel = tag === 'WHEEL';
      const preset = isLegacyWheel ? 'wheel' : (parts[0] || 'wheel').toLowerCase();
      const coordIdx = isLegacyWheel ? 0 : 1;
      const coordPart = (parts[coordIdx] || '').trim();
      const params = (parts[coordIdx + 1] || '')
        .split(',')
        .map((v) => parseFloat(v.trim()))
        .filter((v) => Number.isFinite(v));

      const rawPairs = coordPart
        ? coordPart.split('->').map((pair) => {
            const nums = pair.split(',').map((v) => parseFloat(v.trim()));
            return {
              x: Number.isFinite(nums[0]) ? nums[0] : undefined,
              y: Number.isFinite(nums[1]) ? nums[1] : undefined,
              extra: Number.isFinite(nums[2]) ? nums[2] : undefined,
            };
          })
        : [];
      const pts = rawPairs.filter((p) => p.x !== undefined && p.y !== undefined);
      const start = pts[0] || { x: 110, y: 310 };
      const end = pts[1] || { x: (start.x ?? 110) + 350, y: start.y ?? 310 };

      commands.push({
        type: 'ANIMATE',
        preset,
        x1: start.x ?? 110,
        y1: start.y ?? 310,
        x2: end.x ?? 460,
        y2: end.y ?? start.y ?? 310,
        points: pts.map((p) => ({ x: p.x as number, y: p.y as number })),
        r: params[0] ?? pts[0]?.extra ?? 54,
        peakH: pts[1]?.extra ?? params[1],
        label: parts[coordIdx + 2] || `Animated ${preset}`,
        color: parts[coordIdx + 3] || 'cyan',
        loop: true,
      });
    } else if (tag === 'ANATOMY' || tag === 'ORGAN' || tag === 'BIOLOGY' || tag === 'BODY') {
      // Format: [ANATOMY:nervous|heart|lungs|digestive|skeletal|neuron|dna:cx,cy,scale:label:color]
      const system = (parts[0] || 'nervous').toLowerCase();
      const [cx, cy, scale] = (parts[1] || '285,315,1').split(',').map(Number);
      commands.push({
        type: 'ANATOMY',
        system,
        cx: cx || 285,
        cy: cy || 315,
        scale: scale || 1,
        label: parts[2] || `Human ${system} system`,
        color: parts[3] || 'cyan',
        loop: true,
      });
    } else if (tag === 'ACTOR' || tag === 'HUMAN' || tag === 'ACTION' || tag === 'EMOTE') {
      // Format: [ACTOR:action:pov:x1,y1->x2,y2:label:color]
      // 15-joint kinematic rig, 3rd/2nd/1st person cameras, loops forever.
      //   [ACTOR:sprint:3rd:120,315->445,315:Sprinting Figure:cyan]
      //   [ACTOR:dive:3rd:120,315->445,315:Diving Into Pool:cyan]
      //   [ACTOR:wave:2nd::Wave From the Front:cyan]
      //   [ACTOR:swim:1st::Swimming POV:cyan]
      const action = (parts[0] || 'walk').toLowerCase();
      const povRaw = (parts[1] || '3rd').toLowerCase();
      const pov = /1st|first|fpv/.test(povRaw)
        ? '1st'
        : /2nd|second|front|face/.test(povRaw)
          ? '2nd'
          : '3rd';
      const coordPart = (parts[2] || '').trim();
      const pts = coordPart
        ? coordPart.split('->').map((pair) => {
            const nums = pair.split(',').map((v) => parseFloat(v.trim()));
            return { x: nums[0], y: nums[1] };
          })
        : [];
      const start = { x: pts[0]?.x, y: pts[0]?.y };
      const end = { x: pts[1]?.x, y: pts[1]?.y };
      commands.push({
        type: 'ACTOR',
        action,
        pov,
        x1: Number.isFinite(start.x as number) ? (start.x as number) : 120,
        y1: Number.isFinite(start.y as number) ? (start.y as number) : 315,
        x2: Number.isFinite(end.x as number) ? (end.x as number) : 445,
        y2: Number.isFinite(end.y as number) ? (end.y as number) : 315,
        cx: Number.isFinite(start.x as number) ? (start.x as number) : 275,
        cy: Number.isFinite(start.y as number) ? (start.y as number) : 315,
        label: parts[3] || `Dynamic Human: ${action.toUpperCase()}`,
        color: parts[4] || 'cyan',
        loop: true,
      });
    } else if (tag === 'KEYFRAMES') {
      // Format: [KEYFRAMES:shape:t0,x0,y0,rot0,scale0->t1,x1,y1,rot1,scale1:label:color]
      const shape = (parts[0] || 'circle').toLowerCase();
      const keyframes = (parts[1] || '')
        .split('->')
        .map((frameStr, idx, arr) => {
          const [t, x, y, rot, scale] = frameStr.split(',').map(Number);
          return {
            t: Number.isFinite(t) ? t : idx / Math.max(1, arr.length - 1),
            x: Number.isFinite(x) ? x : 140 + idx * 120,
            y: Number.isFinite(y) ? y : 300,
            rot: Number.isFinite(rot) ? rot : 0,
            scale: Number.isFinite(scale) ? scale : 1,
          };
        })
        .filter((f) => Number.isFinite(f.x) && Number.isFinite(f.y));
      if (keyframes.length < 2) continue;
      commands.push({
        type: 'KEYFRAMES',
        shape,
        keyframes,
        label: parts[2] || `Custom Keyframe Animation (${shape})`,
        color: parts[3] || 'cyan',
        loop: true,
      });
    } else if (tag === 'GRAPH' || tag === 'FLOWCHART' || tag === 'MINDMAP') {
      // Format: [GRAPH:From->To|From->To:label:color]
      const edges: { from: string; to: string }[] = [];
      const nodeSet = new Set<string>();
      for (const edgeStr of (parts[0] || '').split('|')) {
        const [from, to] = edgeStr.split('->').map((s) => (s || '').trim());
        if (from && to) {
          edges.push({ from, to });
          nodeSet.add(from);
          nodeSet.add(to);
        }
      }
      if (!edges.length) continue;
      commands.push({
        type: 'GRAPH',
        nodes: Array.from(nodeSet),
        edges,
        nodePositions: {},
        label: parts[1] || 'System Architecture & Flow',
        color: parts[2] || 'cyan',
        loop: true,
      });
    } else if (tag === 'TRACE') {
      // Format: [TRACE:v1,v2,...:swap=i,j:ptr=k:label:color]
      const values = (parts[0] || '')
        .split(',')
        .map((s) => s.trim())
        .filter((s) => s.length > 0);
      if (!values.length) continue;
      const meta = `${parts[1] || ''}:${parts[2] || ''}`;
      const swapMatch = meta.match(/swap\s*=\s*(\d+)\s*,\s*(\d+)/i);
      const ptrMatch = meta.match(/ptr\s*=\s*(\d+)/i);
      commands.push({
        type: 'TRACE',
        values,
        swapIndices: swapMatch ? [Number(swapMatch[1]), Number(swapMatch[2])] : [0, 1],
        pointerIndex: ptrMatch ? Number(ptrMatch[1]) : 0,
        label: parts[3] || 'Live Memory & Array Step-Tracer',
        color: parts[4] || 'yellow',
        loop: true,
      });
    } else if (tag === 'FIELD') {
      // Format: [FIELD:gas|electric|magnetic|fluid:intensity:label:color]
      const fieldType = (parts[0] || 'gas').toLowerCase();
      const intensity = Number(String(parts[1] || '60').replace(/[^0-9.]/g, '')) || 60;
      commands.push({
        type: 'FIELD',
        fieldType,
        intensity,
        label: parts[2] || `Live ${fieldType.toUpperCase()} Field Simulation`,
        color: parts[3] || 'orange',
        loop: true,
      });
    } else if (tag === 'DJ' || tag === 'MUSIC' || tag === 'BEAT') {
      // Format: [DJ:lofi|synthwave|focus|hype:bpm:label:color]
      const genre = (parts[0] || 'lofi').toLowerCase();
      const bpm = Number(parts[1]) || 84;
      const chordRoot =
        genre === 'hype' ? 220 : genre === 'synthwave' ? 196 : genre === 'focus' ? 174.61 : 261.63;
      commands.push({
        type: 'DJ',
        genre,
        bpm,
        chordRoot,
        label: parts[2] || `Live WebAudio ${genre.toUpperCase()} Synth (${bpm} BPM)`,
        color: parts[3] || 'purple',
        loop: true,
      });
    } else if (tag === 'AIM_TRAINER' || tag === 'AIM' || tag === 'FOSTRACER') {
      // Format: [AIM_TRAINER:flick|tracking|micro:label:color]
      const drillMode = /track/i.test(parts[0] || '')
        ? 'tracking'
        : /micro/i.test(parts[0] || '')
          ? 'micro'
          : 'flick';
      commands.push({
        type: 'AIM_TRAINER',
        drillMode,
        dpi: 800,
        sourceSens: 0.35,
        targetSens: 0,
        cmPer360: 0,
        label: parts[1] || `Live ${drillMode.toUpperCase()} Precision Drill`,
        color: parts[2] || 'cyan',
        loop: true,
      });
    } else if (tag === 'SVG') {
      // Format: [SVG:pathData:x,y,scale:label:color] - arbitrary vector paths.
      const d = parts[0] || '';
      const [cx, cy, scale] = (parts[1] || '250,250,1').split(',').map(Number);
      commands.push({
        type: 'SVG',
        d,
        cx: cx || 250,
        cy: cy || 250,
        scale: scale || 1,
        label: parts[2] || '',
        color: parts[3] || 'cyan',
        loop: true,
      });
    } else if (tag === 'POINTX') {
      // never happens; keeps POINT out of the spoken text path
    }
  }

  const spokenText = normalized
    .replace(/\[\/?STEP\]/gi, ' ')
    .replace(/\[[A-Z0-9_]+:[^\]]*\]/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  return { spokenText, commands, point };
}

/** Splits a raw LLM reply into sequential [STEP] blocks (falls back to one block). */
export function splitStepBlocks(rawResponse: string): string[] {
  const stepRegex = /\[STEP\]([\s\S]*?)\[\/STEP\]/gi;
  const steps: string[] = [];
  let match: RegExpExecArray | null;
  while ((match = stepRegex.exec(rawResponse)) !== null) {
    steps.push(match[1].trim());
  }
  if (steps.length === 0) {
    const withoutMarkers = rawResponse.replace(/\[\/?STEP\]/gi, '').trim();
    if (withoutMarkers) steps.push(withoutMarkers);
  }
  return steps;
}

/**
 * Smart motion guarantee: small local vision models often just write out what
 * they plan to animate ("we'll start the wheel on the left side...") or fall
 * back to a static [CIRCLE]. If the prompt is about motion and no [ANIMATE]
 * tag arrived, inject the matching looping 60 FPS primitive + its physics notes.
 */
/**
 * Biology diagram upgrade: small vision models approximate humans with 4-point
 * diamond [POLYGON] heads and giant [BOX] torsos. On any anatomy/biology prompt,
 * strip those crude drawing placeholders (keeping every note card, board, plot
 * and animation) and inject the detailed animated anatomical figure instead.
 * Mutates `commands` in place; returns true when the prompt is a bio topic.
 */
const CRUDE_PLACEHOLDER_TYPES = new Set([
  'BOX',
  'RECT',
  'CIRCLE',
  'BEACON',
  'POLYGON',
  'CURVE',
  'ARROW',
  'LINE',
  'SHAPE3D',
  'POLY3D',
]);

/** Strong organ/anatomy topics - these always win over action/scene words. */
const STRONG_ANATOMY_TOPIC =
  /\b(anatomy|nervous\s+system|circulatory|digestive|respiratory|neuron|synapse|dna|double\s+helix|brain|heart|lungs?|liver|stomach|intestin|spinal\s+cord)\b/i;

/**
 * Detects human action / multi-POV scene prompts that must render the 15-joint
 * kinematic ACTOR rig instead of the (static-mannequin) anatomy engine.
 *
 * Requires BOTH an action verb AND contextual grounding (a human/body word,
 * a scene word, or an explicit POV request) so physics prompts like
 * "teach wave motion" or "run the algorithm" never get hijacked.
 *
 * The old bio-keyword interceptor grabbed "the skeleton sits on the pool's
 * edge, ready to dive in" (matched 'skeleton' -> static mannequin). The
 * STRONG_ANATOMY_TOPIC gate deliberately excludes skeleton/bones/skull so
 * skeleton-in-action prompts resolve to ACTOR, while genuine organ topics
 * ("teach the skeletal system") still reach the anatomy engine.
 */
export function detectActorScene(
  userPrompt: string
): { action: string; pov: string } | null {
  const q = (userPrompt || '').toLowerCase();
  if (!q) return null;
  if (STRONG_ANATOMY_TOPIC.test(q)) return null;

  const povMatch = q.match(
    /\b(1st|first\s+person|fpv|pov|2nd|second\s+person|front\s+view|face\s+to\s+face|3rd|third\s+person)\b/i
  );
  const actionMatch = q.match(
    /\b(sprinting|sprint|running|run|jogging|jog|walking|walk|jumping|jump|diving|dive|pool|swimming|swim|sitting|sit|waving|wave|dancing|dance|emote|celebrating|celebrate|squat|kicking|kick|athlete|flirt|wingman)\b/i
  );
  if (!actionMatch) return null;

  const human = /\b(human|person|people|guy|guys|man|woman|men|women|character|buddy|body|someone|skeleton|bones|athlete|coach|figure|player|dancer|swimmer|runner|diver|hand|arms?|legs?|kid|child)\b/i.test(
    q
  );
  const scene =
    /\b(pool|dive|diving|edge|lane|water|track|ground|race|stage|floor|sky|road|start\s+line|ready\s+to)\b/i.test(
      q
    );
  if (!human && !scene && !povMatch) return null;

  const pov = povMatch
    ? /1st|first|fpv/i.test(povMatch[0])
      ? '1st'
      : /2nd|second|front|face/i.test(povMatch[0])
        ? '2nd'
        : '3rd'
    : /wingman|flirt|greet/.test(actionMatch[1] || '')
      ? '2nd' // wingman/flirt coach speaks face-to-face with the user
      : '3rd';
  return { action: (actionMatch[1] || 'walk').toLowerCase(), pov };
}

/**
 * Scene/action upgrade: strips crude placeholders (keeping notes, boards,
 * plots, animations) and injects the looping 15-joint ACTOR rig once per
 * lesson. Mutates `commands` in place; returns true when the prompt is an
 * action/scene topic.
 */
export function ensureActionActorForPrompt(
  userPrompt: string,
  commands: ParsedOverlayCommand[],
  allowInject = true
): boolean {
  const det = detectActorScene(userPrompt);
  if (!det) return false;

  for (let i = commands.length - 1; i >= 0; i--) {
    if (CRUDE_PLACEHOLDER_TYPES.has(commands[i].type)) commands.splice(i, 1);
  }

  if (allowInject && !commands.some((c) => c.type === 'ACTOR')) {
    commands.unshift({
      type: 'ACTOR',
      action: det.action,
      pov: det.pov,
      x1: 120,
      y1: 315,
      x2: 445,
      y2: 315,
      cx: 275,
      cy: 315,
      label: `Dynamic Human: ${det.action.toUpperCase()}`,
      color: 'cyan',
      loop: true,
    });
  }
  return true;
}

/**
 * Universal capability dispatcher (merged from the drop-in module).
 *
 * Deliberate deviations from the original:
 *  - Mutates `commands` IN PLACE and returns it. The original's wingman/DJ/
 *    athlete builders returned brand-new arrays, discarding every command the
 *    model had already emitted (violates the merge policy).
 *  - No canned reply/coach text. The original hardcoded pickup lines and
 *    biomechanics cards; content must come from the model (prompt rules), so
 *    only structural fallbacks are injected here.
 *  - Wingman avatar and desktop emote buddy sections were skipped: the avatar
 *    is just our existing ACTOR rig (wingman action, now defaulting to 2nd
 *    POV) and the buddy section was a hardcoded-position ACTOR command.
 *
 * Sections adopted: TRACE (algo step-tracer), GRAPH (auto-layout flowchart),
 * FIELD (particle/vector sim), DJ (WebAudio mood engine), and the biomechanics
 * `showProtractor` upgrade on the ACTOR rig. KEYFRAMES is model-driven only.
 */
export function enrichUniversalCapabilities(
  userPrompt: string,
  commands: ParsedOverlayCommand[],
  allowInject = true
): ParsedOverlayCommand[] {
  const q = (userPrompt || '').toLowerCase();
  if (!q) return commands;

  // Gaming aim trainer + cross-game sensitivity conversion goes FIRST so a
  // "track my aim in valorant" prompt can never fall through to FIELD/DJ.
  if (enrichGamingAimForPrompt(userPrompt, commands, allowInject)) return commands;

  const stripCrude = () => {
    for (let i = commands.length - 1; i >= 0; i--) {
      if (CRUDE_PLACEHOLDER_TYPES.has(commands[i].type)) commands.splice(i, 1);
    }
  };

  // --- Algorithm / code / search step-tracer ---
  if (
    /\b(bubble\s+sort|quick\s+sort|merge\s+sort|insertion\s+sort|selection\s+sort|linear\s+search|binary\s+search|array\s+trace|step\s+trace|pointer\s+trace|stack\s+trace|recursion\s+stack)\b/i.test(q) &&
    !commands.some((c) => c.type === 'TRACE')
  ) {
    if (allowInject) {
      stripCrude();
      commands.unshift({
        type: 'TRACE',
        values: ['38', '14', '52', '9', '27', '61'],
        swapIndices: [0, 1],
        pointerIndex: 1,
        label: 'Live Array Step-Tracer',
        color: 'yellow',
        loop: true,
      });
    }
  }

  // --- Auto-layout flowchart / mind-map / system graph ---
  if (
    /\b(flowchart|mind\s*map|concept\s+map|decision\s+tree|food\s+chain|food\s+web|system\s+architecture|ecosystem\s+(energy|flow|web)|call\s+graph|dependency\s+graph)\b/i.test(q) &&
    !commands.some((c) => c.type === 'GRAPH')
  ) {
    if (allowInject) {
      stripCrude();
      // Topic-derived chain: meaningful prompt words become graph nodes so the
      // fallback is never a fixed canned diagram.
      const STOP = new Set([
        'the', 'and', 'for', 'with', 'that', 'this', 'from', 'into', 'your',
        'teach', 'explain', 'show', 'give', 'draw', 'make', 'about', 'what',
        'how', 'when', 'where', 'does', 'are', 'was', 'were', 'have', 'has',
        'please', 'could', 'would', 'should', 'step', 'steps', 'lesson', 'topic',
      ]);
      const words = Array.from(
        new Set(
          q
            .replace(/[^a-z0-9\s]/g, ' ')
            .split(/\s+/)
            .filter((w) => w.length > 3 && !STOP.has(w))
        )
      ).slice(0, 4);
      const nodes = words.length >= 2 ? words : ['Input', 'Process', 'Output'];
      const edges = nodes.slice(0, -1).map((n, i) => ({ from: n, to: nodes[i + 1] }));
      // Guard clause: Ensure nodes is an array before joining
      const nodesLabel = Array.isArray(nodes) && nodes.length > 0 
        ? nodes.join(' → ') 
        : 'No nodes';
      
      commands.unshift({
        type: 'GRAPH',
        nodes,
        edges,
        nodePositions: {},
        label: `Auto Layout: ${nodesLabel}`,
        color: 'cyan',
        loop: true,
      });
    }
  }

  // --- Particle / vector-field / fluid simulator ---
  if (
    /\b(thermodynamic|kinetic\s+theory|gas\s+particles?|brownian|electric\s+field|magnetic\s+field|electromagnetic|fluid\s+flow|airflow|laminar|turbulen)/i.test(q) &&
    !commands.some((c) => c.type === 'FIELD')
  ) {
    if (allowInject) {
      stripCrude();
      const fieldType = /magnetic/.test(q)
        ? 'magnetic'
        : /electric|electromagnetic/.test(q)
          ? 'electric'
          : /fluid|airflow|laminar|turbulen/.test(q)
            ? 'fluid'
            : 'gas';
      const tempMatch = q.match(/(\d+)\s*(?:°|deg|k\b|c\b)/);
      const intensity = tempMatch ? Math.min(200, Number(tempMatch[1]) || 75) : 75;
      commands.unshift({
        type: 'FIELD',
        fieldType,
        intensity,
        label: `Live ${fieldType.toUpperCase()} Field Simulation`,
        color: 'orange',
        loop: true,
      });
    }
  }

  // --- Mood / environment WebAudio DJ ---
  if (
    /\b(play|put\s+on|start|loop|dj)\b[^.]{0,40}\b(music|song|beat|beats|track|lofi|lo-fi|synthwave|tune|vibes?)\b|\b(background|study|chill|vibe|lofi|lo-fi)\s+(music|beat|beats)\b/i.test(q) &&
    !commands.some((c) => c.type === 'DJ')
  ) {
    if (allowInject) {
      const genre = /synth|neon|cyber|retro/.test(q)
        ? 'synthwave'
        : /hype|gym|workout|party|edm/.test(q)
          ? 'hype'
          : /lofi|lo-fi|chill/.test(q)
            ? 'lofi'
            : /focus|study|exam|deep/.test(q)
              ? 'focus'
              : 'lofi';
      const bpm = genre === 'hype' ? 128 : genre === 'synthwave' ? 108 : genre === 'focus' ? 76 : 84;
      const chordRoot =
        genre === 'hype' ? 220 : genre === 'synthwave' ? 196 : genre === 'focus' ? 174.61 : 261.63;
      commands.unshift({
        type: 'DJ',
        genre,
        bpm,
        chordRoot,
        label: `Live WebAudio ${genre.toUpperCase()} Synth (${bpm} BPM)`,
        color: 'purple',
        loop: true,
      });
    }
  }

  // --- Athletic biomechanics protractor (upgrade on the existing ACTOR rig) ---
  if (/\b(biomechanic|posture|form\s+check|sprint\s+form|squat\s+form|running\s+form|joint\s+angle|gait\s+analys|ergonomic)/i.test(q)) {
    stripCrude();
    const existing = commands.find((c) => c.type === 'ACTOR');
    if (existing) {
      existing.showProtractor = true;
    } else if (allowInject) {
      const action = /\bsquat\b/.test(q)
        ? 'squat'
        : /\bjump\b/.test(q)
          ? 'jump'
          : /\bkick\b/.test(q)
            ? 'kick'
            : 'sprint';
      commands.unshift({
        type: 'ACTOR',
        action,
        pov: '3rd',
        x1: 125,
        y1: 315,
        x2: 435,
        y2: 315,
        cx: 275,
        cy: 315,
        showProtractor: true,
        label: `Biomechanics Rig: ${action.toUpperCase()}`,
        color: 'green',
        loop: true,
      });
    }
  }

  return commands;
}

export function ensureBiologyDiagramForPrompt(
  userPrompt: string,
  commands: ParsedOverlayCommand[],
  allowInject = true
): boolean {
  const q = (userPrompt || '').toLowerCase();
  if (!q) return false;

  // Action/scene prompts ("skeleton sits on the pool's edge, ready to dive")
  // must never be hijacked by the bio keyword matcher - the ACTOR rig owns them.
  if (detectActorScene(userPrompt)) return false;

  // Stems (not full words) so plurals/derivatives match: lungs, breathing,
  // skeletal, digestion, arteries, bones, ribcage, circulation...
  const bioMatch = q.match(
    /\b(human\s+body|anatomy|nervous\s+system|brain|spinal\s+cord|peripheral\s+nerve|neurons?|synapse|heart|circulatory|blood\s+vessels?|arter(y|ies|ial)|veins?|venous|lungs?|respirat|breath|diaphragm|digest|stomach|intestin|livers?|esophag|skeleton|skeletal|bones?|skull|ribcage|ribs|dna|double\s+helix|helix)/i
  );
  if (!bioMatch) return false;

  let system = 'nervous';
  if (/\b(heart|circulat|blood|arter|veins?|venous|cardio)/i.test(q)) system = 'heart';
  else if (/\b(lung|respirat|breath|trachea|diaphragm|alveol)/i.test(q)) system = 'lungs';
  else if (/\b(digest|stomach|intestin|liver|esophag|gut)/i.test(q)) system = 'digestive';
  else if (/\b(skelet|bones?|skull|ribcage|ribs|femur|spine)/i.test(q)) system = 'skeletal';
  else if (/\b(neuron|synapse|axon|dendrite|myelin)/i.test(q)) system = 'neuron';
  else if (/\b(dna|helix|chromosome|genes?)/i.test(q)) system = 'dna';

  // Remove crude placeholders in place (array identity is kept for callers);
  // WRITE/BOARD/TOPIC_BANNER/PLOT/ANIMATE/POINT/SVG/ANATOMY all survive.
  for (let i = commands.length - 1; i >= 0; i--) {
    if (CRUDE_PLACEHOLDER_TYPES.has(commands[i].type)) commands.splice(i, 1);
  }

  if (allowInject && !commands.some((c) => c.type === 'ANATOMY')) {
    commands.unshift({
      type: 'ANATOMY',
      system,
      cx: 285,
      cy: 315,
      scale: 1,
      label: `Human ${system.toUpperCase()} System`,
      color: 'cyan',
      loop: true,
    });
  }
  return true;
}

export function ensureMotionAnimationForPrompt(
  userPrompt: string,
  commands: ParsedOverlayCommand[],
  allowInject = true
): ParsedOverlayCommand[] {
  // Action/scene prompts are fully handled by the 15-joint ACTOR rig.
  if (ensureActionActorForPrompt(userPrompt, commands, allowInject)) return commands;
  // Biology prompts are fully handled by the anatomy engine above.
  if (ensureBiologyDiagramForPrompt(userPrompt, commands, allowInject)) return commands;

  const q = (userPrompt || '').toLowerCase();
  if (!q) return commands;
  if (
    commands.some(
      (c) =>
        c.type === 'ANIMATE' ||
        c.type === 'ANATOMY' ||
        c.type === 'ACTOR' ||
        c.type === 'KEYFRAMES' ||
        c.type === 'GRAPH' ||
        c.type === 'TRACE' ||
        c.type === 'FIELD' ||
        c.type === 'DJ' ||
        c.type === 'AIM_TRAINER'
    )
  ) {
    return commands;
  }
  if (!allowInject) return commands;

  const isWheel = /\b(wheel|rolling|roll|tire|cycloid|bicycle|car)\b/i.test(q);
  const isSpring = /\b(spring|hooke|oscillat|harmonic|shm|bounce|bouncing)\b/i.test(q);
  const isPendulum = /\b(pendulum|swing|swinging)\b/i.test(q);
  const isProjectile = /\b(projectile|throw|launch|parabola.*ball|ball.*arc|trajectory)\b/i.test(q);
  const isOrbit = /\b(orbit|planet|solar|electron|atom|satellite)\b/i.test(q);
  const isWave = /\b(wave|wavelength|frequency|transverse|sine.*move|moving.*wave)\b/i.test(q);
  const isGenericMove = /\b(animate|moving|move\s+across|moves?\b|motion|sliding|slides?\b)/i.test(q);

  if (isWheel) {
    commands.unshift(
      {
        type: 'ANIMATE',
        preset: 'wheel',
        x1: 110,
        y1: 310,
        x2: 460,
        y2: 310,
        points: [
          { x: 110, y: 310 },
          { x: 460, y: 310 },
        ],
        r: 54,
        label: 'Rolling Wheel (No-Slip Motion)',
        color: 'cyan',
        loop: true,
      },
      { type: 'WRITE', label: 'Rolling Without Slipping: v_cm = omega * R', color: 'cyan' },
      { type: 'WRITE', label: 'Distance Rolled: delta_x = R * theta', color: 'green' },
      { type: 'WRITE', label: 'Red Rim Point traces a Cycloid path', color: 'yellow' },
      { type: 'WRITE', label: 'Bottom contact point has instantaneous v = 0', color: 'orange' }
    );
  } else if (isSpring) {
    commands.unshift(
      {
        type: 'ANIMATE',
        preset: 'spring',
        x1: 95,
        y1: 300,
        points: [{ x: 95, y: 300 }],
        r: 75,
        label: 'Simple Harmonic Oscillator',
        color: 'cyan',
        loop: true,
      },
      { type: 'WRITE', label: "Hooke's Law: F_s = -k * x", color: 'cyan' },
      { type: 'WRITE', label: 'Position: x(t) = A * sin(omega*t)', color: 'green' },
      { type: 'WRITE', label: 'Angular Frequency: omega = sqrt(k / m)', color: 'yellow' }
    );
  } else if (isPendulum) {
    commands.unshift(
      {
        type: 'ANIMATE',
        preset: 'pendulum',
        x1: 280,
        y1: 145,
        points: [{ x: 280, y: 145 }],
        r: 190,
        label: 'Simple Pendulum Motion',
        color: 'yellow',
        loop: true,
      },
      { type: 'WRITE', label: 'Period: T = 2*pi * sqrt(L / g)', color: 'cyan' },
      { type: 'WRITE', label: 'Restoring Torque: tau = -m*g*L*sin(theta)', color: 'red' }
    );
  } else if (isProjectile) {
    commands.unshift(
      {
        type: 'ANIMATE',
        preset: 'projectile',
        x1: 100,
        y1: 380,
        x2: 460,
        y2: 380,
        points: [
          { x: 100, y: 380 },
          { x: 460, y: 380 },
        ],
        r: 170,
        peakH: 170,
        label: '2D Projectile Trajectory',
        color: 'green',
        loop: true,
      },
      { type: 'WRITE', label: 'Horizontal: x(t) = v0*cos(theta)*t (constant vx)', color: 'green' },
      { type: 'WRITE', label: 'Vertical: y(t) = v0*sin(theta)*t - 0.5*g*t^2', color: 'red' }
    );
  } else if (isOrbit) {
    commands.unshift(
      {
        type: 'ANIMATE',
        preset: 'orbit',
        x1: 280,
        y1: 295,
        points: [{ x: 280, y: 295 }],
        r: 135,
        label: 'Keplerian Orbital Motion',
        color: 'cyan',
        loop: true,
      },
      { type: 'WRITE', label: 'Orbital Speed: v = sqrt(G*M / r)', color: 'cyan' }
    );
  } else if (isWave) {
    commands.unshift(
      {
        type: 'ANIMATE',
        preset: 'wave',
        x1: 90,
        y1: 290,
        points: [{ x: 90, y: 290 }],
        r: 65,
        label: 'Traveling Wave y(x,t) = A*sin(k*x - omega*t)',
        color: 'purple',
        loop: true,
      },
      { type: 'WRITE', label: 'Wave Speed: v = f * lambda', color: 'cyan' }
    );
  } else if (isGenericMove) {
    commands.unshift({
      type: 'ANIMATE',
      preset: 'move',
      x1: 110,
      y1: 300,
      x2: 450,
      y2: 300,
      points: [
        { x: 110, y: 300 },
        { x: 450, y: 300 },
      ],
      r: 46,
      label: 'Motion Across the Screen',
      color: 'cyan',
      loop: true,
    });
  }

  return commands;
}

/**
 * Merge adaptation of the provided `routeSpecializedEngines` wiring snippet:
 *  - The original REPLACED `commands` with the router's return value, discarding
 *    every command the model had already emitted (violates merge policy). Here
 *    the specialized commands are merged IN PLACE (unshifted before model
 *    commands, which stay referenced) so array identity is preserved.
 *  - An injected [BOARD] banner is dropped when the model already emitted one
 *    (avoids duplicate topic banners).
 *  - Routing is async because the AppScanner / video-director paths run a
 *    Windows UIA scan (execFile powershell).
 *  - Sandbox/AutoRepair/WorkspaceSafety/HojaigaBridge are compiled libraries,
 *    intentionally not auto-triggered here (they need code payloads / external
 *    triggers, not free-text prompts).
 */
/** Lazily-created on first memory-palace prompt (no import-time side effects). */
let memoryPalaceInstance: MemoryPalaceEngine | null = null;

/** Coder engines: no filesystem side effects in constructors - safe at module scope. */
const polyglotCoder = new PolyglotVisualArchitectCoder();
const fullStackArchitect = new FullStackScaffoldAndVerifyEngine();

function mergeSpecialized(
  commands: ParsedOverlayCommand[],
  injected: ParsedOverlayCommand[],
  allowInject: boolean
): boolean {
  if (!allowInject || !injected || injected.length === 0) return false;
  // Strip the MODEL's crude placeholders first, THEN merge the specialized
  // commands - some engines (chart zones) legitimately emit BOX themselves,
  // which must not be eaten by the crude filter.
  for (let i = commands.length - 1; i >= 0; i--) {
    if (CRUDE_PLACEHOLDER_TYPES.has(commands[i].type)) commands.splice(i, 1);
  }
  const hasBoard = commands.some((c) => c.type === 'BOARD');
  const usable = hasBoard ? injected.filter((c) => c.type !== 'BOARD') : injected;
  for (let i = usable.length - 1; i >= 0; i--) {
    commands.unshift(usable[i]);
  }
  return true;
}

export async function routeSpecializedEngines(
  userPrompt: string,
  commands: ParsedOverlayCommand[],
  allowInject = true
): Promise<boolean> {
  const q = (userPrompt || '').trim();
  if (!q) return false;
  try {
    // Priority order adopted from the pasted master router (File 26), kept as
    // ONE in-place chain: active coding help first, then SWE workbenches,
    // creator/media engines, domain tutors, and the app scanner last (its
    // narrow trigger stays narrow - never an unconditional fallback).
    //
    // 1. Active coding help (highest priority for stuck/active coding prompts)
    if (LiveIDEPairProgrammer.isIDEPairPrompt(q)) {
      return mergeSpecialized(commands, await LiveIDEPairProgrammer.buildLivePairProgrammerOverlay(q), allowInject);
    }
    if (BugRootCauseAutopsyEngine.isBugAutopsyPrompt(q)) {
      return mergeSpecialized(commands, BugRootCauseAutopsyEngine.buildBugAutopsyOverlay(q), allowInject);
    }
    // 2. Specialized software engineering workbenches: SQL, Git, Regex,
    //    latency, UI/UX critic, algorithm trace, full-stack scaffold, polyglot.
    if (SQLQueryPlanAndSchemaVisualizer.isSQLVisualizerPrompt(q)) {
      return mergeSpecialized(commands, SQLQueryPlanAndSchemaVisualizer.buildSQLVisualizerOverlay(q), allowInject);
    }
    if (GitTimeMachineAndConflictResolver.isGitPrompt(q)) {
      return mergeSpecialized(commands, await GitTimeMachineAndConflictResolver.buildGitVisualizerOverlay(q), allowInject);
    }
    if (RegexAndParserVisualWorkbench.isRegexPrompt(q)) {
      return mergeSpecialized(commands, RegexAndParserVisualWorkbench.buildRegexWorkbenchOverlay(q), allowInject);
    }
    if (APILoadAndLatencySimulator.isLoadSimulatorPrompt(q)) {
      return mergeSpecialized(commands, await APILoadAndLatencySimulator.buildLatencySimulatorOverlay(q), allowInject);
    }
    if (UIUXAccessibilityAndDesignCritic.isUIUXCriticPrompt(q)) {
      return mergeSpecialized(commands, await UIUXAccessibilityAndDesignCritic.buildUIUXCriticOverlay(q), allowInject);
    }
    if (VisualAlgorithmStepDebugger.isAlgorithmTracePrompt(q)) {
      return mergeSpecialized(commands, VisualAlgorithmStepDebugger.buildVisualDebuggerOverlay(q), allowInject);
    }
    if (FullStackScaffoldAndVerifyEngine.isArchitectureScaffoldPrompt(q)) {
      return mergeSpecialized(commands, fullStackArchitect.buildArchitectureOverlay(q), allowInject);
    }
    if (PolyglotVisualArchitectCoder.isCodingIntentPrompt(q)) {
      const { overlayCommands } = await polyglotCoder.teachVerifyAndBuild(q);
      return mergeSpecialized(commands, overlayCommands, allowInject);
    }
    // 3. Creator, media & career engines
    if (ProVideoEditorDirector.isVideoEditPrompt(q)) {
      return mergeSpecialized(commands, await ProVideoEditorDirector.buildVideoDirectorOverlay(q), allowInject);
    }
    if (UGCContentEngine.isUGCPrompt(q)) {
      return mergeSpecialized(commands, UGCContentEngine.buildUGCOverlay(q), allowInject);
    }
    if (GhostwritingEngine.isGhostwritePrompt(q)) {
      return mergeSpecialized(commands, GhostwritingEngine.buildGhostwritingOverlay(q), allowInject);
    }
    if (InterviewCoachEngine.isInterviewPrompt(q)) {
      return mergeSpecialized(commands, InterviewCoachEngine.buildInterviewCoachOverlay(q), allowInject);
    }
    // 4. Domain tutors & live screen utilities
    if (LiveScreenTranslator.isTranslationPrompt(q)) {
      return mergeSpecialized(commands, await LiveScreenTranslator.buildScreenTranslatorOverlay(q), allowInject);
    }
    if (ChartPatternTutor.isChartPrompt(q)) {
      return mergeSpecialized(commands, ChartPatternTutor.buildChartAnalystOverlay(q), allowInject);
    }
    if (HardwareSchematicTutor.isHardwareOrCADPrompt(q)) {
      return mergeSpecialized(commands, await HardwareSchematicTutor.buildHardwareOrCADOverlay(q), allowInject);
    }
    if (CyberDefenseTutorEngine.isSecurityConceptPrompt(q)) {
      return mergeSpecialized(commands, CyberDefenseTutorEngine.buildSecurityOverlay(q), allowInject);
    }
    if (HomeworkSocraticTutor.isHomeworkPrompt(q)) {
      return mergeSpecialized(commands, HomeworkSocraticTutor.buildSocraticOverlay(q), allowInject);
    }
    if (MemoryPalaceEngine.isMemoryPalacePrompt(q)) {
      // Lazy: instantiated on first memory-palace prompt so module import has
      // no filesystem side effects.
      if (!memoryPalaceInstance) memoryPalaceInstance = new MemoryPalaceEngine();
      return mergeSpecialized(
        commands,
        memoryPalaceInstance.buildMemoryPalaceOverlay(q, HojaigaIntegrationBridge.getInstance()),
        allowInject
      );
    }
    // 5. App-scan trigger: needs explicit app framing ("teach me this app",
    // "scan app", "walk me through the app") OR a capitalized target
    // ("How do i use Photoshop") - a bare lowercase "walk me through bubble
    // sort" is a concept lesson, not an app lesson, and must not scan.
    const APP_ABSTRACT_STOP =
      '(?!(?:bubble|quick|merge|insertion|selection|binary|linear|radix|recursion|stack|queue|hash|sorting|search|the\\s+basics)\\b)';
    const appFramed =
      /\b(?:teach\s+me\s+(?:this|the)\s+app|scan\s+(?:the\s+)?app)\b/i.test(q) ||
      new RegExp(
        `\\b(?:walk\\s+me\\s+through|how\\s+do\\s+i\\s+use)\\s+(?:this|the|my)\\s+${APP_ABSTRACT_STOP}`,
        'i'
      ).test(q);
    const trigger = userPrompt.match(/\b(?:how\s+do\s+i\s+use|walk\s+me\s+through)\s+/i);
    const capsTarget =
      !!trigger &&
      /[A-Z][a-zA-Z0-9]/.test(userPrompt.slice((trigger.index || 0) + trigger[0].length));
    if (appFramed || capsTarget) {
      return mergeSpecialized(commands, await DynamicAppScannerAndTeacher.buildInteractiveAppLesson(q), allowInject);
    }
  } catch {
    /* specialized enrichment is best-effort - lesson continues without it */
  }
  return false;
}

/**
 * Synchronises drawing animations with the voice, one [STEP] at a time.
 */
export async function executeSynchronizedLesson(
  rawResponse: string,
  sendSegment: (commands: ParsedOverlayCommand[], clearFirst: boolean, subtitle?: string) => void,
  speakSegment: (text: string) => Promise<void>,
  onPoint?: (point: { x: number; y: number; label: string | null }) => void,
  userPrompt?: string
): Promise<void> {
  const steps = splitStepBlocks(rawResponse);
  let motionInjected = false;

  for (let i = 0; i < steps.length; i++) {
    const { spokenText, commands, point } = parseVisualTagsFromText(steps[i]);

    // Guarantee a dynamic primitive (ACTOR rig / anatomy figure / looping
    // animation) when the lesson is about a scene, biology or motion but the
    // model only emitted prose or crude boxes.
    if (userPrompt) {
      // Specialized engines (coding help / SWE workbenches first, then
      // creator engines, domain tutors and the app scanner) route FIRST and
      // merge in place, then universal + motion enrichment run with their
      // existing once-per-lesson gating (their type guards see the
      // specialized commands now present, e.g. DJ from the video director).
      await routeSpecializedEngines(userPrompt, commands, !motionInjected);
      // Crude-placeholder filtering runs on EVERY step (allowInject=false on
      // later steps), but each dynamic primitive is injected only once per
      // lesson (later steps already carry it via the overlay state).
      enrichUniversalCapabilities(userPrompt, commands, !motionInjected);
      ensureMotionAnimationForPrompt(userPrompt, commands, !motionInjected);
      if (
        commands.some((c) => c.type === 'ACTOR') ||
        commands.some((c) => c.type === 'ANIMATE') ||
        commands.some((c) => c.type === 'ANATOMY') ||
        commands.some((c) => c.type === 'KEYFRAMES') ||
        commands.some((c) => c.type === 'GRAPH') ||
        commands.some((c) => c.type === 'TRACE') ||
        commands.some((c) => c.type === 'FIELD') ||
        commands.some((c) => c.type === 'DJ') ||
        commands.some((c) => c.type === 'AIM_TRAINER') ||
        commands.some((c) => c.type === 'UIRECT')
      ) {
        motionInjected = true;
      }
    }

    if (commands.length > 0) {
      sendSegment(commands, i === 0, spokenText || undefined);
    } else if (i === 0) {
      sendSegment([], true, spokenText || undefined);
    }

    if (point && onPoint) onPoint(point);

    if (spokenText.length > 0) {
      await speakSegment(spokenText);
    }
  }
}

/** Scales screenshot-space coordinates to real display pixels. */
export function scaleCommands(
  commands: ParsedOverlayCommand[],
  sx: number,
  sy: number
): ParsedOverlayCommand[] {
  const avg = (sx + sy) / 2;
  return commands.map((c) => {
    const o: ParsedOverlayCommand = { ...c };
    switch (c.type) {
      case 'BOARD':
      case 'BOX':
      case 'PLOT':
        o.x = c.x * sx;
        o.y = c.y * sy;
        o.w = c.w * sx;
        o.h = c.h * sy;
        break;
      case 'WRITE':
        o.x = c.x * sx;
        o.y = c.y * sy;
        break;
      case 'CIRCLE':
        o.x = c.x * sx;
        o.y = c.y * sy;
        o.r = c.r * avg;
        break;
      case 'ARROW':
        o.x1 = c.x1 * sx;
        o.y1 = c.y1 * sy;
        o.x2 = c.x2 * sx;
        o.y2 = c.y2 * sy;
        break;
      case 'CURVE':
      case 'POLYGON':
        o.points = (c.points || []).map((p: any) => ({ x: p.x * sx, y: p.y * sy }));
        break;
      case 'ACTOR':
        o.x1 = c.x1 * sx;
        o.y1 = c.y1 * sy;
        o.x2 = c.x2 * sx;
        o.y2 = c.y2 * sy;
        o.cx = c.cx * sx;
        o.cy = c.cy * sy;
        break;
      case 'KEYFRAMES':
        o.keyframes = (c.keyframes || []).map((k: any) => ({
          ...k,
          x: k.x * sx,
          y: k.y * sy,
        }));
        break;
      case 'GRAPH':
        o.nodePositions = Object.fromEntries(
          Object.entries(c.nodePositions || {}).map(([name, p]: any) => [
            name,
            { x: p.x * sx, y: p.y * sy },
          ])
        );
        break;
      case 'FIELD':
        o.x = c.x * sx;
        o.y = c.y * sy;
        o.w = c.w * sx;
        o.h = c.h * sy;
        break;
      case 'DJ':
        o.cx = c.cx * sx;
        o.cy = c.cy * sy;
        break;
      case 'AIM_TRAINER':
        o.cx = c.cx * sx;
        o.cy = c.cy * sy;
        break;
      case 'UIRECT':
        o.x = c.x * sx;
        o.y = c.y * sy;
        o.w = c.w * sx;
        o.h = c.h * sy;
        break;
      case 'ANATOMY':
        o.cx = c.cx * sx;
        o.cy = c.cy * sy;
        o.scale = (c.scale || 1) * ((sx + sy) / 2);
        break;
      case 'SVG':
        o.cx = c.cx * sx;
        o.cy = c.cy * sy;
        o.scale = (c.scale || 1) * ((sx + sy) / 2);
        break;
      case 'ANIMATE':
        o.x1 = c.x1 * sx;
        o.y1 = c.y1 * sy;
        o.x2 = c.x2 * sx;
        o.y2 = c.y2 * sy;
        o.r = (c.r || 0) * avg;
        if (c.peakH) o.peakH = c.peakH * sy;
        o.points = (c.points || []).map((p: any) => ({ x: p.x * sx, y: p.y * sy }));
        break;
      case 'SHAPE3D':
        o.cx = c.cx * sx;
        o.cy = c.cy * sy;
        o.size = c.size * avg;
        break;
      case 'POLY3D':
        o.cx = c.cx * sx;
        o.cy = c.cy * sy;
        o.scale = c.scale * avg;
        o.points3D = (c.points3D || []).map((p: any) => ({
          x: p.x * sx,
          y: p.y * sy,
          z: (p.z || 0) * avg,
        }));
        break;
    }
    return o;
  });
}

export class CompanionManager {
  public voiceState: CompanionVoiceState = 'idle';
  public anotherScreenNavigating = false;

  public readonly claudeAPI = new ClaudeAPI();
  public readonly edgeNeuralTTSClient = new EdgeNeuralTTSClient();
  public readonly overlayWindowManager = new OverlayWindowManager();
  public readonly menuBarPanelManager = new MenuBarPanelManager();
  public readonly shortcutMonitor = new GlobalPushToTalkShortcutMonitor();
  public readonly buddyDictationManager = new BuddyDictationManager();

  private conversationHistory: { userTranscript: string; assistantResponse: string }[] = [];
  private requestCounter = 0;

  // Task queue system
  private taskQueue: Array<{ prompt: string; timestamp: number }> = [];
  private isProcessingTask = false;

  // Interrupt words for voice cancellation
  private static readonly INTERRUPT_WORDS = ['stop', 'cancel', 'never mind', 'forget it', 'nevermind'];

  private ttsResolve: (() => void) | null = null;
  private ttsTimer: ReturnType<typeof setTimeout> | null = null;

  // Vision-based teaching agent (initialized on demand)
  private visionTeacherAgent: any = null;
  private visionTeachingActive = false;

  // Dynamic app teacher for comprehensive app exploration
  private dynamicAppTeacher: any = null;
  private dynamicTeachingActive = false;

  // Action explorer for UI discovery
  private actionExplorer: any = null;

  // Ollama installation directory (D drive)
  private readonly ollamaHome = 'D:\\Ollama';

  start() {
    this.overlayWindowManager.showOverlay();
    this.menuBarPanelManager.createPanelAndTray((prompt) => {
      this.sendTranscriptToClaudeWithScreenshot(prompt, false);
    });

    this.shortcutMonitor.start((transition) => this.handleShortcutTransition(transition));
    this.startCursorTrackingLoop();
  }

  /** Called by main.ts whenever the overlay reports TTS finished (or was stopped). */
  public notifyTtsEnded() {
    if (this.ttsResolve) {
      const resolve = this.ttsResolve;
      this.ttsResolve = null;
      if (this.ttsTimer) {
        clearTimeout(this.ttsTimer);
        this.ttsTimer = null;
      }
      resolve();
    }
  }

  private handleShortcutTransition(transition: ShortcutTransition) {
    const primaryWin = this.overlayWindowManager.overlayWindowsByDisplayId.get(
      screen.getPrimaryDisplay().id
    );
    if (transition === 'pressed') {
      ClickyAnalytics.trackPushToTalkStarted();
      this.overlayWindowManager.broadcast('stop-tts-audio');
      this.notifyTtsEnded();
      this.setVoiceState('listening');
      primaryWin?.webContents.send('start-listening');
    } else if (transition === 'released') {
      ClickyAnalytics.trackPushToTalkReleased();
      this.setVoiceState('processing');
      primaryWin?.webContents.send('stop-listening');
    }
  }

  private checkForInterruptWords(transcript: string): boolean {
    const lowerTranscript = transcript.toLowerCase();
    return CompanionManager.INTERRUPT_WORDS.some(word => lowerTranscript.includes(word));
  }

  public setVoiceState(newState: CompanionVoiceState) {
    this.voiceState = newState;
    this.overlayWindowManager.broadcast('voice-state', newState);
    if (
      this.menuBarPanelManager.panelWindow &&
      !this.menuBarPanelManager.panelWindow.isDestroyed()
    ) {
      this.menuBarPanelManager.panelWindow.webContents.send('status-update', newState);
    }
  }

  private startCursorTrackingLoop() {
    setInterval(() => {
      const mousePt = screen.getCursorScreenPoint();
      const displays = screen.getAllDisplays();

      for (const display of displays) {
        const win = this.overlayWindowManager.overlayWindowsByDisplayId.get(display.id);
        if (!win || win.isDestroyed()) continue;

        const isCursorOnThisScreen =
          mousePt.x >= display.bounds.x &&
          mousePt.x <= display.bounds.x + display.bounds.width &&
          mousePt.y >= display.bounds.y &&
          mousePt.y <= display.bounds.y + display.bounds.height;

        win.webContents.send('cursor-tick', {
          isCursorOnThisScreen,
          anotherScreenNavigating: this.anotherScreenNavigating,
          localX: mousePt.x - display.bounds.x,
          localY: mousePt.y - display.bounds.y,
        });
      }
    }, 16);
  }

  private async speakAndWait(text: string): Promise<void> {
    this.notifyTtsEnded();

    let audioBase64: string | null = null;
    try {
      audioBase64 = await this.edgeNeuralTTSClient.speakText(text);
    } catch {
      audioBase64 = null;
    }

    const primaryWin = this.overlayWindowManager.overlayWindowsByDisplayId.get(
      screen.getPrimaryDisplay().id
    );

    // Edge neural TTS unavailable -> free offline Windows SAPI fallback.
    if (!audioBase64) {
      await WindowsNativeTTSProvider.speak(text, 1);
      return;
    }

    return new Promise<void>((resolve) => {
      this.ttsResolve = resolve;
      this.ttsTimer = setTimeout(() => this.notifyTtsEnded(), 45000);
      if (primaryWin) {
        primaryWin.webContents.send('play-tts-audio', { audioBase64, spokenText: text });
      } else {
        this.notifyTtsEnded();
      }
    });
  }

  async sendTranscriptToClaudeWithScreenshot(transcript: string, isDemo = false) {
    if (!transcript || !transcript.trim()) {
      this.setVoiceState('idle');
      return;
    }

    // Check for interrupt words
    if (this.checkForInterruptWords(transcript)) {
      this.overlayWindowManager.broadcast('stop-tts-audio');
      this.notifyTtsEnded();
      this.setVoiceState('idle');
      this.overlayWindowManager.clearDrawings();
      return;
    }

    // Add to task queue if currently processing
    if (this.isProcessingTask) {
      this.taskQueue.push({ prompt: transcript, timestamp: Date.now() });
      this.updateQueueBadge();
      return;
    }

    const currentRequestId = ++this.requestCounter;
    this.overlayWindowManager.broadcast('stop-tts-audio');
    this.notifyTtsEnded();

    ClickyAnalytics.trackUserMessageSent(transcript);
    this.setVoiceState('processing');
    this.isProcessingTask = true;

    try {
      const screenCaptures = await CompanionScreenCaptureUtility.captureAllScreensAsJPEG();
      if (currentRequestId !== this.requestCounter) return;

      const systemPrompt = isDemo
        ? ClaudeAPI.onboardingDemoSystemPrompt
        : VISUAL_TUTOR_SYSTEM_PROMPT;

      const fullResponseText = await this.claudeAPI.analyzeImageStreaming(
        screenCaptures,
        systemPrompt,
        this.conversationHistory,
        transcript
      );
      if (currentRequestId !== this.requestCounter) return;

      const targetCapture =
        screenCaptures.find((c) => c.isCursorScreen) || screenCaptures[0];

      const scaleX = targetCapture.displayWidthInPoints / targetCapture.screenshotWidthInPixels;
      const scaleY = targetCapture.displayHeightInPoints / targetCapture.screenshotHeightInPixels;

      let pointHandled = false;
      let spokenAll = '';

      await executeSynchronizedLesson(
        fullResponseText,
        (commands, clearFirst, subtitle) => {
          if (currentRequestId !== this.requestCounter) return;
          const scaled = scaleCommands(commands, scaleX, scaleY);
          if (clearFirst) this.overlayWindowManager.clearDrawings();
          if (scaled.length > 0) {
            this.overlayWindowManager.renderCommands(
              targetCapture.displayId,
              scaled,
              clearFirst,
              subtitle
            );
          }
        },
        async (segmentText) => {
          if (currentRequestId !== this.requestCounter) return;
          if (isDemo) return;

          spokenAll = spokenAll ? `${spokenAll} ${segmentText}` : segmentText;
          const clean = EdgeNeuralTTSClient.sanitizeSpokenText(segmentText);
          if (!clean) return;

          this.setVoiceState('responding');
          await this.speakAndWait(clean);
        },
        (point) => {
          if (pointHandled || currentRequestId !== this.requestCounter) return;
          pointHandled = true;

          const clampedX = Math.max(0, Math.min(point.x, targetCapture.screenshotWidthInPixels));
          const clampedY = Math.max(0, Math.min(point.y, targetCapture.screenshotHeightInPixels));

          this.anotherScreenNavigating = true;
          ClickyAnalytics.trackElementPointed(point.label);
          const targetWindow = this.overlayWindowManager.overlayWindowsByDisplayId.get(
            targetCapture.displayId
          );
          targetWindow?.webContents.send('navigate-to-element', {
            localX: clampedX * scaleX,
            localY: clampedY * scaleY,
            bubbleText: isDemo ? point.label : point.label,
          });
        },
        transcript
      );

      if (currentRequestId !== this.requestCounter) return;

      if (!isDemo) {
        const spokenSummary = EdgeNeuralTTSClient.sanitizeSpokenText(
          spokenAll || fullResponseText
        );
        if (spokenSummary) {
          this.conversationHistory.push({
            userTranscript: transcript,
            assistantResponse: spokenSummary,
          });
          if (this.conversationHistory.length > 10) {
            this.conversationHistory.shift();
          }
        }
      }

      ClickyAnalytics.trackAIResponseReceived(spokenAll || fullResponseText);
      this.setVoiceState('idle');
      this.isProcessingTask = false;

      // Process next task in queue
      this.processNextTask();
    } catch (err: any) {
      ClickyAnalytics.trackResponseError(String(err));
      this.setVoiceState('idle');
      this.isProcessingTask = false;
      this.processNextTask();
    }
  }

  private updateQueueBadge() {
    const primaryWin = this.overlayWindowManager.overlayWindowsByDisplayId.get(
      screen.getPrimaryDisplay().id
    );
    primaryWin?.webContents.send('queue-count', this.taskQueue.length);
  }

  private async processNextTask() {
    if (this.taskQueue.length === 0) {
      this.updateQueueBadge();
      return;
    }

    const nextTask = this.taskQueue.shift();
    this.updateQueueBadge();

    if (nextTask) {
      await this.sendTranscriptToClaudeWithScreenshot(nextTask.prompt, false);
    }
  }

  // Vision-based teaching methods
  async startVisionTeaching(goal: string): Promise<void> {
    if (this.visionTeachingActive) {
      console.log('[CompanionManager] Vision teaching already active');
      return;
    }

    console.log('[CompanionManager] Starting vision-based teaching:', goal);

    try {
      // Initialize the vision teacher agent
      if (!this.visionTeacherAgent) {
        this.visionTeacherAgent = await createTeacherAgent(
          this.menuBarPanelManager.panelWindow,
          false, // Production mode
          this.ollamaHome // D drive installation
        );
      }

      this.visionTeachingActive = true;

      // Start the teaching loop in the background
      this.visionTeacherAgent.startTeaching(goal).catch((error: Error) => {
        console.error('[CompanionManager] Vision teaching error:', error);
        this.visionTeachingActive = false;
      });
    } catch (error) {
      console.error('[CompanionManager] Failed to start vision teaching:', error);
      this.visionTeachingActive = false;
    }
  }

  stopVisionTeaching(): void {
    if (this.visionTeacherAgent && this.visionTeachingActive) {
      console.log('[CompanionManager] Stopping vision teaching');
      this.visionTeacherAgent.stopTeaching();
      this.visionTeachingActive = false;
    }
  }

  // Dynamic app teaching methods
  async startComprehensiveAppTeaching(): Promise<void> {
    if (this.dynamicTeachingActive) {
      console.log('[CompanionManager] Dynamic app teaching already active');
      return;
    }

    console.log('[CompanionManager] Starting comprehensive app teaching...');

    try {
      if (!this.dynamicAppTeacher) {
        this.dynamicAppTeacher = await createDynamicAppTeacher(
          this.menuBarPanelManager.panelWindow,
          false,
          this.ollamaHome // D drive installation
        );
      }

      this.dynamicTeachingActive = true;

      this.dynamicAppTeacher.startComprehensiveTeaching().catch((error: Error) => {
        console.error('[CompanionManager] Dynamic teaching error:', error);
        this.dynamicTeachingActive = false;
      });
    } catch (error) {
      console.error('[CompanionManager] Failed to start dynamic teaching:', error);
      this.dynamicTeachingActive = false;
    }
  }

  async startSpecificFeatureTeaching(feature: string): Promise<void> {
    if (this.dynamicTeachingActive) {
      console.log('[CompanionManager] Dynamic app teaching already active');
      return;
    }

    console.log(`[CompanionManager] Starting specific feature teaching: ${feature}`);

    try {
      if (!this.dynamicAppTeacher) {
        this.dynamicAppTeacher = await createDynamicAppTeacher(
          this.menuBarPanelManager.panelWindow,
          false,
          this.ollamaHome // D drive installation
        );
      }

      this.dynamicTeachingActive = true;

      this.dynamicAppTeacher.startSpecificTeaching(feature).catch((error: Error) => {
        console.error('[CompanionManager] Dynamic teaching error:', error);
        this.dynamicTeachingActive = false;
      });
    } catch (error) {
      console.error('[CompanionManager] Failed to start dynamic teaching:', error);
      this.dynamicTeachingActive = false;
    }
  }

  stopDynamicTeaching(): void {
    if (this.dynamicAppTeacher && this.dynamicTeachingActive) {
      console.log('[CompanionManager] Stopping dynamic teaching');
      this.dynamicAppTeacher.stopTeaching();
      this.dynamicTeachingActive = false;
    }
  }

  // Action exploration methods
  async exploreUIActions(): Promise<void> {
    console.log('[CompanionManager] Starting UI action exploration...');

    try {
      if (!this.actionExplorer) {
        this.actionExplorer = await createActionExplorer(
          this.menuBarPanelManager.panelWindow,
          false,
          this.ollamaHome // D drive installation
        );
      }

      const screenshot = await CompanionScreenCaptureUtility.captureAllScreensAsJPEG();
      const base64Img = screenshot[0]?.imageDataBase64 || '';

      const uiElements = await this.actionExplorer.scanner.performOCR(base64Img);

      await this.actionExplorer.exploreAllClickTypes(uiElements);
      await this.actionExplorer.exploreEmptyRegions();
      await this.actionExplorer.discoverShortcuts();

      console.log('[CompanionManager] UI exploration complete');
    } catch (error) {
      console.error('[CompanionManager] UI exploration error:', error);
    }
  }

  getDynamicTeachingStatus(): any {
    if (this.dynamicAppTeacher) {
      return this.dynamicAppTeacher.getSessionStatus();
    }
    return null;
  }
}
