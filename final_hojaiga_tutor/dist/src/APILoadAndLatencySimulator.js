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
exports.APILoadAndLatencySimulator = void 0;
/**
 * File 24 - Localhost Endpoint Latency Profiler, p95/p99 Calculator & Bottleneck Visualizer.
 * Merge deviation from the pasted source: the bare `rate\s+limit` alternative was
 * removed from isLoadSimulatorPrompt so coding prompts like "write code for a
 * rate limiter function" still route to the polyglot coder (which runs earlier
 * in the SWE workbench group). All other triggers are unchanged; probes stay
 * strictly localhost-only via isSafeLocalhostUrl.
 */
const http = __importStar(require("http"));
class APILoadAndLatencySimulator {
    static isLoadSimulatorPrompt(prompt) {
        return /\b(latency|p95|p99|load\s+test|benchmark\s+api|slow\s+endpoint|throughput|n\+1\s+query|bottleneck|stress\s+test)\b/i.test(prompt);
    }
    static isSafeLocalhostUrl(rawUrl) {
        try {
            const parsed = new URL(rawUrl);
            return parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1';
        }
        catch {
            return false;
        }
    }
    static async measureLocalEndpoint(rawUrl = 'http://127.0.0.1:3000/health', probes = 5) {
        if (!this.isSafeLocalhostUrl(rawUrl)) {
            throw new Error('Safety Guard: APILoadAndLatencySimulator only probes localhost / 127.0.0.1 endpoints.');
        }
        const cappedProbes = Math.min(8, Math.max(1, probes));
        const durations = [];
        for (let i = 0; i < cappedProbes; i++) {
            const start = Date.now();
            await new Promise(resolve => {
                const req = http.get(rawUrl, { timeout: 600 }, res => {
                    res.resume();
                    res.on('end', () => resolve());
                });
                req.on('error', () => resolve());
                req.on('timeout', () => {
                    req.destroy();
                    resolve();
                });
            });
            durations.push(Math.max(2, Date.now() - start));
        }
        durations.sort((a, b) => a - b);
        const pickPercentile = (p) => durations[Math.min(durations.length - 1, Math.floor(durations.length * p))];
        const p50Ms = pickPercentile(0.5);
        const p95Ms = pickPercentile(0.95);
        const p99Ms = pickPercentile(0.99);
        return {
            targetUrl: rawUrl,
            samplesCount: cappedProbes,
            p50Ms,
            p95Ms,
            p99Ms,
            bottleneckDiagnosis: p95Ms > 150
                ? 'High tail latency detected → Add Redis/LRU read-through cache & batch N+1 DB queries.'
                : 'Healthy sub-150ms tail latency → Event loop and connection pool are well-balanced.'
        };
    }
    static async buildLatencySimulatorOverlay(userPrompt) {
        const urlMatch = userPrompt.match(/https?:\/\/(?:localhost|127\.0\.0\.1):\d+[^\s"']*/i);
        const targetUrl = urlMatch ? urlMatch[0] : 'http://127.0.0.1:3000/api/health';
        const report = await this.measureLocalEndpoint(targetUrl, 5);
        return [
            {
                type: 'BOARD',
                label: `API Latency & Bottleneck Profiler • p50: ${report.p50Ms}ms | p95: ${report.p95Ms}ms | p99: ${report.p99Ms}ms`
            },
            {
                type: 'GRAPH',
                nodes: [
                    '1. Token-Bucket Rate Limiter',
                    '2. In-Memory LRU Cache Hit',
                    '3. Pooled Async DB Query',
                    '4. Gzip / JSON Stream Response'
                ],
                edges: [
                    { from: '1. Token-Bucket Rate Limiter', to: '2. In-Memory LRU Cache Hit' },
                    { from: '2. In-Memory LRU Cache Hit', to: '3. Pooled Async DB Query' },
                    { from: '3. Pooled Async DB Query', to: '4. Gzip / JSON Stream Response' }
                ],
                nodePositions: {
                    '1. Token-Bucket Rate Limiter': { x: 155, y: 175 },
                    '2. In-Memory LRU Cache Hit': { x: 355, y: 175 },
                    '3. Pooled Async DB Query': { x: 155, y: 315 },
                    '4. Gzip / JSON Stream Response': { x: 355, y: 315 }
                },
                label: 'Low-Latency Request Pipeline',
                color: 'orange',
                loop: true
            },
            {
                type: 'WRITE',
                label: `STAGE 1 [VISUAL TEACH]: Tail latency (p99) spikes when synchronous serialization or unbatched DB calls block the Node/Python event loop.`,
                color: 'cyan'
            },
            {
                type: 'WRITE',
                label: `STAGE 2 [LOCALHOST TELEMETRY]: Probed ${report.targetUrl} (${report.samplesCount}x) → ${report.bottleneckDiagnosis}`,
                color: 'yellow'
            },
            {
                type: 'WRITE',
                label: 'STAGE 3 [BUILT OPTIMIZATION]: Wrap hot reads in a 30s TTL Map cache and replace sequential await-in-loop with Promise.all().',
                color: 'green'
            }
        ];
    }
}
exports.APILoadAndLatencySimulator = APILoadAndLatencySimulator;
