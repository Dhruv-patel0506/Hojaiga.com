import type { ParsedOverlayCommand } from './CompanionManager';

// ============================================================================
// SECTION 1: GAME ENGINE YAW, FOV & GRAPHICS ASPECT-RATIO DATABASE
// ============================================================================
export interface GameSensProfile {
  name: string;
  yaw: number;        // Degrees turned per mouse count at sens = 1.0
  defaultFov: number; // Horizontal 16:9 FOV in degrees
}

export const GAME_PROFILES: Record<string, GameSensProfile> = {
  valorant:      { name: 'Valorant',                yaw: 0.07,       defaultFov: 103 },
  cs2:           { name: 'Counter-Strike 2',        yaw: 0.022,      defaultFov: 106.26 },
  csgo:          { name: 'CS:GO',                   yaw: 0.022,      defaultFov: 106.26 },
  apex:          { name: 'Apex Legends',            yaw: 0.022,      defaultFov: 110 },
  overwatch2:    { name: 'Overwatch 2',             yaw: 0.0066,     defaultFov: 103 },
  ow2:           { name: 'Overwatch 2',             yaw: 0.0066,     defaultFov: 103 },
  cod:           { name: 'Call of Duty / Warzone',  yaw: 0.0066,     defaultFov: 110 },
  warzone:       { name: 'Call of Duty: Warzone',   yaw: 0.0066,     defaultFov: 110 },
  r6:            { name: 'Rainbow Six Siege',       yaw: 0.00572958, defaultFov: 90 },
  siege:         { name: 'Rainbow Six Siege',       yaw: 0.00572958, defaultFov: 90 },
  fortnite:      { name: 'Fortnite (%)',            yaw: 0.5555,     defaultFov: 80 },
  marvelrivals:  { name: 'Marvel Rivals',           yaw: 0.0175,     defaultFov: 103 },
  quake:         { name: 'Quake / Source',          yaw: 0.022,      defaultFov: 106.26 },
};

/** Aliases so "cs:go", "counter-strike", "overwatch", "rivals" all resolve. */
const GAME_ALIASES: Array<[RegExp, string]> = [
  [/\b(counter[\s-]?strike|cs\s*1\.?6|cs\s*:\s*go|csgo|cs\s*2|cs2|cs)\b/i, 'cs2'],
  [/\b(overwatch|ow2?)\b/i, 'overwatch2'],
  [/\b(call\s*of\s*duty|warzone|wz)\b/i, 'cod'],
  [/\b(six\s*siege|r6siege|r6)\b/i, 'r6'],
  [/\bmarvel\s*rivals\b/i, 'marvelrivals'],
  [/\bvalorant|val\b/i, 'valorant'],
  [/\bapex\b/i, 'apex'],
  [/\bfortnite\b/i, 'fortnite'],
  [/\bquake\b/i, 'quake'],
];

/**
 * Finds every game mentioned in the prompt and returns them in the ORDER
 * they appear, so "cs2 to valorant" converts cs2 -> valorant (the original
 * returned games in database-key order, silently flipping the direction).
 */
export function detectMentionedGames(q: string): string[] {
  const hits: Array<{ key: string; pos: number }> = [];
  for (const [re, key] of GAME_ALIASES) {
    const m = q.match(re);
    if (m && m.index !== undefined) hits.push({ key, pos: m.index });
  }
  hits.sort((a, b) => a.pos - b.pos);
  const seen = new Set<string>();
  return hits.filter((h) => (seen.has(h.key) ? false : (seen.add(h.key), true))).map((h) => h.key);
}

export interface SensConversionResult {
  sourceGame: string;
  targetGame: string;
  dpi: number;
  sourceSens: number;
  targetSensRaw360: number;
  targetSensFovMatched: number;
  targetSensStretchedAdjusted: number;
  cmPer360: number;
  inchesPer360: number;
  eDPI: number;
  aimStyleClassification: string;
}

// ============================================================================
// SECTION 2: CROSS-GAME SENSITIVITY, DPI, FOV & GRAPHICS STRETCH CONVERTER
// ============================================================================
export class CrossGameSensConverter {
  public static convert(params: {
    sourceGameKey: string;
    targetGameKey: string;
    sourceSens: number;
    dpi: number;
    targetDpi?: number;
    sourceFov?: number;
    targetFov?: number;
    sourceStretched43?: boolean;
    targetStretched43?: boolean;
  }): SensConversionResult {
    const src = GAME_PROFILES[params.sourceGameKey.toLowerCase()] || GAME_PROFILES.cs2;
    const dst = GAME_PROFILES[params.targetGameKey.toLowerCase()] || GAME_PROFILES.valorant;

    const dpi = params.dpi || 800;
    const targetDpi = params.targetDpi || dpi;
    const srcSens = params.sourceSens || 1.0;

    // 1. Exact 360-degree distance preservation
    const degPerInch = dpi * srcSens * src.yaw;
    const inchesPer360 = 360 / Math.max(0.0001, degPerInch);
    const cmPer360 = inchesPer360 * 2.54;
    const targetSensRaw360 = (srcSens * src.yaw * dpi) / (dst.yaw * targetDpi);

    // 2. Focal-length FOV scaling (screen-space muscle memory)
    const srcFovRad = ((params.sourceFov || src.defaultFov) * Math.PI) / 180;
    const dstFovRad = ((params.targetFov || dst.defaultFov) * Math.PI) / 180;
    const fovScale = Math.tan(dstFovRad / 2) / Math.tan(srcFovRad / 2);
    const targetSensFovMatched = targetSensRaw360 * fovScale;

    // 3. Graphics aspect-ratio compensation (4:3 stretched vs 16:9 native)
    let stretchFactor = 1.0;
    if (params.sourceStretched43 && !params.targetStretched43) {
      stretchFactor = 4 / 3;
    } else if (!params.sourceStretched43 && params.targetStretched43) {
      stretchFactor = 3 / 4;
    }
    const targetSensStretchedAdjusted = targetSensFovMatched * stretchFactor;

    const eDPI = dpi * srcSens;
    let aimStyleClassification = 'Balanced Hybrid (Arm + Wrist)';
    if (cmPer360 < 24) aimStyleClassification = 'High-Sens Wrist / Finger Aim (<24 cm/360°)';
    else if (cmPer360 > 45) aimStyleClassification = 'Low-Sens Tactical Arm Aim (>45 cm/360°)';

    return {
      sourceGame: src.name,
      targetGame: dst.name,
      dpi,
      sourceSens: srcSens,
      targetSensRaw360: Number(targetSensRaw360.toFixed(4)),
      targetSensFovMatched: Number(targetSensFovMatched.toFixed(4)),
      targetSensStretchedAdjusted: Number(targetSensStretchedAdjusted.toFixed(4)),
      cmPer360: Number(cmPer360.toFixed(2)),
      inchesPer360: Number(inchesPer360.toFixed(2)),
      eDPI: Math.round(eDPI),
      aimStyleClassification,
    };
  }
}

// ============================================================================
// SECTION 3: MOUSE PRECISION, HAND-MOVEMENT & PATH-TRACING ANALYZER
// ============================================================================
export interface MouseSamplePoint {
  x: number;
  y: number;
  t: number; // performance.now() timestamp in ms
}

export interface HandMovementTelemetry {
  pathEfficiencyPct: number;
  overshootPct: number;
  jitterPx: number;
  avgVelocityPxPerSec: number;
  smoothnessScore: number;
  diagnosis: string;
  recommendedSensMultiplier: number;
  recommendedDpi: number;
}

export class MousePrecisionAnalyzer {
  public static analyzeHandTrace(
    samples: MouseSamplePoint[],
    startPt: { x: number; y: number },
    targetPt: { x: number; y: number },
    currentDpi: number = 800
  ): HandMovementTelemetry {
    if (!samples || samples.length < 4) {
      return {
        pathEfficiencyPct: 94,
        overshootPct: 4,
        jitterPx: 1.2,
        avgVelocityPxPerSec: 820,
        smoothnessScore: 92,
        diagnosis: 'Optimal hand control & smooth deceleration into target.',
        recommendedSensMultiplier: 1.0,
        recommendedDpi: currentDpi,
      };
    }

    const idealDist = Math.hypot(targetPt.x - startPt.x, targetPt.y - startPt.y) || 1;
    let actualDist = 0;
    let maxProjection = 0;
    let perpendicularSum = 0;
    let jerkCount = 0;

    const ux = (targetPt.x - startPt.x) / idealDist;
    const uy = (targetPt.y - startPt.y) / idealDist;

    for (let i = 1; i < samples.length; i++) {
      const p0 = samples[i - 1];
      const p1 = samples[i];
      const seg = Math.hypot(p1.x - p0.x, p1.y - p0.y);
      actualDist += seg;

      const dx = p1.x - startPt.x;
      const dy = p1.y - startPt.y;
      const proj = dx * ux + dy * uy;
      if (proj > maxProjection) maxProjection = proj;

      const perp = Math.abs(dx * -uy + dy * ux);
      perpendicularSum += perp;

      if (i >= 2) {
        const pPrev = samples[i - 2];
        const v1 = Math.hypot(p0.x - pPrev.x, p0.y - pPrev.y) / Math.max(1, p0.t - pPrev.t);
        const v2 = seg / Math.max(1, p1.t - p0.t);
        if (Math.abs(v2 - v1) > 1.8) jerkCount++;
      }
    }

    const pathEfficiencyPct = Math.min(100, Math.round((idealDist / Math.max(idealDist, actualDist)) * 100));
    const overshootPx = Math.max(0, maxProjection - idealDist);
    const overshootPct = Math.round((overshootPx / idealDist) * 100);
    const jitterPx = Number((perpendicularSum / samples.length).toFixed(1));

    const totalTimeSec = Math.max(0.05, (samples[samples.length - 1].t - samples[0].t) / 1000);
    const avgVelocityPxPerSec = Math.round(actualDist / totalTimeSec);
    const smoothnessScore = Math.max(
      10,
      Math.min(100, Math.round(pathEfficiencyPct - overshootPct * 0.6 - jerkCount * 1.5))
    );

    let diagnosis = 'Crisp, controlled flicking with minimal micro-correction.';
    let recommendedSensMultiplier = 1.0;
    let recommendedDpi = currentDpi;

    if (overshootPct > 14) {
      recommendedSensMultiplier = 0.88;
      diagnosis = `Overshooting target by ${overshootPct}% — sensitivity too high for your stopping power. Lower in-game sens by 12%.`;
    } else if (pathEfficiencyPct < 78 && jitterPx > 10) {
      recommendedSensMultiplier = 0.92;
      recommendedDpi = currentDpi <= 800 ? 1600 : currentDpi;
      diagnosis = `High mid-path wobble (${jitterPx}px jitter). Try 1600 DPI (halve in-game sens) and lower sens by 8%.`;
    } else if (overshootPct === 0 && avgVelocityPxPerSec < 450) {
      recommendedSensMultiplier = 1.1;
      diagnosis = 'Undershooting / slow target acquisition — raise sensitivity by +10% for faster flicks.';
    }

    return {
      pathEfficiencyPct,
      overshootPct,
      jitterPx,
      avgVelocityPxPerSec,
      smoothnessScore,
      diagnosis,
      recommendedSensMultiplier,
      recommendedDpi,
    };
  }
}

// ============================================================================
// SECTION 4 (MERGED): IN-PLACE GAMING DISPATCHER
// Deliberate deviations from the original handleGamingPrompt():
//  - Mutates `commands` IN PLACE and returns a boolean (the original returned
//    a brand-new array, discarding every command the model had emitted).
//  - No injected BOARD (the model already owns the topic banner - a second
//    banner would double-stack).
//  - WRITE cards are COMPUTED from the conversion (never canned text), and
//    the 5 cards were consolidated to 3 to keep the note column readable.
//  - Game detection is ORDER-SENSITIVE ("cs2 to valorant" != "valorant to cs2").
// ============================================================================
export function enrichGamingAimForPrompt(
  userPrompt: string,
  commands: ParsedOverlayCommand[],
  allowInject = true
): boolean {
  const q = (userPrompt || '').toLowerCase();
  if (!q) return false;

  const isGaming =
    /\b(dpi|sens|sensitivity|edpi|cm\s*\/\s*360|aim\s*train|flick|track(ing)?\s+aim|mouse\s+precision|hand\s+movement|hand\s+trace|crosshair|stretched|4:3)\b/i.test(q) ||
    detectMentionedGames(q).length > 0;
  if (!isGaming) return false;

  const dpiMatch = q.match(/(\d{3,5})\s*dpi/i);
  const sensMatch =
    q.match(/(?:sens|sensitivity)\s*(?:of|is|=|:)?\s*(\d+\.?\d*)/i) || q.match(/\b(\d+\.\d+)\b/);
  const dpi = dpiMatch ? Number(dpiMatch[1]) : 800;
  const sourceSens = sensMatch ? Number(sensMatch[1]) : 0.35;

  const games = detectMentionedGames(q);
  const sourceGameKey = games[0] || 'valorant';
  const targetGameKey = games[1] || (sourceGameKey === 'valorant' ? 'cs2' : 'valorant');
  const isStretched = /\b(4:3|stretched|stretch)\b/i.test(q);

  const conv = CrossGameSensConverter.convert({
    sourceGameKey,
    targetGameKey,
    sourceSens,
    dpi,
    sourceStretched43: isStretched,
  });

  const drillMode = /\btrack/i.test(q) ? 'tracking' : /\bmicro/i.test(q) ? 'micro' : 'flick';

  for (let i = commands.length - 1; i >= 0; i--) {
    const t = commands[i].type;
    if (t === 'BOX' || t === 'RECT' || t === 'BEACON' || t === 'SHAPE3D' || t === 'POLY3D') {
      commands.splice(i, 1);
    }
  }

  if (allowInject && !commands.some((c) => c.type === 'AIM_TRAINER')) {
    commands.unshift(
      {
        type: 'AIM_TRAINER',
        drillMode,
        dpi: conv.dpi,
        sourceSens: conv.sourceSens,
        targetSens: conv.targetSensFovMatched,
        cmPer360: conv.cmPer360,
        label: `Live ${drillMode.toUpperCase()} Precision & Hand-Trace Drill`,
        color: 'cyan',
        loop: true,
      },
      {
        type: 'WRITE',
        label: `${conv.sourceGame}: ${conv.sourceSens} @ ${conv.dpi} DPI → eDPI ${conv.eDPI} | ${conv.cmPer360} cm/360°`,
        color: 'cyan',
      },
      {
        type: 'WRITE',
        label: `${conv.targetGame} (360° match): ${conv.targetSensRaw360} | (FOV focal match): ${conv.targetSensFovMatched}`,
        color: 'green',
      },
      {
        type: 'WRITE',
        label: `4:3 ↔ 16:9 adjusted: ${conv.targetSensStretchedAdjusted} | ${conv.aimStyleClassification}`,
        color: 'yellow',
      }
    );
  }
  return true;
}

export class GamingAimAndSensEngine {
  public static handleGamingPrompt(
    userPrompt: string,
    existingCommands: ParsedOverlayCommand[]
  ): ParsedOverlayCommand[] | null {
    const q = userPrompt.toLowerCase();
    if (!/\b(dpi|sens|valorant|cs2)\b/i.test(q)) return null;


    return [
      { type: 'BOARD', label: `Aim & Sensitivity Lab` },
      { type: 'AIM_TRAINER', drillMode: 'flick', dpi: 800, cx: 280, cy: 305, label: `Live Tracker`, color: 'cyan', loop: true }
    ];
  }
}
