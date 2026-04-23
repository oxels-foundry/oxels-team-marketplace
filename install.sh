#!/usr/bin/env bash
#
# Oxels Contract Intelligence - Cursor plugin installer
#
# Installs the Oxels Contract Intelligence plugin as a local Cursor plugin
# at ~/.cursor/plugins/local/oxels-contract-intelligence. Delivers the same
# contents as installing via the Cursor marketplace: skills, rules, MCP
# server config, and assets.
#
# Usage:
#   curl -sSL https://mcp.oxels.com/install | bash
#
# Env overrides:
#   OXELS_PLUGINS_DIR   Cursor local plugins dir (default: ~/.cursor/plugins/local)
#   OXELS_BRANCH        Branch to install from  (default: main)
#
set -euo pipefail

REPO="oxels-foundry/oxels-team-marketplace"
BRANCH="${OXELS_BRANCH:-main}"
PLUGIN="oxels-contract-intelligence"
PLUGINS_DIR="${OXELS_PLUGINS_DIR:-$HOME/.cursor/plugins/local}"
DEST="$PLUGINS_DIR/$PLUGIN"

log() { printf '%s\n' "$*"; }
err() { printf 'Error: %s\n' "$*" >&2; }

command -v curl >/dev/null 2>&1 || { err "curl is required"; exit 1; }
command -v tar  >/dev/null 2>&1 || { err "tar is required";  exit 1; }

log "Installing Oxels Contract Intelligence plugin to $DEST"
mkdir -p "$PLUGINS_DIR"

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

ARCHIVE_URL="https://github.com/${REPO}/archive/refs/heads/${BRANCH}.tar.gz"
log "Downloading ${REPO}@${BRANCH}..."
curl -fsSL "$ARCHIVE_URL" -o "$TMPDIR/archive.tar.gz"

log "Extracting..."
tar -xzf "$TMPDIR/archive.tar.gz" -C "$TMPDIR"

SRC="$TMPDIR/oxels-team-marketplace-${BRANCH}/plugins/${PLUGIN}"
if [ ! -d "$SRC" ]; then
  err "Plugin directory not found in archive: $SRC"
  exit 1
fi

log "Installing plugin files..."
rm -rf "$DEST"
cp -R "$SRC" "$DEST"

log ""
log "Done. Plugin installed at $DEST"
log "Contents:"
ls -1 "$DEST" | sed 's/^/  /'
log ""
log "Restart Cursor to load the plugin."
