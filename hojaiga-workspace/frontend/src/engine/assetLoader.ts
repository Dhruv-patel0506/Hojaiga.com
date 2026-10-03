import { rgbaToHex } from './colorUtils';
import {
  CHAR_FRAME_H,
  CHAR_FRAME_W,
  CHAR_FRAMES_PER_ROW,
  CHARACTER_DIRECTIONS,
  FLOOR_TILE_SIZE,
  WALL_BITMASK_COUNT,
  WALL_GRID_COLS,
  WALL_PIECE_HEIGHT,
  WALL_PIECE_WIDTH,
} from './constants';
import type { CharacterDirectionSprites, SpriteData } from './types';

interface DecodedPng {
  width: number;
  height: number;
  data: Uint8ClampedArray;
}

function getPixel(
  data: Uint8ClampedArray,
  width: number,
  x: number,
  y: number,
): [number, number, number, number] {
  const idx = (y * width + x) * 4;
  return [data[idx], data[idx + 1], data[idx + 2], data[idx + 3]];
}

function readSprite(
  png: DecodedPng,
  width: number,
  height: number,
  offsetX = 0,
  offsetY = 0,
): string[][] {
  const sprite: string[][] = [];
  for (let y = 0; y < height; y++) {
    const row: string[] = [];
    for (let x = 0; x < width; x++) {
      const [r, g, b, a] = getPixel(png.data, png.width, offsetX + x, offsetY + y);
      row.push(rgbaToHex(r, g, b, a));
    }
    sprite.push(row);
  }
  return sprite;
}

export async function decodePng(url: string): Promise<DecodedPng> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch PNG: ${url} (${res.status})`);
  }
  const blob = await res.blob();
  const bitmap = await createImageBitmap(blob);
  const canvas = document.createElement('canvas');
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  const ctx = canvas.getContext('2d');
  if (!ctx) {
    bitmap.close();
    throw new Error('Failed to create 2d canvas context for PNG decode');
  }
  ctx.drawImage(bitmap, 0, 0);
  bitmap.close();
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
  return { width: canvas.width, height: canvas.height, data: imageData.data };
}

export async function loadCharacterSprites(base: string, count = 6): Promise<CharacterDirectionSprites[]> {
  const sprites: CharacterDirectionSprites[] = [];
  for (let i = 0; i < count; i++) {
    try {
        const png = await decodePng(`${base}assets/characters/char_${i}.png`);
        const byDir: CharacterDirectionSprites = { down: [], up: [], right: [] };

        for (let dirIdx = 0; dirIdx < CHARACTER_DIRECTIONS.length; dirIdx++) {
        const dir = CHARACTER_DIRECTIONS[dirIdx];
        const rowOffsetY = dirIdx * CHAR_FRAME_H;
        const frames: string[][][] = [];
        for (let frame = 0; frame < CHAR_FRAMES_PER_ROW; frame++) {
            frames.push(readSprite(png, CHAR_FRAME_W, CHAR_FRAME_H, frame * CHAR_FRAME_W, rowOffsetY));
        }
        byDir[dir] = frames;
        }

        sprites.push(byDir);
    } catch (e) {
        console.warn(`Failed to load char_${i}.png`);
    }
  }
  return sprites;
}

export async function loadFloorSprites(base: string, count = 9): Promise<SpriteData[]> {
  const floors: SpriteData[] = [];
  for (let i = 0; i < count; i++) {
    try {
        const png = await decodePng(`${base}assets/floors/floor_${i}.png`);
        floors.push(readSprite(png, FLOOR_TILE_SIZE, FLOOR_TILE_SIZE));
    } catch (e) {
        console.warn(`Failed to load floor_${i}.png`);
    }
  }
  return floors;
}

export async function loadWallSprites(base: string, count = 1): Promise<SpriteData[][]> {
  const wallSets: SpriteData[][] = [];
  for (let i = 0; i < count; i++) {
    try {
        const png = await decodePng(`${base}assets/walls/wall_${i}.png`);
        const set: SpriteData[] = [];
        for (let mask = 0; mask < WALL_BITMASK_COUNT; mask++) {
        const ox = (mask % WALL_GRID_COLS) * WALL_PIECE_WIDTH;
        const oy = Math.floor(mask / WALL_GRID_COLS) * WALL_PIECE_HEIGHT;
        set.push(readSprite(png, WALL_PIECE_WIDTH, WALL_PIECE_HEIGHT, ox, oy));
        }
        wallSets.push(set);
    } catch (e) {
        console.warn(`Failed to load wall_${i}.png`);
    }
  }
  return wallSets;
}
