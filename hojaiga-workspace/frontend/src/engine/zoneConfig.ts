import { CompoundRooms } from './layoutBuilder';

export interface ZoneConfig {
    id: string;
    globalX: number; // In flat grid tiles
    globalY: number; // In flat grid tiles
    width: number;
    height: number;
}

// Convert CompoundRooms to ZoneMapping for backward compatibility
export const ZoneMapping: Record<string, ZoneConfig> = {};

CompoundRooms.forEach(room => {
    // We map the layoutBuilder IDs to the names we want to use, or just use the layout IDs directly.
    ZoneMapping[room.id] = {
        id: room.id,
        globalX: room.x,
        globalY: room.y,
        width: room.w,
        height: room.h
    };
});
