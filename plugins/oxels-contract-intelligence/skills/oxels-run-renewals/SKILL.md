---
name: oxels-run-renewals
description: Builds a renewal brief by finding upcoming renewals, confirming the operative terms, and surfacing risk, approvals, and next steps.
metadata:
  short-description: Renewal approval and strategy workflow
---

# Run Renewals

Use this skill to produce a forward-looking renewal package for agreements nearing renewal. The job is to identify in-scope contracts, explain the operative renewal position from source text, recommend what to do next, and route the work to the right owners.

## Scope

- Primary audience: `Commercial counsel / legal`
- Primary systems: `Oxels MCP` for contract analysis, `Notion MCP` only when the user wants persistence
- Delivery modes: `Notion mode` or `Chat mode`

Slack is optional and is never the system of record.

## Required decisions

Resolve output mode before any `Notion MCP` write:

1. Use `Notion mode` only if the user explicitly asks to write to Notion, update the `Renewal Approval Engine`, persist rows, or use `Notion MCP`.
2. Use `Chat mode` if the user asks for the full package in chat, markdown only, or says not to use Notion.
3. If unspecified, ask once: `Should I write these results to your Notion workspace (Renewal Approval Engine), or deliver the full renewal package here in chat?`

If the user wants analysis first, you may complete the Oxels analysis before asking again, but do not write to Notion until the mode is confirmed.

## Standing rules

- Use `Oxels MCP` first for corpus search, clause retrieval, full text, amendment chains, and precedent.
- Go to source text. Missing extracted fields do not prove a term is absent.
- Review order forms, not just MSAs.
- Distinguish DPA or security obligations from SKU mentions unless the SKU language independently creates the obligation.
- Never analyze termination for convenience in isolation; pair it with refund, payment, and survival consequences.
- Include section numbers and direct quotes for material conclusions.
- Treat custom security or third-party security paper as manual-review items by default.
- Do not use broad ranked retrieval as absence proof.
- Advise, do not merely extract.
- In `Notion mode`, reuse one stable Notion structure, do not read existing run content before writing, and prefer enriched run pages with narrative sections plus aligned databases. Where a renewal deserves strategy work, it should exist as its own database entry with its own page.

## Workflow

Follow these steps in order for each batch of `15-20` contracts.

### 1. Preflight

- Use a forward-looking cohort only: contracts whose renewal, expiration, or term-end date is on or after today and within the default `30` day horizon.
- Exclude contracts whose relevant dates have already passed.
- Reserve full analysis for `Critical`, `Elevated`, `Auto-Terminates / Action Required`, `Non-Auto-Renew / New Paper Required`, and meaningful `Manual Review Required` items.
- Give `Standard` contracts lightweight cohort coverage only.
- Confirm that every in-scope contract will receive a cohort entry in the chosen output mode.

### 2. Identify the cohort with `Oxels MCP`

Determine the renewal mechanism from source text and amendment-aware review:

- `Auto-Renew`
- `Mutual Agreement / New Order Form Required`
- `Explicit New Agreement Required`
- `Auto-Terminates Unless Action Is Taken`

Use `list_renewals` as the default cohort scan for this step. Prefer:

- `sort_by=days_until_expiry sort_direction=asc` for urgency-first review
- `sort_by=total_amount sort_direction=desc` when triaging the largest renewals first

Treat `renewal_type` and `notice_days` as the operative structured renewal fields returned by `list_renewals`. Note that `notice_days` is sourced from the extracted field `renewal_notification_days`; use that field name when calling `get_agreement_fields` or `retrieve_field_definitions` directly.

For auto-renewing contracts, determine whether the notice window is already passed, closing soon, or still open. If date data is ambiguous, say so and route for follow-up instead of guessing.

### 3. Build the operative position with `Oxels MCP`

Consolidate the current position across the full document stack:

- base agreement
- order forms
- amendment chain
- DPA or privacy addenda
- SLA
- security agreement
- incorporated exhibits
- third-party paper

State the current operative position and where each material point lives. Do not dump documents.

### 4. Extract renewal-relevant evidence with `Oxels MCP`

Capture, for every material finding:

- section number
- direct quote
- source document type
- confidence note when ambiguous

Review at least:

- `Termination and exit`
- `Pricing and financial`
- `Liability and risk`
- `Operational terms`

### 5. Analyze interactions and precedent with `Oxels MCP`

Analyze interacting rights together, including:

- `T4C + refund + payment obligations`
- `Pricing notice + renewal caps + auto-renewal`
- `Data residency + subprocessors + DPA`
- `Assignment / change of control + termination`
- `Order-form economics + MSA boilerplate + amendments`
- `Security agreement obligations + renewal leverage`

Then compare the operative position to standard paper, negotiated patterns, and comparable prior deals. Do not invent precedent; say when support is thin.

### 6. Score the contract

Assign both:

- `Overall Renewal Status`
- `Approval Posture`

Use the organization’s actual approval bands when provided. If none are given, infer relative size from corpus context without inventing numeric thresholds.

Use `Manual Review Required` whenever a material conclusion cannot be verified from source text.

Detailed status rules, routing rules, and weightings are in [reference.md](reference.md).

### 7. Deliver the package

In `Notion mode`:

- Use `Notion MCP` only after Steps 1-6 are complete for the batch.
- Persist under `Renewal Approval Engine`.
- Reuse existing databases and views instead of creating duplicates.
- Write cohort rows for every in-scope contract.
- Upsert queue rows for action items.
- Append evidence rows for material findings and ambiguities.
- Keep the run page highly readable: use narrative sections with real paragraphs, then place the linked database view that supports each section directly beneath it.

In `Chat mode`:

- Do not call `Notion MCP`.
- Deliver the same substance directly in chat: run header, executive summary, cohort, queue, evidence, and Tier 1 contract briefs.

Detailed output schemas and templates are in [reference.md](reference.md).

## Quality bar

Before delivering:

- Confirm conclusions are clause-accurate and amendment-aware.
- Keep quotes and section references next to material conclusions.
- Make interacting terms explicit, not isolated.
- Tell the legal or commercial owner what to do next.
- Mark confidence and ambiguity clearly.
- Use a specific imperative sentence for every `Recommended Action`.

If a contract does not meet this bar, mark it `Manual Review Required` and explain why.

## Delivery tiers

- `Tier 1`: `Critical`, `Elevated`, `Auto-Terminates / Action Required`, `Non-Auto-Renew / New Paper Required`, and meaningful `Manual Review Required`
- `Tier 2`: `Standard`

Every in-scope contract gets a cohort entry. Only Tier 1 gets full evidence and a full contract brief.

## Additional resources

- Detailed scoring, output specs, database schemas, and defaults: [reference.md](reference.md)