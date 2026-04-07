# Run Renewals Reference

Use this file for the detailed rules that do not need to live in `SKILL.md`.

## Scoring reference

### Overall Renewal Status

Use the highest-severity applicable result.

| Status | Assign when |
| --- | --- |
| `Critical` | Notice deadline has passed, notice deadline is `<= 14` days away, contract auto-terminates unless action is taken, or ACV is in the organization’s large-deal band with material non-standard terms |
| `Elevated` | Notice deadline is `15-30` days away and action is required, ACV is in the organization’s medium-deal-or-above band with meaningful deviations, or pricing or renewal economics require negotiation before renewal |
| `Standard` | Auto-renewing on standard or near-standard terms with no immediate action required |
| `Non-Auto-Renew / New Paper Required` | Source text confirms renewal requires new paper or a new order form |
| `Auto-Terminates / Action Required` | Contract ends unless action is taken before term end |
| `Manual Review Required` | OCR, source quality, amendment-chain gaps, or other evidence issues prevent a reliable conclusion |

### Approval Posture

`Approval Posture` is the routing category. `Approval Required From` should name only the actors who actually need to act.

| Approval Posture | Assign when |
| --- | --- |
| `Commercial Counsel / Legal Review` | Clause interpretation, drafting, amendment work, customer paper, incomplete amendment chain, or source-quality review is required |
| `Commercial Approval` | ACV is medium-or-above, the decision is strategic or commercial, or a policy-level exception is needed |
| `Both Required` | High ACV plus clause work, major customer-paper deviation, or both commercial and legal approval are genuinely needed |
| `Deal Desk / CPQ Coordination Needed` | Renewal needs a new or revised order form, pricing change, or CPQ configuration |
| `Security / Privacy Specialist Review Needed` | Custom security paper, non-standard DPA or residency obligations, or meaningful privacy-mode commitments are present |
| `Monitor Only` | Standard or near-standard auto-renew with no action required |

Routing rules:

- Use `["None required"]` only when `Approval Posture = Monitor Only`.
- Do not force multiple approvers if one actor is enough.
- Weight the decision in this order: ACV or deal size, severity of non-standard terms, renewal mechanism, days to deadline, strategic importance, then document confidence.

## Retrieval and evidence policy

Apply this policy throughout Steps 1-6:

1. Use structured fields to scope the population.
2. Use amendment-aware retrieval before concluding anything.
3. Use clause retrieval for candidate identification and comparison.
4. Escalate to full agreement text when the issue is high-stakes, ambiguous, interaction-heavy, or on customer or third-party paper.
5. Quote source language for all material conclusions.
6. Separate citation-grade findings from manual-review items.

Current MCP notes:

- use `list_renewals` for the cohort scan and rely on `expiry_field_name` to understand which date drove the result
- use `sort_by=days_until_expiry` for urgency ordering and `sort_by=total_amount` for largest-renewal ordering
- use `renewal_type` and `renewal_notification_days` for structured renewal signals

If a value is unclear, do not default immediately. Instead:

1. Attempt clause retrieval on the relevant concept.
2. Retrieve full agreement text and search directly if needed.
3. Check the amendment chain.
4. Check order forms separately.
5. Only then use a default and log the ambiguity.

Every unresolved ambiguity that affects a material conclusion must include:

- `Confidence = Low` or `Manual Review`
- a `Reviewer Note` describing what was attempted and what remains unclear
- a `Risk Level` describing the downside if unresolved before renewal

## Chat output specification

Use this structure in `Chat mode`, in this order:

1. `Run header`: `RUN_ID`, `As Of Date`, number of in-scope contracts, and a note that this is `Chat mode`
2. `Executive summary`: totals, counts by status and approval posture, most urgent deadlines, and headline risks
3. `Cohort`: one row or compact block per in-scope contract
4. `Approval & Review Queue`: every Tier 1 or non-`Monitor Only` action item
5. `Evidence`: every Tier 1 material finding and every material ambiguity
6. `Tier 1 contract briefs`: one subsection per Tier 1 contract
7. `Tier 2`: lightweight cohort rows only

Chat-specific rules:

- Lead with what the legal or commercial owner should do next.
- Keep quotes and section references adjacent to the conclusion they support.
- If the response is too long, summarize in the first message and continue Tier 1 briefs in a second message instead of omitting required fields.
- Do not tell the user to look in Notion for required content.
- Only send a Slack digest in `Chat mode` if the user explicitly asks.

## Notion output specification

Use this only in `Notion mode`.

### Canonical destination

Persist everything under the Notion page titled `Renewal Approval Engine`.

If it does not exist:

1. Ask once whether to create it.
2. If the user confirms and did not provide a parent page, ask once for the parent URL or ID.
3. Create the hub and only the missing databases or views.

If it already exists, reuse it. Do not create a second hub or duplicate master databases.

### Notion policy

- Do not read existing Notion content before writing.
- Do not use Notion as an evidence source; use `Oxels MCP` for contract proof.
- Use only the create and update operations needed to maintain the canonical structure.
- Reuse existing databases and views when present.
- Prefer an enriched page composition with narrative sections, paragraphs, and linked database views aligned directly below the section they support. Where a renewal needs strategic planning, that renewal should also exist as its own database entry with its own page.

### Run variables

Set these at the start of every run:

- `RUN_ID = renewal-run-YYYY-MM-DD`
- `AS_OF_DATE = today's date`
- `RUN_PAGE_TITLE = Renewal Run - YYYY-MM-DD`

### Workspace structure

Maintain one stable workspace:

- `Renewal Cohort`: append one row per in-scope contract per run
- `Approval & Review Queue`: upsert action rows
- `Evidence Log`: append-only evidence and ambiguity rows
- `Renewal Strategy Briefs`: one row per renewal that merits strategic planning; each row is a page containing the full renewal-specific plan
- `Renewal Run - YYYY-MM-DD`: child page with summary and linked views filtered to `Run ID`

### Update rules

| Database | Rule |
| --- | --- |
| `Renewal Cohort` | Append new rows each run, tagged with `Run ID` |
| `Approval & Review Queue` | Upsert on `Agreement ID + Item Type` and preserve owner or status when already in progress |
| `Evidence Log` | Append only; never modify existing rows |
| `Renewal Strategy Briefs` | Create or upsert one row per strategic renewal brief; the row page is the canonical enriched brief for that renewal |

Every row in every database must include `Run ID` and `As Of Date`.

## Defaults and completeness

No property may be left blank unless the field rule below explicitly allows it.

### Default policy

| Field type | Unknown | Confirmed absent |
| --- | --- | --- |
| Text | `Not identified` | `None` |
| Select | `Unknown` or closest option | `None` |
| Multi-select | `["Unknown"]` | `["None"]` |
| Checkbox | `false` | `false` |
| Number | blank only for ACV if truly unavailable; otherwise `0` for day counts | `0` |
| Date | blank only if no date can be inferred; explain in `Recommended Action` | n/a |

### Specific defaults

- `ACV`: may be blank only if truly unavailable; say `ACV not available` in `Recommended Action`
- `Renewal Date`: if unknown, leave blank and flag `Manual Review Required`
- `Notice Deadline`: calculate from source; if notice period is unknown, use `Renewal Date` and note the limitation
- `Days to Deadline`: days from today to notice deadline; use `0` if passed
- `Refund Exposure`: `Unknown`
- `Price Cap Type`: `Unknown`
- `Liability Position`: `Unknown`
- `Approval Required From`: `["None required"]` only when `Approval Posture = Monitor Only`
- `Recommended Action`: always a specific imperative sentence
- `Evidence Confidence`: `Low` when the source could not be confirmed

### Confidence levels

| Level | Meaning |
| --- | --- |
| `High` | Direct quote with section number from retrieved source and an unambiguous conclusion |
| `Medium` | Reasonable inference with partial quote or approximate citation |
| `Low` | Metadata-only, partially extracted, or ambiguous source |
| `Manual Review` | Human review is required; do not guess |

## Database schemas

These field names are the source of truth for `Notion mode`. In `Chat mode`, use the same field names and semantics in markdown tables or compact blocks.

### Renewal Cohort

One row per in-scope contract per run.

- `Title`: Customer - agreement short name
- `Customer`
- `Agreement ID`
- `ACV`
- `Renewal Date`
- `Notice Deadline`
- `Days to Deadline`
- `Renewal Mechanism`
- `Overall Renewal Status`
- `Approval Posture`
- `Deal ID`
- `Deal Owner`
- `Agreement Type`
- `Governing Document Stack`
- `Counterparty Paper`
- `T4C Present`
- `Refund Exposure`
- `Price Cap Type`
- `Pricing Notice Days`
- `Liability Position`
- `Data Residency`
- `Security Agreement Present`
- `Needs Manual Review`
- `Recommended Action`
- `Approval Required From`
- `CPQ / Deal Desk Trigger`
- `Run ID`
- `As Of Date`

Preferred display order:

`Title -> Customer -> ACV -> Renewal Date -> Notice Deadline -> Days to Deadline -> Overall Renewal Status -> Approval Posture -> Renewal Mechanism -> remaining properties`

### Approval & Review Queue

One row per action requiring sign-off, escalation, coordinated action, or manual review.

- `Title`
- `Run ID`
- `Customer`
- `Agreement ID`
- `Item Type`: `Approval`, `Manual Review`, or `Deal Desk Coordination`
- `Approval Posture`
- `Approval Required From`
- `Approval Reason`
- `Renewal Mechanism`
- `Overall Renewal Status`
- `Recommended Action`
- `Owner`
- `Due Date`
- `Status`
- `Blocking Issue`
- `CPQ / Deal Desk Needed`
- `Manual Review Reason`
- `Missing / Ambiguous Document`
- `Risk if Unresolved`
- `Source Confidence`
- `As Of Date`
- `Relation -> Cohort`

### Evidence Log

One row per material finding or unresolved ambiguity. Append only.

- `Title`
- `Run ID`
- `Customer`
- `Agreement ID`
- `Provision Family`
- `Risk Level`
- `Source Document Type`
- `Section Number`
- `Quote`
- `Interconnected With`
- `Confidence`
- `Reviewer Note`
- `As Of Date`
- `Relation -> Cohort`

### Renewal Strategy Briefs

One row per upcoming renewal that merits strategic planning, especially Tier 1 renewals. Each row must be a page that contains the full enriched brief for that renewal.

- `Title`
- `Run ID`
- `Customer`
- `Agreement ID`
- `Deal ID`
- `Renewal Date`
- `Overall Renewal Status`
- `Approval Posture`
- `Primary Owner`
- `Strategy Status`
- `Recommended Renewal Strategy`
- `Top Risks`
- `Key Negotiation Themes`
- `Approvals Needed`
- `Next Decision`
- `Due Date`
- `Confidence`
- `As Of Date`
- `Relation -> Cohort`
- `Relation -> Approval & Review Queue`
- `Relation -> Evidence Log`

## Tiered delivery rules

`Tier 1 - Full Analysis` applies to:

- `Critical`
- `Elevated`
- `Auto-Terminates / Action Required`
- `Non-Auto-Renew / New Paper Required`
- meaningful `Manual Review Required`

For Tier 1 contracts:

- populate all cohort properties
- create or output queue entries
- create or output evidence items
- create a `Renewal Strategy Briefs` row in Notion when the contract merits strategic planning; the row page is the detailed brief

`Tier 2 - Lightweight Row` applies to `Standard`.

For Tier 2 contracts:

- populate the cohort row with timing, status, mechanism, IDs, and run metadata
- do not do deep clause extraction unless something becomes non-standard
- do not create evidence or a full brief unless the contract stops being `Standard`

## Run page structure

The Notion run page should include:

- an executive summary with totals, counts by status, counts by approval posture, urgent deadlines, notable changes, and callouts for auto-terminations, active notice windows, and `Both Required`
- linked views filtered to the current `Run ID` for cohort, queue, evidence, and strategy briefs

Readability rules:

- Keep the page order top-down: overview, cohort, queue, evidence, then strategy briefs.
- Put each linked database view directly beneath its explanatory heading.
- Favor rich but controlled narrative sections, curated visible properties, and filtered views over dense prose or overly wide tables.
- Use property ordering that matches how a reviewer scans the workflow: urgency, owner, action, evidence.
- Let users click from the run page into the relevant `Renewal Strategy Briefs` row page for the full deal-specific plan.

Each `Renewal Strategy Briefs` page should include:

- header fields
- renewal context and current posture
- governing documents
- non-standard provisions or key issues table
- practical renewal position
- approval recommendation
- historical precedent
- recommended renewal strategy
- action plan and decision points
- evidence appendix
- caveats

## Persistent views

Preserve these views on the master databases:

- Cohort: latest run, next `30` days, critical or elevated, auto-terminates, non-standard pricing, manual review, grouped-by-status, all contracts this run
- Queue: all open, legal review, commercial approval, both required, Deal Desk or CPQ, due this week, overdue, manual reviews, security agreements
- Evidence: high-risk provisions, grouped by provision family, low-confidence items
- Strategy Briefs: active strategic renewals, due soon, legal-led, commercial-led, both-required, awaiting decision

## Slack digest

Slack is optional. Use it only after the Notion run is complete, unless the user explicitly asks for a chat-only digest.

Include:

- run date and `RUN_ID`
- total contracts in scope
- counts by renewal status
- counts by approval posture
- top `3-5` urgent deadlines
- top `3-5` highest-priority contracts with one-line summaries
- notable changes since the prior run
- link to the Notion run page when one exists
- callouts for any auto-terminating contract, active notice-window issue, or `Both Required` contract

Keep the digest short and action-oriented.
