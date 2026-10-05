/**
 * InteractiveInputHandler - Handles user input during teaching
 * Provides visible input interface for interactive tutoring
 */

import { EventEmitter } from 'events';

export interface UserInputEvent {
  question: string;
  timestamp: number;
  response?: string;
}

export interface QuestionAskedEvent {
  question: string;
  timestamp: number;
}

export interface ResponseReceivedEvent {
  response: string;
  timestamp: number;
}

export interface ListeningStartedEvent {
  timestamp: number;
}

export interface ListeningStoppedEvent {
  timestamp: number;
}

export interface QuestionCancelledEvent {
  timestamp: number;
}

export class InteractiveInputHandler extends EventEmitter {
  private isListening: boolean = false;
  private currentQuestion: string | null = null;
  private inputCallbacks: Map<string, (response: string) => void> = new Map();

  // Explicitly type the EventEmitter methods for TypeScript
  on(event: 'question-asked', listener: (data: QuestionAskedEvent) => void): this;
  on(event: 'response-received', listener: (data: ResponseReceivedEvent) => void): this;
  on(event: 'listening-started', listener: (data: ListeningStartedEvent) => void): this;
  on(event: 'listening-stopped', listener: (data: ListeningStoppedEvent) => void): this;
  on(event: 'question-cancelled', listener: (data: QuestionCancelledEvent) => void): this;
  on(event: string, listener: (...args: any[]) => void): this {
    return super.on(event, listener);
  }

  once(event: 'question-asked', listener: (data: QuestionAskedEvent) => void): this;
  once(event: 'response-received', listener: (data: ResponseReceivedEvent) => void): this;
  once(event: string, listener: (...args: any[]) => void): this {
    return super.once(event, listener);
  }

  emit(event: 'question-asked', data: QuestionAskedEvent): boolean;
  emit(event: 'response-received', data: ResponseReceivedEvent): boolean;
  emit(event: 'listening-started', data: ListeningStartedEvent): boolean;
  emit(event: 'listening-stopped', data: ListeningStoppedEvent): boolean;
  emit(event: 'question-cancelled', data: QuestionCancelledEvent): boolean;
  emit(event: string, ...args: any[]): boolean {
    return super.emit(event, ...args);
  }

  /**
   * Start listening for user input
   */
  startListening(): void {
    this.isListening = true;
    console.log('[InteractiveInput] Listening for user input...');
    this.emit('listening-started', { timestamp: Date.now() } as ListeningStartedEvent);
  }

  /**
   * Stop listening for user input
   */
  stopListening(): void {
    this.isListening = false;
    this.currentQuestion = null;
    console.log('[InteractiveInput] Stopped listening');
    this.emit('listening-stopped', { timestamp: Date.now() } as ListeningStoppedEvent);
  }

  /**
   * Ask a question and wait for user response
   * Returns a promise that resolves when user responds
   */
  async askQuestion(question: string, timeoutMs: number = 30000): Promise<string> {
    console.log(`[InteractiveInput] Question: "${question}"`);
    this.currentQuestion = question;
    
    // Emit event for UI to show input field
    this.emit('question-asked', { question, timestamp: Date.now() } as QuestionAskedEvent);

    return new Promise((resolve, reject) => {
      const callbackId = `q_${Date.now()}`;
      
      // Set up callback for this specific question
      this.inputCallbacks.set(callbackId, (response: string) => {
        console.log(`[InteractiveInput] Received response: "${response}"`);
        this.currentQuestion = null;
        this.inputCallbacks.delete(callbackId);
        resolve(response);
      });

      // Set timeout
      const timeout = setTimeout(() => {
        this.inputCallbacks.delete(callbackId);
        this.currentQuestion = null;
        console.warn('[InteractiveInput] Question timed out');
        reject(new Error('Question timed out'));
      }, timeoutMs);

      // Cleanup on event
      this.once('response-received', (data: ResponseReceivedEvent) => {
        clearTimeout(timeout);
      });
    });
  }

  /**
   * Handle user response
   */
  handleResponse(response: string): void {
    if (!this.isListening) {
      console.warn('[InteractiveInput] Not listening, ignoring response');
      return;
    }

    console.log(`[InteractiveInput] Handling response: "${response}"`);
    
    // Find the waiting callback
    for (const [id, callback] of this.inputCallbacks.entries()) {
      callback(response);
      this.emit('response-received', { response, timestamp: Date.now() } as ResponseReceivedEvent);
      return;
    }

    // If no specific callback, emit general event
    this.emit('response-received', { response, timestamp: Date.now() } as ResponseReceivedEvent);
  }

  /**
   * Check if currently listening
   */
  isActive(): boolean {
    return this.isListening;
  }

  /**
   * Get current question
   */
  getCurrentQuestion(): string | null {
    return this.currentQuestion;
  }

  /**
   * Cancel current question
   */
  cancelQuestion(): void {
    if (this.currentQuestion) {
      console.log(`[InteractiveInput] Cancelled question: "${this.currentQuestion}"`);
      this.currentQuestion = null;
      this.emit('question-cancelled', { timestamp: Date.now() } as QuestionCancelledEvent);
    }
  }
}
