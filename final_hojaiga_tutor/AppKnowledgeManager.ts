/**
 * AppKnowledgeManager - Learn and remember what buttons do across apps
 * Stores semantic knowledge about UI elements and workflows
 */

import { AppKnowledge, ButtonKnowledge, UITreeNode } from './src/types';
import { readFileSync, writeFileSync, existsSync } from 'fs';
import { join } from 'path';

export class AppKnowledgeManager {
  private knowledgeBase: Map<string, AppKnowledge> = new Map();
  private knowledgePath: string;

  constructor() {
    this.knowledgePath = join(__dirname, 'app_knowledge.json');
    this.loadKnowledge();
  }

  /**
   * Load existing knowledge from disk
   */
  private loadKnowledge(): void {
    try {
      if (existsSync(this.knowledgePath)) {
        const data = readFileSync(this.knowledgePath, 'utf-8');
        const parsed = JSON.parse(data);
        for (const [appId, knowledge] of Object.entries(parsed)) {
          const knowledgeAny = knowledge as any;
          const appKnowledge: AppKnowledge = {
            ...knowledgeAny,
            buttons: new Map(Object.entries(knowledgeAny.buttons || {}))
          };
          this.knowledgeBase.set(appId, appKnowledge);
        }
        console.log(`[AppKnowledge] Loaded ${this.knowledgeBase.size} apps from knowledge base`);
      }
    } catch (error) {
      console.warn('[AppKnowledge] Could not load knowledge base:', error);
    }
  }

  /**
   * Save knowledge to disk
   */
  private saveKnowledge(): void {
    try {
      const serializable: Record<string, any> = {};
      for (const [appId, knowledge] of this.knowledgeBase.entries()) {
        serializable[appId] = {
          ...knowledge,
          buttons: Object.fromEntries(knowledge.buttons)
        };
      }
      writeFileSync(this.knowledgePath, JSON.stringify(serializable, null, 2));
    } catch (error) {
      console.error('[AppKnowledge] Could not save knowledge base:', error);
    }
  }

  /**
   * Get or create knowledge for an app
   */
  getAppKnowledge(appId: string, appName: string): AppKnowledge {
    if (!this.knowledgeBase.has(appId)) {
      const newKnowledge: AppKnowledge = {
        appId,
        appName,
        appType: this.detectAppType(appName),
        buttons: new Map(),
        workflows: [],
        lastScanned: Date.now(),
        version: 1
      };
      this.knowledgeBase.set(appId, newKnowledge);
      this.saveKnowledge();
    }
    return this.knowledgeBase.get(appId)!;
  }

  /**
   * Detect app type from name
   */
  private detectAppType(appName: string): string {
    const name = appName.toLowerCase();
    if (name.includes('word') || name.includes('document') || name.includes('notepad')) {
      return 'Word Processor';
    }
    if (name.includes('excel') || name.includes('spreadsheet') || name.includes('calc')) {
      return 'Spreadsheet';
    }
    if (name.includes('chrome') || name.includes('firefox') || name.includes('edge') || name.includes('browser')) {
      return 'Browser';
    }
    if (name.includes('paint') || name.includes('photoshop') || name.includes('gimp')) {
      return 'Image Editor';
    }
    if (name.includes('code') || name.includes('visual studio') || name.includes('intellij')) {
      return 'IDE';
    }
    return 'Unknown';
  }

  /**
   * Add button knowledge from OmniParser results
   */
  addButtonKnowledge(
    appId: string,
    uiTree: UITreeNode[],
    appName: string
  ): AppKnowledge {
    const knowledge = this.getAppKnowledge(appId, appName);

    for (const node of uiTree) {
      const buttonId = node.id || `element_${node.boundingBox?.x}_${node.boundingBox?.y}`;
      
      // Skip if we already have high-confidence knowledge
      const existing = knowledge.buttons.get(buttonId);
      if (existing && existing.confidence > 0.9) {
        continue;
      }

      // Infer semantic meaning from position and context
      const semanticLabel = this.inferButtonSemantics(node, knowledge);

      const buttonKnowledge: ButtonKnowledge = {
        id: buttonId,
        name: node.name || node.role || 'Unknown',
        semanticLabel,
        description: this.generateButtonDescription(node, semanticLabel),
        category: this.inferButtonCategory(node),
        position: node.boundingBox || { x: 0, y: 0, width: 0, height: 0 },
        shortcut: this.inferShortcut(node, semanticLabel),
        confidence: existing ? Math.max(existing.confidence, 0.7) : 0.7
      };

      knowledge.buttons.set(buttonId, buttonKnowledge);
    }

    knowledge.lastScanned = Date.now();
    knowledge.version++;
    this.saveKnowledge();

    console.log(`[AppKnowledge] Updated ${appName} with ${knowledge.buttons.size} buttons`);
    return knowledge;
  }

  /**
   * Infer what a button does based on position and context
   */
  private inferButtonSemantics(node: UITreeNode, knowledge: AppKnowledge): string {
    const name = (node.name || '').toLowerCase();
    const role = (node.role || '').toLowerCase();
    const x = node.boundingBox?.x || 0;
    const y = node.boundingBox?.y || 0;

    // Top-left corner usually has File menu
    if (x < 200 && y < 100) {
      if (name.includes('file') || role.includes('menu')) return 'File Menu';
      if (name.includes('home') || role.includes('tab')) return 'Home Tab';
      if (name.includes('insert') || role.includes('tab')) return 'Insert Tab';
    }

    // Top-right usually has window controls or search
    if (x > 1400 && y < 100) {
      if (name.includes('close') || name.includes('x')) return 'Close Button';
      if (name.includes('maximize') || name.includes('□')) return 'Maximize Button';
      if (name.includes('minimize') || name.includes('-')) return 'Minimize Button';
    }

    // Common button keywords
    if (name.includes('new') || name.includes('create')) return 'Create New';
    if (name.includes('save') || name.includes('disk')) return 'Save';
    if (name.includes('open') || name.includes('folder')) return 'Open';
    if (name.includes('delete') || name.includes('trash')) return 'Delete';
    if (name.includes('copy') || name.includes('duplicate')) return 'Copy';
    if (name.includes('paste') || name.includes('clipboard')) return 'Paste';
    if (name.includes('cut')) return 'Cut';
    if (name.includes('undo')) return 'Undo';
    if (name.includes('redo')) return 'Redo';
    if (name.includes('bold') || name.includes('b')) return 'Bold Text';
    if (name.includes('italic') || name.includes('i')) return 'Italic Text';
    if (name.includes('underline') || name.includes('u')) return 'Underline Text';
    if (name.includes('search') || name.includes('find')) return 'Search';
    if (name.includes('print')) return 'Print';
    if (name.includes('help') || name.includes('?')) return 'Help';

    // Role-based inference
    if (role.includes('button')) return 'Action Button';
    if (role.includes('checkbox')) return 'Checkbox';
    if (role.includes('radio')) return 'Radio Button';
    if (role.includes('text') || role.includes('input')) return 'Text Input';
    if (role.includes('dropdown') || role.includes('combo')) return 'Dropdown Menu';
    if (role.includes('slider')) return 'Slider';
    if (role.includes('tab')) return 'Tab';

    return name || 'Unknown Control';
  }

  /**
   * Generate human-readable description
   */
  private generateButtonDescription(node: UITreeNode, semanticLabel: string): string {
    const descriptions: Record<string, string> = {
      'File Menu': 'Opens the file menu to create, open, save, or print documents',
      'Create New': 'Creates a new blank document',
      'Save': 'Saves the current document',
      'Open': 'Opens an existing document',
      'Delete': 'Deletes the selected item',
      'Copy': 'Copies the selected item to clipboard',
      'Paste': 'Pastes clipboard content at cursor',
      'Bold Text': 'Makes selected text bold',
      'Italic Text': 'Makes selected text italic',
      'Search': 'Searches for text in the document',
      'Print': 'Prints the current document',
      'Close Button': 'Closes the current window',
      'Action Button': 'Performs an action when clicked',
      'Checkbox': 'Toggles an option on or off',
      'Text Input': 'Enter text here',
      'Dropdown Menu': 'Click to select from a list of options'
    };

    return descriptions[semanticLabel] || `Control: ${semanticLabel}`;
  }

  /**
   * Infer button category (ribbon, toolbar, menu, etc.)
   */
  private inferButtonCategory(node: UITreeNode): string {
    const y = node.boundingBox?.y || 0;
    const x = node.boundingBox?.x || 0;

    if (y < 150) return 'Top Ribbon';
    if (y > 600) return 'Bottom Status Bar';
    if (x < 100) return 'Left Sidebar';
    if (x > 1400) return 'Right Sidebar';
    return 'Main Content';
  }

  /**
   * Infer keyboard shortcut
   */
  private inferShortcut(node: UITreeNode, semanticLabel: string): string | undefined {
    const shortcuts: Record<string, string> = {
      'Create New': 'Ctrl+N',
      'Save': 'Ctrl+S',
      'Open': 'Ctrl+O',
      'Print': 'Ctrl+P',
      'Copy': 'Ctrl+C',
      'Paste': 'Ctrl+V',
      'Cut': 'Ctrl+X',
      'Undo': 'Ctrl+Z',
      'Redo': 'Ctrl+Y',
      'Bold Text': 'Ctrl+B',
      'Italic Text': 'Ctrl+I',
      'Underline Text': 'Ctrl+U',
      'Search': 'Ctrl+F'
    };

    return shortcuts[semanticLabel];
  }

  /**
   * Get button knowledge for a specific element
   */
  getButtonKnowledge(appId: string, buttonId: string): ButtonKnowledge | undefined {
    const app = this.knowledgeBase.get(appId);
    return app?.buttons.get(buttonId);
  }

  /**
   * Get all buttons for an app
   */
  getAppButtons(appId: string): ButtonKnowledge[] {
    const app = this.knowledgeBase.get(appId);
    return app ? Array.from(app.buttons.values()) : [];
  }

  /**
   * Get high-confidence teaching plan for an app
   */
  getTeachingPlan(appId: string): Array<{ button: ButtonKnowledge; order: number }> {
    const app = this.knowledgeBase.get(appId);
    if (!app) return [];

    const buttons = Array.from(app.buttons.values());
    
    // Prioritize: File menu > Core actions > Formatting
    const priority: Record<string, number> = {
      'File Menu': 1,
      'Create New': 2,
      'Save': 3,
      'Open': 4,
      'Bold Text': 5,
      'Italic Text': 6,
      'Underline Text': 7,
      'Search': 8,
      'Print': 9
    };

    return buttons
      .filter(b => b.confidence > 0.6)
      .map((button, index) => ({
        button,
        order: priority[button.semanticLabel] || 100 + index
      }))
      .sort((a, b) => a.order - b.order);
  }
}
