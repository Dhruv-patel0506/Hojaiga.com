"""Claude Code PreToolUse hook for NI gate 1 (shadow mode).

Reads the hook payload on stdin, sends it to the local scorer (cc_serve.py, 127.0.0.1:8766) and exits 0 with no output, so
the tool call always goes ahead unchanged. Runs as an async hook: it adds no delay to the agent. If the scorer is not
running, it does nothing. Standard library only, so it starts fast.
"""
import sys, json, urllib.request

try:
    body = sys.stdin.buffer.read()
    json.loads(body or b"{}")
    req = urllib.request.Request("http://127.0.0.1:8766/score", data=body, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10).read()
except Exception:
    pass
sys.exit(0)
