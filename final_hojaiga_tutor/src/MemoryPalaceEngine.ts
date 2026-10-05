import * as fs from 'fs';
import * as path from 'path';
import { ParsedOverlayCommand } from './CompanionManager';
import { HojaigaIntegrationBridge } from './HojaigaIntegrationBridge';

export interface SpatialFlashcard {
  id: string;
  locusRoom: string;
  concept: string;
  mnemonicAnchor: string;
  intervalDays: number;
  easeFactor: number;
  nextReviewAt: number;
}

/**
 * Spatial Memory Palace Builder & SM-2 Spaced-Repetition Flashcard Canvas.
 *
 * Merge notes (deviations from the original paste):
 *  - Bridge registration uses our HojaigaCapability shape ({name, engine,
 *    description}) - the original passed id/category/triggerKeywords/handler
 *    fields our registry does not model, which would not compile.
 *  - Building a palace twice for the SAME topic reuses the existing 4 cards
 *    instead of appending duplicates to the deck on every prompt.
 *  - SM-2 math unchanged (standard SuperMemo-2 interval/ease formulas).
 */
export class MemoryPalaceEngine {
  private deckPath: string;
  private cards: SpatialFlashcard[] = [];

  constructor(workspaceDir: string = 'D:\\new_automation\\final hojaiga tutor') {
    this.deckPath = path.join(workspaceDir, 'memory_palace_deck.json');
    this.loadDeck();
  }

  public static isMemoryPalacePrompt(prompt: string): boolean {
    return /\b(memory\s+palace|flashcard|spaced\s+repetition|memorize\s+this|quiz\s+me\s+later|ankify|study\s+map|loci)\b/i.test(prompt);
  }

  public get cardCount(): number {
    return this.cards.length;
  }

  public createSpatialLociForTopic(topicPrompt: string): SpatialFlashcard[] {
    const cleanTopic =
      topicPrompt
        .replace(/\b(memory\s+palace|flashcard|memorize|create|build|for|about)\b/gi, '')
        .trim() || 'Core Study Module';

    // Idempotent: same topic returns the existing palace instead of piling up
    // duplicate cards on every repeated prompt.
    const existing = this.cards.filter((c) => c.concept.toLowerCase() === cleanTopic.toLowerCase());
    if (existing.length >= 4) return existing.slice(0, 4);

    const lociRooms = [
      { room: 'Locus 1: Front Gate', anchor: `First Principles & Definition of ${cleanTopic}` },
      { room: 'Locus 2: Atrium Pillar', anchor: 'Key Mechanism & Governing Formula' },
      { room: 'Locus 3: Library Desk', anchor: 'Real-World Application & Edge Cases' },
      { room: 'Locus 4: Vault Door', anchor: 'Common Exam Pitfalls & Self-Test Cue' },
    ];

    const generated = lociRooms.map((item, idx) => ({
      id: `card_${Date.now()}_${idx}`,
      locusRoom: item.room,
      concept: cleanTopic,
      mnemonicAnchor: item.anchor,
      intervalDays: 1,
      easeFactor: 2.5,
      nextReviewAt: Date.now() + 24 * 60 * 60 * 1000,
    }));

    this.cards.push(...generated);
    this.saveDeck();
    return generated;
  }

  /**
   * Updates card review interval using the SM-2 Spaced Repetition formula.
   * @param cardId ID of the flashcard
   * @param qualityGrade Recall grade from 0 (blackout) to 5 (instant recall)
   */
  public recordSM2Review(cardId: string, qualityGrade: number): SpatialFlashcard | null {
    const card = this.cards.find((c) => c.id === cardId);
    if (!card) return null;

    const q = Math.max(0, Math.min(5, qualityGrade));
    if (q < 3) {
      card.intervalDays = 1;
    } else {
      card.intervalDays = card.intervalDays === 1 ? 6 : Math.round(card.intervalDays * card.easeFactor);
    }

    card.easeFactor = Math.max(1.3, card.easeFactor + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)));
    card.nextReviewAt = Date.now() + card.intervalDays * 24 * 60 * 60 * 1000;
    this.saveDeck();
    return card;
  }

  public buildMemoryPalaceOverlay(userPrompt: string, bridge?: HojaigaIntegrationBridge): ParsedOverlayCommand[] {
    const newCards = this.createSpatialLociForTopic(userPrompt);

    if (bridge) {
      try {
        bridge.registerCapability({
          name: 'Memory Palace Spaced-Repetition Quizzer',
          engine: 'MemoryPalaceEngine',
          description: 'Triggers scheduled spatial recall quizzes on the overlay',
        });
      } catch {
        /* registry persistence is best-effort */
      }
    }

    return [
      {
        type: 'BOARD',
        label: `3D Memory Palace & SM-2 Flashcards • ${newCards[0].concept.slice(0, 38)}`,
      },
      {
        type: 'GRAPH',
        nodes: newCards.map((c) => c.locusRoom),
        edges: [
          { from: newCards[0].locusRoom, to: newCards[1].locusRoom },
          { from: newCards[1].locusRoom, to: newCards[2].locusRoom },
          { from: newCards[2].locusRoom, to: newCards[3].locusRoom },
        ],
        label: 'Method of Loci Spatial Walk',
        color: 'purple',
        loop: true,
      },
      ...newCards.map((card, i) => ({
        type: 'WRITE' as const,
        label: `${card.locusRoom} → ${card.mnemonicAnchor} [Next SM-2 Review: ${card.intervalDays}d]`,
        color: ['cyan', 'yellow', 'green', 'orange'][i % 4],
      })),
    ];
  }

  private loadDeck(): void {
    try {
      if (fs.existsSync(this.deckPath)) {
        this.cards = JSON.parse(fs.readFileSync(this.deckPath, 'utf-8'));
      }
    } catch {
      this.cards = [];
    }
  }

  private saveDeck(): void {
    try {
      fs.writeFileSync(this.deckPath, JSON.stringify(this.cards, null, 2), 'utf-8');
    } catch {
      /* persistence is best-effort */
    }
  }
}
