# Add a plugin

Add a new plugin under `plugins/` and register it in both marketplace manifests:

- `.cursor-plugin/marketplace.json`
- `.claude-plugin/marketplace.json`

## 1. Create plugin directory

Create a new folder:

```text
plugins/my-new-plugin/
```

Add manifests for both hosts:

```text
plugins/my-new-plugin/.cursor-plugin/plugin.json
plugins/my-new-plugin/.claude-plugin/plugin.json
```

Example manifest:

```json
{
  "name": "my-new-plugin",
  "displayName": "My New Plugin",
  "version": "0.1.0",
  "description": "Describe what this plugin does",
  "author": {
    "name": "Your Org"
  },
  "logo": "assets/logo.png",
  "skills": "./skills",
  "mcpServers": "./mcp.json"
}
```

Claude Code ignores unrecognized fields, so one manifest can usually be copied between `.cursor-plugin/` and `.claude-plugin/`. Cursor-specific fields such as `rules` can stay in the Cursor manifest only.

## 2. Add plugin components

Add only the components you need:

- `skills/<skill-name>/SKILL.md` (YAML frontmatter required)
- `agents/*.md` (YAML frontmatter required)
- `commands/*.(md|mdc|markdown|txt)` (frontmatter recommended)
- `hooks/hooks.json` and `scripts/*` for automation hooks
- `mcp.json` for MCP server definitions
- `assets/logo.png` (or similar) for marketplace display
- `rules/` with `.mdc` files for Cursor only

## 3. Register in marketplace manifests

Edit both `.cursor-plugin/marketplace.json` and `.claude-plugin/marketplace.json`, and append a new entry:

```json
{
  "name": "my-new-plugin",
  "source": "./my-new-plugin",
  "description": "Describe your plugin"
}
```

When using `metadata.pluginRoot: "plugins"`, `source` is relative to that directory.

## 4. Validate

```bash
node scripts/validate-template.mjs
claude plugin validate plugins/my-new-plugin
```

Fix all reported errors before committing.

## 5. Common pitfalls

- Plugin `name` not kebab-case.
- `source` path in marketplace manifest does not match folder name.
- Missing `.cursor-plugin/plugin.json` or `.claude-plugin/plugin.json`.
- Missing frontmatter keys (`name`, `description`) in skills, agents, or commands.
- Rule files missing frontmatter `description`.
- Broken relative paths for `logo`, `hooks`, or `mcpServers` in manifest files.
- Updating only one marketplace manifest and forgetting the other host.
