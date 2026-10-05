import React from 'react';
import { OfficeState } from './office/engine/officeState';

interface Props {
  agentId: number;
  onClose: () => void;
  officeState: OfficeState;
  agentStatuses: Record<string, any>;
}

export const AgentInspectorModal: React.FC<Props> = ({ agentId, onClose, officeState, agentStatuses }) => {
  const character = officeState.characters.get(agentId);
  const status = agentStatuses[agentId];
  
  if (!character) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center pointer-events-auto" style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}>
      <div className="bg-slate-800 border-4 border-slate-400 p-6 shadow-pixel w-96 font-mono text-white relative">
        <button 
          onClick={onClose}
          className="absolute top-2 right-2 bg-red-600 border-2 border-red-800 text-white w-6 h-6 flex items-center justify-center cursor-pointer shadow-pixel"
        >
          X
        </button>
        <h2 className="text-xl mb-4 border-b-2 border-slate-500 pb-2 text-accent-bright">INSPECTING AGENT #{agentId}</h2>
        
        <div className="flex flex-col gap-3">
          <div>
            <span className="text-slate-400">STATE:</span> 
            <span className="ml-2 text-green-400">{character.state.toUpperCase()}</span>
          </div>
          <div>
            <span className="text-slate-400">DIRECTION:</span> 
            <span className="ml-2">{character.dir === 0 ? 'SOUTH' : character.dir === 1 ? 'WEST' : character.dir === 2 ? 'EAST' : 'NORTH'}</span>
          </div>
          <div>
            <span className="text-slate-400">SEAT:</span> 
            <span className="ml-2">{character.seatId ? character.seatId : 'UNASSIGNED'}</span>
          </div>
          
          <div className="mt-4 border-t-2 border-slate-600 pt-2">
            <span className="text-slate-400 block mb-1">LIVE TELEMETRY:</span>
            <div className="bg-black p-2 border border-slate-700 text-sm h-24 overflow-y-auto font-mono text-green-500">
              {status?.taskDescription ? (
                <>
                  <p>Processing payload...</p>
                  <p className="text-yellow-400">&gt; {status.taskDescription}</p>
                  <p>CPU: {Math.floor(Math.random() * 20 + 80)}% | RAM: {Math.floor(Math.random() * 1024 + 512)}MB</p>
                </>
              ) : (
                <p>AWAITING INSTRUCTIONS...</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
