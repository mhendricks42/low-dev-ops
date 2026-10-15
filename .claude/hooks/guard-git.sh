#!/usr/bin/env bash
# PreToolUse(Bash): enforce the git workflow in CLAUDE.md. Exit 2 blocks the call.
cmd=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input", {}).get("command", ""))')
[[ $cmd =~ git[[:space:]]+(commit|push) ]] || exit 0

if [[ $(git branch --show-current 2>/dev/null) == main ]]; then
  echo "Blocked: never commit or push on main. Branch first: git switch -c feat/<short-name>" >&2
  exit 2
fi
if [[ $cmd =~ --no-verify|--force|[[:space:]]-f([[:space:]]|$) ]]; then
  echo "Blocked: --no-verify and force-push are not allowed." >&2
  exit 2
fi
