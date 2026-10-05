/**
 * LocalVectorStore - In-memory vector store with Cosine Similarity
 * Runs entirely in memory without requiring Docker, ChromaDB, or Python dependencies
 */

import { DocumentChunk, SearchResult } from './types';

export class LocalVectorStore {
  private chunks: DocumentChunk[] = [];

  public addChunks(newChunks: DocumentChunk[]): void {
    this.chunks.push(...newChunks);
  }

  public clearApp(appName: string): void {
    this.chunks = this.chunks.filter(c => c.appName.toLowerCase() !== appName.toLowerCase());
  }

  public search(queryEmbedding: number[], appName: string, topK: number = 3): SearchResult[] {
    const appChunks = this.chunks.filter(
      c => c.appName.toLowerCase() === appName.toLowerCase() && c.embedding
    );

    const scored = appChunks.map(chunk => ({
      chunk,
      score: this.cosineSimilarity(queryEmbedding, chunk.embedding!)
    }));

    scored.sort((a, b) => b.score - a.score);
    return scored.slice(0, topK);
  }

  private cosineSimilarity(vecA: number[], vecB: number[]): number {
    let dotProduct = 0.0;
    let normA = 0.0;
    let normB = 0.0;

    for (let i = 0; i < vecA.length; i++) {
      dotProduct += vecA[i] * vecB[i];
      normA += vecA[i] * vecA[i];
      normB += vecB[i] * vecB[i];
    }

    if (normA === 0 || normB === 0) return 0;
    return dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
  }
}
