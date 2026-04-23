#!/usr/bin/env bash
#
# Oxels Contract Intelligence - skills installer
#
# Installs Oxels Contract Intelligence skills into ~/.agents/skills
# for teams that cannot install the plugin via a marketplace.
#
# Usage:
#   curl -sSL https://mcp.oxels.com/install | bash
#
# Env overrides:
#   OXELS_SKILLS_DIR   Destination directory (default: ~/.agents/skills)
#   OXELS_BRANCH       Branch to install from (default: main)
#
set -euo pipefail

REPO="oxels-foundry/oxels-team-marketplace"
BRANCH="${OXELS_BRANCH:-main}"
PLUGIN="oxels-contract-intelligence"
DEST="${OXELS_SKILLS_DIR:-$HOME/.agents/skills}"

log() { printf '%s\n' "$*"; }
err() { printf 'Error: %s\n' "$*" >&2; }

command -v curl >/dev/null 2>&1 || { err "curl is required"; exit 1; }
command -v tar  >/dev/null 2>&1 || { err "tar is required";  exit 1; }

log "Installing Oxels skills to $DEST"
mkdir -p "$DEST"

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

ARCHIVE_URL="https://github.com/${REPO}/archive/refs/heads/${BRANCH}.tar.gz"
log "Downloading ${REPO}@${BRANCH}..."
curl -fsSL "$ARCHIVE_URL" -o "$TMPDIR/archive.tar.gz"

log "Extracting..."
tar -xzf "$TMPDIR/archive.tar.gz" -C "$TMPDIR"

SRC="$TMPDIR/oxels-team-marketplace-${BRANCH}/plugins/${PLUGIN}/skills"
if [ ! -d "$SRC" ]; then
  err "Skills directory not found in archive: $SRC"
  exit 1
fi

count=0
for skill in "$SRC"/*/; do
  [ -d "$skill" ] || continue
  name="$(basename "$skill")"
  log "  installing: $name"
  rm -rf "$DEST/$name"
  cp -R "$skill" "$DEST/$name"
  count=$((count + 1))
done

log ""
log "Done. Installed $count skill(s) to $DEST"
log "Restart Cursor to load the new skills."
