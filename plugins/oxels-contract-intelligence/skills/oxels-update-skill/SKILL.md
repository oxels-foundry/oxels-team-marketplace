---
name: oxels-update-skill
description: Update an existing skill playbook body in the live Oxels catalog.
metadata:
  short-description: Edit a skill playbook body via Oxels MCP
---

# Update Skill

**Plugin skill:** `oxels-update-skill`

Meta workflow for patching live skill `body_md` through Oxels MCP (`get_object`, `run_sql`) .

## Before you proceed

Run [load-or-find-oxels-skill.md](../../load-or-find-oxels-skill.md) for `oxels-update-skill`, then follow the catalog `body_md` from `get_object` for the user's edit request. Do not edit skills from this file alone.