import { ParsedOverlayCommand } from './CompanionManager';

export interface SocraticCard {
  step: number;
  type: 'QUESTION' | 'HINT' | 'CONCEPT' | 'ANSWER';
  text: string;
  color: string;
}

/**
 * Builds a Socratic-style homework roadmap.
 *
 * Merge note: the cards are a deterministic pedagogical STRUCTURE (question ->
 * hint -> concept -> answer) - the actual lesson prose still comes from the
 * model via the standard lesson text. Returned commands are merged in place by
 * routeSpecializedEngines (never replacing model commands).
 */
export class HomeworkSocraticTutor {
  public static isHomeworkPrompt(prompt: string): boolean {
    const q = prompt.toLowerCase();
    return (
      /\b(homework|worksheet|assignment|solve this problem|problem\s*\d|exam prep|study guide|quiz prep)\b/.test(q) ||
      (/\b(help me solve|step by step solution|show the working)\b/.test(q))
    );
  }

  public static buildSocraticOverlay(userPrompt: string): ParsedOverlayCommand[] {
    const subject = this.guessSubject(userPrompt);

    const nodes = [
      { id: 'q', label: 'Q', color: 'yellow', nodePosition: { x: 0, y: 0 } },
      { id: 'h', label: 'Hint', color: 'cyan', nodePosition: { x: 0, y: 0 } },
      { id: 'c', label: 'Concept', color: 'green', nodePosition: { x: 0, y: 0 } },
      { id: 'a', label: 'Answer', color: 'orange', nodePosition: { x: 0, y: 0 } },
    ];
    const edges = [
      { from: 'q', to: 'h', label: 'stuck?', color: 'yellow' },
      { from: 'h', to: 'c', label: 'recall', color: 'cyan' },
      { from: 'c', to: 'a', label: 'apply', color: 'green' },
    ];

    const commands: ParsedOverlayCommand[] = [
      { type: 'BOARD', label: `Socratic Homework • ${subject} • Think → Hint → Concept → Answer` },
      { type: 'GRAPH', nodes, edges, showLegend: true, nodePositions: {} as Record<string, { x: number; y: number }> },
    ];

    const cards: SocraticCard[] = [
      { step: 1, type: 'QUESTION', text: 'What exactly is being asked? Restate it in your own words.', color: 'yellow' },
      { step: 2, type: 'HINT', text: 'Which formula / rule from class is the entry point here?', color: 'cyan' },
      { step: 3, type: 'CONCEPT', text: 'Write the concept + its conditions before plugging numbers.', color: 'green' },
      { step: 4, type: 'ANSWER', text: 'Compute, sanity-check units/magnitude, then state the answer.', color: 'orange' },
    ];

    for (const card of cards) {
      commands.push({ type: 'WRITE', label: `${card.step}. [${card.type}] ${card.text}`, color: card.color });
    }

    return commands;
  }

  private static guessSubject(prompt: string): string {
    const q = prompt.toLowerCase();
    if (/\b(physics|velocity|force|kinetic|momentum)\b/.test(q)) return 'Physics';
    if (/\b(chem|reaction|mole|enthalpy|organic)\b/.test(q)) return 'Chemistry';
    if (/\b(calculus|integral|derivative|limit|algebra|matrix|quadratic)\b/.test(q)) return 'Math';
    if (/\b(biology|cell|mitosis|dna|enzyme)\b/.test(q)) return 'Biology';
    if (/\b(history|war|century|revolution)\b/.test(q)) return 'History';
    if (/\b(code|function|recursion|array|big o|algorithm)\b/.test(q)) return 'CS / Algorithms';
    return 'General';
  }
}
