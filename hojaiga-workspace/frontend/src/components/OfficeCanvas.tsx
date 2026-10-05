import React, { useEffect, useRef, useState } from 'react';
import { AssetManager } from '../engine/gameEngine';
import { generateCompoundGrid, TILE, CompoundFurniture } from '../engine/layoutBuilder';

// We use a scale factor so the 16x16 pixel art isn't microscopic on modern monitors
const TILE_SIZE = 32; 

export const OfficeCanvas: React.FC = () => {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const [isLoaded, setIsLoaded] = useState(false);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        // Pixel art crispness
        ctx.imageSmoothingEnabled = false;

        // 1. Generate the massive 60x60 Master Grid
        const grid = generateCompoundGrid(60, 60);
        const assets = new AssetManager();

        // 2. Load the Flat 2D Assets from the repository
        // (Ensure these match the paths in your public folder)
        Promise.all([
            assets.loadSprite('wall', '/assets/walls/wall_0.png'),
            assets.loadSprite('floor_wood', '/assets/floors/floor_0.png'),      // Used for Manager/Reception
            assets.loadSprite('carpet_ceo', '/assets/carpets/carpet_2.png'),    // Used for CEO
            assets.loadSprite('floor_ind', '/assets/floors/floor_1.png'),       // Used for Execution Train
            assets.loadSprite('floor_dark', '/assets/floors/floor_2.png'),      // Used for Agent Wing
            assets.loadSprite('floor_glow', '/assets/floors/floor_4.png'),      // Used for CNS Hub
            assets.loadSprite('char_ceo', '/assets/characters/char_0.png'),
            assets.loadSprite('desk_ceo', '/assets/furniture/DESK/DESK_FRONT.png'),
            assets.loadSprite('desk_worker', '/assets/furniture/DESK/DESK_FRONT.png'),
            assets.loadSprite('pc_on', '/assets/furniture/PC/PC_FRONT_ON_1.png'),
            assets.loadSprite('server_rack', '/assets/furniture/DOUBLE_BOOKSHELF/DOUBLE_BOOKSHELF.png')
        ]).then(() => {
            setIsLoaded(true);

            // Basic Camera Panning State (Looking at the center of the map)
            let panX = (60 * TILE_SIZE) / 2 - window.innerWidth / 2;
            let panY = (60 * TILE_SIZE) / 2 - window.innerHeight / 2;

            // 3. The Flat 2D Render Loop
            let animationFrameId: number;
            const loop = () => {
                // Clear the Void (Black Background)
                ctx.fillStyle = '#0B0B0C'; // A nice dark terminal background
                ctx.fillRect(0, 0, window.innerWidth, window.innerHeight);

                ctx.save();
                ctx.translate(-panX, -panY);

                // A. Paint the Architecture (Floors and Walls)
                for (let y = 0; y < grid.length; y++) {
                    for (let x = 0; x < grid[y].length; x++) {
                        const tileType = grid[y][x];
                        if (tileType === TILE.VOID) continue;

                        let imgToDraw: HTMLImageElement | undefined;

                        // Map the grid numbers to the loaded images
                        if (tileType === TILE.WALL) imgToDraw = assets.get('wall');
                        else if (tileType === TILE.FLOOR_CEO) imgToDraw = assets.get('carpet_ceo');
                        else if (tileType === TILE.FLOOR_MANAGER) imgToDraw = assets.get('floor_wood');
                        else if (tileType === TILE.FLOOR_EXECUTION) imgToDraw = assets.get('floor_ind');
                        else if (tileType === TILE.FLOOR_AGENT) imgToDraw = assets.get('floor_dark');
                        else if (tileType === TILE.FLOOR_CNS) imgToDraw = assets.get('floor_glow');

                        if (imgToDraw) {
                            // Draw the tile exactly at the grid coordinates!
                            // For walls, we might need a slight offset since they are 16x32 in a 16x16 grid space
                            if (tileType === TILE.WALL) {
                                ctx.drawImage(imgToDraw, x * TILE_SIZE, y * TILE_SIZE - TILE_SIZE, TILE_SIZE, TILE_SIZE * 2);
                            } else {
                                ctx.drawImage(imgToDraw, x * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE);
                            }
                        }
                    }
                }

                // B. Paint the Furniture Layer
                for (const prop of CompoundFurniture) {
                    const propSprite = assets.get(prop.spriteKey);
                    if (propSprite) {
                        ctx.drawImage(propSprite, prop.x * TILE_SIZE, prop.y * TILE_SIZE, propSprite.width * 2, propSprite.height * 2);
                    }
                }

                // C. Paint the Entities (Characters)
                const charSprite = assets.get('char_ceo');
                const entities: any[] = []; // TODO: Integrate actual Engine entities
                if (charSprite && entities.length > 0) {
                    for (const entity of entities) {
                        const frameW = 16; 
                        const frameH = 32;

                        let row = 0;
                        let flip = false;
                        switch(entity.facingDirection) {
                            case 'down': row = 0; break;
                            case 'up': row = 1; break;
                            case 'right': row = 2; break;
                            case 'left': row = 2; flip = true; break; 
                            default: row = 0; break;
                        }

                        // If moving or typing, use the animated column. If idle, lock to column 0.
                        const isAnimating = entity.isMoving || entity.state === 'type';
                        const col = isAnimating ? (entity.animFrame || 0) : 0; 

                        const sx = col * frameW;
                        const sy = row * frameH;
                        
                        const destX = entity.x * TILE_SIZE;
                        const destY = entity.y * TILE_SIZE - frameH + 16;

                        if (flip) {
                            ctx.save();
                            ctx.translate(destX + TILE_SIZE/2, destY);
                            ctx.scale(-1, 1);
                            ctx.drawImage(
                                charSprite, 
                                sx, sy, frameW, frameH, 
                                -TILE_SIZE/2, 0, 
                                TILE_SIZE, TILE_SIZE * 2
                            );
                            ctx.restore();
                        } else {
                            ctx.drawImage(
                                charSprite, 
                                sx, sy, frameW, frameH, 
                                destX, destY, 
                                TILE_SIZE, TILE_SIZE * 2
                            );
                        }

                        // Draw Task Speech Bubble
                        if (entity.taskText) {
                            const text = entity.taskText;
                            ctx.font = '10px "Courier New", monospace'; // Pixel-art style font
                            const textWidth = ctx.measureText(text).width;
                            const bubbleWidth = textWidth + 10;
                            const bubbleHeight = 16;
                            const bubbleX = destX + (TILE_SIZE / 2) - (bubbleWidth / 2);
                            const bubbleY = destY - bubbleHeight - 5; // Above head

                            // Draw bubble background
                            ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
                            ctx.fillRect(bubbleX, bubbleY, bubbleWidth, bubbleHeight);
                            
                            // Draw bubble outline
                            ctx.strokeStyle = '#000';
                            ctx.lineWidth = 1;
                            ctx.strokeRect(bubbleX, bubbleY, bubbleWidth, bubbleHeight);

                            // Draw bubble tail
                            ctx.beginPath();
                            ctx.moveTo(destX + TILE_SIZE / 2 - 4, bubbleY + bubbleHeight);
                            ctx.lineTo(destX + TILE_SIZE / 2, bubbleY + bubbleHeight + 4);
                            ctx.lineTo(destX + TILE_SIZE / 2 + 4, bubbleY + bubbleHeight);
                            ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
                            ctx.fill();
                            ctx.stroke();

                            // Draw text
                            ctx.fillStyle = '#000';
                            ctx.textAlign = 'center';
                            ctx.textBaseline = 'middle';
                            ctx.fillText(text, destX + TILE_SIZE / 2, bubbleY + bubbleHeight / 2);
                        }
                    }
                }

                ctx.restore();
                animationFrameId = requestAnimationFrame(loop);
            };
            loop();
        }).catch(err => console.error("Asset load failed. Check your public/assets/ paths!", err));

    }, []);

    return (
        <div style={{ width: '100vw', height: '100vh', background: '#000', overflow: 'hidden' }}>
            {!isLoaded && <div style={{ color: 'white', position: 'absolute', top: 20, left: 20, fontFamily: 'monospace' }}>Loading Assets...</div>}
            <canvas ref={canvasRef} width={window.innerWidth} height={window.innerHeight} />
        </div>
    );
};
