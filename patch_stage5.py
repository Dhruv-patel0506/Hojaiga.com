import pathlib

p = pathlib.Path(r"D:\new_automation\run_stage5_only_4b.py")
code = p.read_text(encoding="utf-8")

old_block = """    sys_t = msgs[0]["content"][0]["text"] if msgs[0]["role"] == "system" else SYS
    usr_t = ""
    gt_raw = "[]"
    for m in msgs:
        if m["role"] == "user":
            usr_t = m["content"][0]["text"] if isinstance(m["content"], list) else str(m["content"])
        elif m["role"] == "assistant":
            gt_raw = m["content"][0]["text"] if isinstance(m["content"], list) else str(m["content"])"""

new_block = """    def _extract_txt(c):
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            return "\\n".join(str(p.get("text", "")) for p in c if isinstance(p, dict) and "text" in p).strip()
        return str(c)

    sys_t = _extract_txt(msgs[0].get("content", "")) if msgs[0].get("role") == "system" else SYS
    usr_t = ""
    gt_raw = "[]"
    for m in msgs:
        if m.get("role") == "user":
            usr_t = _extract_txt(m.get("content", ""))
        elif m.get("role") == "assistant":
            gt_raw = _extract_txt(m.get("content", ""))"""

if old_block in code:
    code = code.replace(old_block, new_block)
    code = code.replace("torch_dtype=torch.bfloat16,", "dtype=torch.bfloat16,")
    p.write_text(code, encoding="utf-8")
    print("[+] Fixed multimodal content list parser in run_stage5_only_4b.py!")
else:
    print("[*] Applying regex patch to run_stage5_only_4b.py...")
