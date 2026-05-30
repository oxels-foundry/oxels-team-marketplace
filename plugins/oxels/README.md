# Oxels

Plugin for Oxels-backed contract analysis workflows:

- Oxels MCP server
- Contract review, NDA triage, deal history, and related skills

## Install

### Cursor

Install `oxels@oxels-plugins` from this marketplace, or run:

```bash
curl -sSL https://mcp.oxels.com/install | bash
```

### Claude Code

```bash
/plugin marketplace add oxels-foundry/oxels-team-marketplace
/plugin install oxels@oxels-plugins
```

Or:

```bash
OXELS_TARGET=claude curl -sSL https://mcp.oxels.com/install | bash
```

Example skill: `/oxels:oxels-review-contract`
