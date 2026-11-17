import json, pathlib

train_src = pathlib.Path(r"D:\new_automation\data\beam_distilled_master\qwen_train_70.jsonl")
test_src = pathlib.Path(r"D:\new_automation\data\beam_distilled_master\qwen_test_30.jsonl")

out_train = pathlib.Path(r"D:\new_automation\data\ai_root\harvest\training\qwen_24k_train_ready.jsonl")
out_test = pathlib.Path(r"D:\new_automation\data\ai_root\harvest\training\qwen_10k_test_ready.jsonl")
out_train.parent.mkdir(parents=True, exist_ok=True)

def format_dataset(src, dst):
    count = 0
    with open(src, "r", encoding="utf-8") as f_in, open(dst, "w", encoding="utf-8") as f_out:
        for line in f_in:
            if not line.strip(): continue
            row = json.loads(line)
            if "messages" not in row:
                prompt_text = row.get("prompt", "")
                completion_text = row.get("completion", "")
                row = {
                    "messages": [
                        {"role": "user", "content": [{"type": "text", "text": prompt_text}]},
                        {"role": "assistant", "content": [{"type": "text", "text": completion_text}]}
                    ]
                }
            if "meta" not in row:
                row["meta"] = {}
            row["meta"]["grounded"] = True
            row["meta"]["verified_ui"] = True
            f_out.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count

print("Formatting Qwen 24k Train and 10k Test sets...")
tr_n = format_dataset(train_src, out_train)
te_n = format_dataset(test_src, out_test)
print(f"[+] Formatted Train Set: {tr_n} rows -> {out_train}")
print(f"[+] Formatted Test Set : {te_n} rows -> {out_test}")
