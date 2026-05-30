# Oxels Team Marketplace

Oxels plugin bundles: agent skills and MCP configuration for teams using **Cursor** or **Claude Code**.

The marketplace manifest name is `oxels-plugins` (see `.cursor-plugin/marketplace.json` and `.claude-plugin/marketplace.json`).

## Included plugins

| Plugin | Folder | Summary |
|--------|--------|---------|
| **Contract Intelligence** | `plugins/oxels` | MCP-backed contract analysis: ontology, effective terms, portfolio scans, provisioning taxonomy, and retrieval guidance for legal, accounting, and revenue operations work |

Add new plugins by creating a folder under `plugins/` and registering it in both marketplace manifests. See `docs/add-a-plugin.md` for the full workflow.

## Install

### Quick install (Cursor + Claude Code)

```bash
curl -sSL https://mcp.oxels.com/install | bash
```

Install only one target:

```bash
OXELS_TARGET=cursor curl -sSL https://mcp.oxels.com/install | bash
OXELS_TARGET=claude curl -sSL https://mcp.oxels.com/install | bash
```

### Cursor marketplace

Add this repository as a marketplace in Cursor, then install `oxels@oxels-plugins`.

### Claude Code marketplace

```bash
/plugin marketplace add oxels-foundry/oxels-team-marketplace
/plugin install oxels@oxels-plugins
```

Or from a local checkout:

```bash
claude plugin marketplace add ./path/to/oxels-team-marketplace
claude plugin install oxels@oxels-plugins
```

Skills are namespaced by plugin name, for example `/oxels:oxels-review-contract`.

## Repository structure

- `.cursor-plugin/marketplace.json` — Cursor marketplace manifest and plugin registry
- `.claude-plugin/marketplace.json` — Claude Code marketplace manifest and plugin registry
- `plugins/<plugin-slug>/.cursor-plugin/plugin.json` — Cursor per-plugin metadata
- `plugins/<plugin-slug>/.claude-plugin/plugin.json` — Claude Code per-plugin metadata
- `plugins/<plugin-slug>/skills` — skill folders with `SKILL.md`
- `plugins/<plugin-slug>/mcp.json` — MCP server configuration

Skills and MCP config are shared between Cursor and Claude Code. Each host reads its own manifest directory (`.cursor-plugin/` or `.claude-plugin/`).

## Validate changes

```bash
node scripts/validate-template.mjs
claude plugin validate plugins/oxels
claude plugin validate .
```

This checks marketplace paths, plugin manifests, and required frontmatter in rule, skill, agent, and command files.

## Submission checklist

- Each plugin has valid `.cursor-plugin/plugin.json` and `.claude-plugin/plugin.json`
- Plugin names are unique, lowercase, and kebab-case
- Both marketplace manifests map to real plugin folders
- Required frontmatter metadata exists in plugin content files
- Logo paths resolve correctly from each plugin manifest
- `node scripts/validate-template.mjs` passes
