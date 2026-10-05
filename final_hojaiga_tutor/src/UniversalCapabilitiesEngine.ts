import { ParsedOverlayCommand } from './CompanionManager';


export class UniversalCapabilitiesEngine {
  public static enrichCommands(
    userPrompt: string,
    commands: ParsedOverlayCommand[]
  ): ParsedOverlayCommand[] {
    const q = userPrompt.toLowerCase();


    // Wingman / Flirt Coach
    if (/\b(wingman|reply\s+to\s+her)\b/i.test(q)) {
      commands.push(
        { type: 'ACTOR', action: 'wingman', pov: '2nd', cx: 275, cy: 310, label: 'Your AI Wingman', color: 'cyan', loop: true },
        { type: 'WRITE', label: '1. [PLAYFUL TEASE]: ...', color: 'cyan' },
        { type: 'WRITE', label: '2. [WITTY CALLBACK]: ...', color: 'yellow' },
        { type: 'WRITE', label: '3. [SMOOTH ESCALATION]: ...', color: 'green' }
      );
    }
    // Mood DJ
    else if (/\b(play\s+a\s+synthwave|beat)\b/i.test(q)) {
      commands.push({ type: 'DJ', genre: 'synthwave', bpm: 108, cx: 280, cy: 320, label: 'Live DJ', color: 'purple', loop: true });
    }
    // Code Trace
    else if (/\b(bubble\s+sort|trace)\b/i.test(q)) {
      commands.push({ type: 'TRACE', values: ['38','14','52'], swapIndices: [0,1], pointerIndex: 1, label: 'Code Trace', color: 'yellow', loop: true });
    }


    return commands;
  }
}
