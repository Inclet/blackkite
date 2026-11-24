#!/usr/bin/env python3
"""PreToolUse guard for Bash in read-only agents: allow only listed command prefixes."""
import json, re, sys
ALLOWED = sys.argv[1:]
cmd = ((json.load(sys.stdin).get("tool_input") or {}).get("command") or "").strip()
if re.search(r"(^|[^<>])>(?!&)|\btee\b|\brm\b|\bmv\b|\bsed\s+-i|git\s+(commit|push|checkout|reset|stash|add|merge|rebase)", cmd):
    print("Blocked: read-only agent; command would modify files or git state.", file=sys.stderr); sys.exit(2)
parts = [p.strip() for p in re.split(r"&&|\|\||;|\|", cmd) if p.strip()]
for p in parts:
    p = re.sub(r"^cd\s+\S+\s*$", "", p).strip()
    if p and not any(p.startswith(a) for a in ALLOWED):
        print(f"Blocked: '{p.split()[0]}' is not on this agent's allowlist: {ALLOWED}", file=sys.stderr); sys.exit(2)
sys.exit(0)
