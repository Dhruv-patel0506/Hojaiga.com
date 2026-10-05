"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.UIUXAccessibilityAndDesignCritic = void 0;
const DynamicAppScannerAndTeacher_1 = require("./DynamicAppScannerAndTeacher");
class UIUXAccessibilityAndDesignCritic {
    static isUIUXCriticPrompt(prompt) {
        return /\b(ui\s+audit|ux\s+review|wcag|accessibility|contrast\s+ratio|tailwind\s+fix|css\s+layout|padding|alignment|design\s+critic|frontend\s+review)\b/i.test(prompt);
    }
    /**
     * Computes relative luminance contrast ratio per WCAG 2.1 formula.
     */
    static computeHexContrastRatio(fgHex = '#38BDF8', bgHex = '#0F172A') {
        const toLuminance = (hex) => {
            const clean = hex.replace('#', '');
            const num = parseInt(clean.length === 3 ? clean.replace(/(.)/g, '$1$1') : clean, 16) || 0;
            const channels = [(num >> 16) & 255, (num >> 8) & 255, num & 255].map(v => {
                const s = v / 255;
                return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
            });
            return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
        };
        const l1 = toLuminance(fgHex);
        const l2 = toLuminance(bgHex);
        const brightest = Math.max(l1, l2);
        const darkest = Math.min(l1, l2);
        return Number(((brightest + 0.05) / (darkest + 0.05)).toFixed(2));
    }
    static async buildUIUXCriticOverlay(userPrompt) {
        let snap = {
            windowTitle: 'Frontend Preview',
            elements: [],
        };
        try {
            snap = await DynamicAppScannerAndTeacher_1.DynamicAppScannerAndTeacher.scanActiveOrNamedApp();
        }
        catch {
            /* scan is best-effort */
        }
        const hexMatches = userPrompt.match(/#[0-9a-fA-F]{6}\b/g) || ['#38BDF8', '#0F172A'];
        const ratio = this.computeHexContrastRatio(hexMatches[0], hexMatches[1] || '#0F172A');
        const undersized = snap.elements.filter(el => el.width < 44 || el.height < 32).slice(0, 3);
        const commands = [
            {
                type: 'BOARD',
                label: `Live UI/UX & WCAG Critic • Contrast: ${ratio}:1 (${ratio >= 4.5 ? 'WCAG AA PASS' : 'NEEDS BOOST'})`
            }
        ];
        undersized.forEach((el, idx) => {
            commands.push({
                type: 'UIRECT',
                x: el.x,
                y: el.y,
                w: Math.max(48, el.width),
                h: Math.max(36, el.height),
                label: `Hit-Target Audit #${idx + 1}: ${el.name} (${el.width}x${el.height}px → Expand to ≥44x44px)`.slice(0, 72),
                color: 'yellow'
            });
        });
        commands.push({
            type: 'WRITE',
            label: 'STAGE 1 [VISUAL HIERARCHY TEACH]: Use an 8pt spacing grid (0.5rem, 1rem, 1.5rem) and limit line width to 60–75ch for effortless scanning.',
            color: 'cyan'
        }, {
            type: 'WRITE',
            label: `STAGE 2 [WCAG 2.1 VERIFICATION]: Foreground/Background contrast is ${ratio}:1 (Minimum 4.5:1 for normal text, 7.0:1 for AAA).`,
            color: ratio >= 4.5 ? 'green' : 'orange'
        }, {
            type: 'WRITE',
            label: 'STAGE 3 [TAILWIND / CSS FIX]: className="min-h-[44px] min-w-[44px] px-4 py-2.5 rounded-xl bg-slate-900 text-sky-300 focus-visible:ring-2 focus-visible:ring-sky-400"',
            color: 'green'
        });
        return commands;
    }
}
exports.UIUXAccessibilityAndDesignCritic = UIUXAccessibilityAndDesignCritic;
