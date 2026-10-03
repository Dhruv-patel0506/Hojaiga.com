export type Direction = 'up' | 'down' | 'left' | 'right';
export type SpriteData = string[][];

export interface AssetIndex {
  floors: string[];
  walls: string[];
  characters: string[];
  defaultLayout: string | null;
}

export interface CatalogEntry {
  id: string;
  name: string;
  label: string;
  category: string;
  file: string;
  furniturePath: string;
  width: number;
  height: number;
  footprintW: number;
  footprintH: number;
  isDesk: boolean;
  canPlaceOnWalls: boolean;
  canPlaceOnSurfaces?: boolean;
  backgroundTiles?: number;
  groupId?: string;
  orientation?: string;
  state?: string;
  mirrorSide?: boolean;
  rotationScheme?: string;
  animationGroup?: string;
  frame?: number;
}

export interface CharacterDirectionSprites {
  down: SpriteData[];
  up: SpriteData[];
  right: SpriteData[];
}

export interface Entity {
    id: string;
    type: 'npc' | 'player' | 'prop' | 'interactive';
    spriteKey: string;
    x: number;
    y: number;
    isSolid: boolean;
    dialogue?: string;
}

export interface NPC extends Entity {
    type: 'npc' | 'player';
    isPlayer: boolean;
    organId: string;
    organName: string;
    jobTitle: string;
    
    // Pixel matching properties
    palette: string; // Used to colorize them if needed, or identify them
    state: 'idle' | 'walk' | 'type';
    dir: 0 | 1 | 2 | 3; // 0=down, 1=left, 2=right, 3=up
    facingDirection?: 'up' | 'down' | 'left' | 'right';
    isMoving?: boolean;
    animFrame?: number;
    animTimer?: number;
    taskText?: string;
    frame: number;
    frameTimer: number;
    tileCol: number;
    tileRow: number;
    moveProgress: number; // 0 to 1 for lerping between tiles

    isPaused: boolean;
    currentPath?: { x: number, y: number }[];
    targetX?: number;
    targetY?: number;
    hasActiveTask?: boolean;
    matrixEffect?: 'spawn' | 'despawn' | 'none';
}

export interface WSCommand {
    type: 'SPAWN_INTERN' | 'MOVE_AGENT' | 'UPDATE_STATUS' | 'DESPAWN_INTERN';
    payload: any;
}
