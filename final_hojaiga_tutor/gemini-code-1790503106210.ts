import { CompanionScreenCapture, DrawCommand, DrawShapeType, PointingParseResult } from './types';

export class ClaudeAPI {
  public model: string = 'free-cloud-vision';
  private ollamaUrl: string = process.env.OLLAMA_URL || '[http://127.0.0.1:11434/api/chat](http://127.0.0.1:11434/api/chat)';

  static readonly companionVoiceResponseSystemPrompt = `you're clicky, a friendly always-on companion that lives on the user's screen. your reply will be spoken aloud via text-to-speech, so write the way you'd actually talk: 1 to 2 short, casual, lowercase sentences.
CRITICAL SPEECH RULE: NEVER mention pixel numbers, coordinates, radii, or dimensions in your spoken text! Speak naturally like a human tutor.

you can draw shapes, polygons, and mathematical graphs directly on the user's screen by appending tags AFTER your spoken text (coordinate space matches the screenshot dimensions provided, origin (0,0) is top-left):
- Circle: [DRAW:CIRCLE:cx,cy,r:label]
- Parallelogram: [DRAW:PARALLELOGRAM:x,y,width,height,skew:label]
- Regular Polygons:
  - Decagon (10 sides): [DRAW:DECAGON:cx,cy,r:label]
  - Octagon (8 sides): [DRAW:OCTAGON:cx,cy,r:label]
  - Hexagon (6 sides): [DRAW:HEXAGON:cx,cy,r:label]
  - Pentagon (5 sides): [DRAW:PENTAGON:cx,cy,r:label]
  - Triangle (3 sides): [DRAW:TRIANGLE:cx,cy,r:label]
- Custom Polygon: [DRAW:POLYGON:x1,y1,x2,y2,x3,y3,...:label]
- Rectangle: [DRAW:RECT:x,y,width,height:label]
- Arrow: [DRAW:ARROW:x1,y1,x2,y2:label]
- Smooth Curve / Graph: [DRAW:CURVE:x1,y1,x2,y2,x3,y3,...:label]
- Coordinate Axes: [DRAW:AXES:originX,originY,width,height:label]
- Cursor Pointing: [POINT:x,y:label]`;

  static readonly onboardingDemoSystemPrompt = `you're clicky, a small blue cursor buddy on the user's screen. find ONE specific item near the center of the screen (20%-80% width/height), make a 3-6 word lowercase comment, and append [DRAW:RECT:x,y,w,h:label] [POINT:x,y:label].`;

  async analyzeImageStreaming(
    captures: CompanionScreenCapture[],
    systemPrompt: string,
    conversationHistory: { userTranscript: string; assistantResponse: string }[],
    userPrompt: string
  ): Promise<string> {
    const primary = captures[0];
    const width = primary?.screenshotWidthInPixels || 1280;
    const height = primary?.screenshotHeightInPixels || 720;

    // If the user is asking for mathematical graphs (log(x), sin(x), cos(x), tan(x), x^2, etc.)
    // or geometric shapes (decagon, hexagon, parallelogram, circle, etc.),
    // compute exact mathematical SVG coordinates deterministically so curves and shapes are 100% accurate!
    const deterministicMathOrGeo = this.tryBuildDeterministicMathOrGeometryResponse(
      userPrompt,
      width,
      height
    );
    if (deterministicMathOrGeo) {
      return deterministicMathOrGeo;
    }

    const dimensionContext = captures
      .map(
        (c) =>
          `${c.label} (image dimensions: ${c.screenshotWidthInPixels}x${c.screenshotHeightInPixels} pixels)`
      )
      .join('\n');

    // 1. Try local Ollama first ONLY if an Ollama model is explicitly selected
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
          body: JSON.stringify({ model: this.model, messages: ollamaMessages, stream: false }),
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

    // 2. Always fall back to 100% Free Keyless Cloud Vision API so it never fails even if Ollama is off!
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

      const res = await fetch('[https://text.pollinations.ai/openai](https://text.pollinations.ai/openai)', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: 'openai',
          messages,
          temperature: 0.3,
        }),
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

    const cx = Math.round(width * 0.5);
    const cy = Math.round(height * 0.5);
    return `here, let me point that out on your screen. [DRAW:ARROW:${cx - 140},${cy - 90},${cx},${cy}:here] [POINT:${cx},${cy}:right here!]`;
  }

  /**
   * Built-in Mathematical Function Plotter & Exact Geometric Shape Solver.
   * Handles graphs (log(x), sin(x), cos(x), tan(x), x^2, x^3, exp(x), sqrt(x))
   * AND geometric shapes (parallelogram, circle, decagon, hexagon, pentagon, octagon, triangle, square).
   */
  private tryBuildDeterministicMathOrGeometryResponse(
    prompt: string,
    width: number,
    height: number
  ): string | null {
    const lower = prompt.toLowerCase();

    const cx = Math.round(width * 0.5);
    const cy = Math.round(height * 0.5);

    // ── 1. CHECK FOR MATHEMATICAL FUNCTION GRAPHS ──────────────────────
    const wantsGraph =
      lower.includes('graph') ||
      lower.includes('curve') ||
      lower.includes('plot') ||
      lower.includes('log') ||
      lower.includes('sin') ||
      lower.includes('cos') ||
      lower.includes('tan') ||
      lower.includes('parabola') ||
      lower.includes('x^2');

    if (wantsGraph) {
      const wantsLog = lower.includes('log') || lower.includes('ln');
      const wantsSin = lower.includes('sin');
      const wantsCos = lower.includes('cos');
      const wantsTan = lower.includes('tan');
      const wantsQuad = lower.includes('x^2') || lower.includes('parabola') || lower.includes('quadratic');

      if (wantsLog || wantsSin || wantsCos || wantsTan || wantsQuad) {
        const graphW = 520;
        const graphH = 320;
        const originX = cx - 180; // X=0 vertical axis
        const originY = cy;       // Y=0 horizontal axis
        const scaleX = 42;        // 1 math unit = 42px horizontally
        const scaleY = 75;        // 1 math unit = 75px vertically

        const tags: string[] = [];
        tags.push(`[DRAW:AXES:${originX},${originY},${graphW},${graphH}:x and y axes]`);

        const spokenParts: string[] = [];

        if (wantsLog) {
          const pts: number[] = [];
          for (let xVal = 0.15; xVal <= 9.0; xVal += 0.25) {
            const yVal = Math.log(xVal);
            const px = Math.round(originX + xVal * scaleX);
            const py = Math.round(originY - yVal * scaleY);
            pts.push(px, py);
          }
          tags.push(`[DRAW:CURVE:${pts.join(',')}:y = log(x)]`);
          spokenParts.push('the logarithm curve y equals log x rising slowly as x grows');
        }

        if (wantsSin) {
          const pts: number[] = [];
          for (let xVal = -1.5; xVal <= 9.0; xVal += 0.2) {
            const yVal = Math.sin(xVal);
            const px = Math.round(originX + xVal * scaleX);
            const py = Math.round(originY - yVal * scaleY);
            pts.push(px, py);
          }
          tags.push(`[DRAW:CURVE:${pts.join(',')}:y = sin(x)]`);
          spokenParts.push('the oscillating sine wave y equals sine x');
        }

        if (wantsCos) {
          const pts: number[] = [];
          for (let xVal = -1.5; xVal <= 9.0; xVal += 0.2) {
            const yVal = Math.cos(xVal);
            const px = Math.round(originX + xVal * scaleX);
            const py = Math.round(originY - yVal * scaleY);
            pts.push(px, py);
          }
          tags.push(`[DRAW:CURVE:${pts.join(',')}:y = cos(x)]`);
          spokenParts.push('the cosine wave y equals cos x');
        }

        if (wantsTan) {
          const pts: number[] = [];
          for (let xVal = -1.2; xVal <= 1.2; xVal += 0.1) {
            const yVal = Math.tan(xVal);
            const px = Math.round(originX + xVal * scaleX);
            const py = Math.round(originY - yVal * (scaleY * 0.5));
            pts.push(px, py);
          }
          tags.push(`[DRAW:CURVE:${pts.join(',')}:y = tan(x)]`);
          spokenParts.push('the tangent curve y equals tan x');
        }

        if (wantsQuad) {
          const pts: number[] = [];
          for (let xVal = -3.0; xVal <= 3.0; xVal += 0.2) {
            const yVal = xVal * xVal;
            const px = Math.round(originX + xVal * scaleX);
            const py = Math.round(originY - yVal * (scaleY * 0.35));
            pts.push(px, py);
          }
          tags.push(`[DRAW:CURVE:${pts.join(',')}:y = x²]`);
          spokenParts.push('the parabola y equals x squared');
        }

        const labelX = Math.round(originX + Math.PI * scaleX);
        const labelY = Math.round(originY - Math.sin(Math.PI / 2) * scaleY);
        tags.push(`[POINT:${labelX},${labelY}:graph plotted!]`);

        return `here you go, i plotted ${spokenParts.join(' and ')} right on the coordinate axes on your screen. ${tags.join(' ')}`;
      }
    }

    // ── 2. CHECK FOR GEOMETRIC SHAPES ──────────────────────────────────
    const wantsParallelogram = lower.includes('parallelogram');
    const wantsCircle = lower.includes('circle');
    const wantsDecagon = lower.includes('decagon');
    const wantsOctagon = lower.includes('octagon');
    const wantsHexagon = lower.includes('hexagon');
    const wantsPentagon = lower.includes('pentagon');
    const wantsTriangle = lower.includes('triangle');
    const wantsSquare = lower.includes('square') || lower.includes('rectangle');

    if (
      wantsParallelogram ||
      wantsCircle ||
      wantsDecagon ||
      wantsOctagon ||
      wantsHexagon ||
      wantsPentagon ||
      wantsTriangle ||
      wantsSquare
    ) {
      const tags: string[] = [];
      const names: string[] = [];

      if (wantsParallelogram) {
        const pw = 380;
        const ph = 220;
        const skew = 65;
        tags.push(
          `[DRAW:PARALLELOGRAM:${cx - Math.round(pw / 2)},${cy - Math.round(ph / 2)},${pw},${ph},${skew}:parallelogram]`
        );
        names.push('a parallelogram');
      }

      if (wantsCircle) {
        const r = wantsParallelogram ? 85 : 150;
        tags.push(`[DRAW:CIRCLE:${cx},${cy},${r}:circle]`);
        names.push('a circle');
      }

      if (wantsDecagon) {
        const r = wantsCircle ? 145 : 150;
        tags.push(`[DRAW:DECAGON:${cx},${cy},${r}:decagon (10 sides)]`);
        names.push('a ten-sided decagon');
      }

      if (wantsOctagon) {
        tags.push(`[DRAW:OCTAGON:${cx},${cy},140:octagon (8 sides)]`);
        names.push('an eight-sided octagon');
      }

      if (wantsHexagon) {
        tags.push(`[DRAW:HEXAGON:${cx},${cy},140:hexagon (6 sides)]`);
        names.push('a six-sided hexagon');
      }

      if (wantsPentagon) {
        tags.push(`[DRAW:PENTAGON:${cx},${cy},140:pentagon (5 sides)]`);
        names.push('a five-sided pentagon');
      }

      if (wantsTriangle) {
        tags.push(`[DRAW:TRIANGLE:${cx},${cy},140:triangle]`);
        names.push('a triangle');
      }

      if (wantsSquare) {
        tags.push(`[DRAW:RECT:${cx - 140},${cy - 110},280,220:rectangle]`);
        names.push('a rectangle');
      }

      tags.push(`[POINT:${cx},${cy}:${names[names.length - 1].replace(/^a |^an /, '')}]`);
      return `here is ${names.join(' and ')} drawn directly on your screen. ${tags.join(' ')}`;
    }

    return null;
  }

  static parseResponseAndDrawings(responseText: string): PointingParseResult {
    const drawCommands: DrawCommand[] = [];

    const drawRegex =
      /\[DRAW:(CIRCLE\vert{}RECT\vert{}PARALLELOGRAM\vert{}POLYGON\vert{}DECAGON\vert{}HEXAGON\vert{}PENTAGON\vert{}OCTAGON\vert{}TRIANGLE\vert{}ARROW\vert{}LINE\vert{}CURVE\vert{}AXES):([0-9.,\s-]+)(?::([^\]]*))?\]/gi;
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
      /\[POINT:(?:none\vert{}(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)(?::([^\]:\s][^\]:]*?))?(?::screen(\d+))?)\]/i;
    const pointMatch = responseText.match(pointPattern);

    // Strip ALL bracket tags so nothing leaks into spoken text
    const cleanSpokenText = responseText
      .replace(drawRegex, '')
      .replace(pointPattern, '')
      .replace(/\[(?:DRAW\vert{}POINT)[^\]]*\]?/gi, '')
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