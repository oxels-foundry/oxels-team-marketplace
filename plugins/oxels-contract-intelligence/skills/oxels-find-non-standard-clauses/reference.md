# Find Non-Standard Clauses Reference

Use this file for the detailed benchmarking rules that do not need to live in `SKILL.md`.

## Intake QA loop

Resolve these before making strong benchmark claims.

### Target contract resolution

Ask only for what is missing:

- customer or counterparty name
- deal or agreement identifier if known
- whether the target is already in Oxels
- whether the user has the actual contract text or file
- which document in the stack is the real target: `ORDER_FORM`, `MSA`, `DPA`, `SLA`, `AMENDMENT`, or the operative package
- which clause families matter most

### Comparator definition

Ask for missing comparator dimensions when Oxels metadata alone is not enough:

- ACV or contract size band
- enterprise versus SMB or mid-market
- customer segment or vertical
- geography or market
- new business versus renewal
- standard paper versus customer paper
- product family or commercial model

If the user supplies a peer rule, keep it fixed unless the evidence forces you to qualify it.

## Default comparator heuristics

Use these in order, and stop once the peer set is good enough.

1. Exact user-specified peer group
2. Same customer segment or vertical if known
3. Same deal shape: `NEW_BUSINESS` versus `RENEWAL`
4. Same document type and paper posture
5. Same geography or market when operational terms depend on region
6. Similar contract value band inferred from total contract value or other available commercial signals
7. Similar product or packaging model

If a peer dimension cannot be supported by current Oxels metadata, say so explicitly and downgrade confidence instead of implying the peer set is precise.

## Field and retrieval workflow

Apply this ladder for each material concept.

1. `retrieve_field_definitions`
   - use when starting from fuzzy language like `net terms`, `termination for convenience`, `price protection`, `data residency`, `liability cap`
2. `describe_fields`
   - use when exact field names, categories, document-type coverage, or examples are needed
3. `search_agreements`
   - use to build the bounded population first
4. `get_deal` or `get_organization_deals`
   - use when the target or comparator context is a commercial package rather than one isolated agreement
5. `get_agreement_fields`
   - use for normalized terms and known fields
6. `retrieve_agreement_chunks`
   - use for clause-heavy, override-heavy, or text-first concepts
7. `get_agreement_text`
   - use when chunk evidence is ambiguous, interaction-heavy, or high-stakes
8. `get_amendment_chain`
   - use when the operative position may have changed over time

## Missing-field escalation

If a target concept is not cleanly answered:

1. Confirm the concept has a real field or family in Oxels.
2. If the field exists but the target value is null or sparse, report that limitation.
3. Retrieve clause evidence with `retrieve_agreement_chunks`.
4. Escalate to `get_agreement_text` for target agreements that remain ambiguous.
5. Review override text, additional-terms sections, and amendments before concluding the term is absent or standard.

Never equate:

- field not found in schema
- field exists but value is null
- extraction coverage is low
- the clause is absent from the contract

## Provision-family mapping

Use these canonical families and typical signals. Discover the concrete field names dynamically in the current ontology rather than assuming one fixed schema.

| Family | Typical Oxels signals |
| --- | --- |
| `termination` | termination rights, notice windows, extra termination triggers, refund obligations, or wind-down mechanics |
| `renewal` | renewal mechanism, renewal term, notice timing, repricing signals, or renewal cap language |
| `pricing_and_price_protection` | total contract value, effective rate signals, credits, rebates, price holds, repricing language, or cap language |
| `payment_mechanics` | payment timing, billing cadence, true-up mechanics, invoicing rules, or milestone structure |
| `liability` | liability cap structure, carveouts, or override text that changes the default allocation of risk |
| `indemnity` | indemnity scope, triggers, exclusions, defense or control mechanics, or override text |
| `publicity_and_brand_use` | publicity rights, name or logo permissions, approval requirements, or brand-use restrictions |
| `privacy_and_data_processing` | processing scope, privacy commitments, security measures, data-use limitations, or regulated-data handling |
| `data_residency_and_subprocessors` | hosting location requirements, transfer restrictions, residency commitments, or subprocessors terms |
| `support_and_service_levels` | support tier commitments, service levels, credits, response obligations, or uptime language |
| `ip_and_confidentiality` | IP ownership or license language, confidentiality scope, return or destruction obligations, or use restrictions |
| `non_standard_overrides` | override text, bespoke attachments, amendment-specific changes, rider conflicts, or cross-document exceptions |

## Benchmarking rubric

Use a bounded, evidence-backed rubric.

### `Standard globally and for peers`

Assign when:

- the provision aligns with the broader bounded corpus
- the near-peer set shows the same or materially similar pattern
- no amendment or override changes the practical outcome

### `Non-standard globally but standard for peers`

Assign when:

- the provision is unusual across the broader corpus
- the peer set shows the same negotiated pattern often enough to make it normal for similar deals
- the peer definition is explicit and not artificially broad

This is the key nuance bucket for large enterprise or segment-specific deals.

### `Standard globally but unusual for peers`

Assign when:

- the term may look ordinary in the overall corpus
- but it is unexpectedly favorable or unfavorable compared with similar deals
- the peer set is more decision-useful than the global corpus for this question

### `Non-standard both globally and for peers`

Assign when:

- the term is meaningfully outside both baselines
- the deviation survives amendment and override review
- the evidence is strong enough to support an exception call

### `Manual review required`

Assign when:

- the target contract text is incomplete or ambiguous
- amendment layering is unresolved
- the peer set is too thin
- extraction coverage is too weak for a material clause
- ranked retrieval cannot safely support the claim

## Peer-set QA checklist

Before using a near-peer benchmark, verify:

- the peer set is bounded, not generic
- the target and peers share the attributes that matter for the clause family
- the peer set is not so small that a single outlier drives the conclusion
- the peer definition is exposed in the output
- the skill explains whether the peer set is exact, inferred, or approximate

If any of these fail, keep the global benchmark but soften or withhold the peer benchmark.

## Evidence requirements

For every material exception call, capture:

- canonical provision family
- business concepts, discovered fields, or clause concepts used
- target-side finding
- global baseline result
- near-peer baseline result
- source mode: `structured field`, `retrieval snippet`, `full-text review`, `external contract text`, or `mixed`
- section number when available
- direct quote for high-impact or disputed clauses
- confidence level

## Confidence levels

| Level | Meaning |
| --- | --- |
| `High` | Clause-accurate, amendment-aware, and supported by direct text or reliable structured facts plus confirmation where needed |
| `Medium` | Strong directional support, but some nuance still depends on retrieval snippets or partial comparator precision |
| `Low` | Sparse extraction, thin comparator set, or unresolved clause context limits confidence |
| `Manual Review` | Human review is required before relying on the conclusion |

## Chat output template

Use this in `Chat mode`.

### 1. Target contract and scope

- identify the target
- state whether it came from Oxels or external text
- state the governing document stack
- state what clause families were benchmarked

### 2. Comparator set used

- global corpus scope
- near-peer scope
- peer dimensions used
- known limitations in the peer set

### 3. Top takeaways

- most important exception themes
- biggest peer-specific nuance
- anything that is clearly standard despite looking unusual at first glance
- anything that is clearly exceptional and likely worth escalation

### 4. Clause-by-clause exception table

Recommended columns:

| Provision family | Target position | Global baseline | Near-peer baseline | Classification | Evidence source | Confidence |
| --- | --- | --- | --- | --- | --- | --- |

### 5. Peer nuance

Use this section to explain cases like:

- globally unusual but normal for large enterprise deals
- globally ordinary but richer than the target's natural peer group
- operationally important clauses driven by market or geography

### 6. Evidence and caveats

For each Tier 1 finding:

- section number
- quote or precise paraphrase
- controlling document
- amendment or override note
- why the comparator set supports the conclusion

### 7. Recommended follow-up

Use imperative next steps, for example:

- `Validate the liability override against full amendment text.`
- `Re-run the benchmark against only renewal deals above the same value band.`
- `Escalate this data residency restriction for privacy review.`

## Notion output template

Use this only in `Notion mode`.

Prefer an enriched page with these sections in this order:

1. `Target Contract and Scope`
2. `Comparator Set`
3. `Executive Summary`
4. `Clause-by-Clause Benchmark`
5. `Peer Nuance`
6. `Evidence and Caveats`
7. `Recommended Follow-Up`

Use narrative paragraphs to explain the benchmark and use databases or linked database views wherever the reader should be able to open a specific finding, clause family, evidence item, or action as its own entry. Align each section header with the database view beneath it so the artifact reads cleanly from top to bottom.

Recommended database or view layout:

- `Benchmark Findings`: one row per provision family with columns like `Provision family`, `Target position`, `Global baseline`, `Near-peer baseline`, `Classification`, `Evidence source`, `Confidence`
- `Evidence Log`: one row per quote, section, or ambiguity
- `Follow-Up Actions`: one row per recommended next step, escalation, or manual-review item

Readability rules:

- Use real explanatory paragraphs, not just headings and tables.
- Keep database property names short, explicit, and consistently ordered.
- Put the linked view for each database directly under the section that explains it.
- Prefer filtered views and display-order curation over dumping every property at once.
- When a specific finding or clause family deserves deeper treatment, make it a database row with its own detail page.

## External contract handling

When the target contract is not in Oxels:

- treat the user-supplied file or text as the target-side source of truth
- keep target extraction clearly separate from Oxels corpus evidence
- do not imply that Oxels retrieved the target contract when it did not
- use Oxels only for the corpus baseline and precedent side
- downgrade confidence when the external target is incomplete, OCR-heavy, or missing amendments

## Common failure modes

Watch for these mistakes:

- calling something non-standard because the field is blank
- using a broad ranked retrieval result as a definitive corpus census
- comparing a large enterprise customer to the entire corpus without a peer correction
- ignoring override or additional-terms text because a clause field exists
- ignoring the order form when the commercial deviation lives there
- collapsing a deal package into one agreement when the real operative position spans multiple instruments
