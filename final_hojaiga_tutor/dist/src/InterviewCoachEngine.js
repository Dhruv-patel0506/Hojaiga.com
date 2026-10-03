"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.InterviewCoachEngine = void 0;
/**
 * Live Mock Interviewer, Filler-Word Telemetry & Salary Negotiation Coach.
 *
 * Merge note: graphs use string nodes (auto-layouted into the claimed rect by
 * the overlay engine). Telemetry is computed from the prompt, which is only a
 * real "transcript" when it is long or actually contains filler words - for a
 * short typed instruction we deliberately do NOT fabricate a clarity/WPM
 * number in the banner (reported deviation from the original, which stamped
 * prompt-based telemetry as if it were live speech).
 */
class InterviewCoachEngine {
    static FILLER_REGEX = /\b(um+|uh+|like|basically|honestly|you know|sort of|kind of|literally)\b/gi;
    static isInterviewPrompt(prompt) {
        return /\b(mock\s+interview|system\s+design|leetcode|behavioral\s+question|star\s+method|salary\s+negotiation|counter\s+offer|interview\s+coach)\b/i.test(prompt);
    }
    /**
     * Evaluates a user's spoken/transcribed answer for filler words, WPM, and pacing.
     */
    static analyzeSpeechTranscript(transcript, durationSeconds = 45) {
        const words = transcript.trim().split(/\s+/).filter(Boolean);
        const matches = transcript.match(this.FILLER_REGEX) || [];
        const wordCount = words.length;
        const fillerCount = matches.length;
        const pacingWpm = Math.round((wordCount / Math.max(10, durationSeconds)) * 60);
        const penalty = Math.min(45, fillerCount * 6);
        const clarityScore = Math.max(50, 100 - penalty);
        return {
            wordCount,
            fillerCount,
            fillerWordsDetected: Array.from(new Set(matches.map((m) => m.toLowerCase()))),
            clarityScore,
            pacingWpm,
        };
    }
    /** True only when the prompt plausibly IS a speech transcript. */
    static isTranscriptLike(telemetry) {
        return telemetry.fillerCount > 0 || telemetry.wordCount >= 15;
    }
    static buildInterviewCoachOverlay(userPrompt) {
        const isNegotiation = /\b(salary|negotiation|offer|comp|compensation|counter)\b/i.test(userPrompt);
        if (isNegotiation) {
            return [
                { type: 'BOARD', label: 'Salary Negotiation Coach • Leverage & Counter-Offer Matrix' },
                {
                    type: 'GRAPH',
                    nodes: ['Pause & Validate', 'Anchor Total Comp', 'Trade Base/Equity/Sign-On', 'Close Collaboratively'],
                    edges: [
                        { from: 'Pause & Validate', to: 'Anchor Total Comp' },
                        { from: 'Anchor Total Comp', to: 'Trade Base/Equity/Sign-On' },
                        { from: 'Trade Base/Equity/Sign-On', to: 'Close Collaboratively' },
                    ],
                    label: 'Negotiation Playbook',
                    color: 'green',
                    loop: true,
                },
                { type: 'WRITE', label: 'Rule [NEVER GIVE A SINGLE NUMBER]: Anchor with a researched Total Compensation band (+15% to +22%).', color: 'cyan' },
                { type: 'WRITE', label: 'Script: "I am thrilled about the team. If we can bring the base to $X and add a $Y sign-on, I am ready to sign today."', color: 'yellow' },
                { type: 'WRITE', label: 'Multi-Lever Fallback: If base salary is capped, pivot immediately to RSUs, sign-on bonus, or a 6-month review cycle.', color: 'green' },
            ];
        }
        const telemetry = this.analyzeSpeechTranscript(userPrompt, 45);
        const transcriptLike = this.isTranscriptLike(telemetry);
        const commands = [
            {
                type: 'BOARD',
                label: transcriptLike
                    ? `Live Mock Interviewer • Clarity: ${telemetry.clarityScore}% | Pacing: ${telemetry.pacingWpm} WPM`
                    : 'Live Mock Interviewer • System Design & Behavioral Rubric',
            },
            {
                type: 'GRAPH',
                nodes: ['Clarify Constraints', 'High-Level Design', 'Bottlenecks & Scale', 'Trade-Off Defense'],
                edges: [
                    { from: 'Clarify Constraints', to: 'High-Level Design' },
                    { from: 'High-Level Design', to: 'Bottlenecks & Scale' },
                    { from: 'Bottlenecks & Scale', to: 'Trade-Off Defense' },
                ],
                label: 'System Design / STAR Rubric',
                color: 'cyan',
                loop: true,
            },
        ];
        if (transcriptLike) {
            commands.push({
                type: 'WRITE',
                label: `Speech Telemetry: ${telemetry.fillerCount} filler words detected (${telemetry.fillerWordsDetected.join(', ') || 'clean delivery'}).`,
                color: telemetry.fillerCount > 2 ? 'yellow' : 'green',
            });
            commands.push({
                type: 'WRITE',
                label: `Delivery: ${telemetry.pacingWpm} WPM, ${telemetry.wordCount} words. Target 120-150 WPM with a 2-second pause before each section.`,
                color: 'cyan',
            });
        }
        else {
            commands.push({ type: 'WRITE', label: 'Answer skeleton: Situation -> Task -> Action -> Result, then name the metric you moved.', color: 'green' });
        }
        commands.push({ type: 'WRITE', label: 'Follow-Up Probe #1: "What happens to your p99 latency if the primary cache shard goes down during a 10x traffic spike?"', color: 'cyan' }, { type: 'WRITE', label: 'Follow-Up Probe #2: "State your Big-O time and space complexity explicitly before writing the loop."', color: 'orange' });
        return commands;
    }
}
exports.InterviewCoachEngine = InterviewCoachEngine;
