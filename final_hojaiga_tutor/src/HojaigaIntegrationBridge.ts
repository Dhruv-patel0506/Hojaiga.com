import * as fs from 'fs';
import * as path from 'path';
import { ParsedOverlayCommand } from './CompanionManager';

export interface HojaigaCapability {
  id: string;
  name: string;
  engine?: string;
  category?: string;
  description: string;
  triggerKeywords?: string[];
  handler?: (...args: any[]) => any;
  registeredAt: number;
}

export interface HojaigaScheduleEntry {
  id: string;
  lessonTitle: string;
  cronLike: string;
  nextRunAt: number;
}

/**
 * Capability registry + lightweight scheduler for Hojaiga's engine fleet.
 *
 * Merge note: this is infrastructure (no overlay commands of its own) - it is
 * compiled and exported but intentionally NOT auto-triggered from the lesson
 * chain, since scheduling needs an external trigger source (IPC/CLI) that is
 * out of scope for the overlay merge.
 */
export class HojaigaIntegrationBridge {
  private static instance: HojaigaIntegrationBridge | null = null;

  private capabilities = new Map<string, HojaigaCapability>();
  private schedules = new Map<string, HojaigaScheduleEntry>();
  private registryFile: string;

  constructor(registryFile?: string) {
    this.registryFile = registryFile || path.join(process.cwd(), 'hojaiga_registry.json');
    this.loadRegistry();
  }

  public static getInstance(): HojaigaIntegrationBridge {
    if (!this.instance) {
      this.instance = new HojaigaIntegrationBridge();
    }
    return this.instance;
  }

  public registerCapability(
    cap: Omit<HojaigaCapability, 'id' | 'registeredAt'> & { id?: string }
  ): HojaigaCapability {
    // APP LOGIC FIX: honor an explicitly provided id first (callers may
    // register stable ids like 'cap_math'); only derive one when absent.
    const id =
      cap.id ||
      (cap.engine
        ? `cap_${cap.engine.toLowerCase().replace(/[^a-z0-9]+/g, '_')}`
        : `cap_${cap.name.toLowerCase().replace(/[^a-z0-9]+/g, '_')}`);
    const entry: HojaigaCapability = { ...cap, id, registeredAt: Date.now() };
    this.capabilities.set(id, entry);
    this.persistRegistry();
    return entry;
  }

  public listCapabilities(): HojaigaCapability[] {
    return Array.from(this.capabilities.values());
  }

  /** Keyword match used by the lesson router to pick a capability for a prompt. */
  public findMatchingCapability(prompt: string): HojaigaCapability | null {
    const q = prompt.toLowerCase();
    for (const cap of this.capabilities.values()) {
      if (cap.triggerKeywords && cap.triggerKeywords.some((kw) => q.includes(kw.toLowerCase()))) {
        return cap;
      }
    }
    return null;
  }

  public scheduleLesson(lessonTitle: string, cronLike: string, nextRunAt: number): HojaigaScheduleEntry {
    const entry: HojaigaScheduleEntry = {
      id: `sched_${Date.now()}`,
      lessonTitle,
      cronLike,
      nextRunAt,
    };
    this.schedules.set(entry.id, entry);
    this.persistRegistry();
    return entry;
  }

  public getDueSchedules(now: number = Date.now()): HojaigaScheduleEntry[] {
    return Array.from(this.schedules.values()).filter((s) => s.nextRunAt <= now);
  }

  public reschedule(id: string, nextRunAt: number): boolean {
    const entry = this.schedules.get(id);
    if (!entry) return false;
    entry.nextRunAt = nextRunAt;
    this.persistRegistry();
    return true;
  }

  private persistRegistry(): void {
    try {
      const payload = {
        capabilities: this.listCapabilities(),
        schedules: Array.from(this.schedules.values()),
        updatedAt: Date.now(),
      };
      fs.writeFileSync(this.registryFile, JSON.stringify(payload, null, 2), 'utf8');
    } catch {
      /* registry persistence is best-effort */
    }
  }

  private loadRegistry(): void {
    try {
      if (!fs.existsSync(this.registryFile)) return;
      const raw = JSON.parse(fs.readFileSync(this.registryFile, 'utf8'));
      for (const cap of raw.capabilities || []) this.capabilities.set(cap.id, cap);
      for (const s of raw.schedules || []) this.schedules.set(s.id, s);
    } catch {
      /* corrupt registry is reset on next persist */
    }
  }

  /** Optional: describe the registry as overlay commands for debugging. */
  public describeAsCommands(): ParsedOverlayCommand[] {
    const cmds: ParsedOverlayCommand[] = [
      { type: 'BOARD', label: `Hojaiga Bridge • ${this.capabilities.size} capabilities • ${this.schedules.size} schedules` },
    ];
    for (const cap of this.listCapabilities()) {
      cmds.push({ type: 'WRITE', label: `${cap.name}: ${cap.description}`.slice(0, 90), color: 'cyan' });
    }
    return cmds;
  }
}
