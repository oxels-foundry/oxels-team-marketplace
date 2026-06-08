---
name: oxels-reconcile-opportunity
description: Reconcile a closed-won Salesforce opportunity against its signed contract documents using Oxels MCP. Use when someone wants to check whether an opportunity's Salesforce fields — totals, subscription term, dates, payment and billing terms, special terms — match the executed order form, surface deals whose CRM data disagrees with the signed paper, or get a clean field-by-field comparison for a deal. Resolve the deal by opportunity id or by company / opportunity name.
metadata:
  short-description: Reconcile a won opportunity's Salesforce fields against its signed contract
---

# Reconcile Opportunity

**Plugin skill:** `oxels-reconcile-opportunity`

Compare a closed-won Salesforce opportunity's data (the opportunity plus its primary quote) against what the signed documents actually say, and return a clean, neutral field-by-field reconciliation of every match and mismatch — totals, subscription term, dates, payment and billing terms, special terms. Resolve the deal by opportunity id or by company / opportunity name. Reads the structured extraction first and falls back to the document text only to fill gaps. Closed-won only.

## Before you answer

Run [load-or-find-oxels-skill.md](../../load-or-find-oxels-skill.md) for `oxels-reconcile-opportunity`, then follow the catalog `body_md` from `get_object` for the user's question. Do not answer from this file alone.
