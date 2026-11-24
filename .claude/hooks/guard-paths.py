#!/usr/bin/env python3
"""PreToolUse guard for Edit/Write: block writes outside the allowed repo-relative prefixes.
Usage: guard-paths.py PREFIX [PREFIX ...]   (prefixes relative to the repo/worktree root)"""
import json, os, subprocess, sys

allowed = sys.argv[1:]
data = json.load(sys.stdin)
path = (data.get("tool_input") or {}).get("file_path") or (data.get("tool_input") or {}).get("notebook_path")
if not path:
    sys.exit(0)
path = os.path.abspath(path)
probe = os.path.dirname(path)
while probe and not os.path.isdir(probe):
    probe = os.path.dirname(probe)
try:
    top = subprocess.check_output(["git", "-C", probe, "rev-parse", "--show-toplevel"], text=True).strip()
except Exception:
    print(f"Blocked: {path} is not inside a Blackkite checkout.", file=sys.stderr); sys.exit(2)
rel = os.path.relpath(path, top)
if rel.startswith("design/"):
    print("Blocked: design/ is read-only (approved references).", file=sys.stderr); sys.exit(2)
if any(rel == p.rstrip("/") or rel.startswith(p.rstrip("/") + "/") for p in allowed):
    sys.exit(0)
print(f"Blocked: this agent may only write under {', '.join(allowed)}; tried {rel}.", file=sys.stderr)
sys.exit(2)
