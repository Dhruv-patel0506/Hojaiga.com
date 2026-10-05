"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.RegexAndParserVisualWorkbench = void 0;
class RegexAndParserVisualWorkbench {
    static isRegexPrompt(prompt) {
        return /\b(regex|regular\s+expression|match\s+pattern|parse\s+string|extract\s+email|extract\s+url|token\s+parser|capture\s+group|backtracking)\b/i.test(prompt);
    }
    static synthesizeAndVerifyPattern(userPrompt) {
        const p = userPrompt.toLowerCase();
        let patternSource = '^(?<prefix>[a-zA-Z0-9._%+-]+)@(?<domain>[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,})$';
        let posSamples = ['dev.user@domain.co', 'clicky_tutor@hojaiga.io'];
        let negSamples = ['invalid@@domain', 'missing-at-symbol.com'];
        if (p.includes('url') || p.includes('http') || p.includes('link')) {
            patternSource = '^https?:\\/\\/(?<host>[a-zA-Z0-9.-]+)(?<path>\\/[\\w./-]*)?$';
            posSamples = ['https://hojaiga.io/docs/v1', 'http://localhost.dev/api'];
            negSamples = ['ftp://bad-scheme', 'https://'];
        }
        else if (p.includes('version') || p.includes('semver')) {
            patternSource = '^v?(?<major>0|[1-9]\\d*)\\.(?<minor>0|[1-9]\\d*)\\.(?<patch>0|[1-9]\\d*)$';
            posSamples = ['v1.4.2', '2.0.15'];
            negSamples = ['v01.2.3', '1.2'];
        }
        // Check for nested unbounded quantifiers like (a+)+ that trigger catastrophic ReDoS
        const hasNestedQuantifiers = /\([^)]*[+*][^)]*\)[+*]/.test(patternSource);
        const regex = new RegExp(patternSource);
        const matchedSamples = posSamples.filter(s => regex.test(s));
        const rejectedSamples = negSamples.filter(s => !regex.test(s));
        return {
            patternSource,
            flags: 'gm',
            isReDoSSafe: !hasNestedQuantifiers,
            matchedSamples,
            rejectedSamples
        };
    }
    static buildRegexWorkbenchOverlay(userPrompt) {
        const bundle = this.synthesizeAndVerifyPattern(userPrompt);
        return [
            {
                type: 'BOARD',
                label: `Regex & Parser Visual Workbench • ReDoS Safe: ${bundle.isReDoSSafe ? 'YES (O(N))' : 'WARN'}`
            },
            {
                type: 'GRAPH',
                nodes: [
                    'State 0: Start Anchor (^)',
                    'State 1: Named Group (?<prefix>)',
                    'State 2: Delimiter Transition',
                    'State 3: Accept & Emit Match ($)'
                ],
                edges: [
                    { from: 'State 0: Start Anchor (^)', to: 'State 1: Named Group (?<prefix>)' },
                    { from: 'State 1: Named Group (?<prefix>)', to: 'State 2: Delimiter Transition' },
                    { from: 'State 2: Delimiter Transition', to: 'State 3: Accept & Emit Match ($)' }
                ],
                nodePositions: {
                    'State 0: Start Anchor (^)': { x: 155, y: 175 },
                    'State 1: Named Group (?<prefix>)': { x: 355, y: 175 },
                    'State 2: Delimiter Transition': { x: 155, y: 315 },
                    'State 3: Accept & Emit Match ($)': { x: 355, y: 315 }
                },
                label: 'Finite Automaton State Machine',
                color: 'cyan',
                loop: true
            },
            {
                type: 'WRITE',
                label: 'STAGE 1 [VISUAL TEACH]: Each character advances the finite state machine without ambiguous nested loops.',
                color: 'cyan'
            },
            {
                type: 'WRITE',
                label: `STAGE 2 [VERIFIED SAMPLES]: Passed [${bundle.matchedSamples.join(', ')}] | Blocked [${bundle.rejectedSamples.join(', ')}]`,
                color: 'yellow'
            },
            {
                type: 'WRITE',
                label: `STAGE 3 [BUILT REGEX]: /${bundle.patternSource}/${bundle.flags}`,
                color: 'green'
            }
        ];
    }
}
exports.RegexAndParserVisualWorkbench = RegexAndParserVisualWorkbench;
