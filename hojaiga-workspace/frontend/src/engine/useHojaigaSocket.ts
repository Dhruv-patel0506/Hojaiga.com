import { useEffect } from 'react';
import { Engine } from './gameEngine';

export const useHojaigaSocket = (engine: Engine | null) => {
    useEffect(() => {
        if (!engine) return;

        // Connect to the Live Python Backend (organ_99_visual_adapter.py)
        const socket = new WebSocket('ws://127.0.0.1:8767');

        socket.onopen = () => console.log('🟢 Connected to Live Hojaiga Backend');

        socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                
                // Map the backend's "choreoEvent" to our engine's commands
                if (data.type === 'choreoEvent') {
                    const choreo = data.event;
                    
                    // Generate a consistent agent ID (just for visualization purposes)
                    const agentId = `Agent_${data.data?.taskId || 'default'}`;

                    switch (choreo) {
                        case 'TaskReceived':
                        case 'SystemBoot':
                            // Spawn agent at Reception (X: 25, Y: 43)
                            engine.spawnAgent({ id: agentId, x: 25, y: 43, organName: "Live Agent" });
                            break;
                            
                        case 'TaskCompiled':
                        case 'SecurityClearance':
                            // Route agent to CNS Hub door (X: 25, Y: 28)
                            engine.commandQueue.push({
                                type: 'MOVE_AGENT',
                                payload: { id: agentId, targetX: 25, targetY: 28 }
                            });
                            break;
                            
                        case 'ExecutionStarted':
                        case 'TempAgentRequired':
                            // Route agent to Execution Train (X: 35, Y: 25)
                            engine.commandQueue.push({
                                type: 'MOVE_AGENT',
                                payload: { id: agentId, targetX: 35, targetY: 25 }
                            });
                            // Start typing with a task bubble!
                            engine.commandQueue.push({
                                type: 'START_TASK',
                                payload: { id: agentId, text: `Executing: ${data.data?.taskId || 'Process'}` }
                            });
                            break;
                            
                        case 'TaskError':
                        case 'TaskCompleted':
                            // Update task bubble to show result
                            engine.commandQueue.push({
                                type: 'START_TASK',
                                payload: { id: agentId, text: choreo === 'TaskError' ? 'ERROR!' : 'COMPLETED!' }
                            });
                            // Route out via the Agent Wing
                            setTimeout(() => {
                                engine.commandQueue.push({
                                    type: 'MOVE_AGENT',
                                    payload: { id: agentId, targetX: 10, targetY: 40 }
                                });
                            }, 3000); // Leave bubble up for 3 seconds before moving
                            break;
                    }
                } else {
                    // Fallback to our old test commands if needed
                    switch (data.type) {
                        case 'SPAWN_AGENT':
                            engine.spawnAgent(data.payload);
                            break;
                        case 'MOVE_AGENT':
                        case 'START_TASK':
                            engine.commandQueue.push(data);
                            break;
                    }
                }
            } catch (err) {
                console.error("WebSocket parsing error:", err);
            }
        };

        socket.onclose = () => console.log('🔴 CNS Connection Lost');

        return () => socket.close();
    }, [engine]);
};
