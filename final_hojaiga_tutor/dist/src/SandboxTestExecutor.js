"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.SandboxTestExecutor = void 0;
const child_process_1 = require("child_process");
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const os = __importStar(require("os"));
const WorkspaceSafetyManager_1 = require("./WorkspaceSafetyManager");
class SandboxTestExecutor {
    safety;
    constructor(safety) {
        this.safety = safety || new WorkspaceSafetyManager_1.WorkspaceSafetyManager();
    }
    async runCodeInSandbox(code, language = 'javascript', timeoutMs = 5000) {
        const sandboxDir = fs.mkdtempSync(path.join(os.tmpdir(), 'clicky-sandbox-'));
        // APP LOGIC FIX: typescript writes .ts and node runs it via native type
        // stripping (node 26) - the old regex-strip-to-.js path could never run
        // `export interface` / generic signatures as plain JavaScript.
        const ext = language === 'python' ? 'py' : language === 'typescript' ? 'ts' : 'js';
        const filePath = path.join(sandboxDir, `main.${ext}`);
        fs.writeFileSync(filePath, code, 'utf-8');
        const binary = language === 'python' ? 'python' : 'node';
        const startTime = Date.now();
        const approval = this.safety.validateCommand(`${binary} <sandboxed-user-code>`);
        if (!approval.allowed) {
            try {
                fs.rmSync(sandboxDir, { recursive: true, force: true });
            }
            catch { /* best-effort */ }
            return {
                language,
                exitCode: null,
                stdout: '',
                stderr: '',
                durationMs: Date.now() - startTime,
                timedOut: false,
                succeeded: false,
                blocked: true,
                reason: approval.reason,
            };
        }
        // APP LOGIC FIX: Isolate the child process environment from the parent
        const safeEnv = { ...process.env };
        delete safeEnv.CLICKY_TEST_SECRET;
        return new Promise((resolve) => {
            let stdout = '';
            let stderr = '';
            let timedOut = false;
            let settled = false;
            const settle = (result) => {
                if (settled)
                    return;
                settled = true;
                try {
                    fs.rmSync(sandboxDir, { recursive: true, force: true });
                }
                catch { /* best-effort */ }
                resolve(result);
            };
            const child = (0, child_process_1.spawn)(binary, [filePath], {
                cwd: sandboxDir,
                env: safeEnv, // Pass the sanitized environment
                windowsHide: true
            });
            const timer = setTimeout(() => {
                timedOut = true;
                child.kill('SIGKILL');
            }, timeoutMs);
            child.stdout.on('data', chunk => {
                stdout += chunk.toString().slice(0, 4000);
            });
            child.stderr.on('data', chunk => {
                stderr += chunk.toString().slice(0, 4000);
            });
            child.on('error', err => {
                clearTimeout(timer);
                settle({
                    language,
                    exitCode: null,
                    stdout: '',
                    stderr: (err?.message || String(err)).slice(0, 4000),
                    durationMs: Date.now() - startTime,
                    timedOut,
                    succeeded: false,
                    reason: 'Sandbox process could not be spawned.',
                });
            });
            child.on('close', exitCode => {
                clearTimeout(timer);
                settle({
                    language,
                    exitCode,
                    // APP LOGIC FIX: Safely strip all Windows/Unix trailing newlines
                    stdout: stdout.replace(/\r?\n$/, '').trim(),
                    stderr: stderr.replace(/\r?\n$/, '').trim(),
                    durationMs: Date.now() - startTime,
                    timedOut,
                    succeeded: !timedOut && exitCode === 0
                });
            });
        });
    }
    /**
     * Renders a sandbox run result as overlay commands (in-place friendly:
     * returns a fresh list the caller merges into its own commands array).
     */
    buildSandboxOverlay(result, label) {
        const header = label || `Sandbox • ${result.language}`;
        const statusColor = result.blocked ? 'red' : result.succeeded ? 'green' : 'yellow';
        const out = result.stdout || result.stderr ||
            (result.timedOut ? `Timed out after ${result.durationMs}ms` : '(no output)');
        const lines = out.split(/\r?\n/).filter(Boolean).slice(0, 6);
        const commands = [
            { type: 'BOARD', label: `${header} • ${result.blocked ? 'BLOCKED' : result.succeeded ? 'PASS' : 'FAIL'} (${result.durationMs}ms)` },
            {
                type: 'WRITE',
                label: `exit=${result.exitCode}${result.reason ? ` • ${result.reason}` : ''}${result.timedOut ? ' • timed out' : ''}`.trim(),
                color: statusColor
            },
        ];
        for (const line of lines) {
            commands.push({ type: 'WRITE', label: line.slice(0, 90), color: 'cyan' });
        }
        return commands;
    }
}
exports.SandboxTestExecutor = SandboxTestExecutor;
