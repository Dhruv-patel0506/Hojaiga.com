import React from 'react';

export const DialogueBox: React.FC = () => {
    return (
        <div style={{ 
            position: 'absolute', bottom: 20, left: '50%', transform: 'translateX(-50%)', 
            background: 'blue', color: 'white', padding: 20, border: '4px solid white', 
            fontFamily: '"Press Start 2P", cursive' 
        }}>
            DialogueBox Placeholder
        </div>
    );
};
