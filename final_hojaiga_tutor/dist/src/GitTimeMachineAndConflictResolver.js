"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.GitTimeMachineAndConflictResolver = void 0;
/**
 * File 22 - Visual Git Commit DAG Tutor, 3-Way Merge Resolver & Safe Recovery Builder.
 * As pasted, verbatim (static class; git inspection is read-only
 * `git status --porcelain -b` with a 2.5s timeout and a safe fallback).
 */
const child_process_1 = require("child_process");
const util_1 = require("util");
const execFileAsync = (0, util_1.promisify)(child_process_1.execFile);
class GitTimeMachineAndConflictResolver {
    static isGitPrompt(prompt) {
        return /\b(git\s+conflict|merge\s+conflict|git\s+rebase|git\s+reset|git\s+reflog|cherry-pick|detached\s+head|undo\s+commit|fix\s+git)\b/i.test(prompt);
    }
    static async inspectWorkspaceGitState(cwd = process.cwd()) {
        try {
            const { stdout: statusOut } = await execFileAsync('git', ['status', '--porcelain', '-b'], {
                cwd,
                timeout: 2500
            });
            const lines = statusOut.split(/\r?\n/).filter(Boolean);
            const branchLine = lines[0] || '## main';
            const branchName = branchLine.replace(/^##\s+/, '').split('...')[0].trim();
            const statusLines = lines.slice(1);
            const conflictedFiles = statusLines
                .filter(l => /^(UU|AA|DD|AU|UA)/.test(l))
                .map(l => l.slice(3).trim());
            return {
                branchName,
                conflictedFiles,
                dirtyFilesCount: statusLines.length,
                safeToMutateHistory: statusLines.length === 0
            };
        }
        catch {
            return {
                branchName: 'main',
                conflictedFiles: [],
                dirtyFilesCount: 0,
                safeToMutateHistory: true
            };
        }
    }
    static async buildGitVisualizerOverlay(userPrompt) {
        const state = await this.inspectWorkspaceGitState();
        return [
            {
                type: 'BOARD',
                label: `Visual Git Time-Machine • Branch: ${state.branchName} (${state.conflictedFiles.length} Conflicts)`
            },
            {
                type: 'GRAPH',
                nodes: [
                    '1. Merge-Base Ancestor',
                    '2. Ours (Current HEAD)',
                    '3. Theirs (Incoming Branch)',
                    '4. Verified Clean Commit'
                ],
                edges: [
                    { from: '1. Merge-Base Ancestor', to: '2. Ours (Current HEAD)' },
                    { from: '1. Merge-Base Ancestor', to: '3. Theirs (Incoming Branch)' },
                    { from: '2. Ours (Current HEAD)', to: '4. Verified Clean Commit' },
                    { from: '3. Theirs (Incoming Branch)', to: '4. Verified Clean Commit' }
                ],
                nodePositions: {
                    '1. Merge-Base Ancestor': { x: 145, y: 245 },
                    '2. Ours (Current HEAD)': { x: 265, y: 165 },
                    '3. Theirs (Incoming Branch)': { x: 265, y: 325 },
                    '4. Verified Clean Commit': { x: 395, y: 245 }
                },
                label: '3-Way DAG Reconciliation Graph',
                color: 'purple',
                loop: true
            },
            {
                type: 'WRITE',
                label: 'STAGE 1 [VISUAL TEACH]: Git compares both branches against their shared Merge-Base ancestor to isolate overlapping line edits.',
                color: 'cyan'
            },
            {
                type: 'WRITE',
                label: `STAGE 2 [SAFETY VERIFICATION]: ${state.dirtyFilesCount} uncommitted change(s) detected. Always run "git stash push -u" or check "git reflog" before resetting.`,
                color: state.conflictedFiles.length > 0 ? 'yellow' : 'green'
            },
            {
                type: 'WRITE',
                label: 'STAGE 3 [SAFE RESOLUTION COMMANDS]: 1) git status  2) Resolve <<<<<<< HEAD markers  3) git add <file>  4) git rebase --continue',
                color: 'green'
            }
        ];
    }
}
exports.GitTimeMachineAndConflictResolver = GitTimeMachineAndConflictResolver;
