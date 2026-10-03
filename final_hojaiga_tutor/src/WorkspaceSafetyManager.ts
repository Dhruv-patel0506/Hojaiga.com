import * as path from 'path';

export interface SafetyPolicyConfig {
  allowedWorkspaceRoots: string[];
  requireApprovalForWrite: boolean;
  requireApprovalForExec: boolean;
  allowedCommands: string[];
  blockedPatterns: RegExp[];
}

export interface ApprovalRequest {
  id: string;
  operation: 'FILE_WRITE' | 'COMMAND_EXEC';
  target: string;
  reason: string;
  timestamp: number;
}

export class WorkspaceSafetyManager {
  private config: SafetyPolicyConfig;
  private pendingApprovals = new Map<string, ApprovalRequest>();

  constructor(customRoot?: string) {
    const defaultRoot = customRoot || path.resolve(process.cwd());
    this.config = {
      allowedWorkspaceRoots: [defaultRoot, 'D:\\new_automation'],
      requireApprovalForWrite: false,
      requireApprovalForExec: true,
      allowedCommands: ['node', 'npm', 'npx', 'tsc', 'python', 'pytest', 'git'],
      blockedPatterns: [
        /\brm\s+-rf\b/i,
        /\bdel\s+\/[fqs]/i,
        /\bformat\s+[a-z]:/i,
        /\bshutdown\b/i,
        /\breg\s+delete\b/i,
        /\bpowershell.*-enc/i,
      ],
    };
  }

  public isPathInsideWorkspace(targetPath: string): boolean {
    const resolved = path.resolve(targetPath).toLowerCase();
    return this.config.allowedWorkspaceRoots.some((root) => resolved.startsWith(path.resolve(root).toLowerCase()));
  }

  public validateCommand(commandLine: string): { allowed: boolean; requiresApproval: boolean; reason: string } {
    const trimmed = commandLine.trim();

    for (const pattern of this.config.blockedPatterns) {
      if (pattern.test(trimmed)) {
        return {
          allowed: false,
          requiresApproval: false,
          reason: `Blocked by WorkspaceSafetyManager pattern: ${pattern}`,
        };
      }
    }

    const binary = trimmed.split(/\s+/)[0].replace(/\.exe$/i, '').toLowerCase();
    if (!this.config.allowedCommands.includes(binary)) {
      return {
        allowed: false,
        requiresApproval: true,
        reason: `Executable "${binary}" is not in the safe allowlist (${this.config.allowedCommands.join(', ')}).`,
      };
    }

    return {
      allowed: true,
      requiresApproval: this.config.requireApprovalForExec,
      reason: 'Verified safe workspace command.',
    };
  }

  public queueApproval(operation: 'FILE_WRITE' | 'COMMAND_EXEC', target: string, reason: string): ApprovalRequest {
    const req: ApprovalRequest = {
      id: `approval_${Date.now()}`,
      operation,
      target,
      reason,
      timestamp: Date.now(),
    };
    this.pendingApprovals.set(req.id, req);
    return req;
  }

  public getPendingApprovals(): ApprovalRequest[] {
    return Array.from(this.pendingApprovals.values());
  }

  public resolveApproval(id: string, approved: boolean): boolean {
    const req = this.pendingApprovals.get(id);
    if (!req) return false;
    this.pendingApprovals.delete(id);
    return approved;
  }
}
