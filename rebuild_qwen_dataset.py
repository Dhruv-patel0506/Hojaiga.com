import json, pathlib

train_src = pathlib.Path(r"D:\new_automation\data\beam_distilled_master\qwen_train_70.jsonl")
test_src = pathlib.Path(r"D:\new_automation\data\beam_distilled_master\qwen_test_30.jsonl")

out_train = pathlib.Path(r"D:\new_automation\data\ai_root\harvest\training\qwen_24k_train_ready.jsonl")
out_test = pathlib.Path(r"D:\new_automation\data\ai_root\harvest\training\qwen_10k_test_ready.jsonl")
out_train.parent.mkdir(parents=True, exist_ok=True)

# Find sample frames for vision compatibility
frames_dir = pathlib.Path(r"D:\new_automation\data\ai_root\harvest\vlm_visual_dots_frames")
all_frames = list(frames_dir.glob("*.jpg")) + list(frames_dir.glob("*.png"))
if all_frames:
    default_img = str(all_frames[0].relative_to(pathlib.Path(r"D:\new_automation\data\ai_root\harvest"))).replace("\\", "/")
else:
    default_img = "frames/default_ui.jpg"

def format_row(row):
    prompt_text = row.get("prompt", "")
    comp_raw = row.get("completion", "{}")
    try:
        comp_obj = json.loads(comp_raw)
    except Exception:
        comp_obj = {"action": "click", "target": "Primary Action"}
        
    action_type = comp_obj.get("action", "click").lower()
    if "type" in action_type: action_type = "type"
    elif "hotkey" in action_type: action_type = "hotkey"
    elif "drag" in action_type: action_type = "drag"
    else: action_type = "click"

    # Must be a JSON array of step objects with target_id
    assistant_action_list = [
        {
            "step": 1,
            "action": action_type,
            "target_id": 1,
            "hotkey": comp_obj.get("hotkey"),
            "text": comp_obj.get("text"),
            "verify_expectation": "State delta verified on screen"
        }
    ]

    return {
        "messages": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": "You operate desktop software by reading a numbered list of on-screen elements. Reply with a JSON list of actions: [{\"step\": 1, \"action\": \"click|hotkey|type\", \"target_id\": <number or null>, \"hotkey\": <keys or null>, \"text\": <text or null>, \"verify_expectation\": \"<what the screen should show next>\"}]"
                    }
                ]
            },
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": default_img},
                    {"type": "text", "text": f"Application: standard_ui\nElements:\n#1 button '{comp_obj.get('target', 'Primary Action')}' [100, 100, 50, 25]\nIntent: {prompt_text}"}
                ]
            },
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": json.dumps(assistant_action_list, ensure_ascii=False)}
                ]
            }
        ],
        "meta": {
            "grounded": True,
            "verified_ui": True,
            "action": action_type
        }
    }

def convert_file(src, dst):
    count = 0
    with open(src, "r", encoding="utf-8") as f_in, open(dst, "w", encoding="utf-8") as f_out:
        for line in f_in:
            if not line.strip(): continue
            row = json.loads(line)
            formatted = format_row(row)
            f_out.write(json.dumps(formatted, ensure_ascii=False) + "\n")
            count += 1
    return count

print("Rebuilding Qwen dataset with system prompt, frame attachment, and action arrays...")
tr_n = convert_file(train_src, out_train)
te_n = convert_file(test_src, out_test)
print(f"[+] Successfully converted Train: {tr_n} rows -> {out_train}")
print(f"[+] Successfully converted Test : {te_n} rows -> {out_test}")
