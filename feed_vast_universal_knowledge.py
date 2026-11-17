r"""
D:\new_automation\feed_vast_universal_knowledge.py
==================================================
VAST EXPOSURE & UNIVERSAL KNOWLEDGE INGESTOR (5,000 TO 15,000+ UNIQUE RECORDS)
- Zero Duplication: SHA-256 content hashing guarantees 100% unique records across runs.
- Full Spectrum:
    1. All 35 Macro App/Web Archetypes x 45 Micro UI & Child-Window Patterns.
    2. Full 6,711+ App Ledger (app_guides_master.xlsx) + Local Markdown/JSON Guides.
    3. Balanced 7 Action Modalities (click, hotkey, type, drag, scroll, reveal_child, macro).
    4. 3D Physical/Ergonomic Proportion Knowledge + Complex Vector/Anatomy Drawing Schemas.
    5. Depth-3 Recursive Child-Window, Wizard & Popup Recovery Playbooks.
- Auto-Bridge & Dense Vectors: Updates SQLite FTS5, Dense BGE Embeddings (CPU),
  data\ai_root stores, and trimmed 70/30 Qwen SFT + DPO datasets.
"""

from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import json
import os
import random
import re
import shutil
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

# ==============================================================================
# PATHS & CONFIGURATION
# ==============================================================================
ROOT_DIR = Path(r"D:\new_automation")
DATA_DIR = ROOT_DIR / "data"
DISTILLED_DIR = DATA_DIR / "beam_distilled_master"
AI_ROOT_DIR = DATA_DIR / "ai_root"
RAG_DB_PATH = DATA_DIR / "hojaiga_master_rag.db"
AI_ROOT_RAG_DB = AI_ROOT_DIR / "rag_store.db"
VECTORS_OUT_PATH = DATA_DIR / "hojaiga_bge_vectors.npz"
EXCEL_GUIDES_PATH = ROOT_DIR / "app_guides_master.xlsx"
UI_TRAIN_JSONL = AI_ROOT_DIR / "harvest" / "training" / "ui_training_dataset.jsonl"

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
TEACHER_MODEL = "beam:cloud"

for d in [DATA_DIR, DISTILLED_DIR, AI_ROOT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ==============================================================================
# 1. FULL 35 MACRO ARCHETYPES (DESKTOP APPS, WEBSITES, WEB APPS)
# ==============================================================================
MACRO_ARCHETYPES_35: List[Tuple[str, str, str, List[str]]] = [
    ("ARCH_01_RICH_TEXT", "desktop_app", "MS Word, LibreOffice Writer, Google Docs",
     ["insert_formatted_table", "apply_heading_hierarchy", "find_and_replace_regex", "export_pdf_document", "page_setup_margins", "track_changes_review", "insert_header_footer", "mail_merge_wizard"]),
    ("ARCH_02_SPREADSHEET", "desktop_app", "MS Excel, Google Sheets, LibreOffice Calc",
     ["write_vlookup_formula", "build_pivot_table", "conditional_color_scale", "name_box_range_jump", "sort_multi_column", "insert_combo_chart", "freeze_header_panes", "data_validation_dropdown"]),
    ("ARCH_03_2D_CANVAS", "desktop_app", "MS Paint, Krita, GIMP, Photopea",
     ["select_brush_and_stroke", "trace_parametric_contour", "color_palette_mix_rgb", "layer_blend_multiply", "magic_wand_selection", "crop_to_aspect_ratio", "bezier_curve_path", "gradient_shading_pass"]),
    ("ARCH_04_3D_VIEWPORT", "desktop_app", "Blender, AutoCAD, FreeCAD, Maya",
     ["spawn_proportional_mesh", "extrude_region_along_normal", "bevel_hard_edges", "assign_pbr_shader_nodes", "set_camera_dof_lighting", "boolean_difference_cut", "array_modifier_grid", "render_cycles_output"]),
    ("ARCH_05_IDE_CODE", "desktop_app", "VS Code, Cursor, PyCharm, IntelliJ",
     ["quick_open_file_ctrl_p", "command_palette_action", "multi_cursor_refactor", "open_split_terminal", "set_conditional_breakpoint", "git_commit_staged", "run_pytest_suite", "search_workspace_regex"]),
    ("ARCH_06_CHAT_MESSAGING", "web_app", "WhatsApp, Discord, Slack, MS Teams",
     ["disambiguate_search_vs_composer", "upload_file_attachment", "create_thread_reply", "mention_user_autocomplete", "jump_to_unread_channel", "pin_important_message", "mute_server_notifications", "voice_screen_share"]),
    ("ARCH_07_EMAIL_CLIENT", "web_app", "Outlook, Gmail, Thunderbird, ProtonMail",
     ["compose_structured_email", "add_cc_bcc_chips", "create_filter_rule_modal", "search_by_sender_date", "attach_from_local_dialog", "schedule_future_send", "flag_follow_up", "manage_signature_settings"]),
    ("ARCH_08_FILE_EXPLORER", "desktop_app", "Windows Explorer, Total Commander, 7-Zip",
     ["focus_address_bar_ctrl_l", "batch_rename_files", "filter_by_extension_size", "extract_nested_archive", "open_properties_security_tab", "create_symbolic_folder", "sort_by_date_modified", "copy_unc_network_path"]),
    ("ARCH_09_BROWSER_NAV", "website", "Chrome, Edge, Brave, Documentation Portals",
     ["omnibox_direct_navigation", "switch_search_tabs_images_videos", "dismiss_cookie_gdpr_banner", "extract_table_pagination", "open_devtools_inspector", "bookmark_folder_save", "manage_site_permissions", "download_file_save_as"]),
    ("ARCH_10_SETTINGS_TREE", "desktop_app", "Windows Settings, Control Panel, macOS Prefs",
     ["navigate_master_detail_category", "toggle_boolean_feature_switch", "open_advanced_sub_dialog", "configure_env_variables", "adjust_display_dpi_scale", "select_default_audio_device", "manage_startup_apps", "network_proxy_setup"]),
    ("ARCH_11_MEDIA_STUDIO", "desktop_app", "OBS Studio, DaVinci Resolve, Premiere Pro",
     ["add_window_capture_source", "configure_encoder_bitrate_modal", "split_timeline_clip_playhead", "keyframe_audio_ducking", "apply_lut_color_grade", "scene_transition_cut", "remap_hotkey_bindings", "render_queue_export"]),
    ("ARCH_12_KANBAN_BOARD", "web_app", "Trello, Jira, Linear, GitHub Projects",
     ["drag_card_across_columns", "open_card_detail_modal", "assign_priority_and_label", "add_checklist_subtasks", "filter_board_by_assignee", "create_sprint_milestone", "link_blocking_issue", "archive_done_cards"]),
    ("ARCH_13_DATA_DASHBOARD", "web_app", "PowerBI, Tableau, Grafana, Metabase",
     ["set_custom_date_range_picker", "cross_filter_chart_widget", "configure_sql_query_panel", "export_filtered_csv_data", "create_threshold_alert", "drill_down_hierarchy", "edit_dashboard_layout_grid", "share_snapshot_link"]),
    ("ARCH_14_NODE_GRAPH", "web_app", "ComfyUI, n8n, Zapier, Blender Geometry Nodes",
     ["search_and_spawn_node", "drag_wire_output_to_input", "edit_node_float_parameter", "bypass_selected_node_group", "queue_workflow_execution", "inspect_node_preview_output", "save_workflow_json", "reroute_wire_junction"]),
    ("ARCH_15_ECOMMERCE_PORTAL", "website", "Amazon, Shopify Admin, eBay, Stripe Dashboard",
     ["apply_multi_facet_filters", "select_size_color_variant", "sort_by_verified_reviews", "update_cart_line_quantity", "navigate_multi_step_checkout", "create_discount_rule", "inspect_order_fulfillment", "update_inventory_stock"]),
    ("ARCH_16_FORM_WIZARD", "website", "Enterprise Onboarding, Tax Portals, Typeform",
     ["complete_multi_page_stepper", "select_searchable_combobox", "pick_calendar_date_widget", "upload_verification_doc", "handle_inline_field_error", "toggle_conditional_section", "review_summary_table", "submit_with_confirmation"]),
    ("ARCH_17_PDF_VIEWER", "desktop_app", "Adobe Acrobat, Foxit, Okular, Edge PDF",
     ["jump_to_bookmark_outline", "highlight_and_annotate_text", "fill_interactive_pdf_fields", "place_digital_signature", "extract_page_range", "search_document_occurrences", "rotate_view_counterclockwise", "ocr_scanned_page"]),
    ("ARCH_18_AUDIO_SEQUENCER", "desktop_app", "FL Studio, Ableton Live, Audacity, Reaper",
     ["program_channel_rack_beat", "draw_midi_notes_piano_roll", "apply_compressor_eq_plugin", "automate_volume_envelope", "trim_silence_from_waveform", "route_track_to_master_bus", "set_loop_region_markers", "bounce_stems_to_wav"]),
    ("ARCH_19_MAP_NAVIGATOR", "web_app", "Google Maps, QGIS, ArcGIS, OpenStreetMap",
     ["search_coordinates_or_poi", "calculate_multi_stop_route", "toggle_terrain_satellite_layer", "draw_polygon_geofence", "measure_area_perimeter", "inspect_feature_attribute_table", "export_geojson_layer", "zoom_to_bounding_box"]),
    ("ARCH_20_AUTH_GATEWAY", "website", "Okta SSO, OAuth2 Consent, Windows UAC, 2FA",
     ["enter_username_next_step", "reveal_and_verify_password", "select_mfa_method_totp", "handle_remember_device_prompt", "approve_oauth_scope_modal", "recover_locked_session", "switch_tenant_account", "audit_active_sessions"]),
    ("ARCH_21_TERMINAL_SHELL", "desktop_app", "Windows Terminal, PowerShell, Bash, Putty",
     ["open_new_profile_tab", "split_pane_horizontally", "search_command_history_ctrl_r", "copy_selection_output", "run_piped_cli_pipeline", "inspect_exit_code_status", "set_working_directory", "kill_hung_process"]),
    ("ARCH_22_DATABASE_ADMIN", "desktop_app", "DBeaver, pgAdmin, SQLiteStudio, MongoDB Compass",
     ["expand_schema_tree_tables", "execute_sql_query_editor", "filter_result_grid_where", "inspect_foreign_key_erd", "export_table_to_json_csv", "create_index_dialog", "rollback_transaction_guard", "connection_settings_test"]),
    ("ARCH_23_VECTOR_DESIGN", "web_app", "Figma, Adobe Illustrator, Inkscape, Canva",
     ["create_artboard_frame", "boolean_union_shapes", "apply_auto_layout_padding", "edit_svg_anchor_handles", "create_reusable_component", "align_distribute_selection", "export_multi_scale_svg_png", "inspect_css_properties"]),
    ("ARCH_24_PRESENTATION_DECK", "desktop_app", "MS PowerPoint, Google Slides, Keynote, Pitch",
     ["insert_master_layout_slide", "align_visual_cards_grid", "add_entrance_animation_timeline", "embed_chart_from_sheet", "edit_speaker_notes_pane", "apply_global_theme_palette", "rehearse_slideshow_view", "export_handout_pdf"]),
    ("ARCH_25_CRM_ERP_ENTERPRISE", "web_app", "Salesforce, HubSpot, SAP GUI, Odoo, ServiceNow",
     ["create_lead_contact_record", "advance_deal_pipeline_stage", "log_customer_activity_note", "build_custom_cohort_report", "trigger_approval_workflow", "bulk_update_selected_rows", "link_ticket_to_account", "export_audit_log"]),
    ("ARCH_26_CLOUD_DEVOPS", "web_app", "AWS Console, Azure Portal, Cloudflare, Docker Desktop",
     ["filter_running_instances", "inspect_container_live_logs", "edit_security_group_inbound", "create_dns_record_modal", "trigger_ci_cd_deployment", "rotate_api_secret_key", "monitor_cpu_memory_graph", "configure_auto_scaling"]),
    ("ARCH_27_SCIENTIFIC_BIO", "desktop_app", "ImageJ/Fiji, PyMOL, MATLAB, Anatomy Tutor",
     ["render_human_nervous_system_svg", "draw_4_chamber_heart_flow", "measure_cell_roi_intensity", "plot_3d_molecular_surface", "calibrate_scale_bar_microns", "run_threshold_segmentation", "animate_neuron_action_potential", "export_publication_figure"]),
    ("ARCH_28_FINANCE_TRADING", "web_app", "TradingView, QuickBooks, Tally Prime, Stripe",
     ["reconcile_invoice_ledger", "place_limit_order_ticket", "add_moving_average_indicator", "generate_profit_loss_sheet", "switch_candlestick_timeframe", "create_recurring_billing", "audit_tax_summary_modal", "export_journal_entries"]),
    ("ARCH_29_LMS_EDUCATION", "web_app", "Coursera, Canvas LMS, Anki, Khan Academy, HoJaiga Tutor",
     ["launch_interactive_lightboard", "spotlight_ui_control_pathway", "narrate_step_by_step_lesson", "grade_quiz_rubric_modal", "create_spaced_repetition_card", "annotate_math_geometry_proof", "track_curriculum_mastery", "verify_student_try_it_click"]),
    ("ARCH_30_SYSTEM_INSTALLER", "desktop_app", "WinGet, NSIS Setup Wizard, MSI Installer, Rufus",
     ["advance_license_agreement_step", "select_custom_install_components", "change_destination_folder_path", "uncheck_bundled_bloatware", "verify_disk_space_requirement", "complete_install_finish_wizard", "repair_existing_installation", "silent_cli_install_fallback"]),
    ("ARCH_31_API_NETWORK_TOOL", "desktop_app", "Postman, Insomnia, Wireshark, Fiddler",
     ["configure_http_post_headers", "edit_json_request_body", "inspect_response_status_tree", "set_bearer_auth_token", "filter_packet_capture_stream", "save_request_to_collection", "switch_environment_variables", "export_har_trace"]),
    ("ARCH_32_VIRTUALIZATION", "desktop_app", "VMware, VirtualBox, Hyper-V, WSL2 Manager",
     [" take_vm_state_snapshot", "configure_virtual_ram_cpu", "mount_iso_optical_drive", "bridge_network_adapter_modal", "restore_previous_snapshot", "shared_folder_path_mapping", "start_headless_instance", "export_ova_appliance"]),
    ("ARCH_33_CAD_ENGINEERING", "desktop_app", "AutoCAD, SolidWorks, Fusion 360, KiCad",
     ["parametric_sketch_dimension", "extrude_boss_base_feature", "apply_fillet_chamfer_edge", "mate_assembly_concentric", "route_pcb_copper_trace", "layer_freeze_lock_toggle", "measure_clearance_tolerance", "plot_dwg_to_pdf_sheet"]),
    ("ARCH_34_NOTE_KNOWLEDGE_BASE", "desktop_app", "Notion, Obsidian, OneNote, Logseq",
     ["trigger_slash_block_command", "link_bidirectional_wiki_page", "filter_inline_database_view", "toggle_collapsible_heading", "embed_code_snippet_block", "inspect_backlink_graph_view", "export_markdown_vault", "apply_page_template"]),
    ("ARCH_35_SECURITY_ANTIVIRUS", "desktop_app", "Windows Defender, Bitwarden, KeePassXC, Firewall",
     ["unlock_vault_master_key", "copy_totp_auto_clear", "add_custom_exclusion_path", "inspect_quarantined_threats", "create_outbound_port_rule", "generate_high_entropy_password", "run_targeted_folder_scan", "audit_security_health_report"]),
]

# ==============================================================================
# 2. ALL 45 MICRO UI & HIDDEN CHILD-WINDOW PATTERNS
# ==============================================================================
MICRO_UI_PATTERNS_45: List[Tuple[str, str, str]] = [
    ("MICRO_01_RIBBON_TAB", "Ribbon Tab Switcher", "Click top tab -> wait 80ms -> re-scan newly swapped ribbon strip"),
    ("MICRO_02_SPLIT_BUTTON", "Split Button (Direct vs Chevron)", "Left half triggers default; right chevron opens dropdown gallery"),
    ("MICRO_03_OVERFLOW_CHEVRON", "Collapsed Ribbon Overflow (>>)", "Narrow window hides buttons under '>>' flyout; expand first"),
    ("MICRO_04_CONTEXTUAL_TAB", "Selection-Dependent Contextual Tab", "Select object/table/image on canvas first to reveal Format tab"),
    ("MICRO_05_MODAL_DIALOG_OPENER", "Ellipsis/Plus Dialog Opener ('...', '+')", "Spawns child modal window; requires active window switch"),
    ("MICRO_06_MASTER_DETAIL_SPLIT", "Master-Detail Left List / Right Pane", "Click left category item -> inspect updated right-hand controls"),
    ("MICRO_07_MULTI_PAGE_WIZARD", "Multi-Page Stepper ('Next >' / 'Finish')", "Fill required fields -> click Next -> repeat to depth 4 -> Finish"),
    ("MICRO_08_DEPTH3_SUB_DIALOG", "Nested Sub-Child Dialog (Depth 3)", "Parent -> Properties -> Advanced -> Sub-Modal -> OK/Cancel"),
    ("MICRO_09_WIN32_FILE_PICKER", "Common File Dialog (#32770 Open/Save)", "Focus Filename combo or Ctrl+L path bar -> type full path -> Enter"),
    ("MICRO_10_UNLABELLED_ICON_STRIP", "16x16 Unlabelled Toolbar Icon Strip", "Use Set-of-Marks high-res strip crop + pHash icon memory"),
    ("MICRO_11_CASCADING_CONTEXT_MENU", "Right-Click Cascading Flyout Menu", "Right-click target -> hover parent item -> click child flyout item"),
    ("MICRO_12_HAMBURGER_DRAWER", "Off-Canvas Hamburger Navigation Drawer", "Click 3-bar icon -> wait 150ms for slide-in -> click nav link"),
    ("MICRO_13_ACCORDION_INSPECTOR", "Collapsible Inspector Accordion", "Check aria-expanded/ExpandCollapseState; expand if collapsed"),
    ("MICRO_14_TREE_OUTLINER", "Hierarchical Scene/Folder Tree", "Click disclosure triangle (>) to reveal nested child nodes"),
    ("MICRO_15_COMMAND_PALETTE", "Searchable Command Palette (Ctrl+Shift+P / F3)", "Open palette -> type command name -> wait 100ms -> press Enter"),
    ("MICRO_16_AUTOCOMPLETE_COMBO", "Async Autocomplete Combobox", "Type query -> wait 300ms for popup list -> ArrowDown + Enter"),
    ("MICRO_17_SEARCH_VS_COMPOSER", "Dual Textbox Disambiguation Trap", "Distinguish top/left Search Filter from bottom Message Composer"),
    ("MICRO_18_STATEFUL_2D_CANVAS", "Tool-Modal 2D Drawing Surface", "Click tool icon once -> verify active state -> drag on canvas"),
    ("MICRO_19_3D_GIZMO_VIEWPORT", "3D Viewport + Transform Axis / Hotkey", "Select object -> use exact numerical panel or G/R/S + Axis + value"),
    ("MICRO_20_TIMELINE_SCRUBBER", "Keyframe Timeline & Playhead Track", "Move playhead to timestamp -> arm track -> insert/split keyframe"),
    ("MICRO_21_NODE_SOCKET_WIRE", "Node Graph Input/Output Socket Drag", "Mouse down on output socket -> drag to compatible input socket"),
    ("MICRO_22_COOKIE_MODAL_BLOCKER", "Cookie/GDPR/Promo Overlay Blocker", "Detect z-index modal blocker -> click Reject/Accept/Close first"),
    ("MICRO_23_VIRTUALIZED_SCROLL_LIST", "Lazy-Loaded Infinite/Virtualized List", "Target off-screen -> scroll container incrementally until visible"),
    ("MICRO_24_TABBED_DOCK_PANEL", "Multi-Tab Dockable Workspace Panel", "Click tab header to bring hidden panel controls into UIA tree"),
    ("MICRO_25_COLOR_PICKER_POPUP", "Custom Color Wheel / Hex Input Dialog", "Open color swatch -> focus Hex/RGB numeric fields -> type exact value"),
    ("MICRO_26_INLINE_CELL_EDITOR", "Double-Click Inline Grid/Cell Editor", "Double-click or press F2 on cell -> type value -> press Enter"),
    ("MICRO_27_BREADCRUMB_PATH_BAR", "Interactive Breadcrumb / Address Bar", "Click empty right area or press Ctrl+L to turn breadcrumbs into textbox"),
    ("MICRO_28_DRAG_DROP_UPLOAD_ZONE", "Dropzone / Hidden File Input Trigger", "Click 'Browse' trigger inside dropzone -> handle OS file dialog"),
    ("MICRO_29_HOVER_ACTION_ROW", "Hover-Only Table Row Action Buttons", "Move cursor over row first to reveal hidden Edit/Delete icons"),
    ("MICRO_30_UNSAVED_CHANGES_GUARD", "Dirty State 'Save Changes?' Guard Modal", "Intercept closing popup -> choose Save / Don't Save / Cancel safely"),
    ("MICRO_31_SLIDER_SCRUB_NUMERICAL", "Slider + Paired Numerical Spinbox", "Prefer typing exact number into paired spinbox over imprecise drag"),
    ("MICRO_32_CHIP_TAG_INPUT", "Multi-Value Recipient/Tag Chip Box", "Type item -> press Enter/Tab/Comma to convert text into chip"),
    ("MICRO_33_DATE_RANGE_CALENDAR", "Dual-Month Calendar Popover", "Prefer direct ISO date typing if editable; else navigate Month/Year header"),
    ("MICRO_34_SPLIT_PANE_RESIZER", "Collapsed Pane Divider Bar", "Detect 0-width/narrow pane -> drag splitter or click Expand button"),
    ("MICRO_35_TOAST_UNDO_BANNER", "Transient Toast Notification with Undo", "Verify status message in toast region within 3s window"),
    ("MICRO_36_IFRAME_EMBEDDED_WIDGET", "Cross-Origin Embedded Iframe Surface", "Switch DOM frame context or fallback to UIA/Vision coordinates"),
    ("MICRO_37_FLOATING_MINI_TOOLBAR", "Selection-Triggered Floating Mini-Bar", "Appears near cursor after text selection; use stable Ribbon/Hotkey instead"),
    ("MICRO_38_STATUS_BAR_ZOOM_MODE", "Bottom Status Bar Mode/Zoom Controls", "Locate right-aligned zoom percentage or view-mode icons in status strip"),
    ("MICRO_39_PAGINATION_STEPPER", "Table Page Size & Next/Prev Bar", "Scroll to table footer -> select page size or click Next Page '>'"),
    ("MICRO_40_PERMISSION_PROMPT", "Browser/OS Native Permission Popup", "Handle native Allow/Block notification or microphone bar"),
    ("MICRO_41_MULTI_SELECT_MODIFIER", "Ctrl/Shift Range Selection List", "Click anchor item -> hold Shift/Ctrl -> click end item"),
    ("MICRO_42_LOCKED_LAYER_GUARD", "Disabled/Locked Item in Outliner", "Check lock/eye icon state in layer row; unlock before editing"),
    ("MICRO_43_FORMULA_BAR_COMMIT", "Spreadsheet Formula Bar + Enter/Esc", "Click fx bar -> enter expression -> press Enter (never click random cell)"),
    ("MICRO_44_FIND_REPLACE_PALETTE", "Non-Modal Find & Replace Bar (Ctrl+F/H)", "Press Ctrl+H -> fill Find and Replace boxes -> click Replace All"),
    ("MICRO_45_SANDBOX_SAFETY_GATE", "Irreversible Action Confirmation Gate", "Detect Send/Delete/Pay/Publish -> halt for human confirmation"),
]

# ==============================================================================
# 3. SPECIALIZED DOMAIN KNOWLEDGE: 3D PROPORTIONS & COMPLEX ANATOMY/DIAGRAMS
# ==============================================================================
SPECIALIZED_PRO_KNOWLEDGE: List[Dict[str, Any]] = [
    {
        "arch_id": "ARCH_04_3D_VIEWPORT",
        "domain": "desktop_app",
        "app": "Blender",
        "goal": "Build proportional 3D Dining Chair with ergonomic real-world dimensions",
        "action_kind": "script",
        "steps": [
            {"step": 1, "action": "script", "target": "Blender Python API (bpy)", "hotkey": None,
             "expected_delta": "Seat cube spawned at z=0.45m (0.48m x 0.48m x 0.04m); 4 legs at corners (0.04m x 0.04m x 0.45m); backrest at rear edge y=-0.22m, z=0.47m..0.92m"},
            {"step": 2, "action": "hotkey", "target": "3D Viewport", "hotkey": "Z",
             "expected_delta": "Viewport shading switched to Material Preview / Rendered"},
            {"step": 3, "action": "script", "target": "Proportion & Contact Verifier", "hotkey": None,
             "expected_delta": "Verified: all parts connected=True, floating=[], total height=0.92m, aspect ratio valid"}
        ],
        "trap_guard": "NEVER use sphere primitives for flat shelves/seats and NEVER place backrest at seat center (0,0); anchor backrest at y = -depth/2.",
    },
    {
        "arch_id": "ARCH_04_3D_VIEWPORT",
        "domain": "desktop_app",
        "app": "Blender",
        "goal": "Build proportional 5-Tier Bookshelf with rectangular plank geometry",
        "action_kind": "script",
        "steps": [
            {"step": 1, "action": "script", "target": "Blender Python API (bpy)", "hotkey": None,
             "expected_delta": "2 vertical side panels (0.03m x 0.30m x 1.80m at x=+-0.40m) + 5 horizontal cube planks (0.80m x 0.30m x 0.025m spaced every 0.38m)"},
            {"step": 2, "action": "script", "target": "Render & Critique Loop", "hotkey": "F12",
             "expected_delta": "Multi-angle orthographic render verified against furniture proportion rubric (>=92/100)"}
        ],
        "trap_guard": "Always use bpy.ops.mesh.primitive_cube_add for wooden planks, never scaled UV spheres (which create flattened ovals).",
    },
    {
        "arch_id": "ARCH_27_SCIENTIFIC_BIO",
        "domain": "desktop_app",
        "app": "HoJaiga Lightboard Tutor / MS Paint",
        "goal": "Draw proportional Human Nervous System Diagram with Brain, Spinal Cord, and Peripheral Nerves",
        "action_kind": "drag",
        "steps": [
            {"step": 1, "action": "script", "target": "Parametric SVG/Bezier Anatomy Engine", "hotkey": None,
             "expected_delta": "Proportional human silhouette rendered with Cranium, Gyri Brain folds, Cerebellum, Cervical-to-Lumbar Spinal Cord, and Brachial/Sciatic nerve branches"},
            {"step": 2, "action": "drag", "target": "Canvas Safe Box [0.0..1.0]", "hotkey": None,
             "expected_delta": "Multi-layer color shading and callout labels placed without bounding-box collision"}
        ],
        "trap_guard": "Never approximate human anatomy with 4-point [POLYGON] diamonds or crude [BOX] rectangles; always project normalized Bezier/SVG anatomical contours.",
    },
]

# ==============================================================================
# 4. BALANCED 7-MODALITY GENERATOR + OLLAMA TEACHER DISTILLATION
# ==============================================================================
ACTION_MODALITIES = ["click", "hotkey", "type", "drag", "scroll", "reveal_child_window", "script"]

MODALITY_TEMPLATES: Dict[str, Dict[str, str]] = {
    "click": {
        "action": "click",
        "hotkey": "",
        "delta": "Target control activated and UI state transitioned",
        "reason": "Direct semantic match on primary control; avoids adjacent lookalike filter/cancel controls"
    },
    "hotkey": {
        "action": "hotkey",
        "hotkey": "Ctrl+Shift+P",
        "delta": "Command/shortcut executed in 5ms bypassing nested ribbon traversal",
        "reason": "Verified fast-path keyboard chord is faster and immune to collapsed ribbon layout"
    },
    "type": {
        "action": "type",
        "hotkey": "Enter",
        "delta": "Text value committed into focused input field and submitted",
        "reason": "Targets active input field after verifying focus, avoiding sidebar search trap"
    },
    "drag": {
        "action": "drag",
        "hotkey": "",
        "delta": "Parameterized normalized vector path [0.0..1.0] projected onto live canvas bounding box",
        "reason": "Canvas/viewport interaction requires continuous mouse-down -> move -> mouse-up stroke"
    },
    "scroll": {
        "action": "scroll",
        "hotkey": "PageDown",
        "delta": "Viewport scrolled to bring off-screen virtualized target control into visible DOM/UIA tree",
        "reason": "Target row is below fold in virtualized container; scroll required before clicking"
    },
    "reveal_child_window": {
        "action": "click",
        "hotkey": "",
        "delta": "Child modal/dialog window spawned -> Master-Detail left tab selected -> target control revealed",
        "reason": "Target setting is hidden inside a depth-2/3 child dialog; must click opener button first"
    },
    "script": {
        "action": "script",
        "hotkey": "",
        "delta": "Programmatic macro/API (bpy / COM / Playwright / SVG) executed and verified on disk",
        "reason": "Complex multi-part creation achieves higher precision via programmatic macro injection"
    },
}

DEFAULT_SHORTCUT_MAP = {
    "find": "Ctrl+F", "replace": "Ctrl+H", "save": "Ctrl+S", "open": "Ctrl+O",
    "new": "Ctrl+N", "print": "Ctrl+P", "address": "Ctrl+L", "command": "Ctrl+Shift+P",
    "terminal": "Ctrl+`", "undo": "Ctrl+Z", "redo": "Ctrl+Y", "copy": "Ctrl+C",
    "paste": "Ctrl+V", "cut": "Ctrl+X", "select_all": "Ctrl+A", "zoom": "Ctrl+Plus",
    "render": "F12", "rename": "F2", "refresh": "F5", "close": "Alt+F4",
}


def pick_realistic_hotkey(task_slug: str) -> str:
    low = task_slug.lower()
    for k, v in DEFAULT_SHORTCUT_MAP.items():
        if k in low:
            return v
    return "Ctrl+Shift+P"


def synthesize_rich_record(
    arch_id: str,
    domain: str,
    app_name: str,
    task_slug: str,
    micro_id: str,
    micro_title: str,
    micro_rule: str,
    modality: str,
) -> Dict[str, Any]:
    """Builds a grounded, multi-modal Causal RAG + SFT + DPO record."""
    clean_task = task_slug.replace("_", " ").strip().title()
    mod_info = MODALITY_TEMPLATES[modality]
    hk = pick_realistic_hotkey(task_slug) if modality == "hotkey" else mod_info["hotkey"]

    if modality == "reveal_child_window":
        steps = [
            {"step": 1, "action": "click", "target": f"{clean_task} Opener ('...' / '+')", "hotkey": None,
             "expected_delta": f"Child modal dialog for {clean_task} opened (HWND/DOM modal detected)"},
            {"step": 2, "action": "click", "target": f"{micro_title} Category Tab", "hotkey": None,
             "expected_delta": "Right-hand detail pane updated with target controls"},
            {"step": 3, "action": "click", "target": f"Apply / Confirm {clean_task}", "hotkey": "Enter",
             "expected_delta": f"{clean_task} committed and child dialog closed cleanly"},
        ]
        chosen_target = f"{clean_task} Opener ('...' / '+')"
        trap_target = f"Disabled {clean_task} Label (Unrevealed)"
    elif modality == "drag":
        steps = [
            {"step": 1, "action": "click", "target": f"{clean_task} Tool Icon", "hotkey": None,
             "expected_delta": "Tool state switched to active"},
            {"step": 2, "action": "drag", "target": f"Canvas Safe Box ({clean_task} Parametric Path)", "hotkey": None,
             "expected_delta": mod_info["delta"]},
        ]
        chosen_target = f"Canvas Safe Box ({clean_task} Parametric Path)"
        trap_target = "Window Title Bar Drag Zone"
    elif modality == "type":
        steps = [
            {"step": 1, "action": "click", "target": f"{clean_task} Primary Input Box", "hotkey": None,
             "expected_delta": "Caret focused inside target input box"},
            {"step": 2, "action": "type", "target": f"{clean_task} Primary Input Box", "hotkey": "Enter",
             "expected_delta": mod_info["delta"]},
        ]
        chosen_target = f"{clean_task} Primary Input Box"
        trap_target = "Sidebar Global Search Filter Box"
    elif modality == "hotkey":
        steps = [
            {"step": 1, "action": "hotkey", "target": f"{app_name} Workspace", "hotkey": hk,
             "expected_delta": mod_info["delta"]},
        ]
        chosen_target = hk
        trap_target = "Wrong Menu Bar Button"
    else:
        steps = [
            {"step": 1, "action": mod_info["action"], "target": f"{clean_task} ({micro_title})", "hotkey": hk or None,
             "expected_delta": mod_info["delta"]},
        ]
        chosen_target = f"{clean_task} ({micro_title})"
        trap_target = "Lookalike Sidebar / Cancel Control"

    screen_controls = [
        chosen_target,
        trap_target,
        "Global Search / Filter Box",
        "Close / Cancel Modal Button",
    ]

    return {
        "arch_id": arch_id,
        "micro_id": micro_id,
        "domain": domain,
        "app": app_name,
        "action_kind": mod_info["action"],
        "goal": f"{clean_task} in {app_name} via {micro_title}",
        "precondition": f"{app_name} active | Pattern: {micro_title} ({micro_rule})",
        "steps": steps,
        "trap_guard": f"[{micro_id}] {micro_rule}. Avoid '{trap_target}'.",
        "dpo_pair": {
            "intent": f"{clean_task} in {app_name} ({micro_title})",
            "screen_controls": screen_controls,
            "chosen_action": {
                "action": mod_info["action"],
                "target": chosen_target,
                "hotkey": hk if hk else None,
                "reason": mod_info["reason"],
            },
            "rejected_action": {
                "action": "click",
                "target": trap_target,
                "failure_mode": f"Fails {micro_id}: interacts with lookalike trap or skips prerequisite reveal step",
            },
        },
    }


def query_beam_cloud_fast(prompt: str, timeout: int = 8) -> Optional[Dict[str, Any]]:
    """Optional live refinement via Ollama beam:cloud with fast timeout fallback."""
    payload = {
        "model": TEACHER_MODEL,
        "messages": [
            {"role": "system", "content": "Output strict JSON with keys: goal, precondition, steps, trap_guard."},
            {"role": "user", "content": prompt},
        ],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.2, "num_ctx": 2048},
    }
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data.get("message", {}).get("content", "")
            m = re.search(r"\{.*\}", content, re.DOTALL)
            return json.loads(m.group(0)) if m else json.loads(content)
    except Exception:
        return None


# ==============================================================================
# 5. BUILD MASSIVE DEDUPLICATED CURRICULUM (8,000+ TO 15,000+ ITEMS)
# ==============================================================================
def harvest_all_sources_to_queue(target_records: int) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    seen_hashes: Set[str] = set()

    def add_unique(rec: Dict[str, Any]) -> bool:
        sig = f"{rec.get('arch_id')}|{rec.get('app')}|{rec.get('goal')}|{rec.get('action_kind')}"
        h = hashlib.sha256(sig.encode("utf-8")).hexdigest()[:20]
        if h in seen_hashes:
            return False
        seen_hashes.add(h)
        rec["record_hash"] = h
        records.append(rec)
        return True

    # Stream A: Specialized 3D Proportions & Anatomy/Diagram Pro Knowledge
    for sp in SPECIALIZED_PRO_KNOWLEDGE:
        sp_copy = dict(sp)
        sp_copy.setdefault("micro_id", "MICRO_18_STATEFUL_2D_CANVAS")
        sp_copy.setdefault("dpo_pair", {
            "intent": sp_copy["goal"],
            "screen_controls": [sp_copy["steps"][0]["target"], "Crude Box Placeholder", "Global Search", "Cancel"],
            "chosen_action": {"action": sp_copy["action_kind"], "target": sp_copy["steps"][0]["target"], "reason": sp_copy["trap_guard"]},
            "rejected_action": {"action": "click", "target": "Crude Box Placeholder", "failure_mode": "Violates physical/anatomical proportions"},
        })
        add_unique(sp_copy)

    # Stream B: Full 35 Macro Archetypes x 45 Micro UI Patterns x Balanced 7 Modalities
    mod_idx = 0
    for arch_id, domain, apps_str, tasks in MACRO_ARCHETYPES_35:
        app_list = [a.strip() for a in apps_str.split(",") if a.strip()]
        for t_idx, task_slug in enumerate(tasks):
            for m_idx, (micro_id, micro_title, micro_rule) in enumerate(MICRO_UI_PATTERNS_45):
                app_name = app_list[(t_idx + m_idx) % len(app_list)]
                modality = ACTION_MODALITIES[mod_idx % len(ACTION_MODALITIES)]
                mod_idx += 1
                rec = synthesize_rich_record(
                    arch_id, domain, app_name, task_slug, micro_id, micro_title, micro_rule, modality
                )
                add_unique(rec)
                if len(records) >= target_records:
                    return records

    # Stream C: Full 6,711+ App Guides from app_guides_master.xlsx
    if EXCEL_GUIDES_PATH.exists():
        try:
            import pandas as pd
            df = pd.read_excel(EXCEL_GUIDES_PATH, sheet_name=0)
            print(f"-> Loaded {len(df)} total rows from {EXCEL_GUIDES_PATH.name}")
            cols = [str(c) for c in df.columns]
            for idx, row in df.iterrows():
                app_name = str(row.get(cols[0], f"App_{idx}")).strip()
                if not app_name or app_name.lower() == "nan":
                    continue
                cat_hint = str(row.get(cols[1], "Desktop Utility")).strip() if len(cols) > 1 else "Desktop Utility"
                arch_id, domain, _, tasks = MACRO_ARCHETYPES_35[idx % len(MACRO_ARCHETYPES_35)]
                micro_id, micro_title, micro_rule = MICRO_UI_PATTERNS_45[idx % len(MICRO_UI_PATTERNS_45)]
                modality = ACTION_MODALITIES[idx % len(ACTION_MODALITIES)]
                task_slug = tasks[idx % len(tasks)]
                rec = synthesize_rich_record(
                    arch_id, domain, f"{app_name} ({cat_hint})", task_slug, micro_id, micro_title, micro_rule, modality
                )
                add_unique(rec)
                if len(records) >= target_records:
                    break
        except Exception as e:
            print(f"-> Excel full-scan notice: {e}")

    return records


# ==============================================================================
# 6. INDEX INTO SQLITE FTS5 + DENSE BGE VECTORS + 70/30 QWEN DATASET
# ==============================================================================
def main() -> None:
    parser = argparse.ArgumentParser(description="Feed Vast Universal Knowledge into HoJaiga RAG & Qwen")
    parser.add_argument("--target-records", type=int, default=8000, help="Number of unique records to feed (default: 8000)")
    parser.add_argument("--live-beam-sample", type=int, default=40, help="Number of records to live-enrich via beam:cloud")
    args = parser.parse_args()

    t0 = time.time()
    print("=" * 78)
    print(f"HOJAIGA VAST EXPOSURE & UNIVERSAL KNOWLEDGE ENGINE (TARGET: {args.target_records} UNIQUE RECORDS)")
    print("Covering: 35 Macro Archetypes x 45 Micro UI Patterns x 7 Action Modalities + 6,711 Excel Apps")
    print("=" * 78)

    # 1. Connect to SQLite FTS5 & Load Existing Hashes to Prevent Duplicates
    conn = sqlite3.connect(str(RAG_DB_PATH), timeout=30.0)
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS causal_procedures_fts USING fts5("
        "arch_id, domain, goal, steps_json, trap_guard, tokenize='porter unicode61'"
        ")"
    )
    existing_goals: Set[str] = {
        r[0] for r in conn.execute("SELECT goal FROM causal_procedures_fts").fetchall()
    }
    print(f"-> Existing RAG Records in {RAG_DB_PATH.name}: {len(existing_goals)}")

    # 2. Generate Unique Multi-Modal Records
    candidates = harvest_all_sources_to_queue(args.target_records + len(existing_goals))
    new_records = [r for r in candidates if r["goal"] not in existing_goals][: args.target_records]
    print(f"-> Synthesized {len(new_records)} brand-new, deduplicated multi-modal records.")

    # Optional quick live enrichment sample from beam:cloud
    if args.live_beam_sample > 0 and new_records:
        print(f"-> Running live {TEACHER_MODEL} enrichment on {min(args.live_beam_sample, len(new_records))} sample archetypes...")
        for i in range(min(args.live_beam_sample, len(new_records))):
            rec = new_records[i]
            app_val = rec.get("app", "DesktopApp")
            goal_val = rec.get("goal", "Execute task")
            precond_val = rec.get("precondition", f"{app_val} workspace active")
            
            res = query_beam_cloud_fast(f"App: {app_val} | Goal: {goal_val} | Pattern: {precond_val}")
            if res and isinstance(res.get("trap_guard"), str):
                rec["trap_guard"] = res["trap_guard"]

    # 3. Batch Insert into SQLite FTS5 & Append to JSONL Vaults
    f_rag_path = DISTILLED_DIR / "distilled_causal_rag.jsonl"
    f_sft_path = DISTILLED_DIR / "distilled_qwen_sft.jsonl"
    f_dpo_path = DISTILLED_DIR / "distilled_qwen_dpo.jsonl"

    action_counts: Dict[str, int] = {}
    db_batch = []

    with (
        open(f_rag_path, "a", encoding="utf-8") as f_rag,
        open(f_sft_path, "a", encoding="utf-8") as f_sft,
        open(f_dpo_path, "a", encoding="utf-8") as f_dpo,
    ):
        for idx, rec in enumerate(new_records, 1):
            ak = rec.get("action_kind", "click")
            action_counts[ak] = action_counts.get(ak, 0) + 1

            db_batch.append((
                rec["arch_id"],
                rec["domain"],
                rec["goal"],
                json.dumps(rec["steps"], ensure_ascii=False),
                rec["trap_guard"],
            ))
            f_rag.write(json.dumps(rec, ensure_ascii=False) + "\n")

            dpo = rec["dpo_pair"]
            prompt_text = (
                f"[{rec['arch_id']} | {rec.get('micro_id', 'UI')}] Intent: {dpo['intent']}\n"
                f"Screen Elements: {json.dumps(dpo['screen_controls'], ensure_ascii=False)}\n"
                "Predict exact Action JSON:"
            )
            chosen_str = json.dumps(dpo["chosen_action"], ensure_ascii=False)
            rejected_str = json.dumps(dpo["rejected_action"], ensure_ascii=False)

            f_sft.write(json.dumps({"prompt": prompt_text, "completion": chosen_str}, ensure_ascii=False) + "\n")
            f_dpo.write(json.dumps({"prompt": prompt_text, "chosen": chosen_str, "rejected": rejected_str}, ensure_ascii=False) + "\n")

            if len(db_batch) >= 500:
                conn.executemany("INSERT INTO causal_procedures_fts VALUES (?, ?, ?, ?, ?)", db_batch)
                conn.commit()
                db_batch.clear()
                print(f"   [{idx}/{len(new_records)}] Committed to SQLite FTS5 & JSONL...")

        if db_batch:
            conn.executemany("INSERT INTO causal_procedures_fts VALUES (?, ?, ?, ?, ?)", db_batch)
            conn.commit()

    total_in_db = conn.execute("SELECT count(*) FROM causal_procedures_fts").fetchone()[0]
    all_rows = conn.execute("SELECT rowid, arch_id, domain, goal, trap_guard FROM causal_procedures_fts").fetchall()
    conn.close()

    print(f"-> Total Unique Causal Workflows Now in RAG DB: {total_in_db}")
    print(f"-> Action Modality Distribution Added: {json.dumps(action_counts)}")

    # 4. Sync to data\ai_root & Partition 70/30 Split
    shutil.copy2(str(RAG_DB_PATH), str(AI_ROOT_RAG_DB))
    all_sft_lines = [ln.strip() for ln in open(f_sft_path, "r", encoding="utf-8") if ln.strip()]
    random.seed(42)
    random.shuffle(all_sft_lines)
    split_idx = int(len(all_sft_lines) * 0.70)
    (DISTILLED_DIR / "qwen_train_70.jsonl").write_text("\n".join(all_sft_lines[:split_idx]) + "\n", encoding="utf-8")
    (DISTILLED_DIR / "qwen_test_30.jsonl").write_text("\n".join(all_sft_lines[split_idx:]) + "\n", encoding="utf-8")
    print(f"-> Updated 70/30 Split: {split_idx} Train / {len(all_sft_lines) - split_idx} Held-Out Test")

    # 5. Encode Dense BGE Embeddings on CPU for All Indexed RAG Workflows
    try:
        from sentence_transformers import SentenceTransformer
        print(f"-> Encoding all {len(all_rows)} RAG records into Dense BGE Vectors on CPU...")
        bge_path = DATA_DIR / "bge_finetuned_2080"
        model_name = str(bge_path) if bge_path.exists() else "BAAI/bge-small-en-v1.5"
        model = SentenceTransformer(model_name, device="cpu")
        passages = [f"[{r[1]} | {r[2]}] {r[3]} | {r[4]}" for r in all_rows]
        row_ids = np.array([r[0] for r in all_rows], dtype=np.int64)
        embeddings = model.encode(
            passages, batch_size=256, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=True
        )
        np.savez_compressed(str(VECTORS_OUT_PATH), row_ids=row_ids, embeddings=embeddings)
        print(f"-> Saved {embeddings.shape[0]} Dense Vectors to {VECTORS_OUT_PATH.name}")
    except Exception as e:
        print(f"-> Dense BGE notice: {e}")

    print("\n" + "=" * 78)
    print(f"VAST KNOWLEDGE INGESTION COMPLETE IN {(time.time() - t0)/60:.2f} MINUTES!")
    print(f"  • Total RAG Workflows (SQLite FTS5 + Dense BGE) : {total_in_db}")
    print(f"  • Total Qwen Multi-Modal SFT & DPO Pairs        : {len(all_sft_lines)}")
    print(f"  • Synced Live Agent Store                       : {AI_ROOT_RAG_DB}")
    print("=" * 78)


if __name__ == "__main__":
    main()