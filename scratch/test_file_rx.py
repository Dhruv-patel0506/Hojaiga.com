import re, sys
sys.stdout.reconfigure(encoding='utf-8')

rx_old = re.compile(r"(?i)\b(click|press|select|choose)\s+(?:the\s+|on\s+)?[\"'“]?(open|save|select folder|upload|insert|import|export)\b")
rx_new = re.compile(r"(?i)\b(click|press|select|choose)\s+(?:the\s+|on\s+)?[\"'“]?(open|save|select folder|upload|insert|import|export)(?:[\"'”]|(?:\s+button\b)|(?:\s*[\.,:;()!?'\"]|\s*$))")

for s in [
    "Select Open navigation (☰).",
    "Select Review to open the comments",
    "Select Open.",
    "Click Save",
    "Select the Open button",
    "Click the Save button to save the file",
]:
    print(s)
    print("  old:", bool(rx_old.search(s)))
    print("  new:", bool(rx_new.search(s)))
