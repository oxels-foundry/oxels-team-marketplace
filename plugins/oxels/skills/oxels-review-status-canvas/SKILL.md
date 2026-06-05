---
name: oxels-review-status-canvas
description: Renders a canvas of the latest contract review status per Salesforce opportunity using Oxels MCP. Use when someone wants the current SFDC file-review status across opportunities — which uploads are blocking close, which rules failed or were not applicable and why, or the review state of a specific opportunity.
metadata:
  short-description: Contract review status canvas per opportunity
---

# Review Status Canvas

**Plugin skill:** `oxels-review-status-canvas`

Show the latest sfdc-file-review result per Salesforce opportunity as a status canvas — which rules passed, failed, or were not applicable on the most recent upload, the reason for each fail/NA, and a link to the opportunity. Read-only, as of the last review (not live document state).

## Before you answer

Run [load-or-find-oxels-skill.md](../../load-or-find-oxels-skill.md) for `oxels-review-status-canvas`, then follow the catalog `body_md` from `get_object` for the user's question. Do not answer from this file alone.
