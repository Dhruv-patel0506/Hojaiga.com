import { spawn } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { WorkspaceSafetyManager } from './WorkspaceSafetyManager';
import { ParsedOverlayCommand } from './CompanionManager';

export interface SandboxExecutionResult {
  language: 'javascript' | 'typescript' | 'python';
  exitCode: number | null;
  stdout: string;
  stderr: string;
  durationMs: number;
  timedOut: boolean;
  succeeded: boolean;
  blocked?: boolean;
  reason?: string;
}

export class SandboxTestExecutor {
  private safety: WorkspaceSafetyManager;

  constructor(safety?: WorkspaceSafetyManager) {
    this.safety = safety || new WorkspaceSafetyManager();
  }

  public async runCodeInSandbox(
    code: string,
    language: 'javascript' | 'typescript' | 'python' = 'javascript',
    timeoutMs: number = 5000
  ): Promise<SandboxExecutionResult> {
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
      try { fs.rmSync(sandboxDir, { recursive: true, force: true }); } catch { /* best-effort */ }
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

    return new Promise<SandboxExecutionResult>((resolve) => {
      let stdout = '';
      let stderr = '';
      let timedOut = false;
      let settled = false;

      const settle = (result: SandboxExecutionResult) => {
        if (settled) return;
        settled = true;
        try { fs.rmSync(sandboxDir, { recursive: true, force: true }); } catch { /* best-effort */ }
        resolve(result);
      };

      const child = spawn(binary, [filePath], {
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
  public buildSandboxOverlay(result: SandboxExecutionResult, label?: string): ParsedOverlayCommand[] {
    const header = label || `Sandbox • ${result.language}`;
    const statusColor = result.blocked ? 'red' : result.succeeded ? 'green' : 'yellow';
    const out = result.stdout || result.stderr ||
      (result.timedOut ? `Timed out after ${result.durationMs}ms` : '(no output)');

    const lines = out.split(/\r?\n/).filter(Boolean).slice(0, 6);
    const commands: ParsedOverlayCommand[] = [
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
