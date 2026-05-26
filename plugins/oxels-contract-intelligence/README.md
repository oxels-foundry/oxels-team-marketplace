# Oxels Contract Intelligence

Cursor plugin for Oxels-backed contract analysis.

- **MCP** — `mcp.json`
- **Skills** — title, `name`, when-to-use blurb, link to load doc; workflow from catalog `get_object`
- **Load skill** — [load-or-find-oxels-skill.md](load-or-find-oxels-skill.md)

New skill: add `skills/oxels-<slug>/SKILL.md` with `name` and `description`, link to `load-or-find-oxels-skill.md`. Cache maps `name` → catalog `skill_id` + `namespace` (both discovered via MCP).
