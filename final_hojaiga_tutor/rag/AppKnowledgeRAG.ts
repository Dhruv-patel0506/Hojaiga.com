/**
 * AppKnowledgeRAG - Core RAG engine for app documentation
 * Connects to Ollama's free embedding model (nomic-embed-text)
 * Chunks Markdown documentation and indexes it into local store
 */

import * as fs from 'fs';
import * as path from 'path';
import { LocalVectorStore } from './LocalVectorStore';
import { DocumentChunk, SearchResult } from './types';

export class AppKnowledgeRAG {
  private vectorStore: LocalVectorStore;
  private ollamaHost: string;
  private embeddingModel: string;

  constructor(ollamaHost: string = 'http://127.0.0.1:11434', embeddingModel: string = 'nomic-embed-text') {
    this.vectorStore = new LocalVectorStore();
    this.ollamaHost = ollamaHost;
    this.embeddingModel = embeddingModel;
  }

  /**
   * Ingest a local markdown manual for a specific app (e.g., obs_manual.md)
   */
  public async ingestMarkdownFile(appName: string, filePath: string): Promise<void> {
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
  public async queryKnowledge(appName: string, userIntent: string, topK: number = 2): Promise<SearchResult[]> {
    const queryVector = await this.getEmbedding(userIntent);
    return this.vectorStore.search(queryVector, appName, topK);
  }

  private async getEmbedding(text: string): Promise<number[]> {
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

  private chunkMarkdownByHeaders(text: string, appName: string): DocumentChunk[] {
    const lines = text.split('\n');
    const chunks: DocumentChunk[] = [];
    let currentHeader = 'General Overview';
    let currentBuffer: string[] = [];

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
      } else {
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
