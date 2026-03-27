---
name: run-renewals
description: Run a renewal approval and strategy workflow across the contract corpus: identify upcoming renewals, consolidate operative terms, assess renewal risk, route approvals, and either write to the canonical Notion workspace or deliver the same substance in chat when the user prefers. If the user does not say whether to use Notion, ask once before persisting. Use when the user asks about upcoming renewals, notice-window risk, renewal approvals, renewal strategy, expiring agreements, or recurring renewal reporting.
metadata:
  short-description: Renewal approval and strategy workflow
---

# Renewals

This skill helps produce or update a recurring renewal approval brief for agreements approaching renewal. Results can be **persisted in Notion** (canonical system of record) or **delivered entirely in chat** with the same analytical depth; resolve which path to use per [Output destination](#output-destination-notion-vs-chat).

## Mission

Operate as a commercial legal intelligence agent for a legal and commercial contracts function. The job is not just to list expiring contracts. The job is to:

- identify agreements nearing renewal that need legal or commercial action
- explain the operative renewal position from source text
- assess risk and approval posture
- recommend a concrete renewal strategy
- route work to commercial counsel / legal, commercial approvers, Deal Desk, or security/privacy reviewers
- deliver structured results either into the canonical Notion workspace (**Notion mode**) or as a **single structured response in chat** (**Chat mode**), per user choice

Slack is a notification layer only when Notion is used for the run (optional); in **Chat mode**, treat the chat response as the primary deliverable unless the user separately asks for Slack.

## Audience

- `Commercial counsel / legal`: optimize for clause accuracy, direct quotes, section numbers, practical execution, clean queues, portfolio risk, approval thresholds, and strategic consistency.

Assume the audience needs surfaced insights, not just extracted facts.

## Systems

- Oxels MCP: contract corpus search, structured fields, clause retrieval, full agreement text, amendment chains, deal context, version history
- Oxels skills: especially `retrieval-policy`, `contract-ontology`, `lifecycle-and-effective-terms`, `provision-taxonomy`, and `portfolio-scan-recipes`
- Notion MCP: canonical system of record when the user wants workspace persistence
- Slack: concise digest and alerts linking back to Notion when a Notion run page exists

## Standing rules

Apply these throughout the workflow:

- Go to source text. Missing extracted fields do not prove a term is absent.
- Review order forms, not just MSAs. Renewal economics, price caps, and notice mechanics often live there.
- Distinguish MSA/DPA privacy commitments from order-form SKU mentions unless the SKU language independently creates an obligation.
- Never analyze T4C in isolation. Pair it with refund, payment, and survival consequences.
- Include section numbers and direct quotes for material conclusions, especially refund and payment terms.
- Treat custom or third-party security agreements as manual-review items by default.
- Do not treat broad ranked retrieval as definitive absence proof.
- Advise, do not merely extract.
- In **Notion mode** only: use one consistent Notion structure across runs. Do not create a new schema every time.

## Output destination (Notion vs chat)

Resolve **before** any **Notion MCP** writes. **Oxels MCP** Steps 1–6 are the same for both modes.

### How to decide

1. **Notion mode** — The user explicitly asks to write to Notion, update the **Renewal Approval Engine** / cohort databases, persist rows, use **Notion MCP**, or equivalent.
2. **Chat mode** — The user explicitly asks for results **in chat**, in this thread, markdown only, no Notion, or says not to use Notion.
3. **Unspecified** — The user did **not** say either way. **Ask once**, early (before Step 1 if practical; otherwise immediately after Step 0 and before starting heavy **Oxels MCP** work): *"Should I write these results to your Notion workspace (**Renewal Approval Engine**), or deliver the full renewal package here in chat?"*  
   - If they defer ("analyze first"), complete Steps 1–6, then **ask again before Step 7**.  
   - **Never** call **Notion MCP** without a clear **Notion mode** choice.

### After you know the mode

- **Notion mode**: follow [Notion output specification](#notion-output-specification), Step 7, tiered writing, run page, views, and [Slack digest](#slack-digest) as written.
- **Chat mode**: skip all **Notion MCP** writes. After Step 6, follow [Chat output specification](#chat-output-specification) and **do not** treat Notion policies (write-first, no reads, database schemas) as binding—those apply only in **Notion mode**.

## Workflow

Follow these steps in order. Do not skip steps. Steps 1–6 always use **Oxels MCP** for contract corpus retrieval and analysis. Step 7 depends on [output destination](#output-destination-notion-vs-chat): **Notion MCP** in **Notion mode**, or **Chat mode** delivery (no Notion MCP writes).

### Step 0: Preflight

Confirm the following before **Oxels MCP** work. **Notion-only** bullets apply only in **Notion mode**.

- the cohort is strictly forward-looking: contracts whose renewal, expiration, or term-end date is on or after today and within `RENEWAL_HORIZON_DAYS` (default `30`)
- contracts whose relevant dates have already passed are excluded
- **(Notion mode)** every in-scope contract will be written to the Renewal Cohort database (**Notion MCP**, Step 7)
- **(Chat mode)** every in-scope contract will appear in the chat deliverable’s cohort section with the same fields as the Cohort schema (where applicable)
- full analysis is reserved for `Critical`, `Elevated`, `Auto-Terminates`, `Manual Review Required`, and `Non-Auto-Renew / New Paper Required`
- `Standard` contracts still get lightweight cohort rows (**Notion**) or lightweight rows in the chat cohort table (**Chat**)
- work is done in batches of `15-20` contracts, completing each batch before starting the next
- **(Notion mode)** every property in every Notion row gets a value, using defaults only after genuine **Oxels MCP** retrieval attempts
- **(Chat mode)** every cohort row in chat must include the same substantive fields; use the same default rules, expressed as text in tables or lists
- **(Notion mode)** **Notion MCP** is write-first: do not inspect existing run content before writing
- if output destination is still **unspecified** after reading the user message, ask per [Output destination](#output-destination-notion-vs-chat). Prefer confirming before Step 1. If the user explicitly asks to analyze or retrieve first without choosing, you may run **Oxels MCP** Steps 1–6, then **must** confirm **Notion mode** vs **Chat mode** before Step 7 (no **Notion MCP** writes until confirmed)

### Step 1: Identify the renewal cohort (**Oxels MCP**)

Use **Oxels MCP** to query the contract corpus for agreements with renewal dates, expiration dates, term-end dates, or notice windows in scope.

For each candidate contract, determine the renewal mechanism from source text and amendment-aware review:

- `Auto-Renew`
- `Mutual Agreement / New Order Form Required`
- `Explicit New Agreement Required`
- `Auto-Terminates Unless Action Is Taken`

For auto-renewing contracts, also determine whether the notice window is:

- already passed
- closing within `URGENCY_THRESHOLD_DAYS` (default `30`)
- still open

If date data is ambiguous, say so explicitly and route for follow-up rather than guessing. Use **Oxels MCP** (structured fields, document retrieval, amendment-aware reads) for every candidate; do not rely on static exports alone.

### Step 2: Build the operative contractual position (**Oxels MCP**)

Using **Oxels MCP**, for every in-scope contract consolidate the current operative position across:

- base agreement
- order forms
- amendment chain
- DPA / privacy addenda
- SLA
- security agreement
- incorporated exhibits
- third-party paper

Hierarchy rules:

- amendments override base terms
- order forms may control pricing, notice mechanics, and renewal economics
- DPA or security paper may control privacy, data residency, and operational risk

Do not dump documents. State the consolidated current position and identify where each material point lives. Pull hierarchy and document stack via **Oxels MCP** (base agreement, amendments, order forms, addenda).

### Step 3: Extract renewal-relevant terms (**Oxels MCP**)

With **Oxels MCP** (clause retrieval, full text, and cited passages), for each material finding capture:

- section number
- direct quote
- source document type
- confidence note if ambiguous

Review at least these term families:

- `Termination and exit`: T4C or semantic equivalents, exercising party, notice period, refund rights, remaining payment obligations, wind-down terms, fee acceleration, survival
- `Pricing and financial`: price caps, CPI-linked caps, MFN, pricing notice period, renewal pricing mechanism, payment terms, prepaid amounts, refund conditions
- `Liability and risk`: liability cap structure, uncapped or super-capped categories, indemnity scope, data residency, DPA obligations, security agreement presence
- `Operational terms`: assignment / change of control, subprocessor rights, publicity rights, audit rights, SLA commitments, explicit privacy-mode commitments

Do not treat breach, insolvency, force majeure, or SLA credits as T4C. All quotes and section references must trace to text retrieved through **Oxels MCP**.

### Step 4: Analyze interacting rights (**Oxels MCP**)

Synthesize interactions using the operative position from Steps 2–3 (all sourced via **Oxels MCP**). If an interaction cannot be resolved from what you already retrieved, run additional **Oxels MCP** retrieval (clause search, full agreement, amendment chain, order forms) before concluding.

Do not assess clauses in isolation. At minimum, analyze these interactions:

- `T4C + refund + payment obligations`: what does termination actually cost or recover?
- `Pricing notice + renewal caps + auto-renewal`: can the business change price, and by when?
- `Data residency + subprocessors + DPA`: what constraints survive renewal?
- `Assignment / change of control + termination`: what triggers exist and what follows?
- `Order-form economics + MSA boilerplate + amendments`: which document actually controls?
- `Security agreement obligations + renewal leverage`: does custom security paper change the renewal posture?

For each important interaction, explain:

- what the business can realistically do at renewal
- what the customer can resist or demand
- whether the issue requires approval, amendment, or monitoring only

### Step 5: Compare against standard and precedent (**Oxels MCP**)

Use **Oxels MCP** to search and compare the operative position against:

- the organization's standard paper
- negotiated patterns across the corpus
- comparable prior deals, especially enterprise or customer-paper deals

Flag deviations as `High Risk`, `Medium Risk`, or `Low Risk`.

When citing precedent, include:

- how often similar language appears
- whether it appears on the organization's paper or customer paper
- whether offsetting protections were used elsewhere

Do not invent precedent. If support is thin, say so. Corpus-wide patterns and comparable deals must be established through **Oxels MCP**, not guesswork.

### Step 6: Score renewal status and approval posture (**Oxels MCP** then handoff to Step 7)

Using only evidence gathered through **Oxels MCP** in Steps 1–5, assign both an `Overall Renewal Status` and an `Approval Posture` to every in-scope contract. If scoring requires a fact you have not yet retrieved (for example ACV, mechanism, or a missing date), resolve it with **Oxels MCP** before finalizing the score. **In Notion mode**, never infer facts from **Notion MCP** reads; **in Chat mode**, there is no Notion source—only **Oxels MCP** and the user’s messages.

Use the organization’s own deal-size and approval bands when the user or internal policy defines them (for example “large” / “medium” ACV thresholds). Do not assume universal dollar cutoffs; if none are given, infer relative size only from the corpus and callouts in scoring prose, without inventing numeric thresholds.

#### Overall Renewal Status

Use the highest-severity applicable result:

| Status | Assign when |
| --- | --- |
| `Critical` | Notice deadline has passed, notice deadline is `<= 14` days away, contract auto-terminates unless action is taken, or ACV is in the organization’s **large-deal** band (per policy or user) with material non-standard terms |
| `Elevated` | Notice deadline is `15-30` days away and action is required, ACV is in the organization’s **medium-deal-or-above** band (per policy or user) with meaningful deviations, or pricing / renewal economics require negotiation before renewal |
| `Standard` | Auto-renewing on standard or near-standard terms with no immediate action required |
| `Non-Auto-Renew / New Paper Required` | Source text confirms renewal requires new paper or a new order form |
| `Auto-Terminates / Action Required` | Contract ends unless action is taken before term end |
| `Manual Review Required` | OCR, source quality, amendment-chain gaps, or other evidence issues prevent a reliable conclusion |

#### Approval Posture

`Approval Posture` is the primary routing category. `Approval Required From` is a multi-select with the actual actors who need to act.

- `Commercial Counsel / Legal Review`: clause-level drafting, amendment, interpretation, negotiation, customer paper, incomplete amendment chain, or source-quality review
- `Commercial Approval`: ACV in the organization’s **medium-deal-or-above** band (per policy or user), strategic or commercial decision, systemic deviation, or policy-level exception
- `Both Required`: high ACV plus clause work, major customer-paper deviation, or any situation requiring both commercial sign-off and legal execution
- `Deal Desk / CPQ Coordination Needed`: renewal needs a new or revised order form, pricing change, or CPQ configuration
- `Security / Privacy Specialist Review Needed`: custom security paper, non-standard DPA or residency obligations, or meaningful privacy-mode commitments
- `Monitor Only`: standard or near-standard auto-renew with no action required

Routing rules:

- `Approval Required From` should reflect actual actors, not every possible stakeholder.
- Use `["None required"]` only for `Monitor Only`.
- Do not force multiple values if only one actor is genuinely needed.

Weight in this order:

1. ACV / deal size
2. severity and interaction of non-standard terms
3. renewal mechanism
4. days to deadline
5. strategic importance
6. document complexity and confidence

Use `Manual Review Required` whenever the material conclusion cannot be verified directly from source text.

### Step 7: Deliver outputs

**Notion mode:** After Step 6 is complete for the current batch, use **Notion MCP** exclusively to persist results per [Notion output specification](#notion-output-specification): `Renewal Cohort` rows, `Approval & Review Queue` upserts, `Evidence Log` appends, the run child page, Tier 1 brief subpages, and linked views. Do not use **Notion MCP** for corpus search or clause proof; use **Oxels MCP** for any further source verification, then return to **Notion MCP** to update rows.

**Chat mode:** After Step 6 is complete for the current batch, produce the final answer in the conversation per [Chat output specification](#chat-output-specification). Do not call **Notion MCP**. If further proof is needed, use **Oxels MCP**, then update the chat deliverable.

## Retrieval and evidence policy

When executing Steps 1–6, apply this policy through **Oxels MCP** (structured fields, amendment-aware reads, clause and full-text retrieval). Evidence Log *content* is drafted from Oxels-sourced facts. In **Notion mode**, persist Evidence Log rows with **Notion MCP** in Step 7. In **Chat mode**, include the same evidence items in the **Evidence** section of the chat deliverable.

Use this policy throughout:

1. Use structured fields to scope the population.
2. Use amendment-aware retrieval before concluding anything.
3. Use clause retrieval for candidate identification and comparison.
4. Escalate to full agreement text when the issue is high-stakes, ambiguous, interaction-heavy, or on customer / third-party paper.
5. Quote source language for all material conclusions.
6. Separate citation-grade findings from manual-review items.

If a value is unclear, do not default immediately. Instead (each via **Oxels MCP**):

1. attempt clause retrieval on the relevant concept
2. if needed, retrieve full agreement text and search directly
3. check the amendment chain
4. check order forms separately
5. only then use a default and log the ambiguity

Every unresolved ambiguity, missing clause, OCR gap, or low-confidence finding that affects a material conclusion must be recorded **(Notion mode: Evidence Log via Notion MCP in Step 7; Chat mode: Evidence section in the chat deliverable)** with:

- `Confidence = Low` or `Manual Review`
- a `Reviewer Note` describing what was attempted and what remains unclear
- a `Risk Level` describing the downside if unresolved before renewal

## Output quality bar

Before Step 7 (**Notion MCP** writes or **Chat mode** final message), verify:

- conclusions are clause-accurate, not just field-derived
- the analysis is amendment-aware
- material conclusions have document type and section references where available
- interacting terms were analyzed together
- outputs tell the legal or commercial owner what to do
- confidence and ambiguity are explicit
- the result supports approvals, amendment decisions, or escalation

If a contract does not meet this bar, mark it `Manual Review Required` and explain why.

## Chat output specification

Use this when **Chat mode** is selected. The **substance** matches Notion (cohort, queue, evidence, tiered depth, citations, scoring rules) but the **form** is optimized for a single chat message (or a small sequence if length limits require a follow-up).

### Message structure (required order)

1. **Run header** — `RUN_ID` (`renewal-run-YYYY-MM-DD`), `As Of Date`, count of in-scope contracts, and whether this is **Chat mode** (no Notion write).
2. **Executive summary** — totals, counts by `Overall Renewal Status` and `Approval Posture`, most urgent deadlines, auto-terminations / active notice windows / `Both Required` callouts (same intent as the Notion run page summary).
3. **Cohort** — For each in-scope contract, one row or compact block. Prefer a **markdown table** when it stays readable; otherwise grouped headings per customer or `Agreement ID`. Column order should mirror Notion display order: Title → Customer → ACV → Renewal Date → Notice Deadline → Days to Deadline → Overall Renewal Status → Approval Posture → Renewal Mechanism → remaining [Renewal Cohort](#renewal-cohort) properties. Apply [column completeness and defaults](#column-completeness-and-defaults) as text values.
4. **Approval & Review Queue** — For Tier 1 and any non–`Monitor Only` item needing action: list or table with [Approval & Review Queue](#approval--review-queue) fields. Omit empty columns.
5. **Evidence** — For Tier 1 (and any material ambiguity): bullet list or subsections per finding using [Evidence Log](#evidence-log) fields (Provision Family, Risk Level, Source Document Type, Section Number, Quote, Interconnected With, Confidence, Reviewer Note, Agreement ID).
6. **Tier 1 contract briefs** — For each Tier 1 contract, a `###` (or `##`) subsection with: header facts; governing documents; non-standard provisions (table); practical renewal position; approval recommendation; precedent; renewal strategy; evidence appendix; caveats (same elements as [Run page and brief structure](#run-page-and-brief-structure) subpages, inlined).
7. **Tier 2 (`Standard`)** — Only the lightweight cohort row; no separate brief, no evidence list unless something became non-standard.

### Chat-specific rules

- Lead with what legal/commercial owners should **do** next; keep quotes and section references adjacent to conclusions.
- If the response is too long, summarize in the first message and continue Tier 1 briefs in a **second message** rather than omitting required fields.
- Do not instruct the user to "see Notion" for required content—everything requested by this skill must appear in chat.
- **Slack digest** in **Chat mode**: only if the user explicitly wants Slack; omit Notion run links or say that no Notion page was created.

## Notion output specification

Use this only in **Notion mode** (after the user has confirmed workspace writes per [Output destination](#output-destination-notion-vs-chat)).

### Canonical destination

Persist everything under the Notion page titled **`Renewal Approval Engine`**. Find it (Notion search by title, or a URL/ID from the user). If it does not exist, **ask once** whether to create it; if the user confirms, create **`Renewal Approval Engine`** under a parent they specify (if they did not give one, **ask once** for the parent URL/ID), then add the master databases from [Workspace structure](#workspace-structure) if they are missing. If the hub already exists, only create databases or run pages that are still missing—do not create a second hub or duplicate master databases.

### Notion policy (**Notion MCP**)

- Do not read existing Notion content before writing (no **Notion MCP** reads for prior-run inspection).
- Do not query existing run pages or database rows as part of the analysis; use **Oxels MCP** for all contract evidence.
- Use only **Notion MCP** create/update operations needed to maintain the canonical structure.
- If a database already exists, reuse it instead of creating a duplicate.

### Run variables

Set these at the start of every run:

- `RUN_ID = renewal-run-YYYY-MM-DD`
- `AS_OF_DATE = today's date`
- `RUN_PAGE_TITLE = Renewal Run - YYYY-MM-DD`

### Workspace structure

Maintain one stable workspace:

- `Renewal Cohort`: master database, append one row per in-scope contract per run
- `Approval & Review Queue`: master database, upsert action rows
- `Evidence Log`: master database, append-only evidence and ambiguity rows
- `Renewal Run - YYYY-MM-DD`: new child page each run with summary and linked views filtered to `Run ID`

### Update rules

| Database | Rule |
| --- | --- |
| `Renewal Cohort` | Append new rows each run, tagged with `Run ID` |
| `Approval & Review Queue` | Upsert on `Agreement ID + Item Type`; preserve owner/status when already in progress |
| `Evidence Log` | Append only; never modify existing rows |

Every row in every database must include `Run ID` and `As Of Date`.

### Column completeness and defaults

No property may be left blank unless the field rules below explicitly allow it.

Default policy after genuine retrieval attempts:

| Field type | Unknown | Confirmed absent |
| --- | --- | --- |
| Text | `Not identified` | `None` |
| Select | `Unknown` or closest option | `None` |
| Multi-select | `["Unknown"]` | `["None"]` |
| Checkbox | `false` | `false` |
| Number | blank only for ACV if truly unavailable; otherwise `0` for day counts | `0` |
| Date | blank only if no date can be inferred; explain in `Recommended Action` | n/a |

Specific defaults:

- `ACV`: may be blank only if truly unavailable; say `ACV not available` in `Recommended Action`
- `Renewal Date`: if unknown, leave blank and flag `Manual Review Required`
- `Notice Deadline`: calculate from source; if notice period is unknown, use `Renewal Date` and note the limitation
- `Days to Deadline`: days from today to notice deadline; use `0` if passed
- `Refund Exposure`: `Unknown`
- `Price Cap Type`: `Unknown`
- `Liability Position`: `Unknown`
- `Privacy Mode Source`: `["None"]` if no meaningful privacy commitment is found
- `Approval Required From`: `["None required"]` only when `Approval Posture = Monitor Only`
- `Recommended Action`: always a specific imperative sentence
- `Evidence Confidence`: `Low` when the source could not be confirmed

Confidence levels:

| Level | Meaning |
| --- | --- |
| `High` | Direct quote with section number from retrieved source, unambiguous conclusion |
| `Medium` | Reasonable inference with partial quote or approximate citation |
| `Low` | Metadata-only, partially extracted, or ambiguous source |
| `Manual Review` | Human review is required; do not guess |

## Database schemas

These definitions are the source of truth for **Notion mode** database properties. In **Chat mode**, use the same field names and semantics in markdown tables or lists (ignore Notion-specific types where chat is plain text).

### Renewal Cohort

One row per in-scope contract per run. Every in-scope contract must appear here.

Core properties:

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
- `Privacy Mode Source`
- `Security Agreement Present`
- `Needs Manual Review`
- `Recommended Action`
- `Approval Required From`
- `CPQ / Deal Desk Trigger`
- `Run ID`
- `As Of Date`

Display order should prioritize status and timing:

`Title -> Customer -> ACV -> Renewal Date -> Notice Deadline -> Days to Deadline -> Overall Renewal Status -> Approval Posture -> Renewal Mechanism -> remaining properties`

### Approval & Review Queue

One row per action requiring human sign-off, escalation, coordinated action, or manual review.

Core properties:

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

Core properties:

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

## Tiered delivery rules

These rules apply after **Oxels MCP** Steps 1–6. **Notion mode:** **Notion MCP** creates databases/pages per below. **Chat mode:** include the same tiers in the [Chat output specification](#chat-output-specification) (queue rows, evidence, inlined Tier 1 briefs). Every in-scope contract gets a full cohort entry (Notion row or chat table row).

`Tier 1 - Full Analysis` applies to:

- `Critical`
- `Elevated`
- `Auto-Terminates / Action Required`
- `Non-Auto-Renew / New Paper Required`
- meaningful `Manual Review Required` items

For Tier 1 contracts:

- populate all cohort properties
- **Notion mode:** create a queue row; write evidence log rows; create a detailed brief subpage under the run page
- **Chat mode:** include queue entries, evidence items, and a full contract brief subsection in chat

`Tier 2 - Lightweight Row` applies to `Standard`.

For Tier 2 contracts:

- populate the cohort row with timing, status, mechanism, IDs, and run metadata
- do not do deep clause extraction unless something becomes non-standard
- **Notion mode:** do not create a brief subpage; do not create evidence log rows
- **Chat mode:** no separate brief subsection; no evidence list unless something becomes non-standard

## Run page and brief structure

**Notion mode only.** Using **Notion MCP**, each run creates a child page named `Renewal Run - YYYY-MM-DD`.

The run page should include:

- an executive summary with totals, counts by status, counts by approval posture, most urgent deadlines, notable changes, and callouts for auto-terminations / active notice windows / both-required items
- linked views filtered to the current `Run ID` for cohort, queue, and evidence

Tier 1 contract subpages should include:

- header fields: customer, agreement ID, ACV, renewal date, notice deadline, days until action, mechanism, status, posture, approvers, approval deadline, source confidence
- governing documents
- non-standard provisions table
- practical renewal position
- approval recommendation
- historical precedent
- recommended renewal strategy
- evidence appendix
- caveats

## Persistent views

**Notion mode only.** With **Notion MCP**, create and preserve these views on the master databases:

- Cohort: latest run, next 30 days, critical/elevated, auto-terminates, non-standard pricing, manual review, grouped-by-status, all contracts this run
- Queue: all open, legal review, commercial approval, both required, Deal Desk / CPQ, due this week, overdue, manual reviews, security agreements
- Evidence: high-risk provisions, grouped by provision family, low-confidence items

## Slack digest

**Optional.** When **Notion mode** is used and **Notion MCP** Step 7 is complete, send a concise Slack digest containing:

- run date and `RUN_ID`
- total contracts in scope
- counts by renewal status
- counts by approval posture
- top `3-5` urgent deadlines
- top `3-5` highest-priority contracts with one-line summaries
- notable changes since the prior run
- link to the Notion run page
- direct callout for any auto-terminating contract, active notice-window issue, or `Both Required` contract

In **Chat mode**, send Slack **only if the user asks**; there is no Notion run page to link unless they later persist results.

Slack is not the system of record. Keep it short and action-oriented.

## Final reminders

- The cohort is forward-looking only.
- If the user did not specify Notion vs chat, **ask** per [Output destination](#output-destination-notion-vs-chat)—never silently assume Notion.
- Every in-scope contract gets a cohort row (**Notion**) or equivalent chat cohort entry (**Chat**).
- **Notion mode:** every column must have a value unless the field rules explicitly allow blank; do not read Notion before writing (**Notion MCP** policy); do not create duplicate databases or schemas.
- **Chat mode:** include the same substantive fields in chat; do not require Notion for completeness.
- `Recommended Action` must always be a specific imperative sentence.
- Batch work in groups of `15-20` contracts: complete **Oxels MCP** Steps 1–6 for the batch, then Step 7 for that batch (**Notion MCP** or **Chat** deliverable), before starting the next batch.