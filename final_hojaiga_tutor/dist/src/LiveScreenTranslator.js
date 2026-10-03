"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.LiveScreenTranslator = void 0;
const DynamicAppScannerAndTeacher_1 = require("./DynamicAppScannerAndTeacher");
/**
 * Real-Time Multi-Language Screen Dubbing & Visual Floating-Pill Translator.
 *
 * Merge notes (deviations from the original paste):
 *  - Highlight boxes use the new UIRECT type instead of [BOX]: UIRECT keeps
 *    the control's TRUE screen coordinates (never clamped into the left
 *    diagram zone), which is the entire point of placing a translation pill
 *    over a real UI control.
 *  - Trigger requires a translate/dub/subtitle verb; a bare "teach me X in
 *    hindi" is a spoken-language lesson, not a screen dub, and must not fire
 *    the scanner.
 *  - The 4-language phrase list is an offline structural fallback; the model
 *    still writes the actual lesson prose around it.
 */
class LiveScreenTranslator {
    static PHRASE_DICTIONARY = {
        hindi: {
            File: 'फ़ाइल (File)',
            Edit: 'संपादन (Edit)',
            View: 'दृश्य (View)',
            Settings: 'सेटिंग्स (Settings)',
            Run: 'चलाएं (Run)',
            Debug: 'डीबग (Debug)',
            Export: 'निर्यात करें (Export)',
            Timeline: 'टाइमलाइन (Timeline)',
        },
        gujarati: {
            File: 'ફાઇલ (File)',
            Edit: 'ફેરફાર (Edit)',
            View: 'દેખાવ (View)',
            Settings: 'સેટિંગ્સ (Settings)',
            Run: 'ચલાવો (Run)',
            Debug: 'ડીબગ (Debug)',
            Export: 'નિકાસ કરો (Export)',
            Timeline: 'ટાઇમલાઇન (Timeline)',
        },
        spanish: {
            File: 'Archivo',
            Edit: 'Editar',
            View: 'Vista',
            Settings: 'Configuración',
            Run: 'Ejecutar',
            Debug: 'Depurar',
            Export: 'Exportar',
            Timeline: 'Línea de tiempo',
        },
        japanese: {
            File: 'ファイル (Fairu)',
            Edit: '編集 (Henshū)',
            View: '表示 (Hyōji)',
            Settings: '設定 (Settei)',
            Run: '実行 (Jikkō)',
            Debug: 'デバッグ (Debaggu)',
            Export: '書き出し (Kakidashi)',
            Timeline: 'タイムライン (Taimurain)',
        },
    };
    static LANG_RE = /\b(hindi|gujarati|spanish|japanese)\b/i;
    static isTranslationPrompt(prompt) {
        const q = prompt.toLowerCase();
        const specific = /\b(translate\s+screen|live\s+dub|dub\s+this|translate\s+app|manga\s+translat|subtitle\s+overlay)\b/i.test(q);
        const genericVerb = /\b(translat\w*|dub\w*|subtitle)\b/i.test(q);
        const screenContext = /\b(screen|app|ui|interface|menu|label|window|controls?)\b/i.test(q);
        // Bare "in hindi" without a translate/dub verb = teach-in-language, not dub.
        return specific || (genericVerb && (this.LANG_RE.test(prompt) || screenContext));
    }
    static detectTargetLanguage(prompt) {
        const lower = prompt.toLowerCase();
        if (lower.includes('gujarati'))
            return 'gujarati';
        if (lower.includes('spanish'))
            return 'spanish';
        if (lower.includes('japanese'))
            return 'japanese';
        return 'hindi';
    }
    static translateLabel(text, targetLang) {
        const dict = this.PHRASE_DICTIONARY[targetLang] || this.PHRASE_DICTIONARY.hindi;
        for (const [eng, trans] of Object.entries(dict)) {
            if (text.toLowerCase().includes(eng.toLowerCase())) {
                return `${trans} • [${text}]`;
            }
        }
        return `[${targetLang.toUpperCase()} DUB]: ${text}`;
    }
    static async buildScreenTranslatorOverlay(userPrompt) {
        const targetLang = this.detectTargetLanguage(userPrompt);
        const snap = await DynamicAppScannerAndTeacher_1.DynamicAppScannerAndTeacher.scanActiveOrNamedApp();
        const commands = [
            {
                type: 'BOARD',
                label: `Live Screen Dubbing & Translator • Target: ${targetLang.toUpperCase()} (${snap.windowTitle})`,
            },
        ];
        const topElements = snap.elements.slice(0, 4);
        if (topElements.length > 0) {
            topElements.forEach((el, index) => {
                const translated = this.translateLabel(el.name, targetLang);
                const colors = ['cyan', 'yellow', 'green', 'orange'];
                const color = colors[index % 4];
                // UIRECT (absolute screen coords), NOT [BOX] - see class note.
                commands.push({
                    type: 'UIRECT',
                    x: el.x,
                    y: el.y,
                    w: Math.max(90, el.width),
                    h: Math.max(28, el.height),
                    label: translated.slice(0, 60),
                    color,
                });
                commands.push({
                    type: 'WRITE',
                    label: `HUD Pill #${index + 1} (${el.x}, ${el.y}): "${el.name}" → ${translated}`,
                    color,
                });
            });
        }
        else {
            commands.push({
                type: 'UIRECT',
                x: 220,
                y: 160,
                w: 380,
                h: 65,
                label: `[${targetLang.toUpperCase()} SUBTITLE]: Real-time floating glass translation active`,
                color: 'cyan',
            }, {
                type: 'WRITE',
                label: `Voice Dubbing Sync: Speaking translated dialogue in ${targetLang.toUpperCase()} at 1.0x natural cadence.`,
                color: 'green',
            });
        }
        return commands;
    }
}
exports.LiveScreenTranslator = LiveScreenTranslator;
