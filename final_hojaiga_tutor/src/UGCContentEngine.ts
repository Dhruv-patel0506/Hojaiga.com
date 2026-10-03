import { ParsedOverlayCommand } from './CompanionManager';

/**
 * UGC (user-generated content) ad/hook builder.
 *
 * Merge note: cards are a deterministic hook STRUCTURE (Hook -> Problem ->
 * Proof -> CTA); actual ad copy comes from the model. ACTOR 'wave' presenter
 * renders via the existing dynamic-rig actor engine. Commands are merged
 * in place by routeSpecializedEngines.
 */
export class UGCContentEngine {
  public static isUGCPrompt(prompt: string): boolean {
    const q = prompt.toLowerCase();
    return (
      /\b(ugc|tiktok|reels?|shorts?|instagram ad|hook script|ad copy|pitch script|unboxing|testimonial script)\b/.test(q) ||
      (/\b(social media script|creator script|brand deal)\b/.test(q))
    );
  }

  public static buildUGCOverlay(userPrompt: string): ParsedOverlayCommand[] {
    const product = this.guessProduct(userPrompt);

    const commands: ParsedOverlayCommand[] = [
      { type: 'BOARD', label: `UGC Studio • ${product} • 15s Script Structure` },
      {
        type: 'ACTOR',
        action: 'wave',
        pov: 'third',
        label: 'Creator on camera',
        color: 'cyan',
      },
      { type: 'WRITE', label: '0-2s HOOK: pattern-interrupt line + fast zoom', color: 'yellow' },
      { type: 'WRITE', label: '2-6s PROBLEM: name the pain the viewer feels today', color: 'orange' },
      { type: 'WRITE', label: '6-11s PROOF: demo / before-after / social proof', color: 'green' },
      { type: 'WRITE', label: '11-15s CTA: one clear action, on-screen text + verbal', color: 'cyan' },
    ];

    return commands;
  }

  private static guessProduct(prompt: string): string {
    const m =
      prompt.match(/\b(?:for|about|selling|promote|promoting)\s+([a-z0-9][a-z0-9 \-']{2,30})/i) ||
      prompt.match(/\b(product|app|brand|shop|store)\b/i);
    if (m && m[1]) return m[1].trim().slice(0, 32);
    return 'Your Product';
  }
}
