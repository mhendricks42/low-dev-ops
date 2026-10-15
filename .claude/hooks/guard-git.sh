#!/usr/bin/env bash
# PreToolUse(Bash): enforce the git workflow in CLAUDE.md. Exit 2 blocks the call.
cmd=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input", {}).get("command", ""))')

# Check each simple command separately so text elsewhere (e.g. a heredoc) can't trip the flags check.
while IFS= read -r seg; do
  [[ $seg =~ git[[:space:]]+(commit|push)([[:space:]]|$) ]] || continue
  if [[ $(git branch --show-current 2>/dev/null) == main ]]; then
    echo "Blocked: never commit or push on main. Branch first: git switch -c feat/<short-name>" >&2
    exit 2
  fi
  if [[ $seg =~ --no-verify|--force|[[:space:]]-[fn]([[:space:]]|$) ]]; then
    echo "Blocked: --no-verify and force-push are not allowed." >&2
    exit 2
  fi
done < <(tr ';&|' '\n\n\n' <<<"$cmd")
exit 0
