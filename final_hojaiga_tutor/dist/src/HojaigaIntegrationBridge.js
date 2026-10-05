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
exports.HojaigaIntegrationBridge = void 0;
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
/**
 * Capability registry + lightweight scheduler for Hojaiga's engine fleet.
 *
 * Merge note: this is infrastructure (no overlay commands of its own) - it is
 * compiled and exported but intentionally NOT auto-triggered from the lesson
 * chain, since scheduling needs an external trigger source (IPC/CLI) that is
 * out of scope for the overlay merge.
 */
class HojaigaIntegrationBridge {
    static instance = null;
    capabilities = new Map();
    schedules = new Map();
    registryFile;
    constructor(registryFile) {
        this.registryFile = registryFile || path.join(process.cwd(), 'hojaiga_registry.json');
        this.loadRegistry();
    }
    static getInstance() {
        if (!this.instance) {
            this.instance = new HojaigaIntegrationBridge();
        }
        return this.instance;
    }
    registerCapability(cap) {
        // APP LOGIC FIX: honor an explicitly provided id first (callers may
        // register stable ids like 'cap_math'); only derive one when absent.
        const id = cap.id ||
            (cap.engine
                ? `cap_${cap.engine.toLowerCase().replace(/[^a-z0-9]+/g, '_')}`
                : `cap_${cap.name.toLowerCase().replace(/[^a-z0-9]+/g, '_')}`);
        const entry = { ...cap, id, registeredAt: Date.now() };
        this.capabilities.set(id, entry);
        this.persistRegistry();
        return entry;
    }
    listCapabilities() {
        return Array.from(this.capabilities.values());
    }
    /** Keyword match used by the lesson router to pick a capability for a prompt. */
    findMatchingCapability(prompt) {
        const q = prompt.toLowerCase();
        for (const cap of this.capabilities.values()) {
            if (cap.triggerKeywords && cap.triggerKeywords.some((kw) => q.includes(kw.toLowerCase()))) {
                return cap;
            }
        }
        return null;
    }
    scheduleLesson(lessonTitle, cronLike, nextRunAt) {
        const entry = {
            id: `sched_${Date.now()}`,
            lessonTitle,
            cronLike,
            nextRunAt,
        };
        this.schedules.set(entry.id, entry);
        this.persistRegistry();
        return entry;
    }
    getDueSchedules(now = Date.now()) {
        return Array.from(this.schedules.values()).filter((s) => s.nextRunAt <= now);
    }
    reschedule(id, nextRunAt) {
        const entry = this.schedules.get(id);
        if (!entry)
            return false;
        entry.nextRunAt = nextRunAt;
        this.persistRegistry();
        return true;
    }
    persistRegistry() {
        try {
            const payload = {
                capabilities: this.listCapabilities(),
                schedules: Array.from(this.schedules.values()),
                updatedAt: Date.now(),
            };
            fs.writeFileSync(this.registryFile, JSON.stringify(payload, null, 2), 'utf8');
        }
        catch {
            /* registry persistence is best-effort */
        }
    }
    loadRegistry() {
        try {
            if (!fs.existsSync(this.registryFile))
                return;
            const raw = JSON.parse(fs.readFileSync(this.registryFile, 'utf8'));
            for (const cap of raw.capabilities || [])
                this.capabilities.set(cap.id, cap);
            for (const s of raw.schedules || [])
                this.schedules.set(s.id, s);
        }
        catch {
            /* corrupt registry is reset on next persist */
        }
    }
    /** Optional: describe the registry as overlay commands for debugging. */
    describeAsCommands() {
        const cmds = [
            { type: 'BOARD', label: `Hojaiga Bridge • ${this.capabilities.size} capabilities • ${this.schedules.size} schedules` },
        ];
        for (const cap of this.listCapabilities()) {
            cmds.push({ type: 'WRITE', label: `${cap.name}: ${cap.description}`.slice(0, 90), color: 'cyan' });
        }
        return cmds;
    }
}
exports.HojaigaIntegrationBridge = HojaigaIntegrationBridge;
