#!/usr/bin/env bash
# Stop: refuse to finish while `make check` is red. Exit 2 sends the output back to Claude.
input=$(cat)
# One retry per stop: if this stop already came from this hook, let it end to avoid a loop.
python3 -c 'import json,sys; sys.exit(0 if json.loads(sys.argv[1]).get("stop_hook_active") else 1)' "$input" && exit 0
cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}" || exit 0
# Nothing changed since the last commit: nothing new to check.
[[ -z $(git status --porcelain) ]] && exit 0
if ! out=$(make check 2>&1); then
  printf 'make check failed. Fix it before stopping:\n%s\n' "$(tail -n 40 <<<"$out")" >&2
  exit 2
fi
