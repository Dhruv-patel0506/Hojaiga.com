# Shortcut verification: `webapp:excalidraw.com` (https://excalidraw.com)

18 shortcuts, 285.5 s. Verdicts: {'EFFECT_ONLY': 3, 'VERIFIED': 14, 'NO_EFFECT': 1}

VERIFIED = an effect beyond the control's noise AND the effect matches the name. EFFECT_ONLY = it does something, what is not confirmed. MISMATCH / NO_EFFECT = do NOT promote.

## Snap to objects - `alt+s` (shown as `option+s` by 4 authors): **EFFECT_ONLY**
- P0 nothing selected: tiers {'pixel': False, 'dom': False, 'semantic': True}, name check None, pixel 0.0000, dom -0/+0, scene ['state']
  ![before](snap_to_objects_0_before.png) ![control](snap_to_objects_0_control_after.png) ![after](snap_to_objects_0_after.png)

## Zen mode - `alt+z` (shown as `option+z` by 4 authors): **VERIFIED**
- P0 nothing selected: tiers {'pixel': True, 'dom': True, 'semantic': True}, name check True, pixel 0.0057, dom -22/+11, scene ['state']
  ![before](zen_mode_0_before.png) ![control](zen_mode_0_control_after.png) ![after](zen_mode_0_after.png)

## Select all - `ctrl+a` (shown as `cmd+a` by 4 authors): **VERIFIED**
- P0 nothing selected: tiers {'pixel': True, 'dom': True, 'semantic': False}, name check True, pixel 0.0220, dom -2/+55, scene []
  ![before](select_all_0_before.png) ![control](select_all_0_control_after.png) ![after](select_all_0_after.png)

## Canvas Shape properties - `alt+/` (shown as `option+/` by 3 authors): **EFFECT_ONLY**
- P0 nothing selected: tiers {'pixel': True, 'dom': True, 'semantic': False}, name check None, pixel 0.0046, dom -0/+3, scene []
  ![before](canvas_shape_properties_0_before.png) ![control](canvas_shape_properties_0_control_after.png) ![after](canvas_shape_properties_0_after.png)

## View mode - `alt+r` (shown as `option+r` by 3 authors): **VERIFIED**
- P0 nothing selected: tiers {'pixel': True, 'dom': True, 'semantic': False}, name check True, pixel 0.0079, dom -19/+0, scene []
  ![before](view_mode_0_before.png) ![control](view_mode_0_control_after.png) ![after](view_mode_0_after.png)

## Paste - `ctrl+v` (shown as `cmd+v` by 3 authors): **VERIFIED**
- needs `ctrl+c` first (its copy sibling)
- P0 nothing selected: tiers {'pixel': False, 'dom': False, 'semantic': False}, name check False, pixel 0.0000, dom -0/+0, scene []
- P1 one shape selected: tiers {'pixel': True, 'dom': False, 'semantic': True}, name check True, pixel 0.0094, dom -0/+0, scene ['count', 'order']
  ![before](paste_1_before.png) ![control](paste_1_control_after.png) ![after](paste_1_after.png)

## CopytoclipboardasPNG - `shift+alt+c` (shown as `shift+option+c` by 3 authors): **VERIFIED**
- P0 nothing selected: tiers {'pixel': True, 'dom': True, 'semantic': False}, name check True, pixel 0.0015, dom -0/+1, scene []
  ![before](copytoclipboardaspng_0_before.png) ![control](copytoclipboardaspng_0_control_after.png) ![after](copytoclipboardaspng_0_after.png)

## Bring forward - `ctrl+]` (shown as `cmd+]` by 2 authors): **VERIFIED**
- P0 nothing selected: tiers {'pixel': False, 'dom': False, 'semantic': False}, name check False, pixel 0.0000, dom -0/+0, scene []
- P1 one shape selected: tiers {'pixel': False, 'dom': False, 'semantic': True}, name check True, pixel 0.0014, dom -0/+0, scene ['order', 'version']
  ![before](bring_forward_1_before.png) ![control](bring_forward_1_control_after.png) ![after](bring_forward_1_after.png)

## Bring to front - `ctrl+alt+]` (shown as `cmd+option+]` by 2 authors): **VERIFIED**
- P0 nothing selected: tiers {'pixel': False, 'dom': False, 'semantic': False}, name check False, pixel 0.0000, dom -0/+0, scene []
- P1 one shape selected: tiers {'pixel': False, 'dom': False, 'semantic': True}, name check True, pixel 0.0014, dom -0/+0, scene ['order', 'version']
  ![before](bring_to_front_1_before.png) ![control](bring_to_front_1_control_after.png) ![after](bring_to_front_1_after.png)

## Copy styles - `ctrl+alt+c` (shown as `cmd+option+c` by 2 authors): **EFFECT_ONLY**
- P0 nothing selected: tiers {'pixel': False, 'dom': True, 'semantic': False}, name check None, pixel 0.0004, dom -0/+1, scene []
  ![before](copy_styles_0_before.png) ![control](copy_styles_0_control_after.png) ![after](copy_styles_0_after.png)

## Paste styles - `ctrl+alt+v` (shown as `cmd+option+v` by 2 authors): **VERIFIED**
- needs `ctrl+alt+c` first (its copy sibling)
- P0 nothing selected: tiers {'pixel': False, 'dom': False, 'semantic': False}, name check False, pixel 0.0000, dom -0/+0, scene []
- P1 one shape selected: tiers {'pixel': False, 'dom': False, 'semantic': True}, name check False, pixel 0.0000, dom -0/+0, scene ['version']
  ![before](paste_styles_1_before.png) ![control](paste_styles_1_control_after.png) ![after](paste_styles_1_after.png)
- P2 two shapes selected: tiers {'pixel': False, 'dom': False, 'semantic': True}, name check True, pixel 0.0006, dom -0/+0, scene ['style', 'version']
  ![before](paste_styles_2_before.png) ![control](paste_styles_2_control_after.png) ![after](paste_styles_2_after.png)

## Copy - `ctrl+c` (shown as `cmd+c` by 2 authors): **NO_EFFECT**
- P0 nothing selected: tiers {'pixel': False, 'dom': False, 'semantic': False}, name check True, pixel 0.0000, dom -0/+0, scene []
- P1 one shape selected: tiers {'pixel': False, 'dom': False, 'semantic': False}, name check True, pixel 0.0000, dom -0/+0, scene []
- P2 two shapes selected: tiers {'pixel': False, 'dom': False, 'semantic': False}, name check True, pixel 0.0000, dom -0/+0, scene []
- P3 three shapes selected: tiers {'pixel': False, 'dom': False, 'semantic': False}, name check True, pixel 0.0000, dom -0/+0, scene []
  ![before](copy_3_before.png) ![control](copy_3_control_after.png) ![after](copy_3_after.png)

## Duplicate - `ctrl+d` (shown as `cmd+d` by 2 authors): **VERIFIED**
- P0 nothing selected: tiers {'pixel': False, 'dom': False, 'semantic': False}, name check False, pixel 0.0000, dom -0/+0, scene []
- P1 one shape selected: tiers {'pixel': True, 'dom': False, 'semantic': True}, name check True, pixel 0.0049, dom -0/+0, scene ['count', 'order']
  ![before](duplicate_1_before.png) ![control](duplicate_1_control_after.png) ![after](duplicate_1_after.png)

## Group selection - `ctrl+g` (shown as `cmd+g` by 2 authors): **VERIFIED**
- P0 nothing selected: tiers {'pixel': False, 'dom': False, 'semantic': False}, name check False, pixel 0.0000, dom -0/+0, scene []
- P1 one shape selected: tiers {'pixel': False, 'dom': False, 'semantic': False}, name check False, pixel 0.0000, dom -0/+0, scene []
- P2 two shapes selected: tiers {'pixel': True, 'dom': True, 'semantic': True}, name check True, pixel 0.0028, dom -1/+1, scene ['version', 'groups']
  ![before](group_selection_2_before.png) ![control](group_selection_2_control_after.png) ![after](group_selection_2_after.png)

## Lock all - `ctrl+shift+l` (shown as `cmd+shift+l` by 2 authors): **VERIFIED**
- P0 nothing selected: tiers {'pixel': False, 'dom': False, 'semantic': False}, name check False, pixel 0.0000, dom -0/+0, scene []
- P1 one shape selected: tiers {'pixel': True, 'dom': True, 'semantic': True}, name check False, pixel 0.0188, dom -45/+1, scene ['version', 'locked']
  ![before](lock_all_1_before.png) ![control](lock_all_1_control_after.png) ![after](lock_all_1_after.png)
- P2 two shapes selected: tiers {'pixel': True, 'dom': True, 'semantic': True}, name check False, pixel 0.0201, dom -52/+1, scene ['version', 'locked', 'groups']
  ![before](lock_all_2_before.png) ![control](lock_all_2_control_after.png) ![after](lock_all_2_after.png)
- P3 three shapes selected: tiers {'pixel': True, 'dom': True, 'semantic': True}, name check True, pixel 0.0218, dom -54/+1, scene ['version', 'locked', 'groups']
  ![before](lock_all_3_before.png) ![control](lock_all_3_control_after.png) ![after](lock_all_3_after.png)

## Cut - `ctrl+x` (shown as `cmd+x` by 2 authors): **VERIFIED**
- P0 nothing selected: tiers {'pixel': False, 'dom': False, 'semantic': False}, name check False, pixel 0.0000, dom -0/+0, scene []
- P1 one shape selected: tiers {'pixel': True, 'dom': True, 'semantic': True}, name check True, pixel 0.0385, dom -45/+1, scene ['count', 'order']
  ![before](cut_1_before.png) ![control](cut_1_control_after.png) ![after](cut_1_after.png)

## Flip horizontal - `shift+h` (shown as `shift+h` by 2 authors): **VERIFIED**
- P0 nothing selected: tiers {'pixel': False, 'dom': False, 'semantic': False}, name check False, pixel 0.0000, dom -0/+0, scene []
- P1 one shape selected: tiers {'pixel': False, 'dom': False, 'semantic': False}, name check False, pixel 0.0000, dom -0/+0, scene []
- P2 two shapes selected: tiers {'pixel': True, 'dom': False, 'semantic': True}, name check True, pixel 0.0304, dom -0/+0, scene ['geom', 'version']
  ![before](flip_horizontal_2_before.png) ![control](flip_horizontal_2_control_after.png) ![after](flip_horizontal_2_after.png)

## Flip vertical - `shift+v` (shown as `shift+v` by 2 authors): **VERIFIED**
- P0 nothing selected: tiers {'pixel': False, 'dom': False, 'semantic': False}, name check False, pixel 0.0000, dom -0/+0, scene []
- P1 one shape selected: tiers {'pixel': False, 'dom': False, 'semantic': False}, name check False, pixel 0.0000, dom -0/+0, scene []
- P2 two shapes selected: tiers {'pixel': True, 'dom': False, 'semantic': True}, name check True, pixel 0.0308, dom -0/+0, scene ['geom', 'version']
  ![before](flip_vertical_2_before.png) ![control](flip_vertical_2_control_after.png) ![after](flip_vertical_2_after.png)
