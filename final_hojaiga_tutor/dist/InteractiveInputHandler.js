"use strict";
/**
 * InteractiveInputHandler - Handles user input during teaching
 * Provides visible input interface for interactive tutoring
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.InteractiveInputHandler = void 0;
const events_1 = require("events");
class InteractiveInputHandler extends events_1.EventEmitter {
    isListening = false;
    currentQuestion = null;
    inputCallbacks = new Map();
    on(event, listener) {
        return super.on(event, listener);
    }
    once(event, listener) {
        return super.once(event, listener);
    }
    emit(event, ...args) {
        return super.emit(event, ...args);
    }
    /**
     * Start listening for user input
     */
    startListening() {
        this.isListening = true;
        console.log('[InteractiveInput] Listening for user input...');
        this.emit('listening-started', { timestamp: Date.now() });
    }
    /**
     * Stop listening for user input
     */
    stopListening() {
        this.isListening = false;
        this.currentQuestion = null;
        console.log('[InteractiveInput] Stopped listening');
        this.emit('listening-stopped', { timestamp: Date.now() });
    }
    /**
     * Ask a question and wait for user response
     * Returns a promise that resolves when user responds
     */
    async askQuestion(question, timeoutMs = 30000) {
        console.log(`[InteractiveInput] Question: "${question}"`);
        this.currentQuestion = question;
        // Emit event for UI to show input field
        this.emit('question-asked', { question, timestamp: Date.now() });
        return new Promise((resolve, reject) => {
            const callbackId = `q_${Date.now()}`;
            // Set up callback for this specific question
            this.inputCallbacks.set(callbackId, (response) => {
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
            this.once('response-received', (data) => {
                clearTimeout(timeout);
            });
        });
    }
    /**
     * Handle user response
     */
    handleResponse(response) {
        if (!this.isListening) {
            console.warn('[InteractiveInput] Not listening, ignoring response');
            return;
        }
        console.log(`[InteractiveInput] Handling response: "${response}"`);
        // Find the waiting callback
        for (const [id, callback] of this.inputCallbacks.entries()) {
            callback(response);
            this.emit('response-received', { response, timestamp: Date.now() });
            return;
        }
        // If no specific callback, emit general event
        this.emit('response-received', { response, timestamp: Date.now() });
    }
    /**
     * Check if currently listening
     */
    isActive() {
        return this.isListening;
    }
    /**
     * Get current question
     */
    getCurrentQuestion() {
        return this.currentQuestion;
    }
    /**
     * Cancel current question
     */
    cancelQuestion() {
        if (this.currentQuestion) {
            console.log(`[InteractiveInput] Cancelled question: "${this.currentQuestion}"`);
            this.currentQuestion = null;
            this.emit('question-cancelled', { timestamp: Date.now() });
        }
    }
}
exports.InteractiveInputHandler = InteractiveInputHandler;
