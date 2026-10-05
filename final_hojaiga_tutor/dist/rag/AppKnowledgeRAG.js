"use strict";
/**
 * AppKnowledgeRAG - Core RAG engine for app documentation
 * Connects to Ollama's free embedding model (nomic-embed-text)
 * Chunks Markdown documentation and indexes it into local store
 */
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
exports.AppKnowledgeRAG = void 0;
const fs = __importStar(require("fs"));
const LocalVectorStore_1 = require("./LocalVectorStore");
class AppKnowledgeRAG {
    vectorStore;
    ollamaHost;
    embeddingModel;
    constructor(ollamaHost = 'http://127.0.0.1:11434', embeddingModel = 'nomic-embed-text') {
        this.vectorStore = new LocalVectorStore_1.LocalVectorStore();
        this.ollamaHost = ollamaHost;
        this.embeddingModel = embeddingModel;
    }
    /**
     * Ingest a local markdown manual for a specific app (e.g., obs_manual.md)
     */
    async ingestMarkdownFile(appName, filePath) {
        if (!fs.existsSync(filePath)) {
            throw new Error(`Documentation file not found: ${filePath}`);
        }
        const rawText = fs.readFileSync(filePath, 'utf-8');
        const sections = this.chunkMarkdownByHeaders(rawText, appName);
        console.log(`[RAG] Generating local embeddings for ${sections.length} chunks of ${appName}...`);
        for (const chunk of sections) {
            chunk.embedding = await this.getEmbedding(chunk.content);
        }
        this.vectorStore.clearApp(appName);
        this.vectorStore.addChunks(sections);
        console.log(`[RAG] Successfully indexed knowledge base for ${appName}`);
    }
    /**
     * Query the knowledge base for step-by-step procedures
     */
    async queryKnowledge(appName, userIntent, topK = 2) {
        const queryVector = await this.getEmbedding(userIntent);
        return this.vectorStore.search(queryVector, appName, topK);
    }
    async getEmbedding(text) {
        const response = await fetch(`${this.ollamaHost}/api/embeddings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: this.embeddingModel,
                prompt: text
            })
        });
        if (!response.ok) {
            throw new Error(`Ollama Embedding failed: ${response.statusText}`);
        }
        const data = await response.json();
        return data.embedding;
    }
    chunkMarkdownByHeaders(text, appName) {
        const lines = text.split('\n');
        const chunks = [];
        let currentHeader = 'General Overview';
        let currentBuffer = [];
        for (const line of lines) {
            if (line.startsWith('#') || line.startsWith('## ') || line.startsWith('### ')) {
                if (currentBuffer.length > 0) {
                    // CRITICAL RUNTIME CHECK #3: Context-Prefixed RAG Chunks
                    // Prefix the section header to the chunk content for better context during vector search
                    // This prevents ambiguity like "Click '+' to add" (could be Source or Scene)
                    const contentWithContext = `[Section: ${currentHeader}]\n${currentBuffer.join('\n').trim()}`;
                    chunks.push({
                        id: `${appName}_${chunks.length}`,
                        appName,
                        topic: currentHeader,
                        content: contentWithContext
                    });
                    currentBuffer = [];
                }
                currentHeader = line.replace(/#/g, '').trim();
            }
            else {
                currentBuffer.push(line);
            }
        }
        if (currentBuffer.length > 0) {
            // CRITICAL RUNTIME CHECK #3: Context-Prefixed RAG Chunks
            // Prefix the section header to the chunk content for better context during vector search
            const contentWithContext = `[Section: ${currentHeader}]\n${currentBuffer.join('\n').trim()}`;
            chunks.push({
                id: `${appName}_${chunks.length}`,
                appName,
                topic: currentHeader,
                content: contentWithContext
            });
        }
        return chunks.filter(c => c.content.length > 20);
    }
}
exports.AppKnowledgeRAG = AppKnowledgeRAG;
