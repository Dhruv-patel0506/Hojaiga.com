#!/bin/bash
# Repeated questions through the ONE command, in the background. Each line: question ||| text the answer must contain (lower case) ; a line starting with ! expects an honest "don't know".
OUT=/d/new_automation/reports/qa_battery.tsv
: > $OUT
while IFS= read -r line; do
  [ -z "$line" ] && continue
  q="${line%%|||*}"; want="${line##*|||}"
  t0=$(date +%s%N)
  ans=$(powershell -NoProfile -Command "& 'D:\new_automation\hojaiga.bat' '$q'" 2>/dev/null | tr -d '\r')
  t1=$(date +%s%N)
  secs=$(( (t1 - t0) / 1000000 ))
  body=$(echo "$ans" | grep -E "^\s+- \[|^RESULT|NEEDS_INPUT|\? " | tr '\n' ' ' | cut -c1-600)
  low=$(echo "$body" | tr 'A-Z' 'a-z')
  if [[ "$want" == '!'* ]]; then
    if echo "$low" | grep -qE "could not find|nothing in it answers|could not tell which|not in evidence|needs_input|do not have"; then res=PASS; else res=FAIL; fi
  else
    if echo "$low" | grep -qF "$want"; then res=PASS; else res=FAIL; fi
  fi
  printf "%s\t%s ms\t%s\t%s\n" "$res" "$secs" "$q" "$body" >> $OUT
done <<'EOF'
what is the keyboard shortcut for bold in Google Docs?|||ctrl + b
what is the shortcut to italicize text in Google Docs?|||ctrl + i
what is the shortcut for undo in Google Docs?|||ctrl + z
how do I insert a comment in Google Docs?|||ctrl + alt + m
what is the shortcut for copy in Google Sheets?|||ctrl + c
how do I extrude a mesh in Blender?|||press e
how do I add an object in Blender?|||shift
what is the shortcut for save in Notepad?|||ctrl
how do I get to the Pricing page on todoist.com?|||pricing
what is Todoist and what can I do in it?|||task
what does Docker Desktop do?|||docker
what menu shortcuts does GitHub Desktop have?|||ctrl
how do I make a table in Blender?|||!
what is the zoom shortcut in the made up app Frobnitz Studio?|||!
EOF
echo BATTERY_DONE >> $OUT
