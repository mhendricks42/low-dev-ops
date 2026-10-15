#!/usr/bin/env bash
# PostToolUse(Edit|Write): format the edited file. Never fails the tool call.
f=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))')
root=${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}
case $f in
  "$root"/backend/*.py)
    cd "$root/backend" && uv run -q ruff format -q "$f" && uv run -q ruff check -q --fix "$f" ;;
  "$root"/frontend/*.ts | "$root"/frontend/*.tsx | "$root"/frontend/*.js | "$root"/frontend/*.css | "$root"/frontend/*.json)
    cd "$root/frontend" && npx --no-install prettier --write --log-level warn "$f" ;;
esac >/dev/null 2>&1
exit 0
