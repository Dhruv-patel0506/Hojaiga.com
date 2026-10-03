"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ProVideoEditorDirector = void 0;
exports.detectNle = detectNle;
const DynamicAppScannerAndTeacher_1 = require("./DynamicAppScannerAndTeacher");
const NLE_PROFILES = {
    premiere: {
        shortcuts: [
            { keys: 'C', action: 'Razor tool - cut at playhead' },
            { keys: 'V', action: 'Selection tool' },
            { keys: 'J / K / L', action: 'Rewind / pause / shuttle forward' },
            { keys: 'Ctrl+M', action: 'Export Media (H.264)' },
        ],
        exportHint: 'Sequence → Match Sequence Settings, then Ctrl+M, preset H.264, match source.',
    },
    davinci: {
        shortcuts: [
            { keys: 'Ctrl+B', action: 'Blade at playhead' },
            { keys: 'Shift+Z', action: 'Fit timeline to window' },
            { keys: 'Ctrl+D', action: 'Default transition' },
            { keys: 'Ctrl+Shift+D', action: 'Render current timeline via Deliver page' },
        ],
        exportHint: 'Deliver page → presets bar → H.264 Master → Add to Render Queue.',
    },
    capcut: {
        shortcuts: [
            { keys: 'Ctrl+B', action: 'Split clip at playhead' },
            { keys: 'Space', action: 'Play / pause preview' },
            { keys: 'Ctrl+E', action: 'Export' },
        ],
        exportHint: 'Export dialog: 1080p, 30fps, high bitrate for talking-head, 8-12 Mbps.',
    },
    aftereffects: {
        shortcuts: [
            { keys: 'Ctrl+D', action: 'Duplicate layer' },
            { keys: 'U', action: 'Reveal keyframes' },
            { keys: 'Ctrl+M', action: 'Add to Render Queue' },
        ],
        exportHint: 'Composition → Add to Render Queue, lossless master, then encode with Adobe Media Encoder.',
    },
    finalcut: {
        shortcuts: [
            { keys: 'B', action: 'Blade tool' },
            { keys: 'Cmd+E', action: 'Export file' },
            { keys: 'Ctrl+Opt+Cmd+E', action: 'Export with preset' },
        ],
        exportHint: 'Share → Export File → Master File (default codec).',
    },
    editing: {
        shortcuts: [
            { keys: 'C / Ctrl+B', action: 'Cut clip at playhead (most NLEs)' },
            { keys: 'J K L', action: 'Shuttle controls' },
            { keys: 'Ctrl+Z', action: 'Undo' },
        ],
        exportHint: 'Export at source resolution; H.264 for web, ProRes/DNxHR for handoff.',
    },
};
function detectNle(prompt) {
    const q = prompt.toLowerCase();
    if (/premiere|pr\b/.test(q))
        return 'premiere';
    if (/davinci|resolve/.test(q))
        return 'davinci';
    if (/capcut/.test(q))
        return 'capcut';
    if (/after\s*effects|ae\b/.test(q))
        return 'aftereffects';
    if (/final\s*cut|fcpx/.test(q))
        return 'finalcut';
    return 'editing';
}
/**
 * Pro video-editor director: NLE shortcut board + edit-structure timeline +
 * optional app scan for the named editor.
 *
 * Merge note: the DJ beat-keeping commands from the original are preserved
 * (our WebAudio DJ engine renders them); they are injected BEFORE the universal
 * dispatcher runs, whose DJ guard then correctly skips a duplicate.
 * Async because it may run a Windows UIA scan of the NLE window.
 */
class ProVideoEditorDirector {
    static isVideoEditPrompt(prompt) {
        const q = prompt.toLowerCase();
        return (/\b(video edit|premiere|davinci|resolve|capcut|after effects|final cut|color grad|timeline edit|b-roll|broll)\b/.test(q) ||
            (/\b(cut a video|editing shortcut|export settings|render video)\b/.test(q)));
    }
    static async buildVideoDirectorOverlay(userPrompt) {
        const nle = detectNle(userPrompt);
        const profile = NLE_PROFILES[nle];
        const commands = [
            { type: 'BOARD', label: `Video Director • ${nle.toUpperCase()} • Edit → Grade → Export` },
            {
                type: 'DJ',
                bpm: 96,
                label: 'Edit pacing beat (96 BPM)',
                color: 'magenta',
                bars: 4,
            },
            { type: 'WRITE', label: 'STRUCTURE: selects → rough cut → music timing → grade → sound → export', color: 'yellow' },
        ];
        for (const sc of profile.shortcuts) {
            commands.push({ type: 'WRITE', label: `${sc.keys}: ${sc.action}`.slice(0, 90), color: 'cyan' });
        }
        commands.push({ type: 'WRITE', label: `EXPORT: ${profile.exportHint}`.slice(0, 90), color: 'green' });
        try {
            const scan = await DynamicAppScannerAndTeacher_1.DynamicAppScannerAndTeacher.buildInteractiveAppLesson(`teach me ${nle === 'editing' ? '' : nle}`.trim());
            for (const cmd of scan) {
                if (cmd.type === 'UIRECT') {
                    commands.push({ ...cmd, label: `${cmd.label} [${nle}]`.slice(0, 90) });
                }
            }
        }
        catch {
            /* scan is a best-effort enrichment */
        }
        return commands;
    }
}
exports.ProVideoEditorDirector = ProVideoEditorDirector;
