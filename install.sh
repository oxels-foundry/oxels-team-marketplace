#!/usr/bin/env bash
#
# Oxels Contract Intelligence - Cursor and Claude Code plugin installer
#
# Installs the Oxels plugin from this marketplace for Cursor and/or Claude Code.
#
# Usage:
#   curl -sSL https://mcp.oxels.com/install | bash
#
# Env overrides:
#   OXELS_TARGET           Install target: cursor, claude, or both (default: both)
#   OXELS_PLUGINS_DIR      Cursor local plugins dir (default: ~/.cursor/plugins/local)
#   OXELS_BRANCH           Branch to install from (default: main)
#   OXELS_REPO             GitHub repo slug (default: oxels-foundry/oxels-team-marketplace)
#
set -euo pipefail

REPO="${OXELS_REPO:-oxels-foundry/oxels-team-marketplace}"
BRANCH="${OXELS_BRANCH:-main}"
PLUGIN="oxels"
MARKETPLACE="oxels-plugins"
TARGET="${OXELS_TARGET:-both}"
PLUGINS_DIR="${OXELS_PLUGINS_DIR:-$HOME/.cursor/plugins/local}"
DEST="$PLUGINS_DIR/$PLUGIN"

log() { printf '%s\n' "$*"; }
err() { printf 'Error: %s\n' "$*" >&2; }

command -v curl >/dev/null 2>&1 || { err "curl is required"; exit 1; }
command -v tar  >/dev/null 2>&1 || { err "tar is required";  exit 1; }

case "$TARGET" in
  cursor|claude|both) ;;
  *)
    err "OXELS_TARGET must be cursor, claude, or both"
    exit 1
    ;;
esac

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

install_cursor() {
  log "Installing Oxels plugin for Cursor to $DEST"
  mkdir -p "$PLUGINS_DIR"
  rm -rf "$DEST"
  cp -R "$SRC" "$DEST"
  log "Cursor plugin installed at $DEST"
  log "Restart Cursor to load the plugin."
}

install_claude() {
  if ! command -v claude >/dev/null 2>&1; then
    err "Claude Code CLI not found. Install it from https://code.claude.com/docs/en/setup"
    exit 1
  fi

  log "Registering Oxels marketplace for Claude Code..."
  claude plugin marketplace add "https://github.com/${REPO}.git#${BRANCH}"

  log "Installing ${PLUGIN}@${MARKETPLACE}..."
  claude plugin install "${PLUGIN}@${MARKETPLACE}"

  log "Claude Code plugin installed."
  log "Restart Claude Code, then try a skill such as /${PLUGIN}:oxels-review-contract"
}

if [ "$TARGET" = "cursor" ] || [ "$TARGET" = "both" ]; then
  install_cursor
  log ""
fi

if [ "$TARGET" = "claude" ] || [ "$TARGET" = "both" ]; then
  install_claude
  log ""
fi

log "Done."
