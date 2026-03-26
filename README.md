# Oxels Team Marketplace

A Cursor Team Marketplace for Oxels plugins: rules, agent skills, and MCP configuration shipped as installable bundles.

The marketplace manifest name is `oxels-plugins` (see `.cursor-plugin/marketplace.json`).

## Included plugins

| Plugin | Folder | Summary |
|--------|--------|---------|
| **Contract Intelligence** | `plugins/oxels-contract-intelligence` | MCP-backed contract analysis: ontology, effective terms, portfolio scans, provisioning taxonomy, and retrieval guidance for legal, accounting, and revenue operations work |

Add new plugins by creating a folder under `plugins/` and registering it in `.cursor-plugin/marketplace.json`. See `docs/add-a-plugin.md` for the full workflow.

## Repository structure

- `.cursor-plugin/marketplace.json` — marketplace manifest and plugin registry
- `plugins/<plugin-slug>/.cursor-plugin/plugin.json` — per-plugin metadata
- `plugins/<plugin-slug>/rules` — rule files (`.mdc`)
- `plugins/<plugin-slug>/skills` — skill folders with `SKILL.md`
- `plugins/<plugin-slug>/.mcp.json` — MCP server configuration (when the plugin needs Oxels or other servers)

## Validate changes

```bash
node scripts/validate-template.mjs
```

This checks marketplace paths, plugin manifests, and required frontmatter in rule, skill, agent, and command files.

## Submission checklist

- Each plugin has a valid `.cursor-plugin/plugin.json`
- Plugin names are unique, lowercase, and kebab-case
- `.cursor-plugin/marketplace.json` entries map to real plugin folders
- Required frontmatter metadata exists in plugin content files
- Logo paths resolve correctly from each plugin manifest
- `node scripts/validate-template.mjs` passes
