"use strict";
/**
 * LocalVectorStore - In-memory vector store with Cosine Similarity
 * Runs entirely in memory without requiring Docker, ChromaDB, or Python dependencies
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.LocalVectorStore = void 0;
class LocalVectorStore {
    chunks = [];
    addChunks(newChunks) {
        this.chunks.push(...newChunks);
    }
    clearApp(appName) {
        this.chunks = this.chunks.filter(c => c.appName.toLowerCase() !== appName.toLowerCase());
    }
    search(queryEmbedding, appName, topK = 3) {
        const appChunks = this.chunks.filter(c => c.appName.toLowerCase() === appName.toLowerCase() && c.embedding);
        const scored = appChunks.map(chunk => ({
            chunk,
            score: this.cosineSimilarity(queryEmbedding, chunk.embedding)
        }));
        scored.sort((a, b) => b.score - a.score);
        return scored.slice(0, topK);
    }
    cosineSimilarity(vecA, vecB) {
        let dotProduct = 0.0;
        let normA = 0.0;
        let normB = 0.0;
        for (let i = 0; i < vecA.length; i++) {
            dotProduct += vecA[i] * vecB[i];
            normA += vecA[i] * vecA[i];
            normB += vecB[i] * vecB[i];
        }
        if (normA === 0 || normB === 0)
            return 0;
        return dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
    }
}
exports.LocalVectorStore = LocalVectorStore;
