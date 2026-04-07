# Deal Analysis Reference

Use this file for the detailed rules, example lenses, and output templates that do not need to live in `SKILL.md`.

## Intake QA loop

Resolve these before making strong mix-shift claims.

### Business question

Ask only for what is missing:

- what the user wants to understand, decide, or standardize
- which shift matters most: pricing, usage-based structure, discounting, concessions, operational complexity, or paper posture
- whether the user wants a quick directional answer, a deeper archetype analysis, or a visual artifact
- whether the result should go to chat or Notion

### Comparison frame

Ask for the smallest missing set of framing choices:

- time comparison: month-over-month, quarter-over-quarter, last `N` deals versus prior `N`, year-over-year, or custom window
- scope comparison: all deals, enterprise only, renewal only, new business only, product-specific, region-specific, or segment-specific
- weighting approach: agreement count, deal value, or both
- whether the user wants one portfolio-wide answer or separate readouts by segment

If the user gives an approximate frame such as `recent deals`, convert it into an explicit working frame and say what you used.

## Default comparison heuristics

Use these in order and stop once the comparison is good enough.

1. Exact user-specified frame
2. A recent cohort versus the immediately prior cohort of the same size
3. Quarter-over-quarter if the user asks about trend
4. New business versus renewal if lifecycle looks like the main driver
5. Separate enterprise from non-enterprise if deal shape is clearly bifurcated
6. Separate by product or packaging model when the user's question depends on commercial model

If a comparison frame is only approximate because the current metadata does not fully support it, say so explicitly.

## Archetype taxonomy

Use archetypes as working business groupings, not as immutable ontology objects.

Start with the simplest useful grouping. Expand only when the question needs more nuance.

### Core archetypes


| Archetype                       | Typical signals                                                                                                                                            | Use when                                                                                |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `Seat-heavy standard`           | mostly fixed or recurring commercial structure, limited variable usage economics, few meaningful credits or service attachments, light negotiation posture | the portfolio is mostly straightforward recurring commercial terms                      |
| `Usage-based hybrid`            | baseline recurring structure plus a meaningful commitment, allowance, or variable-usage component                                                          | the business is mixing commit and variable usage models                                 |
| `Usage-led / consumption-heavy` | commitments, allowances, overage economics, or true-up behavior drive more of the commercial story than flat recurring pricing                             | the user wants to know whether the business is shifting toward consumption pricing      |
| `Discount-led enterprise`       | materially reduced effective rate, meaningful credits or commercial givebacks, large deal values, negotiation-heavy posture                                | the question is whether larger deals are driving price erosion or strategic discounting |
| `Ops-heavy / services-attached` | onboarding, implementation, support, services, milestones, or side obligations materially change the deal shape                                            | operational burden and deployment complexity matter more than pure price                |
| `Custom-concession-heavy`       | multiple non-standard commercial overrides, credits, bespoke economics, or repeated exception language                                                     | the user wants to identify where standardization is breaking down                       |
| `Manual-review cluster`         | thin field coverage, ambiguity, side-paper dependence, or text-heavy overrides                                                                             | the data cannot safely support a stronger label without deeper review                   |


### Optional sub-archetype lenses

Use only if they materially improve the answer:

- `Renewal repricing cluster`
- `Credit-heavy concession cluster`
- `Support uplift cluster`
- `Customer-paper complexity cluster`
- `High-value but standard cluster`

## Field-to-lens mapping

Use the field model as the first pass. Discover the concrete fields dynamically in the current ontology, then validate important conclusions with text.


| Lens                      | Typical Oxels signals                                                                                                         | Notes                                                                                   |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `Pricing level and value` | total contract value, effective rate signals, line-item mix, or other commercial value indicators                             | value and rate signals are useful but may not capture the full economic structure alone |
| `Discount posture`        | discount indicators, credits, rebates, price holds, or other concession signals                                               | credits and discounts may indicate different concession styles                          |
| `Usage structure`         | commitments, included allowances, variable usage economics, true-up behavior, or overage mechanics                            | this is the core lens for usage-based shift questions                                   |
| `Billing mechanics`       | billing cadence, payment timing, invoicing rules, or true-up mechanics                                                        | use when the commercial shift also changes invoice or settlement behavior               |
| `Operational complexity`  | support or services attachments, onboarding or implementation obligations, milestones, deployment timing, or side obligations | combine with side-paper review if obligations look broader than line items              |
| `Negotiation posture`     | override text, amendment layering, customer paper, exception frequency, or retrieval evidence                                 | this lens is often mixed structured-plus-text rather than purely field-backed           |


## Retrieval and evidence workflow

Apply this ladder for each material claim.

1. `retrieve_field_definitions`
  - use when starting from fuzzy language like `usage-based`, `discounting`, `credits`, `premium support`, or `operational complexity`
2. `describe_fields`
  - use when the current ontology needs to be translated into exact field names, categories, document-type coverage, or examples
3. `search_agreements`
  - use to build the bounded cohort first
4. `aggregate_agreements`
  - use for grouped counts, top values, averages, min/max, and sorted trend summaries once the cohort is bounded
5. `get_agreement_fields`
  - use for normalized fact reads when you need per-agreement values rather than grouped summaries
6. `retrieve_agreement_chunks`
  - use for override-heavy, concession-heavy, or text-first concepts
7. `get_agreement_text`
  - use when chunk evidence is ambiguous, high-impact, or likely to drive a GTM action
8. `get_amendment_chain`
  - use when a shift may actually be caused by amended economics or changed paper

## Missing-field escalation

If a trend claim is not cleanly supported:

1. confirm the concept has a real field family, signal type, or text pattern in Oxels
2. check coverage and document-type applicability
3. say when the field is directional rather than reliable
4. retrieve clause evidence for candidate agreements
5. escalate to full text for the highest-impact examples
6. downgrade confidence when the claim still depends on thin evidence

Never equate:

- field not found in schema
- field exists but value is null
- coverage is low
- the commercial feature is absent from the deal

## Mix-shift rubric

Use a simple, explicit rubric.

### `Meaningful mix shift`

Assign when:

- the archetype share changed in a visible way across the chosen frame
- the shift appears in count, value, or both
- the direction remains stable after checking obvious cohort biases

Preferred measurement pattern:

- use `aggregate_agreements` for count shifts, top values, grouped averages, and sorted rankings
- then use `get_agreement_fields` or clause retrieval only for the agreements that explain the shift

### `Directional shift`

Assign when:

- the signal is real but still rests on partial field coverage
- or the change is clear in a subset but not yet portfolio-wide

### `Localized shift`

Assign when:

- the change is concentrated in one segment, region, product, or lifecycle bucket
- and should not be generalized to the full portfolio

### `Potential artifact`

Assign when:

- the shift may be driven by coverage changes, data sparsity, cohort mismatch, or a few outsized deals

### `Manual review required`

Assign when:

- the change depends on override text or amendment nuance that was not fully reviewed
- the cohort is too thin
- the user's requested frame cannot be supported cleanly

## Standardization-opportunity rubric

Use this when moving from description to recommendation.


| Opportunity type      | Assign when                                                                                           |
| --------------------- | ----------------------------------------------------------------------------------------------------- |
| `Standardize now`     | the pattern repeats often enough to justify default packaging, pricing, or workflow changes           |
| `Codify fallback`     | the concession is not standard, but appears repeatedly enough to warrant an approved fallback posture |
| `Monitor only`        | the pattern is emerging, but still too early or too thin to standardize                               |
| `Escalate for policy` | the pattern has strategic pricing, legal, or operational implications that need owner review          |
| `Needs data cleanup`  | the business question is right, but current extraction quality limits safe standardization            |


## Confidence levels


| Level           | Meaning                                                                                            |
| --------------- | -------------------------------------------------------------------------------------------------- |
| `High`          | field-backed and/or text-confirmed, with the cohort and comparison frame clearly defined           |
| `Medium`        | strong directional support, but some nuance depends on partial coverage or representative examples |
| `Low`           | thin fields, sparse text validation, or approximate comparison frame limit confidence              |
| `Manual Review` | human review is required before relying on the conclusion                                          |


## Chat output template

Use this in `Chat mode`.

### 1. Question and scope

- business question
- cohorts compared
- weighting approach
- major assumptions

### 2. Top takeaways

- the biggest mix shifts
- the most important pricing or concession signals
- the biggest operational complexity change
- the highest-confidence standardization call

### 3. Archetype mix table

Recommended columns:


| Archetype | Prior cohort | Current cohort | Change | Value note | Confidence |
| --------- | ------------ | -------------- | ------ | ---------- | ---------- |


### 4. Pricing, concessions, and complexity signals

Use repeated blocks:

- `Signal`
- `What changed`
- `Why it matters`
- `Evidence`
- `Confidence`

### 5. Evidence and caveats

For each Tier 1 shift:

- fields used
- whether text validation was needed
- key agreement examples or quotes when relevant
- known data limitations

### 6. Standardization opportunities

Recommended columns:


| Pattern | Recommendation | Why now | Owner | Confidence |
| ------- | -------------- | ------- | ----- | ---------- |


### 7. Recommended next steps

Use imperative next steps, for example:

- `Validate whether the support-attached pattern should become a formal package tier.`
- `Review the most discounted usage-led deals to separate strategic wins from repeatable discount posture.`
- `Codify a fallback for credit-led concessions if the pattern is continuing.`

## Notion output template

Use this only in `Notion mode`.

Create a one-off page for the current analysis.

### Recommended section order

1. `Question and Scope`
2. `Executive Summary`
3. `Archetype Mix`
4. `Pricing and Concession Trends`
5. `Operational Complexity Trends`
6. `Heat Map or Matrix`
7. `Evidence and Caveats`
8. `Standardization Opportunities`
9. `Recommended Next Steps`

### Recommended one-off databases

Use only the databases that improve clarity for the current analysis.

#### `Archetype Mix`

One row per archetype and cohort comparison.

- `Archetype`
- `Cohort`
- `Deal Count`
- `Deal Value`
- `Share of Count`
- `Share of Value`
- `Change vs Comparison`
- `Confidence`
- `Notes`

#### `Pattern Findings`

One row per important pricing, concession, or complexity pattern.

- `Pattern`
- `Category`
- `What Changed`
- `Why It Matters`
- `Evidence Mode`
- `Confidence`
- `Standardization Opportunity`

#### `Next Steps`

One row per recommendation, escalation, or follow-up question.

- `Action`
- `Owner`
- `Category`
- `Priority`
- `Why`
- `Confidence`

## Notion chart recipes

Use supported chart views only when they sharpen the readout.


| Question type                                                  | Suggested view                           |
| -------------------------------------------------------------- | ---------------------------------------- |
| share by archetype in one cohort                               | `donut` grouped by `Archetype`           |
| change in archetype counts across time windows                 | `column` or `bar` grouped by `Archetype` |
| trend across multiple periods                                  | `line` grouped by period                 |
| top-line total such as total deals or share of usage-led deals | `number`                                 |
| combined summary page                                          | `dashboard`                              |


Readability rules:

- start with a short executive summary before any database or chart
- keep chart count low; use only the few that answer the main question
- pair each chart with one sentence that explains what the viewer should notice

## Heat map guidance

The current Notion view surface does not expose a native heatmap chart.

When the user asks for a heat map:

1. create a matrix-style table in the page or in a temporary database
2. use rows such as archetypes, segments, or time windows
3. use columns such as pricing posture, concession spread, and operational complexity
4. fill cells with compact labels like `Low`, `Medium`, `High`, percentages, or counts
5. if a visual summary helps, add a `mermaid` diagram beside or below the matrix

Example matrix dimensions:

- rows: `Current quarter archetypes`
- columns: `Usage intensity`, `Discount intensity`, `Operational complexity`, `Override frequency`

## Mermaid guidance

When a diagram helps, keep it simple and business-readable.

Good uses:

- flow from cohort selection to archetype grouping to action categories
- comparison of prior versus current archetype mix
- a concept map of which concessions cluster together

Prefer one diagram that clarifies the main message over several decorative diagrams.

## Common failure modes

Watch for these mistakes:

- claiming a portfolio shift without naming the exact comparison frame
- treating rules-based archetypes as if they were objective learned clusters
- over-reading low-coverage fields
- collapsing count shift and value shift into the same story without checking both
- assuming a discount field tells the entire concession story
- missing operational burden that actually lives in side paper or amendments
- recommending standardization when the pattern is still bespoke or segment-specific
- building a complex Notion artifact when a concise page plus one chart would be clearer