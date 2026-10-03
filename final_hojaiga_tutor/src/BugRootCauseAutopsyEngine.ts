import { ParsedOverlayCommand } from './CompanionManager';

export interface BugAutopsyReport {
  errorSignature: string;
  rootCauseExplanation: string;
  brokenInvariant: string;
  defensiveFixPattern: string;
}

/**
 * Visual Stack-Trace Autopsy, Failure-Chain Diagrammer & Verified Fix Tutor.
 * Diagnostic rules are structural categories; the model writes the concrete
 * patch explanation in its spoken text / WRITE cards per prompt rules.
 */
export class BugRootCauseAutopsyEngine {
  public static isBugAutopsyPrompt(prompt: string): boolean {
    return /\b(bug|error|exception|stack\s+trace|crash|why\s+is\s+this\s+failing|typeerror|referenceerror|syntaxerror|nullpointer|segfault|panic|not\s+working)\b/i.test(prompt);
  }

  public static diagnoseBugCause(prompt: string): BugAutopsyReport {
    if (/cannot\s+read\s+propert|undefined|null/i.test(prompt)) {
      return {
        errorSignature: 'Null / Undefined Dereference Trap',
        rootCauseExplanation: 'An object or async response was accessed before verifying its existence.',
        brokenInvariant: 'Assumed upstream data is always populated on first render/tick.',
        defensiveFixPattern: 'Use optional chaining (obj?.prop ?? fallback) and an explicit early-return guard.',
      };
    }
    if (/maximum\s+call\s+stack|recursion|infinite/i.test(prompt)) {
      return {
        errorSignature: 'Unbounded Recursion / State Cycle',
        rootCauseExplanation: 'Recursive call or state listener re-triggers itself without converging toward a base case.',
        brokenInvariant: 'Missing strictly decreasing termination measure or visited-set guard.',
        defensiveFixPattern: 'Add a base-case return on Line 1 and track visited nodes in a Set<string>().',
      };
    }
    return {
      errorSignature: 'Contract & Boundary Mismatch',
      rootCauseExplanation: 'Runtime input shape or state transition diverged from the function assumption.',
      brokenInvariant: 'Unvalidated external input crossed into core domain logic.',
      defensiveFixPattern: 'Normalize and validate input types at the boundary before executing state mutations.',
    };
  }

  public static buildBugAutopsyOverlay(userPrompt: string): ParsedOverlayCommand[] {
    const report = this.diagnoseBugCause(userPrompt);

    return [
      { type: 'BOARD', label: `Bug Root-Cause Autopsy • ${report.errorSignature}` },
      {
        type: 'GRAPH',
        nodes: ['1. Trigger Input', '2. Broken Assumption', '3. Crash / Exception', '4. Guarded Patch'],
        edges: [
          { from: '1. Trigger Input', to: '2. Broken Assumption' },
          { from: '2. Broken Assumption', to: '3. Crash / Exception' },
          { from: '3. Crash / Exception', to: '4. Guarded Patch' },
        ],
        label: 'Causal Failure Chain & Recovery Point',
        color: 'orange',
        loop: true,
      },
      { type: 'WRITE', label: `WHY IT BROKE: ${report.rootCauseExplanation}`, color: 'red' },
      { type: 'WRITE', label: `VIOLATED INVARIANT: ${report.brokenInvariant}`, color: 'yellow' },
      { type: 'WRITE', label: `VERIFIED FIX PATTERN: ${report.defensiveFixPattern}`, color: 'green' },
    ];
  }
}
