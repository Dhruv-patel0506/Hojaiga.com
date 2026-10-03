"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.CyberDefenseTutorEngine = void 0;
const CONCEPTS = [
    {
        id: 'tls',
        label: 'TLS Handshake / Encryption',
        color: 'cyan',
        nodes: [
            { id: 'client', label: 'ClientHello', color: 'cyan' },
            { id: 'server', label: 'ServerHello + Cert', color: 'green' },
            { id: 'keys', label: 'Key Exchange', color: 'yellow' },
            { id: 'session', label: 'Encrypted Session', color: 'orange' },
        ],
        edges: [
            { from: 'client', to: 'server', label: 'offer suites', color: 'cyan' },
            { from: 'server', to: 'keys', label: 'certificate', color: 'green' },
            { from: 'keys', to: 'session', label: 'session keys', color: 'yellow' },
        ],
        card: 'TLS: authenticate the server, derive symmetric session keys, then encrypt everything.',
    },
    {
        id: 'firewall',
        label: 'Firewall / Segmentation',
        color: 'orange',
        nodes: [
            { id: 'net', label: 'Untrusted Net', color: 'red' },
            { id: 'fw', label: 'Firewall Rules', color: 'orange' },
            { id: 'dmz', label: 'DMZ', color: 'yellow' },
            { id: 'int', label: 'Internal LAN', color: 'green' },
        ],
        edges: [
            { from: 'net', to: 'fw', label: 'ingress', color: 'red' },
            { from: 'fw', to: 'dmz', label: 'allow 443', color: 'orange' },
            { from: 'fw', to: 'int', label: 'deny by default', color: 'green' },
        ],
        card: 'Firewall: default-deny + explicit allow-list; segment trust zones (net / DMZ / LAN).',
    },
    {
        id: 'auth',
        label: 'AuthN / AuthZ / Session',
        color: 'green',
        nodes: [
            { id: 'user', label: 'User', color: 'cyan' },
            { id: 'authn', label: 'AuthN (who)', color: 'green' },
            { id: 'authz', label: 'AuthZ (what)', color: 'yellow' },
            { id: 'sess', label: 'Session Token', color: 'orange' },
        ],
        edges: [
            { from: 'user', to: 'authn', label: 'credentials', color: 'cyan' },
            { from: 'authn', to: 'authz', label: 'identity', color: 'green' },
            { from: 'authz', to: 'sess', label: 'scoped claim', color: 'yellow' },
        ],
        card: 'AuthN proves identity; AuthZ grants least privilege; sessions carry short-lived scoped tokens.',
    },
    {
        id: 'xss',
        label: 'XSS / Input Defense',
        color: 'yellow',
        nodes: [
            { id: 'input', label: 'User Input', color: 'red' },
            { id: 'vld', label: 'Validate/Sanitize', color: 'yellow' },
            { id: 'ctx', label: 'Context Encode', color: 'cyan' },
            { id: 'dom', label: 'Safe DOM/DB', color: 'green' },
        ],
        edges: [
            { from: 'input', to: 'vld', label: 'untrusted', color: 'red' },
            { from: 'vld', to: 'ctx', label: 'allow-list', color: 'yellow' },
            { from: 'ctx', to: 'dom', label: 'encode', color: 'green' },
        ],
        card: 'XSS: validate input, encode output per context (HTML/JS/URL), CSP as defense in depth.',
    },
    {
        id: 'memory',
        label: 'Memory Safety / CVEs',
        color: 'magenta',
        nodes: [
            { id: 'bug', label: 'Overflow/UAF', color: 'red' },
            { id: 'aslr', label: 'ASLR/DEP', color: 'yellow' },
            { id: 'cve', label: 'CVE + Patch', color: 'orange' },
            { id: 'safe', label: 'Safe Lang/RE', color: 'green' },
        ],
        edges: [
            { from: 'bug', to: 'aslr', label: 'exploit', color: 'red' },
            { from: 'bug', to: 'cve', label: 'report', color: 'orange' },
            { from: 'cve', to: 'safe', label: 'patch + rewrite', color: 'green' },
        ],
        card: 'Memory bugs: mitigations (ASLR/DEP) buy time; real fix is patching + memory-safe languages.',
    },
];
/**
 * Defensive Security Architecture Tutor.
 *
 * Merge note: educational / blue-team only (matches the user's stated scope).
 * Structure comes from the concept DB; lesson prose still comes from the model.
 * Merged in place by routeSpecializedEngines.
 */
class CyberDefenseTutorEngine {
    static CONCEPT_RE = /\b(tls|ssl|encrypt(?:ion)?|firewall|authn|authz|authentication|authorization|session (?:token|hijack)|xss|csrf|sql ?injection|input validation|memory safe|use.after.free|buffer overflow|cve|vulnerabilit|penetration test|zero trust|least privilege|sandboxing|key exchange|certificate pinning|hashing|salting|diffie.hellman|aead|ws[- ]?security)\b/i;
    static isSecurityConceptPrompt(prompt) {
        return this.CONCEPT_RE.test(prompt);
    }
    static buildSecurityOverlay(userPrompt) {
        const concept = this.pickConcept(userPrompt);
        const nodes = concept.nodes.map((n) => ({ ...n, nodePosition: { x: 0, y: 0 } }));
        const edges = concept.edges;
        const commands = [
            { type: 'BOARD', label: `Cyber Defense (Blue Team) • ${concept.label}` },
            {
                type: 'GRAPH',
                nodes,
                edges,
                showLegend: true,
                nodePositions: {},
                color: concept.color,
            },
            { type: 'WRITE', label: concept.card, color: 'green' },
            { type: 'WRITE', label: 'ATTACK view: what the adversary tries at each hop (teach both sides).', color: 'red' },
            { type: 'WRITE', label: 'DEFENSE view: the control that stops it + its failure mode.', color: 'cyan' },
        ];
        return commands;
    }
    static pickConcept(prompt) {
        const q = prompt.toLowerCase();
        if (/firewall|segment|zero trust|least privilege|dmz/.test(q))
            return this.byId('firewall');
        if (/authn|authz|session|token|login|password/.test(q))
            return this.byId('auth');
        if (/xss|csrf|sql ?inject|sanitiz|encode/.test(q))
            return this.byId('xss');
        if (/memory|overflow|use.after.free|cve|aslr|safe lang/.test(q))
            return this.byId('memory');
        if (/tls|ssl|encrypt|certificate|key exchange|hash|salting|diffie/.test(q))
            return this.byId('tls');
        return this.byId('tls');
    }
    static byId(id) {
        return CONCEPTS.find((c) => c.id === id) || CONCEPTS[0];
    }
}
exports.CyberDefenseTutorEngine = CyberDefenseTutorEngine;
