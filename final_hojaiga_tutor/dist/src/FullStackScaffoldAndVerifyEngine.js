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
exports.FullStackScaffoldAndVerifyEngine = void 0;
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const WorkspaceSafetyManager_1 = require("./WorkspaceSafetyManager");
/**
 * Multi-File System Architect, Contract Validator & Safe Workspace Builder.
 *
 * Merge note: the router ONLY calls buildArchitectureOverlay (diagram + plan
 * cards). writeVerifiedScaffoldToDisk exists as an explicit callable API and
 * is never auto-triggered from a free-text prompt - writing files to disk
 * requires deliberate user action, with every path validated through
 * WorkspaceSafetyManager.
 */
class FullStackScaffoldAndVerifyEngine {
    safety;
    constructor(safety) {
        this.safety = safety || new WorkspaceSafetyManager_1.WorkspaceSafetyManager();
    }
    static isArchitectureScaffoldPrompt(prompt) {
        return /\b(scaffold|multi-file|full\s*stack|project\s+structure|microservice|build\s+a\s+module|create\s+feature|clean\s+architecture|api\s+and\s+database)\b/i.test(prompt);
    }
    planVerifiedFeatureArchitecture(featureName = 'UserWorkflow') {
        const safeName = featureName.replace(/[^a-zA-Z0-9]/g, '') || 'FeatureModule';
        return [
            {
                relativePath: `src/generated/${safeName}.types.ts`,
                layer: 'TYPES',
                responsibility: 'Strict domain interfaces, DTOs, and validation contracts',
                codeContent: `export interface ${safeName}Record {\n  id: string;\n  createdAt: number;\n  status: 'IDLE' | 'ACTIVE' | 'COMPLETED';\n}\n`,
            },
            {
                relativePath: `src/generated/${safeName}.repo.ts`,
                layer: 'REPOSITORY',
                responsibility: 'Isolated data persistence and in-memory/DB query access',
                codeContent: `import { ${safeName}Record } from './${safeName}.types';\nexport class ${safeName}Repository {\n  private store = new Map<string, ${safeName}Record>();\n  public save(rec: ${safeName}Record): void { this.store.set(rec.id, rec); }\n  public findById(id: string): ${safeName}Record | undefined { return this.store.get(id); }\n}\n`,
            },
            {
                relativePath: `src/generated/${safeName}.service.ts`,
                layer: 'SERVICE',
                responsibility: 'Pure domain rules, invariant checks, and orchestration',
                codeContent: `import { ${safeName}Repository } from './${safeName}.repo';\nexport class ${safeName}Service {\n  constructor(private repo = new ${safeName}Repository()) {}\n  public activate(id: string): boolean {\n    const rec = this.repo.findById(id);\n    if (!rec) return false;\n    rec.status = 'ACTIVE';\n    this.repo.save(rec);\n    return true;\n  }\n}\n`,
            },
            {
                relativePath: `src/generated/${safeName}.controller.ts`,
                layer: 'CONTROLLER',
                responsibility: 'Entry boundary, request sanitization, and structured response',
                codeContent: `import { ${safeName}Service } from './${safeName}.service';\nexport class ${safeName}Controller {\n  constructor(private service = new ${safeName}Service()) {}\n  public handleActivateRequest(id: string): { ok: boolean } {\n    return { ok: this.service.activate(id.trim()) };\n  }\n}\n`,
            },
        ];
    }
    writeVerifiedScaffoldToDisk(baseWorkspaceDir, files) {
        const writtenFiles = [];
        const blockedFiles = [];
        for (const file of files) {
            const fullTarget = path.resolve(baseWorkspaceDir, file.relativePath);
            if (!this.safety.isPathInsideWorkspace(fullTarget)) {
                blockedFiles.push(file.relativePath);
                continue;
            }
            try {
                fs.mkdirSync(path.dirname(fullTarget), { recursive: true });
                fs.writeFileSync(fullTarget, file.codeContent, 'utf-8');
                writtenFiles.push(file.relativePath);
            }
            catch {
                blockedFiles.push(file.relativePath);
            }
        }
        return { writtenFiles, blockedFiles };
    }
    buildArchitectureOverlay(userPrompt) {
        const match = userPrompt.match(/\b(?:for|called|named)\s+([a-zA-Z0-9_]+)/i);
        const featureName = match ? match[1] : 'AutomationFeature';
        const plan = this.planVerifiedFeatureArchitecture(featureName);
        return [
            { type: 'BOARD', label: `Full-Stack Visual Architect • Feature: ${featureName} (4 Verified Layers)` },
            {
                type: 'GRAPH',
                nodes: ['1. Types & Contracts', '2. Repository Layer', '3. Domain Service', '4. API Controller'],
                edges: [
                    { from: '1. Types & Contracts', to: '2. Repository Layer' },
                    { from: '2. Repository Layer', to: '3. Domain Service' },
                    { from: '3. Domain Service', to: '4. API Controller' },
                ],
                label: 'Dependency Direction (Inward toward Types)',
                color: 'green',
                loop: true,
            },
            ...plan.map((file, idx) => ({
                type: 'WRITE',
                label: `[${file.layer}] ${file.relativePath} → ${file.responsibility}`,
                color: ['cyan', 'yellow', 'green', 'orange'][idx % 4],
            })),
        ];
    }
}
exports.FullStackScaffoldAndVerifyEngine = FullStackScaffoldAndVerifyEngine;
