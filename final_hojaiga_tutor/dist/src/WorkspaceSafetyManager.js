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
exports.WorkspaceSafetyManager = void 0;
const path = __importStar(require("path"));
class WorkspaceSafetyManager {
    config;
    pendingApprovals = new Map();
    constructor(customRoot) {
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
    isPathInsideWorkspace(targetPath) {
        const resolved = path.resolve(targetPath).toLowerCase();
        return this.config.allowedWorkspaceRoots.some((root) => resolved.startsWith(path.resolve(root).toLowerCase()));
    }
    validateCommand(commandLine) {
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
    queueApproval(operation, target, reason) {
        const req = {
            id: `approval_${Date.now()}`,
            operation,
            target,
            reason,
            timestamp: Date.now(),
        };
        this.pendingApprovals.set(req.id, req);
        return req;
    }
    getPendingApprovals() {
        return Array.from(this.pendingApprovals.values());
    }
    resolveApproval(id, approved) {
        const req = this.pendingApprovals.get(id);
        if (!req)
            return false;
        this.pendingApprovals.delete(id);
        return approved;
    }
}
exports.WorkspaceSafetyManager = WorkspaceSafetyManager;
