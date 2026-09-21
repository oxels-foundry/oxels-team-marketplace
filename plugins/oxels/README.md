# Oxels

Oxels is an MCP-backed contract intelligence plugin for legal, sales, and
revenue workflows over a tenant's commercial contract corpus.

The plugin includes:

- the Oxels MCP server connection (`https://sandwich.oxels.com/mcp`)
- contract review, NDA triage, deal history, opportunity reconciliation, and
  playbook-management skills
- discovery/search tools and approved playbook or workflow update tools

## Install

### Cursor

Install `oxels@oxels-plugins` from this marketplace, or run:

```bash
curl -sSL https://sandwich.oxels.com/install | bash
```

### Claude Code

```bash
/plugin marketplace add oxels-foundry/oxels-team-marketplace
/plugin install oxels@oxels-plugins
```

Or:

```bash
OXELS_TARGET=claude curl -sSL https://sandwich.oxels.com/install | bash
```

Example skill: `/oxels:oxels-review-contract`

## MCP Server

The plugin registers one production MCP server named `oxels`:

```json
{
  "mcpServers": {
    "oxels": {
      "type": "http",
      "url": "https://sandwich.oxels.com/mcp"
    }
  }
}
```

The server uses OAuth bearer-token authentication. After login, access is scoped
by tenant, user, and namespace. A user can only bind sessions for namespaces
granted to their identity.

## Tool Model

Oxels provides tools for:

- discovering available contract data, skills, and recipes
- searching contract text and related records
- running approved read workflows
- making approved playbook or workflow updates when the user has access

## Data Handling

Oxels only accesses data available to the authenticated workspace and user.
Responses are scoped to the permissions granted for that workspace.

Operational logs are used to monitor and debug the service. Secrets and bearer
tokens are redacted.

## Support

For connector support or review questions, contact `eng@oxels.com`.
