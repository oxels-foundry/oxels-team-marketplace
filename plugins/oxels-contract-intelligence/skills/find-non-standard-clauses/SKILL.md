---
name: find-non-standard-clauses
description: Benchmarks a contract against similar agreements to show which clauses are standard, unusual, or worth escalating.
metadata:
  short-description: Oxels-backed contract benchmarking
---

# Find Non-Standard Clauses

Use this skill to benchmark a target contract against the Oxels corpus and explain what is truly unusual. The job is not just to extract terms. The job is to determine whether a clause is standard in the broader corpus, standard for similar deals, or genuinely exceptional.

## Mission

Operate as a contract benchmarking agent tightly coupled to `Oxels MCP`. The job is to:

- resolve the target contract and governing document stack
- inspect what Oxels already knows through fields and definitions
- fill gaps through clause retrieval and full-text review
- compare the target against both a broader corpus baseline and a near-peer baseline
- explain which clauses are standard, non-standard, or only unusual outside the right peer group
- deliver the result in chat or Notion, depending on user preference

## Systems

- `Oxels MCP`: primary system for field discovery, agreement scoping, clause retrieval, amendment review, full-text confirmation, and precedent
- `Notion MCP`: optional persistence only after the user explicitly chooses `Notion mode`; when writing to Notion, prefer an enriched, well-structured page with narrative sections, paragraphs, and databases wherever row-level findings, specific deals, clauses, or concepts benefit from structured navigation

## Output destination

Resolve output destination early.

1. Use `Notion mode` if the user explicitly asks for Notion, a page, or workspace persistence.
2. Use `Chat mode` if the user explicitly asks for the answer in chat, markdown only, or says not to use Notion.
3. If unspecified, ask once near the start: `Should I deliver this benchmark here in chat, or write it to Notion?`

Never call `Notion MCP` until the user has chosen.

## Intake paths

Support two paths:

- `Oxels-resolved contract`: the user identifies the target by customer, deal, agreement, or other Oxels-resolvable context
- `External contract`: the user provides contract text or a file that is not already in Oxels; analyze that target directly, then use Oxels only for benchmarking and precedent

If the peer group is not obvious from Oxels metadata, ask for the missing comparator dimensions before claiming what is standard.

## Standing rules

Apply these throughout:

- Use `Oxels MCP` first whenever the answer depends on the actual corpus.
- Build the bounded comparison set before making broad claims.
- Missing extracted fields do not prove a term is absent.
- Review order forms, amendments, DPAs, SLAs, and additional terms when they may control the operative position.
- Treat override text, additional-terms sections, and amendment overlays as first-class sources of deviation.
- Separate structured facts, retrieval-backed findings, full-text-confirmed findings, and user-supplied external contract findings.
- Distinguish `global corpus standard` from `near-peer standard`.
- If the comparator set is too broad or thin to support a strong claim, say so and tighten or qualify the benchmark.
- Do not use ranked retrieval over broad batches as final absence proof.
- Advise, do not merely extract.

## Workflow

Follow these steps in order.

### Step 1: Resolve the target and scope

Determine:

- what the target contract is
- whether it is already in Oxels
- which governing instruments matter
- what the user wants benchmarked
- what comparator dimensions matter
- whether the result should go to chat or Notion

Comparator dimensions may include:

- deal size or ACV band
- customer segment
- market or geography
- enterprise versus SMB posture
- document type and paper source
- renewal versus new business

If the user says a `$5M` enterprise contract should be compared to similar enterprise contracts, preserve that framing throughout the analysis.

### Step 2: Inspect the field model first

Before making clause claims:

1. Use `retrieve_field_definitions` for fuzzy concepts like `termination for convenience`, `price protection`, `liability cap`, or `data residency`.
2. Use `describe_fields` to confirm exact field names, categories, document-type coverage, and whether the concept is likely field-backed or text-heavy.

This step determines what can be read structurally and what must be reviewed through text.

### Step 3: Build the target contract position

For an Oxels-resolved contract:

- use `search_agreements`, `get_deal`, or `get_organization_deals` to resolve the governing set
- use `get_agreement_fields` for structured values
- use `get_amendment_chain` when the operative position may be amendment-sensitive

For an external contract:

- analyze the user-supplied text or file directly for the target contract
- keep target-side findings clearly labeled as external evidence
- still use Oxels for the corpus benchmark and precedent side

Always state the operative position across:

- base agreement
- order form
- amendment chain
- DPA
- SLA
- addenda and additional terms

### Step 4: Fill gaps and validate with text

When a relevant concept is absent, sparse, noisy, or high-stakes:

1. Use `retrieve_agreement_chunks` for candidate evidence.
2. Escalate to `get_agreement_text` when the snippet is ambiguous, interaction-heavy, or materially important.
3. Re-check amendments and overrides before finalizing the conclusion.

Do not silently convert `field missing` into `term absent`.

### Step 5: Normalize the target into provision families

Organize findings into canonical provision families:

- `termination`
- `renewal`
- `pricing_and_price_protection`
- `payment_mechanics`
- `liability`
- `indemnity`
- `publicity_and_brand_use`
- `privacy_and_data_processing`
- `data_residency_and_subprocessors`
- `support_and_service_levels`
- `ip_and_confidentiality`
- `non_standard_overrides`

Use the narrowest explicit field when possible, then add text nuance or overrides from freeform additional-terms text, clause text, or external contract review.

### Step 6: Build the two baselines

Construct both:

- `Global corpus baseline`: the broader in-scope population
- `Near-peer baseline`: the narrower comparator set that best matches the target

Use `search_agreements` first to define the bounded population. Then read value-bearing fields and clause evidence to form peer cohorts. Because the current Oxels search surface does not directly filter by ACV band or segment, do peer bucketing as an explicit analysis step after scoping.

If needed, ask for missing peer definitions rather than guessing.

### Step 7: Classify what is standard and what is not

For each material provision, classify it as:

- `Standard globally and for peers`
- `Non-standard globally but standard for peers`
- `Standard globally but unusual for peers`
- `Non-standard both globally and for peers`
- `Manual review required`

Explain why the classification is what it is, what comparator set drove it, and whether the conclusion comes from fields, retrieval, full text, external target review, or a combination.

### Step 8: Deliver the benchmark

In `Chat mode`, deliver:

1. `Target contract and scope`
2. `Comparator set used`
3. `Top takeaways`
4. `Clause-by-clause exception table`
5. `Peer nuance`
6. `Evidence and caveats`
7. `Recommended follow-up`

In `Notion mode`, prefer an enriched artifact, not a thin summary page and not a prose wall. Use well-written narrative sections with paragraphs for interpretation, and add databases wherever the user should be able to click into a clause family, finding, evidence item, or follow-up item as its own structured entry. Keep the page readable top-down by aligning each section with the database or view that supports it.

## Quality bar

Before delivering, confirm:

- the target contract is clearly identified
- the comparator set is explicit
- the governing document stack is reflected
- conclusions are not field-only when text review was needed
- `global` and `near-peer` standards are not collapsed together
- override text and amendments were considered
- evidence source and confidence are explicit

If a material conclusion does not meet this bar, mark it `Manual review required`.

## Additional resources

- Detailed QA loop, comparison rubric, output templates, and escalation rules: [reference.md](reference.md)
