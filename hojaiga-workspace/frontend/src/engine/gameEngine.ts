import { NPC, WSCommand, Direction, SpriteData } from './types';
import { generateCompoundGrid, TILE, CompoundPortals } from './layoutBuilder';
import { isTileBlocked } from './layoutBuilder';
import { findPath } from './pathfinder';
import { loadCharacterSprites, loadFloorSprites, loadWallSprites } from './assetLoader';
import { getCachedSprite } from './spriteCache';
import { TILE_SIZE, WALL_PIECE_WIDTH, WALL_PIECE_HEIGHT, CHARACTER_DIRECTIONS } from './constants';
import { getColorizedFloorSprite, WALL_COLOR } from './colorize';

export class AssetManager {
    images: Record<string, HTMLImageElement> = {};

    loadSprite(key: string, src: string): Promise<void> {
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.src = src;
            img.onload = () => {
                this.images[key] = img;
                resolve();
            };
            img.onerror = () => {
                console.error(`Failed to load sprite: ${src}`);
                reject();
            };
        });
    }

    get(key: string): HTMLImageElement | undefined {
        return this.images[key];
    }
}

// The new flat grid top-down game engine

export class SpriteAssetManager {
    floors: SpriteData[] = [];
    walls: SpriteData[][] = []; // Array of wall sets
    characters: any[] = [];
    isLoaded = false;

    async loadAll(base: string) {
        if (this.isLoaded) return;
        this.floors = await loadFloorSprites(base, 9);
        this.walls = await loadWallSprites(base, 1);
        this.characters = await loadCharacterSprites(base, 6);
        this.isLoaded = true;
    }
}

export class Camera {
    panX = 0; panY = 0; zoom = 2.0; targetZoom = 2.0;

    update() { this.zoom += (this.targetZoom - this.zoom) * 0.1; }
    adjustZoom(delta: number) { this.targetZoom = Math.max(0.5, Math.min(this.targetZoom + delta, 4.0)); }

    follow(targetX: number, targetY: number, screenW: number, screenH: number) {
        const targetPanX = (targetX * TILE_SIZE) - (screenW / 2) / this.zoom;
        const targetPanY = (targetY * TILE_SIZE) - (screenH / 2) / this.zoom;
        this.panX += (targetPanX - this.panX) * 0.1;
        this.panY += (targetPanY - this.panY) * 0.1;
    }
}

export class GlobalMap {
    tiles: number[][];
    width: number;
    height: number;

    constructor() {
        this.tiles = generateCompoundGrid(60, 60);
        this.height = this.tiles.length;
        this.width = this.tiles[0].length;
    }

    render(ctx: CanvasRenderingContext2D, camera: Camera, assets: SpriteAssetManager, screenW: number, screenH: number) {
        if (!assets.isLoaded) return;

        const s = TILE_SIZE * camera.zoom;
        
        // Pixel-perfect center offset
        const offsetX = Math.floor(screenW / 2 - (this.width * s) / 2) - camera.panX * camera.zoom;
        const offsetY = Math.floor(screenH / 2 - (this.height * s) / 2) - camera.panY * camera.zoom;

        // Draw Floor Grid
        for (let r = 0; r < this.height; r++) {
            for (let c = 0; c < this.width; c++) {
                const tileVal = this.tiles[r][c];
                if (tileVal !== TILE.VOID && tileVal !== TILE.WALL) {
                    const floorSprite = assets.floors[0]; // Can vary by tileVal if you have multiple floor types
                    if (floorSprite) {
                        const colorized = getColorizedFloorSprite(floorSprite, '#70543E', '#8B4513'); // Wood
                        const cached = getCachedSprite(colorized, camera.zoom);
                        ctx.drawImage(cached, offsetX + c * s, offsetY + r * s);
                    }
                } else if (tileVal === TILE.WALL) {
                    // Draw base floor color for wall tiles
                    ctx.fillStyle = WALL_COLOR;
                    ctx.fillRect(offsetX + c * s, offsetY + r * s, s, s);
                }
            }
        }
    }
}

export class Engine {
    entities: NPC[] = [];
    commandQueue: any[] = [];
    onTaskComplete?: (npcId: string) => void;

    constructor(
        public globalMap: GlobalMap,
        public camera: Camera,
        public assets: SpriteAssetManager
    ) { }

    spawnAgent(payload: any) {
        const newAgent: NPC = {
            id: payload.id,
            type: 'npc',
            isPlayer: false,
            organId: payload.organId || 'unknown',
            organName: payload.organName || 'Unknown Agent',
            jobTitle: payload.jobTitle || 'Worker',
            spriteKey: 'char_ceo',
            palette: '',
            state: 'idle',
            dir: 0,
            frame: 0,
            frameTimer: 0,
            tileCol: 0,
            tileRow: 0,
            moveProgress: 0,
            isPaused: false,
            x: payload.x || 27,
            y: payload.y || 45,
            isSolid: false
        };
        this.entities.push(newAgent);
    }

    updateGlobalState() {
        this.camera.update();

        // 1. Process new commands from Python
        while (this.commandQueue.length > 0) {
            const cmd = this.commandQueue.shift();
            if (cmd.type === 'MOVE_AGENT') {
                const agent = this.entities.find(e => e.id === cmd.payload.id);
                if (agent) {
                    const start = { x: Math.round(agent.x), y: Math.round(agent.y) };
                    const end = { x: cmd.payload.targetX, y: cmd.payload.targetY };
                    agent.currentPath = findPath(start, end, (nx, ny) => isTileBlocked(nx, ny, this.globalMap.tiles));
                    
                    if (agent.currentPath.length > 0) {
                        agent.targetX = agent.currentPath[0].x;
                        agent.targetY = agent.currentPath[0].y;
                        agent.state = 'walk';
                        agent.taskText = undefined; // Clear task text when moving
                    }
                }
            } else if (cmd.type === 'START_TASK') {
                const agent = this.entities.find(e => e.id === cmd.payload.id);
                if (agent) {
                    agent.state = 'type';
                    agent.taskText = cmd.payload.text;
                    agent.facingDirection = 'up'; // Face the monitor
                }
            }
        }

        // 2. Move Agents and Check for Portals
        for (const entity of this.entities) {
            if (entity.isPaused || entity.targetX === undefined || entity.targetY === undefined) continue;

            const dx = entity.targetX - entity.x;
            const dy = entity.targetY - entity.y;

            if (Math.abs(dx) > 0.05 || Math.abs(dy) > 0.05) {
                entity.isMoving = true;
                
                // Determine the dominant direction of travel
                if (Math.abs(dx) > Math.abs(dy)) {
                    entity.facingDirection = dx > 0 ? 'right' : 'left';
                } else {
                    entity.facingDirection = dy > 0 ? 'down' : 'up';
                }

                // Tick the animation frame every 10 engine ticks (controls leg speed)
                entity.animTimer = (entity.animTimer || 0) + 1;
                if (entity.animTimer > 10) {
                    entity.animFrame = ((entity.animFrame || 0) + 1) % 4; 
                    entity.animTimer = 0;
                }

                // Simple direct movement logic (0.1 tile per frame for testing)
                if (entity.x < entity.targetX) entity.x += Math.min(0.1, entity.targetX - entity.x);
                if (entity.x > entity.targetX) entity.x -= Math.min(0.1, entity.x - entity.targetX);
                if (entity.y < entity.targetY) entity.y += Math.min(0.1, entity.targetY - entity.y);
                if (entity.y > entity.targetY) entity.y -= Math.min(0.1, entity.y - entity.targetY);
            } else {
                entity.x = entity.targetX;
                entity.y = entity.targetY;

                // We reached the current checkpoint, shift the path!
                if (entity.currentPath && entity.currentPath.length > 0) {
                    entity.currentPath.shift();
                    if (entity.currentPath.length > 0) {
                        entity.targetX = entity.currentPath[0].x;
                        entity.targetY = entity.currentPath[0].y;
                    } else {
                        entity.isMoving = false;
                        if (entity.state !== 'type') entity.animFrame = 0; 
                    }
                } else {
                    entity.isMoving = false;
                    if (entity.state !== 'type') entity.animFrame = 0; 
                }
            }

            // Animate typing if stationary and typing
            if (!entity.isMoving && entity.state === 'type') {
                entity.animTimer = (entity.animTimer || 0) + 1;
                if (entity.animTimer > 8) { // Slightly faster typing animation
                    entity.animFrame = ((entity.animFrame || 0) + 1) % 4;
                    entity.animTimer = 0;
                }
            }

            // Snap to grid to check for portals
            const gridX = Math.round(entity.x);
            const gridY = Math.round(entity.y);

            // 3. THE SUCTION DOORMAT MECHANIC
            const portal = CompoundPortals.find(p => p.x === gridX && p.y === gridY);
            if (portal) {
                console.log(`${entity.id} just stepped on a portal! Slurping...`);
                // Teleport the agent instantly to the target room
                entity.x = portal.targetX;
                entity.y = portal.targetY;
                entity.targetX = portal.targetX;
                entity.targetY = portal.targetY;
            }
        }
    }

    renderEntities(ctx: CanvasRenderingContext2D, camera: Camera, screenW: number, screenH: number) {
        if (!this.assets.isLoaded) return;

        const s = TILE_SIZE * camera.zoom;
        const offsetX = Math.floor(screenW / 2 - (this.globalMap.width * s) / 2) - camera.panX * camera.zoom;
        const offsetY = Math.floor(screenH / 2 - (this.globalMap.height * s) / 2) - camera.panY * camera.zoom;

        const allRenderables: any[] = [...this.entities];

        // Create wall instances for z-sorting
        for (let r = 0; r < this.globalMap.height; r++) {
            for (let c = 0; c < this.globalMap.width; c++) {
                if (this.globalMap.tiles[r][c] === TILE.WALL && this.assets.walls.length > 0) {
                    allRenderables.push({ isWall: true, col: c, row: r, y: r, variant: 0 }); // Just using variant 0 for simplicity
                }
            }
        }

        // Z-Sort by Y (row/y position)
        allRenderables.sort((a, b) => a.y - b.y);

        for (const r of allRenderables) {
            if (r.isWall) {
                const wallSprite = this.assets.walls[0][r.variant];
                if (wallSprite) {
                    const cached = getCachedSprite(wallSprite, camera.zoom);
                    // Walls are 16x32, they hang off the top of the 16x16 tile
                    const drawX = offsetX + r.col * s;
                    const drawY = offsetY + r.row * s - (WALL_PIECE_HEIGHT * camera.zoom) + s;
                    ctx.drawImage(cached, drawX, drawY);
                }
            } else {
                // It's a Character
                const entity = r as NPC;
                const charAssets = this.assets.characters[0]; // Just use char 0 for all for now
                if (charAssets) {
                    const dirMap = ['down', 'right', 'right', 'up'] as const;
                    const dirStr = dirMap[entity.dir || 0] as 'down' | 'right' | 'up';
                    const isLeft = entity.dir === 1;
                    const frames = charAssets[dirStr];
                    if (frames) {
                        const sprite = frames[entity.frame || 0];
                        if (sprite) {
                            const cached = getCachedSprite(sprite, camera.zoom);
                            // Characters are 16x32, anchor feet
                            const drawX = offsetX + entity.x * s;
                            const drawY = offsetY + entity.y * s - (32 * camera.zoom) + s;
                            
                            if (isLeft) {
                                ctx.save();
                                ctx.translate(drawX + (16 * camera.zoom) / 2, drawY);
                                ctx.scale(-1, 1);
                                ctx.drawImage(cached, -(16 * camera.zoom) / 2, 0);
                                ctx.restore();
                            } else {
                                ctx.drawImage(cached, drawX, drawY);
                            }

                            // Draw Task Bubble
                            if (entity.taskText) {
                                const padding = 6;
                                ctx.font = '12px "Segoe UI", Tahoma, Geneva, Verdana, sans-serif';
                                
                                // Truncate text if too long
                                let text = entity.taskText;
                                if (text.length > 20) text = text.substring(0, 18) + '...';
                                
                                const textMetrics = ctx.measureText(text);
                                const bubbleWidth = textMetrics.width + padding * 2;
                                const bubbleHeight = 20;
                                
                                // Position above the character's head
                                const bubbleX = drawX + (16 * camera.zoom) / 2 - bubbleWidth / 2;
                                const bubbleY = drawY - bubbleHeight - 8;

                                // Draw Bubble Background
                                ctx.fillStyle = 'rgba(255, 255, 255, 0.95)';
                                ctx.strokeStyle = 'rgba(0, 0, 0, 0.2)';
                                ctx.lineWidth = 1;
                                ctx.beginPath();
                                ctx.roundRect(bubbleX, bubbleY, bubbleWidth, bubbleHeight, 8);
                                ctx.fill();
                                ctx.stroke();

                                // Draw tail
                                ctx.beginPath();
                                ctx.moveTo(bubbleX + bubbleWidth / 2 - 4, bubbleY + bubbleHeight);
                                ctx.lineTo(bubbleX + bubbleWidth / 2, bubbleY + bubbleHeight + 4);
                                ctx.lineTo(bubbleX + bubbleWidth / 2 + 4, bubbleY + bubbleHeight);
                                ctx.fill();
                                ctx.stroke();

                                // Draw Text
                                ctx.fillStyle = '#333';
                                ctx.textAlign = 'center';
                                ctx.textBaseline = 'middle';
                                ctx.fillText(text, bubbleX + bubbleWidth / 2, bubbleY + bubbleHeight / 2);
                            }
                        }
                    }
                }
            }
        }
    }
}