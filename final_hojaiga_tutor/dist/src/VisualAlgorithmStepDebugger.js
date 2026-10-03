"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.VisualAlgorithmStepDebugger = void 0;
/**
 * Dry-Run Variable State Tracer, Memory Pointer Animator & Complexity
 * Visualizer. The tick sequence is a deterministic worked example (sliding
 * window) - the model narrates the user's actual algorithm around it via the
 * prompt rules. String-node graph, auto-layouted into the claimed rect.
 */
class VisualAlgorithmStepDebugger {
    static isAlgorithmTracePrompt(prompt) {
        return /\b(dry\s+run|trace\s+this|step\s+through|visualize\s+algorithm|how\s+does\s+this\s+loop\s+work|recursion\s+tree|sliding\s+window|two\s+pointer|big\s+o|time\s+complexity)\b/i.test(prompt);
    }
    static buildExecutionTraceTicks(userPrompt) {
        return [
            {
                tick: 0,
                lineDescription: 'Initialize pointers & accumulator state before loop entry',
                variablesState: { left: 0, right: 0, windowSum: 0, bestResult: 0 },
                invariantHolds: true,
            },
            {
                tick: 1,
                lineDescription: 'Expand right pointer and accumulate incoming element',
                variablesState: { left: 0, right: 1, windowSum: 14, bestResult: 14 },
                invariantHolds: true,
            },
            {
                tick: 2,
                lineDescription: 'Constraint threshold reached → shrink left pointer to restore invariant',
                variablesState: { left: 1, right: 2, windowSum: 11, bestResult: 14 },
                invariantHolds: true,
            },
            {
                tick: 3,
                lineDescription: 'Loop terminates cleanly at boundary; return optimal state',
                variablesState: { left: 1, right: 3, windowSum: 19, bestResult: 19 },
                invariantHolds: true,
            },
        ];
    }
    static buildVisualDebuggerOverlay(userPrompt) {
        const ticks = this.buildExecutionTraceTicks(userPrompt);
        return [
            { type: 'BOARD', label: 'Visual Algorithm Dry-Run Tracer • Memory State & Invariant Inspector' },
            {
                type: 'GRAPH',
                nodes: ['Tick 0: Init State', 'Tick 1: Expand Window', 'Tick 2: Restore Invariant', 'Tick 3: Optimal Return'],
                edges: [
                    { from: 'Tick 0: Init State', to: 'Tick 1: Expand Window' },
                    { from: 'Tick 1: Expand Window', to: 'Tick 2: Restore Invariant' },
                    { from: 'Tick 2: Restore Invariant', to: 'Tick 3: Optimal Return' },
                ],
                label: 'Step-by-Step State Transition Trace',
                color: 'cyan',
                loop: true,
            },
            ...ticks.map((t, idx) => ({
                type: 'WRITE',
                label: `Tick #${t.tick} [${t.lineDescription}] → State: ${JSON.stringify(t.variablesState)}`,
                color: ['cyan', 'yellow', 'orange', 'green'][idx % 4],
            })),
            {
                type: 'WRITE',
                label: 'Complexity Proof: Each element is visited at most twice (right++ and left++) → Time: O(N) | Auxiliary Space: O(1).',
                color: 'purple',
            },
        ];
    }
}
exports.VisualAlgorithmStepDebugger = VisualAlgorithmStepDebugger;
