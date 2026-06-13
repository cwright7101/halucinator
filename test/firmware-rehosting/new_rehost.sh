#!/usr/bin/env bash
# new_rehost.sh — spawn a per-firmware re-hosting worktree + branch off feature/rehost-fleet.
#
#   ./new_rehost.sh <name> <public|private> [firmware-path]
#
# - <name>          short slug, e.g. p2im-drone, bmxnoe-arm
# - public|private  public  -> feature/rehost-<name> (pushable)
#                   private -> private/rehost-<name>  (pre-push hook blocks it)
# - firmware-path   optional; if omitted, reuses an existing untracked
#                   test/firmware-rehosting/<name>/ dir from the MAIN checkout.
#
# Creates ../hal-rehost-<name> as a worktree, stamps the firmware dir from the
# arm-vxworks-plc template (or carries over prior untracked work), gitignores the
# binary, and prints the kickoff prompt to fill in.
set -euo pipefail

NAME="${1:?usage: new_rehost.sh <name> <public|private> [firmware-path]}"
TRACK="${2:?usage: new_rehost.sh <name> <public|private> [firmware-path]}"
SRCBIN="${3:-}"

case "$TRACK" in
  public)  BRANCH="feature/rehost-$NAME" ;;
  private) BRANCH="private/rehost-$NAME" ;;
  *) echo "track must be 'public' or 'private'" >&2; exit 2 ;;
esac

COMMON=$(git rev-parse --path-format=absolute --git-common-dir)
MAIN=$(dirname "$COMMON")
PARENT=$(dirname "$MAIN")
WT="$PARENT/hal-rehost-$NAME"
DIRREL="test/firmware-rehosting/$NAME"
TEMPLATE="$MAIN/test/firmware-rehosting/arm-vxworks-plc"

[ -e "$WT" ] && { echo "worktree $WT already exists" >&2; exit 1; }
git show-ref --verify --quiet "refs/heads/$BRANCH" && { echo "branch $BRANCH already exists" >&2; exit 1; }

echo ">> creating worktree $WT on $BRANCH (off feature/rehost-fleet)"
git worktree add -b "$BRANCH" "$WT" feature/rehost-fleet >/dev/null

DEST="$WT/$DIRREL"
mkdir -p "$DEST"

# 1) carry over any existing untracked work from the main checkout, else stamp template
if [ -d "$MAIN/$DIRREL" ] && [ -n "$(ls -A "$MAIN/$DIRREL" 2>/dev/null || true)" ]; then
  echo ">> carrying over existing $MAIN/$DIRREL"
  cp -R "$MAIN/$DIRREL/." "$DEST/"
else
  echo ">> stamping from template ($TEMPLATE)"
  cp "$TEMPLATE/extract_symbols.py" "$DEST/" 2>/dev/null || true
  cp "$TEMPLATE/run_cfg.py"        "$DEST/" 2>/dev/null || true
fi

# 2) bring in an explicitly given firmware binary
if [ -n "$SRCBIN" ]; then
  [ -f "$SRCBIN" ] || { echo "firmware-path not found: $SRCBIN" >&2; exit 1; }
  cp "$SRCBIN" "$DEST/$(basename "$SRCBIN")"
  echo ">> copied firmware $(basename "$SRCBIN")"
fi

# 3) ensure binaries / derived files are gitignored (never commit firmware)
cat > "$DEST/.gitignore" <<'EOF'
# firmware image(s) and derived artifacts — never committed
*.bin
*.elf
*.hex
*.img
symbols.csv
*.log
tmp/
EOF

# 4) seed STATUS.md if absent
[ -f "$DEST/STATUS.md" ] || cat > "$DEST/STATUS.md" <<EOF
# $NAME — re-host status

- **Milestone:** M0 (not started)
- **Frontier:** (first run pending)
- **Arch / OS:** TBD (confirm)
- **Config:** ${NAME}_config.yaml
- **Dead-ends tried:** (none yet)

Update every iteration: milestone (M0–M4), the exact gate (fn/PC + why), dead-ends.
EOF

echo
echo "=================================================================="
echo " worktree : $WT"
echo " branch   : $BRANCH   (track: $TRACK)"
echo " dir      : $DIRREL"
echo " next     : fill KICKOFF_TEMPLATE.md and hand it to the agent."
echo "=================================================================="
