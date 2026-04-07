# Assess Security Obligations Reference

Use this file for detailed review structure, domain mapping, evidence rules, and output templates that do not need to live in `SKILL.md`.

## Intake QA loop

Resolve these before making strong claims.

### Review objective

Ask only for what is missing:

- what the user is trying to learn, approve, inventory, or escalate
- whether the goal is an `obligation inventory`, `gap assessment`, `baseline check`, or `risk assessment`
- whether the question is about one agreement, one organization, or a broader bounded portfolio
- which domains matter most
- whether the user has a concrete baseline, policy, or requirement in mind

### Scope resolution

Clarify the narrowest useful scope:

- named agreement, deal, or organization if known
- whether the issue turns on one document or the full governing package
- whether the review should include current agreements only or a broader historical set
- whether date, geography, or agreement-type filters matter
- whether the user needs an answer immediately or a review artifact they can share

### Domain focus

If the user is broad, ask which domains matter most:

- privacy and data processing
- residency and transfer restrictions
- subprocessors and third-party access
- SLA and service support
- breach and incident response
- security controls
- audit and assessment rights
- retention, return, and deletion

If the user says `all of the above`, keep the matrix broad but still prioritize the highest-risk families first.

## Default review heuristics

Use these defaults unless the user gives a better rule:

1. Start with the smallest agreement set that can answer the question.
2. Prefer current operative paper over superseded versions.
3. Treat the full governing stack as relevant when privacy, security, SLA, or data handling may live outside the base agreement.
4. For portfolio scans, build the bounded population first, then compare within that population instead of implying a global census.
5. When a baseline is vague, ask for the requirement rather than silently inventing one.

## Field and retrieval workflow

Apply this ladder for each material concept.

1. `retrieve_field_definitions`
   - use when starting from fuzzy language like `data residency`, `subprocessor approval`, `breach notice`, `service levels`, `audit rights`, `encryption`, or `deletion`
2. `describe_fields`
   - use when exact field names, categories, document-type coverage, or examples are needed
3. `search_agreements`
   - use to build the bounded population first
4. `aggregate_agreements`
   - use for portfolio scans to measure obligation distribution, gap frequency, or domain coverage across the bounded set before drilling into individual agreements
   - `scope` accepts the same org profile filters as `search_agreements`
   - `dimensions` supports extracted field names and org profile fields like `ownership_type`, `employee_count_or_band`, `annual_revenue_band`, `industry_sector`
5. `get_deal` or `get_organization_deals`
   - use when the relevant unit is a commercial package or one customer relationship rather than one isolated agreement
6. `get_agreement_fields`
   - use for normalized terms and known signals
7. `retrieve_agreement_chunks`
   - use for clause-heavy, override-heavy, or text-first concepts
8. `get_agreement_text`
   - use when chunk evidence is ambiguous, interaction-heavy, or high-stakes
9. `get_amendment_chain`
   - use when the operative position may have changed over time

## Missing-field escalation

If a target concept is not cleanly answered:

1. Confirm the concept has a real field family in the current ontology.
2. If the field family exists but the value is null, sparse, or inconsistent, report that limitation.
3. Retrieve clause evidence with `retrieve_agreement_chunks`.
4. Escalate to `get_agreement_text` for agreements that remain ambiguous.
5. Re-check amendments, order forms, DPAs, SLAs, and side paper before concluding the term is absent or weak.

Never equate:

- field family not found in the schema
- field exists but value is null
- extraction coverage is low
- the clause is absent from the contract

## Domain-family mapping

Use these canonical families and typical signals. Discover the concrete field names dynamically in the current ontology rather than assuming one fixed schema.

| Family | Typical signals |
| --- | --- |
| `privacy_and_data_processing` | processing scope, permitted use, onward sharing limits, regulated-data handling, controller or processor framing, privacy commitments |
| `data_residency_and_transfer` | hosting location requirements, regional storage limits, transfer conditions, localization commitments, transfer restrictions |
| `subprocessors_and_third_parties` | subprocessor approval rights, notice obligations, objection windows, third-party access limits, flow-down duties |
| `sla_and_service_levels` | uptime targets, response times, remedy mechanics, support tiers, service credits, exclusions, maintenance windows |
| `breach_and_incident_response` | notice timing, trigger thresholds, content requirements, cooperation duties, investigation support, remediation commitments |
| `security_controls` | encryption expectations, access management, authentication controls, logging, vulnerability handling, testing rights, certification commitments |
| `audit_and_assessment_rights` | audit rights, notice requirements, frequency limits, third-party report acceptance, onsite restrictions, cost allocation |
| `retention_return_and_deletion` | retention periods, deletion timing, return-of-data rights, backup carveouts, certification of destruction, post-termination access |
| `non_standard_overrides` | override text, bespoke riders, amendment-specific changes, conflicting side paper, additional-terms sections |

## Evidence ladder

Use the strongest applicable label for each material conclusion:

| Label | Meaning | When it is enough |
| --- | --- | --- |
| `Field-derived` | Supported by extracted `Oxels MCP` fields or normalized signals | Low-risk, direct, well-defined values |
| `Retrieval-supported` | Supported by clause retrieval snippets | Candidate interpretation, triage, or directional comparison with visible text support |
| `Full-text confirmed` | Supported by full agreement text review | High-stakes, ambiguous, interaction-heavy, or externally relied-upon conclusions |
| `Manual review required` | Evidence is incomplete, conflicting, or too thin | Final answer must be qualified and escalated |

Rules:

- Do not use `Field-derived` alone when the issue turns on clause nuance, carveouts, or document interaction.
- Do not treat `Retrieval-supported` as final absence proof across a broad corpus.
- Use `Full-text confirmed` before making a firm call on residency restrictions, breach timing, deletion duties, SLA remedies, audit rights, or customer-facing compliance assurances.

## Confidence levels

| Level | Meaning |
| --- | --- |
| `High` | Clause-accurate, amendment-aware, and supported by direct text or reliable structured facts plus confirmation where needed |
| `Medium` | Strong directional support, but some nuance still depends on snippets, partial scope, or approximated interpretation |
| `Low` | Sparse extraction, thin support, unclear stack interaction, or incomplete scope limits confidence |
| `Manual Review` | Human review is required before relying on the conclusion |

## Review rubrics by purpose

### Obligation inventory

Use this when the user wants to know what commitments exist.

Capture for each material family:

- operative obligation
- controlling document
- key condition or exception
- evidence source
- confidence

### Gap assessment

Use this when the user wants to know what appears missing, weak, or below the expected baseline.

A gap is credible only when:

- the baseline or expected control is explicit
- the governing stack was reviewed
- missing-field issues were not mistaken for textual absence
- the result is labeled as `potential gap` or `confirmed gap` with the evidence basis shown

### Baseline check

Use this when the user gives a requirement and wants a pass or fail view.

Classify each tested requirement as:

- `Pass`
- `Fail`
- `Conditional`
- `Manual review required`

Use `Conditional` when the paper supports the requirement only with carveouts, dependencies, or implementation assumptions that still matter operationally.

### Risk assessment

Use this when the user wants exposure or prioritization rather than a raw inventory.

For each risk item, separate:

- what the obligation or gap is
- why it matters operationally
- how strong the evidence is
- what action should happen next

## Chat output templates

Use the template that matches the review purpose.

### Obligation inventory

```markdown
## Question and scope
[What is being inventoried and what agreement set was used]

## Top takeaways
- [Most important commitment or pattern]
- [Biggest exception or caveat]

## Obligations matrix
| Domain | Operative position | Controlling document | Conditions or carveouts | Evidence level | Confidence |
| --- | --- | --- | --- | --- | --- |

## Document stack and evidence
- [Document type], [section]: "[Quote]"

## Gaps and caveats
- [Ambiguity, missing document, or thin support]

## Recommended follow-up
- [Specific next action]
```

### Gap assessment

```markdown
## Question and scope
[What baseline was tested and what agreement set was used]

## Baseline used
- [Requirement or expected control]

## Gap summary
- [Highest-priority gap]
- [Most common weak area]

## Gap-by-domain table
| Domain | Expected position | Observed position | Result | Evidence level | Confidence |
| --- | --- | --- | --- | --- | --- |

## Evidence and confidence
- [Document type], [section]: "[Quote]"

## Recommended follow-up
- [Specific next action]
```

### Baseline check

```markdown
## Question and scope
[Requirement being tested and the agreement or population used]

## Requirement being tested
- [Requirement]

## Result
- Status: [Pass / Fail / Conditional / Manual review required]
- Why: [Direct reason]

## Evidence
- [Document type], [section]: "[Quote]"
- Evidence level: [Field-derived / Retrieval-supported / Full-text confirmed]

## Risk and caveats
- [Operational caveat, dependency, or ambiguity]

## Recommended follow-up
- [Specific next action]
```

### Risk assessment

```markdown
## Question and scope
[What exposure was reviewed and what agreement set was used]

## Highest-risk findings
- [Risk item 1]
- [Risk item 2]

## Exposure by domain
| Domain | Exposure | Why it matters | Evidence level | Confidence | Recommended action |
| --- | --- | --- | --- | --- | --- |

## Evidence and confidence
- [Document type], [section]: "[Quote]"

## Immediate actions
- [Specific next action]

## Open ambiguities
- [What still needs review]
```

## Notion output template

Use this only in `Notion mode`.

Prefer an enriched page with these sections in this order:

1. `Question and Scope`
2. `Executive Summary`
3. `Obligations or Gaps by Domain`
4. `Evidence Log`
5. `Risk and Caveats`
6. `Follow-Up Actions`

Use narrative paragraphs to explain the assessment and use databases or linked database views wherever the reader should be able to open a contract, obligation, gap, evidence item, or action as its own entry.

Recommended database or view layout:

- `Contract Obligations`: one row per agreement and domain with columns like `Agreement`, `Domain`, `Operative Position`, `Controlling Document`, `Conditions or Carveouts`, `Evidence Level`, `Confidence`
- `Gap and Risk Log`: one row per identified weakness, exception, or exposure with columns like `Agreement`, `Domain`, `Issue Type`, `Why It Matters`, `Severity`, `Confidence`, `Recommended Action`
- `Evidence Log`: one row per quote, section, ambiguity, or unresolved interaction with columns like `Agreement`, `Domain`, `Source Document Type`, `Section Number`, `Quote`, `Evidence Level`, `Confidence`
- `Follow-Up Actions`: one row per escalation, validation step, or remediation action with columns like `Agreement`, `Domain`, `Owner`, `Action`, `Priority`, `Status`

Readability rules:

- Use real explanatory paragraphs, not just headings and tables.
- Keep property names short, explicit, and consistently ordered.
- Put the linked view for each database directly under the section that explains it.
- Prefer filtered views and curated property order over dumping every property at once.
- Where a single agreement deserves deeper treatment, make it a database row with its own detail page.

## Evidence requirements

For every material finding, capture:

- canonical domain family
- agreement or bounded population used
- operative position or observed issue
- controlling document
- source mode: `structured field`, `retrieval snippet`, `full-text review`, or `mixed`
- section number when available
- direct quote for high-impact or disputed conclusions
- confidence level

For every material gap or failure call, also capture:

- baseline being applied
- whether the result is `potential gap`, `confirmed gap`, or `manual review required`
- what was checked before calling the issue

## Escalation triggers

Escalate to `Manual review required` when:

- the controlling agreement or document stack cannot be identified confidently
- the amendment chain may change the answer and has not been reviewed
- the issue depends on text outside the currently reviewed document set
- ranked retrieval suggests a result but full confirmation is still missing
- the requested conclusion would be used for a firm security, privacy, or compliance assurance
- the baseline is too vague to score fairly
- the source text is incomplete, low-quality, or visibly conflicting

## Common failure modes

Watch for these mistakes:

- calling something absent because the field is blank
- treating a hosting-location mention as a hard residency obligation without reading the surrounding conditions
- reading SLA targets without the credit, exclusion, or measurement language that makes them meaningful
- ignoring the DPA or security exhibit because the base agreement mentions privacy at a high level
- collapsing subprocessor notice, approval, and objection rights into one concept
- calling a baseline `failed` when the paper is actually conditional or override-sensitive
- using a broad ranked retrieval result as a definitive portfolio census
- missing the order form or amendment where the real operational deviation lives
- overlooking deletion carveouts for backups, logs, or legal retention
- presenting a risk conclusion without a concrete next action
