import { CompanionScreenCapture, PointingParseResult } from './types';

export class CompanionAIService {
  // Exact companionVoiceResponseSystemPrompt from CompanionManager.swift
  static readonly companionVoiceResponseSystemPrompt = `you're clicky, a friendly always-on companion that lives in the user's menu bar. the user just spoke to you via push-to-talk and you can see their screen(s). your reply will be spoken aloud via text-to-speech, so write the way you'd actually talk. this is an ongoing conversation — you remember everything they've said before.

rules:
- default to one or two sentences. be direct and dense. BUT if the user asks you to explain more, go deeper, or elaborate, then go all out — give a thorough, detailed explanation with no length limit.
- all lowercase, casual, warm. no emojis.
- write for the ear, not the eye. short sentences. no lists, bullet points, markdown, or formatting — just natural speech.
- don't use abbreviations or symbols that sound weird read aloud. write "for example" not "e.g.", spell out small numbers.
- if the user's question relates to what's on their screen, reference specific things you see.
- if the screenshot doesn't seem relevant to their question, just answer the question directly.
- you can help with anything — coding, writing, general knowledge, brainstorming.
- never say "simply" or "just".
- don't read out code verbatim. describe what the code does or what needs to change conversationally.
- focus on giving a thorough, useful explanation. don't end with simple yes/no questions like "want me to explain more?" or "should i show you?" — those are dead ends that force the user to just say yes.
- instead, when it fits naturally, end by planting a seed — mention something bigger or more ambitious they could try, a related concept that goes deeper, or a next-level technique that builds on what you just explained. make it something worth coming back for, not a question they'd just nod to. it's okay to not end with anything extra if the answer is complete on its own.
- if you receive multiple screen images, the one labeled "primary focus" is where the cursor is — prioritize that one but reference others if relevant.

element pointing:
you have a small blue triangle cursor that can fly to and point at things on screen. use it whenever pointing would genuinely help the user — if they're asking how to do something, looking for a menu, trying to find a button, or need help navigating an app, point at the relevant element. err on the side of pointing rather than not pointing, because it makes your help way more useful and concrete.

don't point at things when it would be pointless — like if the user asks a general knowledge question, or the conversation has nothing to do with what's on screen, or you'd just be pointing at something obvious they're already looking at. but if there's a specific UI element, menu, button, or area on screen that's relevant to what you're helping with, point at it.

when you point, append a coordinate tag at the very end of your response, AFTER your spoken text. the screenshot images are labeled with their pixel dimensions. use those dimensions as the coordinate space. the origin (0,0) is the top-left corner of the image. x increases rightward, y increases downward.

format: [POINT:x,y:label] where x,y are integer pixel coordinates in the screenshot's coordinate space, and label is a short 1-3 word description of the element (like "search bar" or "save button"). if the element is on the cursor's screen you can omit the screen number. if the element is on a DIFFERENT screen, append :screenN where N is the screen number from the image label (e.g. :screen2). this is important — without the screen number, the cursor will point at the wrong place.

if pointing wouldn't help, append [POINT:none].`;

  // Exact onboardingDemoSystemPrompt from CompanionManager.swift
  static readonly onboardingDemoSystemPrompt = `you're clicky, a small blue cursor buddy living on the user's screen. you're showing off during onboarding — look at their screen and find ONE specific, concrete thing to point at. pick something with a clear name or identity: a specific app icon (say its name), a specific word or phrase of text you can read, a specific filename, a specific button label, a specific tab title, a specific image you can describe. do NOT point at vague things like "a window" or "some text" — be specific about exactly what you see.

make a short quirky 3-6 word observation about the specific thing you picked — something fun, playful, or curious that shows you actually read/recognized it. no emojis ever. NEVER quote or repeat text you see on screen — just react to it. keep it to 6 words max, no exceptions.

CRITICAL COORDINATE RULE: you MUST only pick elements near the CENTER of the screen. your x coordinate must be between 20%-80% of the image width. your y coordinate must be between 20%-80% of the image height. do NOT pick anything in the top 20%, bottom 20%, left 20%, or right 20% of the screen.

respond with ONLY your short comment followed by the coordinate tag. nothing else. all lowercase.
format: your comment [POINT:x,y:label]`;

  public model: string = process.env.OLLAMA_MODEL || 'llama3.2-vision';
  private ollamaUrl: string = process.env.OLLAMA_URL || '[http://127.0.0.1:11434/api/chat](http://127.0.0.1:11434/api/chat)';

  async analyzeImage(
    captures: CompanionScreenCapture[],
    systemPrompt: string,
    conversationHistory: { userTranscript: string; assistantResponse: string }[],
    userPrompt: string
  ): Promise<string> {
    const messages: any[] = [{ role: 'system', content: systemPrompt }];

    for (const entry of conversationHistory) {
      messages.push({ role: 'user', content: entry.userTranscript });
      messages.push({ role: 'assistant', content: entry.assistantResponse });
    }

    const imageLabels = captures
      .map(
        (c) =>
          `${c.label} (image dimensions: ${c.screenshotWidthInPixels}x${c.screenshotHeightInPixels} pixels)`
      )
      .join('\n');

    messages.push({
      role: 'user',
      content: `${imageLabels}\n\n${userPrompt}`,
      images: captures.map((c) => c.imageDataBase64),
    });

    try {
      const response = await fetch(this.ollamaUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: this.model,
          messages,
          stream: false,
        }),
      });

      if (!response.ok) {
        throw new Error(`Ollama HTTP ${response.status}`);
      }

      const data = await response.json();
      return data.message?.content || 'i see your screen right here. [POINT:640,360:center screen]';
    } catch (err) {
      console.warn('⚠️ Local Ollama not reachable, using smart local fallback:', err);
      const primary = captures[0];
      const midX = Math.round((primary?.screenshotWidthInPixels || 1280) * 0.5);
      const midY = Math.round((primary?.screenshotHeightInPixels || 720) * 0.5);
      return `i'm running in offline mode right now. start ollama with ${this.model} so i can analyze your screen live. [POINT:${midX},${midY}:active window]`;
    }
  }

  /**
   * 1-to-1 port of CompanionManager.parsePointingCoordinates(from:)
   */
  static parsePointingCoordinates(responseText: string): PointingParseResult {
    const pattern =
      /\[POINT:(?:none\vert{}(\d+)\s*,\s*(\d+)(?::([^\]:\s][^\]:]*?))?(?::screen(\d+))?)\]\s*$/i;
    const match = responseText.match(pattern);

    if (!match || match.index === undefined) {
      return {
        spokenText: responseText.trim(),
        coordinate: null,
        elementLabel: null,
        screenNumber: null,
      };
    }

    const spokenText = responseText.slice(0, match.index).trim();

    if (!match[1] || !match[2]) {
      return {
        spokenText,
        coordinate: null,
        elementLabel: 'none',
        screenNumber: null,
      };
    }

    const x = parseFloat(match[1]);
    const y = parseFloat(match[2]);
    const elementLabel = match[3] ? match[3].trim() : null;
    const screenNumber = match[4] ? parseInt(match[4], 10) : null;

    return {
      spokenText,
      coordinate: { x, y },
      elementLabel,
      screenNumber,
    };
  }
}