import type { OfficeState } from './officeState.js';
import { findPath } from '../layout/tileMap.js';
import { CharacterState } from '../types.js';

export class ChoreographyEngine {
  private static instance: ChoreographyEngine;
  private os: OfficeState | null = null;
  
  // Transition state
  public isTransitioning = false;
  public opacity = 1.0;
  
  private constructor() {}

  static getInstance(): ChoreographyEngine {
    if (!this.instance) {
      this.instance = new ChoreographyEngine();
      (window as any).__choreoEngine = this.instance;
    }
    return this.instance;
  }
  
  setOfficeState(os: OfficeState) {
    this.os = os;
  }

  handleEvent(event: string, data?: any) {
    console.log("Choreo Engine handling:", event, data);
    if (!this.os) return;
    
    switch (event) {
      case 'SystemBoot': this.runSequence1(); break;
      case 'Zone1Warp': this.runSequence2(); break;
      case 'TaskReceived': this.runSequence3(); break;
      case 'TaskCompiled': this.runSequence4(); break;
      case 'SecurityClearance': this.runSequence5(); break;
      case 'ExecutionStarted': this.runSequence6(); break;
      case 'TempAgentRequired': this.runSequence7(); break;
      case 'TaskCompleted': this.runSequence8(); break;
      case 'TaskError': this.runErrorSequence(); break;
    }
  }

  // Checkpoint 1: Boot Sequence & Guard
  private runSequence1() {
    console.log("Checkpoint 1: Boot Sequence");
    // User hero (1) walks North (0, -1)
    this.moveCharacterTo(1, 10, 15);
    // After password, guard (10) steps East (1, 0)
    setTimeout(() => {
        this.moveCharacterTo(10, 11, 14);
        if (this.os) {
            this.os.blockedTiles.delete("10,14"); // Unblock door
        }
    }, 2000);
  }

  // Checkpoint 2: Warp Transition
  private runSequence2() {
    console.log("Checkpoint 2: Entering Zone 1");
    this.triggerZoneTransition('zone1_reception');
  }

  // Checkpoint 3: UI Intake & Swap
  private runSequence3() {
    console.log("Checkpoint 3: Reception");
    this.moveCharacterTo(1, 4, 10);
    setTimeout(() => {
        // Receptionist (2) drops seatId and walks to back door
        this.moveCharacterTo(2, 18, 19);
    }, 2000);
  }

  // Checkpoint 4: CNS Handoff
  private runSequence4() {
    console.log("Checkpoint 4: CNS & Brain");
    this.triggerZoneTransition('zone2_core');
    setTimeout(() => {
        // Manager (4) walks to CEO (3)
        this.moveCharacterTo(4, 5, 6);
        setTimeout(() => {
            // Manager snaps back to seat
            this.moveCharacterTo(4, 15, 6);
            if (this.os) {
                const ch = this.os.characters.get(4);
                if (ch) ch.seatId = 'manager_chair';
            }
        }, 2000);
    }, 1500);
  }

  // Checkpoint 5: Security Gate
  private runSequence5() {
    console.log("Checkpoint 5: Security Gate");
    // Gate scan logic
    if (this.os) {
        this.os.blockedTiles.delete("10,10"); // Unblock gate
    }
    this.moveCharacterTo(4, 10, 10); // Move Manager through gate
  }

  // Checkpoint 6: Execution Floor
  private runSequence6() {
    console.log("Checkpoint 6: Execution Floor");
    this.triggerZoneTransition('zone3_execution');
    setTimeout(() => {
        // Workers walk to desks
        this.moveCharacterTo(5, 4, 11);
        this.moveCharacterTo(6, 9, 11);
    }, 1500);
  }

  // Checkpoint 7: Intern Spawning
  private runSequence7() {
    console.log("Checkpoint 7: Intern Pixel-Dust");
    this.triggerZoneTransition('zone4_agent');
    setTimeout(() => {
        // Pixel dust spawn for interns
        const interns = [7, 8];
        interns.forEach(id => {
           if (this.os) {
               const ch = this.os.characters.get(id);
               if (ch) {
                   ch.matrixEffect = 'spawn';
                   ch.matrixEffectTimer = 0;
               }
           }
        });
        // Move to shared table
        this.moveCharacterTo(7, 4, 6);
        this.moveCharacterTo(8, 9, 6);
    }, 1500);
  }

  // Checkpoint 8: Exit Loop
  private runSequence8() {
    console.log("Checkpoint 8: Return Loop & Exit");
    this.triggerZoneTransition('zone1_reception');
    setTimeout(() => {
        this.moveCharacterTo(1, 10, 19); // Exit
    }, 1500);
  }
  
  // Error & Recovery Injection
  private runErrorSequence() {
    console.log("Dynamic Error & Recovery Injection");
    if (!this.os) return;
    
    // Store original colors for a quick vertical path (e.g., column 5, rows 5 to 10)
    const pipelinePath = [
      { c: 5, r: 5 }, { c: 5, r: 6 }, { c: 5, r: 7 },
      { c: 5, r: 8 }, { c: 5, r: 9 }, { c: 5, r: 10 }
    ];
    
    if (!this.os.layout.tileColors) {
        this.os.layout.tileColors = Array(this.os.layout.cols * this.os.layout.rows).fill(null);
    }
    
    const originalColors = pipelinePath.map(p => this.os!.layout.tileColors![p.r * this.os!.layout.cols + p.c]);
    
    // Set pipeline to red
    pipelinePath.forEach(p => {
        const idx = p.r * this.os!.layout.cols + p.c;
        this.os!.layout.tileColors![idx] = { h: 0, s: 100, b: 50, c: 0 };
    });
    
    // Route agent (e.g., agent 4) backward along the pipeline
    this.moveCharacterTo(4, 5, 5);
    
    // Recover after 3 seconds
    setTimeout(() => {
        pipelinePath.forEach((p, i) => {
            const idx = p.r * this.os!.layout.cols + p.c;
            this.os!.layout.tileColors![idx] = originalColors[i];
        });
        console.log("Error Pipeline Cleared");
    }, 3000);
  }

  private targetZone: string | null = null;
  
  private triggerZoneTransition(targetZone: string) {
    console.log("Transitioning to", targetZone);
    this.targetZone = targetZone;
    this.isTransitioning = true;
  }
  
  update(dt: number) {
    if (this.isTransitioning) {
        this.opacity -= dt * 2.0; // 500ms fade out
        if (this.opacity <= 0) {
            this.opacity = 0;
            this.isTransitioning = false;
            console.log("Swapping layout to", this.targetZone);
            
            // Fetch and swap layout
            if (this.targetZone && this.os) {
              fetch(`/assets/${this.targetZone}.json`)
                .then(r => r.json())
                .then(json => {
                   if (this.os) {
                      this.os.rebuildFromLayout(json);
                   }
                })
                .catch(e => console.error("Failed to load zone:", e));
            }
            // Wait for next transition state to fade back in
        }
    } else if (this.opacity < 1.0) {
        // Wait until layout is loaded? For now just fade in if layout is set
        this.opacity += dt * 2.0; // 500ms fade in
        if (this.opacity > 1.0) this.opacity = 1.0;
    }
  }

  private moveCharacterTo(characterId: number, toCol: number, toRow: number) {
    if (!this.os) return;
    const ch = this.os.characters.get(characterId);
    if (!ch) return;

    ch.isChoreographed = true;
    ch.state = CharacterState.WALK;
    ch.seatId = null;
    const path = findPath(ch.tileCol, ch.tileRow, toCol, toRow, this.os.tileMap, this.os.blockedTiles);
    if (path.length > 0) {
      ch.path = path;
      ch.moveProgress = 0;
    } else {
      console.warn(`No path found for ${characterId} to ${toCol},${toRow}`);
    }
  }
}
