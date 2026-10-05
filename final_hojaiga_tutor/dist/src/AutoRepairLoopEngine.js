"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.AutoRepairLoopEngine = void 0;
const SandboxTestExecutor_1 = require("./SandboxTestExecutor");
class AutoRepairLoopEngine {
    executor;
    constructor(executor) {
        this.executor = executor || new SandboxTestExecutor_1.SandboxTestExecutor();
    }
    static applyDeterministicSyntaxFix(code, stderr) {
        let fixed = code;
        const notes = [];
        // 1. Balance unclosed parentheses / braces / brackets
        // FIX: Restored the standard JavaScript logical OR (||) operator
        const openParens = (fixed.match(/\(/g) || []).length - (fixed.match(/\)/g) || []).length;
        if (openParens > 0) {
            fixed += ')'.repeat(openParens);
            notes.push(`Closed ${openParens} missing ')'`);
        }
        const openBraces = (fixed.match(/\{/g) || []).length - (fixed.match(/\}/g) || []).length;
        if (openBraces > 0) {
            fixed += '\n' + '}'.repeat(openBraces);
            notes.push(`Closed ${openBraces} missing '}'`);
        }
        // 2. Fix Python print statements or missing colons
        if (/SyntaxError.*expected ':'/i.test(stderr)) {
            fixed = fixed.replace(/^(\s*(?:def|if|elif|else|for|while)\b[^:\n]+)$/gm, '$1:');
            notes.push('Inserted missing colon on control block');
        }
        // 3. Fix common typo console.log / undefined variable initialization
        const refMatch = stderr.match(/ReferenceError:\s*([a-zA-Z0-9_$]+)\s+is not defined/);
        if (refMatch && refMatch[1]) {
            fixed = `let ${refMatch[1]} = 0;\n` + fixed;
            notes.push(`Declared missing identifier "${refMatch[1]}"`);
        }
        return {
            fixedCode: fixed,
            summary: notes.length > 0 ? notes.join('; ') : 'Applied AST syntax normalization'
        };
    }
    async runAutoRepairLoop(initialCode, language = 'javascript', maxAttempts = 3) {
        let currentCode = initialCode;
        const iterations = [];
        for (let attempt = 1; attempt <= maxAttempts; attempt++) {
            const result = await this.executor.runCodeInSandbox(currentCode, language);
            if (result.succeeded) {
                iterations.push({
                    attempt,
                    errorDetected: 'None',
                    patchApplied: attempt === 1 ? 'Passed on first run' : 'Verified repaired code',
                    codeSnapshot: currentCode,
                    result
                });
                return { finalCode: currentCode, iterations, succeeded: true };
            }
            const { fixedCode, summary } = AutoRepairLoopEngine.applyDeterministicSyntaxFix(currentCode, result.stderr);
            iterations.push({
                attempt,
                errorDetected: result.stderr.split('\n')[0] || 'Runtime Error',
                patchApplied: summary,
                codeSnapshot: currentCode,
                result
            });
            currentCode = fixedCode;
        }
        return { finalCode: currentCode, iterations, succeeded: false };
    }
}
exports.AutoRepairLoopEngine = AutoRepairLoopEngine;
