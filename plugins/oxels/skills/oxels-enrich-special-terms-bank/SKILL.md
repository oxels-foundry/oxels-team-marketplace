---
name: oxels-enrich-special-terms-bank
description: Propose canonical special-terms clause wording from recently closed-won order forms using Oxels MCP. Sweeps order forms in a close-date window, clusters clauses by what they do, and proposes one canonical wording per recurring term. Proposal-only — surfaces candidates with evidence; does not write the corpus.
metadata:
  short-description: Propose canonical special-terms wording from recent order forms
---

# Enrich Special Terms Bank

**Plugin skill:** `oxels-enrich-special-terms-bank`

Standardize how special terms are papered. Review the special-terms language on order forms closed in a recent window (default the last two weeks), cluster clauses by what they do rather than how they are worded, and propose one canonical wording per recurring term. Each candidate is surfaced with source order forms and quoted evidence; genuine differences between variants are flagged. Proposal-only and read-only — it does not write the approved bank.

## Before you answer

Run [load-or-find-oxels-skill.md](../../load-or-find-oxels-skill.md) for `oxels-enrich-special-terms-bank`, then follow the catalog `body_md` from `get_object` for the user's question. Do not answer from this file alone.
