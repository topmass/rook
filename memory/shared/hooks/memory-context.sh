#!/usr/bin/env bash
# Standalone SessionStart hook for Claude Code: prints the project's memory folder and its index.
base=$(dirname "$(dirname "$(readlink -f "$0")")")
. "$base/memory.conf"
if command -v timeout >/dev/null 2>&1; then
  [ -t 0 ] || cwd=$(timeout 1 jq -r '.cwd // empty' 2>/dev/null)
else # A Mac has no timeout: read waits at most 1 s for the payload.
  [ -t 0 ] || { IFS= read -r -d '' -t 1 payload; cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty' 2>/dev/null); }
fi
cwd=${cwd:-${CLAUDE_PROJECT_DIR:-$PWD}}
dir=$("$base/bin/memory-dir" --start "$cwd")
case $? in
  0) ;;
  3) echo "Memory is off in this folder. Save no notes here, and do not run remember."; exit 0 ;;
  *) exit 0 ;;
esac
mkdir -p "$dir" "$HOME/.agents/dream" 2>/dev/null || exit 0
[ -f "$dir/MEMORY.md" ] || printf '# Memory index\n' >"$dir/MEMORY.md"
# The dream job needs this map after a worktree is deleted.
map="$HOME/.agents/dream/dirs.tsv"
line="$(realpath -m "$cwd" 2>/dev/null || python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$cwd")	$dir"
grep -qxF "$line" "$map" 2>/dev/null || echo "$line" >>"$map"

echo "Memory folder: $dir (private, never commit). Memory model: $MEMORY_MODEL."
echo "Read the notes related to your task before starting."
echo 'Save anything worth knowing next session with ~/.agents/bin/remember "<fact and why>".'
conflicts=$(grep -l 'CONFLICT:' "$dir"/*.md 2>/dev/null | grep -vc '/MEMORY.md$')
[ "$conflicts" -gt 0 ] && echo "$conflicts memory notes hold an unresolved CONFLICT. Ask the user to settle one when it bears on the task."
# The system manages itself, so a broken dream must reach the user through a session.
status="$HOME/.agents/dream/status"
if grep -q '^FAILED' "$status" 2>/dev/null; then
  echo "The nightly memory dream is failing: $(head -c 300 "$status" | tr '\n' ' '). Tell the user."
elif [ -n "$(find "$status" -mtime +3 2>/dev/null)" ]; then
  echo "The nightly memory dream has not run for over 3 days. Tell the user."
fi
echo "Index:"
# The index is the only memory loaded into every session. The limit is Claude Code's own: 200 lines or 25 KB.
head -n 200 "$dir/MEMORY.md" | head -c 25000
