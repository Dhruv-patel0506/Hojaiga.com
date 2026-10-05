import { ParsedOverlayCommand } from './CompanionManager';
import { DynamicAppScannerAndTeacher } from './DynamicAppScannerAndTeacher';

/**
 * 3D CAD / Blender Topology & PCB Hardware Schematic Inspector.
 *
 * Merge note: string-node graphs (auto-layouted into the claimed rect) and
 * the window title from a UIA scan for context only - no screen-coordinate
 * boxes, so no UIRECT needed here.
 */
export class HardwareSchematicTutor {
  public static isHardwareOrCADPrompt(prompt: string): boolean {
    return /\b(pcb|schematic|arduino|esp32|gpio|i2c|spi|voltage\s+rail|blender|solidworks|autocad|3d\s+model|topology|bevel|extrude|microcontroller)\b/i.test(prompt);
  }

  public static async buildHardwareOrCADOverlay(userPrompt: string): Promise<ParsedOverlayCommand[]> {
    const isCAD = /\b(blender|solidworks|autocad|3d\s+model|topology|mesh|bevel|extrude|uv\s+unwrap)\b/i.test(userPrompt);
    let windowTitle = 'Design Workspace';
    try {
      const snap = await DynamicAppScannerAndTeacher.scanActiveOrNamedApp();
      windowTitle = snap.windowTitle || windowTitle;
    } catch {
      /* scan is best-effort context */
    }

    if (isCAD) {
      return [
        { type: 'BOARD', label: `3D CAD & Topology Inspector • Window: ${windowTitle}` },
        {
          type: 'GRAPH',
          nodes: ['1. Base Blockout', '2. Quad Edge-Loops', '3. Bevel & Crease', '4. UV Seam Unwrap'],
          edges: [
            { from: '1. Base Blockout', to: '2. Quad Edge-Loops' },
            { from: '2. Quad Edge-Loops', to: '3. Bevel & Crease' },
            { from: '3. Bevel & Crease', to: '4. UV Seam Unwrap' },
          ],
          label: 'Clean Subdivision Modeling Pipeline',
          color: 'cyan',
          loop: true,
        },
        { type: 'WRITE', label: 'Topology Rule #1: Eliminate N-gons (>4 vertices) on curved surfaces to prevent shading pinching.', color: 'cyan' },
        { type: 'WRITE', label: 'Shortcut Guide: Press [Ctrl+A -> Scale] to normalize transforms before applying a Bevel or Subdivision modifier.', color: 'yellow' },
        { type: 'WRITE', label: 'Support Loops: Place holding edges around sharp hard-surface cutouts to lock specular highlights.', color: 'green' },
      ];
    }

    return [
      { type: 'BOARD', label: `PCB & Microcontroller Schematic Inspector • ${windowTitle}` },
      {
        type: 'GRAPH',
        nodes: ['3.3V Regulator + Cap', 'ESP32 / MCU Core', 'I2C Pull-Ups 4.7k', 'Sensor / Actuator Bus'],
        edges: [
          { from: '3.3V Regulator + Cap', to: 'ESP32 / MCU Core' },
          { from: 'ESP32 / MCU Core', to: 'I2C Pull-Ups 4.7k' },
          { from: 'I2C Pull-Ups 4.7k', to: 'Sensor / Actuator Bus' },
        ],
        label: 'Hardware Signal Integrity Path',
        color: 'orange',
        loop: true,
      },
      { type: 'WRITE', label: 'Power Rail Check: Place a 100nF ceramic decoupling capacitor within 2mm of every IC VCC pin.', color: 'cyan' },
      { type: 'WRITE', label: 'Bus Check [I2C]: Verify SDA (GPIO 21) and SCL (GPIO 22) have 4.7k pull-up resistors to 3.3V.', color: 'yellow' },
      { type: 'WRITE', label: 'Protection Check: Add a flyback diode across inductive relay/motor loads to clamp back-EMF spikes.', color: 'green' },
    ];
  }
}
