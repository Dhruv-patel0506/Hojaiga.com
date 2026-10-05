"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.LiveIDEPairProgrammer = void 0;
const DynamicAppScannerAndTeacher_1 = require("./DynamicAppScannerAndTeacher");
/**
 * Real-Time IDE Stuck-Detector, Visual Unblocker & Context-Aware Code Completer.
 *
 * Merge note: editor/diagnostics highlights use UIRECT (true screen coords,
 * never clamped into the diagram zone) instead of the original [BOX] - same
 * rationale as the AppScanner: the highlight must sit on the real control.
 */
class LiveIDEPairProgrammer {
    static isIDEPairPrompt(prompt) {
        return /\b(i\s+am\s+stuck|im\s+stuck|help\s+me\s+finish|complete\s+this\s+code|how\s+do\s+i\s+write\s+this\s+part|pair\s+program|fix\s+my\s+editor|vscode\s+help|what\s+should\s+i\s+type\s+next)\b/i.test(prompt);
    }
    static classifyStuckPoint(prompt) {
        const p = prompt.toLowerCase();
        if (/\b(async|await|promise|callback|race\s+condition|fetch)\b/.test(p))
            return 'ASYNC_FLOW';
        if (/\b(type|interface|generic|typescript|null|undefined|cannot\s+assign)\b/.test(p))
            return 'TYPE_MISMATCH';
        if (/\b(loop|recursion|tree|graph|dp|dynamic\s+programming|off\s+by\s+one)\b/.test(p))
            return 'ALGORITHM_EDGE_CASE';
        if (/\b(api|endpoint|headers|auth|cors|json|webhook)\b/.test(p))
            return 'API_INTEGRATION';
        return 'GENERAL_IMPLEMENTATION';
    }
    static async buildLivePairProgrammerOverlay(userPrompt) {
        let snap = {
            windowTitle: 'Code Editor',
            elements: [],
        };
        try {
            snap = await DynamicAppScannerAndTeacher_1.DynamicAppScannerAndTeacher.scanActiveOrNamedApp();
        }
        catch {
            /* scan is best-effort */
        }
        const category = this.classifyStuckPoint(userPrompt);
        const commands = [
            {
                type: 'BOARD',
                label: `Live IDE Pair Programmer • Active Editor: ${snap.windowTitle} (${category})`,
            },
        ];
        // Highlight the active editor surface and terminal/problems pane if visible.
        const editorControls = snap.elements.slice(0, 2);
        editorControls.forEach((el, idx) => {
            commands.push({
                type: 'UIRECT',
                x: el.x,
                y: el.y,
                w: el.width,
                h: el.height,
                label: (idx === 0 ? `Active Code Region: ${el.name}` : `Inspector / Diagnostics: ${el.name}`).slice(0, 60),
                color: idx === 0 ? 'cyan' : 'yellow',
            });
        });
        const guidanceMap = {
            ASYNC_FLOW: [
                '1. Wrap the awaiting call in try/catch and enforce an AbortController timeout.',
                '2. Await independent promises in parallel with Promise.allSettled() to prevent single-failure cascades.',
                '3. Return a normalized { data, error } tuple so the caller never crashes on unhandled rejections.',
            ],
            TYPE_MISMATCH: [
                '1. Define the explicit input/output interface above the function before touching the body.',
                '2. Use a type predicate (x is TargetType) or narrowing guard to eliminate undefined/null branches.',
                '3. Replace any/unknown casts with generic constraints (<T extends Record<string, unknown>>).',
            ],
            ALGORITHM_EDGE_CASE: [
                '1. Write the base/termination condition on Line 1 (empty array, single element, or index out of bounds).',
                '2. Track loop invariants with explicit left/right pointers instead of mutating the array in-place.',
                '3. Dry-run with a 2-element input to verify no off-by-one infinite loop occurs.',
            ],
            API_INTEGRATION: [
                '1. Validate request payload schema and required headers before dispatching the network call.',
                '2. Check HTTP status codes explicitly (!res.ok) before calling res.json().',
                '3. Add exponential backoff retry for transient 429 / 503 status codes.',
            ],
            GENERAL_IMPLEMENTATION: [
                '1. Isolate pure business logic into a small helper function with zero side effects.',
                '2. Pass external dependencies (file system, clock, network) as parameters for instant testability.',
                '3. Log state at entry and exit boundaries to verify data transformation.',
            ],
        };
        const steps = guidanceMap[category];
        commands.push({
            type: 'GRAPH',
            nodes: ['Current Cursor State', 'Missing Guard / Bridge', 'Target Output State'],
            edges: [
                { from: 'Current Cursor State', to: 'Missing Guard / Bridge' },
                { from: 'Missing Guard / Bridge', to: 'Target Output State' },
            ],
            label: 'Unblocking Bridge Diagram',
            color: 'green',
            loop: true,
        }, { type: 'WRITE', label: `Unblock Step A: ${steps[0]}`, color: 'cyan' }, { type: 'WRITE', label: `Unblock Step B: ${steps[1]}`, color: 'yellow' }, { type: 'WRITE', label: `Unblock Step C: ${steps[2]}`, color: 'green' });
        return commands;
    }
}
exports.LiveIDEPairProgrammer = LiveIDEPairProgrammer;
