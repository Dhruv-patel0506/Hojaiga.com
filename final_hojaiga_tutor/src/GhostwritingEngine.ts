import { ParsedOverlayCommand } from './CompanionManager';

/**
 * Ghostwriting pipeline roadmap: Research -> Outline -> Draft -> Edit -> Voice.
 *
 * Merge note: node positions are hints only - the overlay GRAPH layout engine
 * recomputes positions to fit its claimed diagram rect, so the hardcoded
 * coordinates in the original paste were kept as inert defaults. Actual
 * ghostwritten prose comes from the model. Merged in place by
 * routeSpecializedEngines.
 */
export class GhostwritingEngine {
  public static isGhostwritePrompt(prompt: string): boolean {
    const q = prompt.toLowerCase();
    return (
      /\b(ghostwrite|write a (blog|article|essay|thread|newsletter|linkedin post|post for me)|blog post|newsletter|copywriting)\b/.test(q) ||
      (/\b(draft an article|twitter thread|x thread|writing pipeline)\b/.test(q))
    );
  }

  public static buildGhostwritingOverlay(userPrompt: string): ParsedOverlayCommand[] {
    const kind = this.guessKind(userPrompt);

    const nodes = [
      { id: 'research', label: 'Research', color: 'cyan', nodePosition: { x: 0, y: 0 } },
      { id: 'outline', label: 'Outline', color: 'yellow', nodePosition: { x: 0, y: 0 } },
      { id: 'draft', label: 'Draft', color: 'green', nodePosition: { x: 0, y: 0 } },
      { id: 'edit', label: 'Edit', color: 'orange', nodePosition: { x: 0, y: 0 } },
      { id: 'voice', label: 'Voice', color: 'magenta', nodePosition: { x: 0, y: 0 } },
    ];
    const edges = [
      { from: 'research', to: 'outline', label: 'sources', color: 'cyan' },
      { from: 'outline', to: 'draft', label: 'sections', color: 'yellow' },
      { from: 'draft', to: 'edit', label: 'rough', color: 'green' },
      { from: 'edit', to: 'voice', label: 'polish', color: 'orange' },
    ];

    const commands: ParsedOverlayCommand[] = [
      { type: 'BOARD', label: `Ghostwriting Pipeline • ${kind}` },
      { type: 'GRAPH', nodes, edges, showLegend: true, nodePositions: {} as Record<string, { x: number; y: number }> },
      { type: 'WRITE', label: '1. Research: 3-5 credible points + key quotes/numbers', color: 'cyan' },
      { type: 'WRITE', label: '2. Outline: hook, 3 sections, payoff - one line each', color: 'yellow' },
      { type: 'WRITE', label: '3. Draft: full pass, no self-editing, hit the outline', color: 'green' },
      { type: 'WRITE', label: '4. Edit: cut 15%, active voice, tighten first/last line', color: 'orange' },
      { type: 'WRITE', label: '5. Voice: match the requested author/brand tone', color: 'magenta' },
    ];

    return commands;
  }

  private static guessKind(prompt: string): string {
    const q = prompt.toLowerCase();
    if (/\bthread|x\b|twitter/.test(q)) return 'Thread';
    if (/newsletter/.test(q)) return 'Newsletter';
    if (/linkedin/.test(q)) return 'LinkedIn Post';
    if (/blog|article|essay/.test(q)) return 'Blog / Article';
    return 'Long-form Draft';
  }
}
