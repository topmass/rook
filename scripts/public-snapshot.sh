#!/bin/sh
# Usage: scripts/public-snapshot.sh OUT_DIR --author "Name <email>" --license FILE [--names FILE]
# Makes a public copy of Rook in OUT_DIR: the committed tree at HEAD, without the private folders,
# as a new git repository with one commit by the given author. It never uses your git identity.
# Before the commit it scans the copy for private values and refuses on any match. The values come from outside
# the repository, so this script ships none:
#   the names file: --names FILE, else $ROOK_PRIVATE_NAMES, else ~/.config/rook/private-names.txt;
#   this computer's host name, the machine names in ~/.config/rook/machines.json, your git email and your home folder.
# Names file: one value per line, # starts a comment. A value matches as a whole word. An all-lowercase value
# matches any case, and a value with a capital matches its exact case.
set -eu

# Left out of every snapshot: the game helper, the shelved stage host (the stage setting refuses "on"),
# the owner's own build rules, and agent memory.
EXCLUDE="wow stage AGENTS.md .agent-memory"

die() { printf 'public-snapshot: %s\n' "$*" >&2; exit 2; }

REPO=$(cd "$(dirname "$0")/.." && pwd)
out="" author="" license="" names=${ROOK_PRIVATE_NAMES:-${XDG_CONFIG_HOME:-$HOME/.config}/rook/private-names.txt}
while [ $# -gt 0 ]; do
  case "$1" in
    --author) [ $# -ge 2 ] || die "--author needs a value."; author=$2; shift 2 ;;
    --license) [ $# -ge 2 ] || die "--license needs a file."; license=$2; shift 2 ;;
    --names) [ $# -ge 2 ] || die "--names needs a file."; names=$2; shift 2 ;;
    -*) die "Unknown option $1." ;;
    *) [ -z "$out" ] || die "Give one OUT_DIR."; out=$1; shift ;;
  esac
done

[ -n "$out" ] || die "Usage: scripts/public-snapshot.sh OUT_DIR --author \"Name <email>\" --license FILE [--names FILE]"
[ -n "$author" ] || die "Who is the author of the public commit? Give --author \"Name <email>\". The tool never uses your git identity."
case "$author" in
  *' <'*'@'*'>') ;;
  *) die "The author must look like \"Name <email>\"." ;;
esac
a_name=${author%% <*}
a_email=${author##*<}
a_email=${a_email%>}
case "$a_name$a_email" in *'<'*|*'>'*) die "The author must look like \"Name <email>\"." ;; esac
[ -n "$license" ] || die "Rook needs a LICENSE. Give --license FILE. This tool does not pick one."
[ -s "$license" ] || die "The license file $license is missing or empty."
[ -s "$names" ] || die "The private names file $names is missing. Write it first, or give --names FILE."
[ ! -e "$out" ] || die "$out already exists. Give a new folder."

work=$(mktemp -d "${TMPDIR:-/tmp}/rook-snapshot.XXXXXX")
mkdir -p "$(dirname "$out")"
tree=$(mktemp -d "$(dirname "$out")/.rook-snapshot.XXXXXX")
trap 'rm -rf "$work" "$tree"' EXIT

# 1. The tree. Uncommitted changes are not in it.
[ -z "$(git -C "$REPO" status --porcelain)" ] || echo "public-snapshot: the work tree has uncommitted changes. The snapshot holds HEAD only." >&2
set --
for path in $EXCLUDE; do set -- "$@" ":(exclude)$path"; done
git -C "$REPO" archive --format=tar HEAD -- . "$@" | tar -x -C "$tree"
cp "$license" "$tree/LICENSE"

# 2. The private values, split into any-case and exact-case lists.
{
  sed -e 's/\r$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e '/^#/d' -e '/^$/d' "$names"
  uname -n | cut -d. -f1
  python3 -c 'import json, sys; print("\n".join(json.load(open(sys.argv[1]))))' \
    "${XDG_CONFIG_HOME:-$HOME/.config}/rook/machines.json" 2>/dev/null || true
  git -C "$REPO" config user.email || true
  printf '%s\n' "$HOME"
} | awk 'length($0) > 1' | sort -u > "$work/all"
awk '$0 == tolower($0)' "$work/all" > "$work/anycase"
awk '$0 != tolower($0)' "$work/all" > "$work/exact"

# 3. The scan: file contents and file names.
# ponytail: binary files (images, sounds) are skipped; scan their metadata too if one ever carries text.
(
  cd "$tree"
  grep -rIno -wiF -f "$work/anycase" . || true
  grep -rIno -wF -f "$work/exact" . || true
  find . -path ./.git -prune -o -print | grep -wiF -f "$work/anycase" | sed 's/$/: (file name)/' || true
  find . -path ./.git -prune -o -print | grep -wF -f "$work/exact" | sed 's/$/: (file name)/' || true
) | sed 's|^\./||' | sort -u > "$work/hits"
if [ -s "$work/hits" ]; then
  cat "$work/hits" >&2
  echo "public-snapshot: refused. $(cut -d: -f1 "$work/hits" | sort -u | wc -l) file(s) hold a private value:" >&2
  cut -d: -f1 "$work/hits" | sort -u | sed 's/^/  /' >&2
  exit 1
fi

# 4. A new repository with one commit, free of your git config, hooks and signing.
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
export GIT_AUTHOR_NAME="$a_name" GIT_AUTHOR_EMAIL="$a_email" GIT_COMMITTER_NAME="$a_name" GIT_COMMITTER_EMAIL="$a_email"
git -C "$tree" init -q -b main
git -C "$tree" add -A
git -C "$tree" commit -q -m "Rook"
mv "$tree" "$out"
echo "Snapshot: $out ($(du -sh "$out" | cut -f1), $(git -C "$out" ls-files | wc -l) files, one commit by $a_name <$a_email>)."
