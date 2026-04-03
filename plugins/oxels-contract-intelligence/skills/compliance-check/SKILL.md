---

## name: compliance-check

description: Run a compliance-style review on an initiative; use Oxels MCP when answers depend on live customer or vendor contract commitments.
metadata:
  short-description: Regulatory vs contractual compliance lanes with corpus grounding

# Compliance Check

Run a compliance check on a proposed action, product feature, marketing program, or business initiative. Use `Oxels MCP` whenever the answer depends on what the organization has already promised in customer or vendor paper.

**Important**: This skill supports legal workflows but does not provide legal advice. Separate regulatory requirements from contract commitments instead of blending them together.

## Invocation

```
/compliance-check [initiative description]
```

Describe what is changing: scope, data or regulated activity, geographies, and affected teams. If the user only gives a headline, ask for missing intake facts before deep retrieval.

## Workflow

1. Intake the initiative: what is changing, where it applies, what data or regulated activity is involved, and what business teams are affected.
2. Classify the question as `regulatory-only`, `contract-backed`, or `mixed`.
3. If the initiative may touch live contract commitments, use `Oxels MCP` first.

## Oxels Rules

- Use `Oxels MCP` for contract-backed questions about privacy, security, data residency, audit rights, deletion, SLA, notice obligations, subprocessors, marketing permissions, or customer-specific restrictions.
- Start with `retrieve_field_definitions` and `describe_fields` for fuzzy concepts before assuming field coverage.
- Build the smallest relevant corpus with `search_agreements`, `get_deal`, or `get_organization_deals`.
- Use `get_agreement_fields` for structured reads, `retrieve_agreement_chunks` for clause evidence, and `get_agreement_text` for high-stakes confirmation.
- Review the full governing stack when obligations may live in an order form, DPA, SLA, amendment, or side paper.
- Distinguish `field-derived`, `retrieval-supported`, `full-text confirmed`, and `manual review required`.

## What To Produce

Separate the answer into three lanes:

1. `Regulatory requirements`: what law or policy may require.
2. `Contractual commitments`: what existing agreements already promise or restrict.
3. `Operational actions`: what the team must do before proceeding.

## Output Format

```markdown
## Compliance Check: [Initiative]

### Summary
[Proceed / Proceed with conditions / Requires further review]

### Regulatory Requirements
[Applicable laws, policies, and approval points]

### Contractual Commitments From Oxels
[Customer or vendor commitments that affect the initiative]

### Risk Areas
[Risk, severity, and mitigation]

### Recommended Actions
1. [Action]
2. [Action]
3. [Action]

### Confidence and Gaps
[What is confirmed from source vs. what still needs manual review]
```

## Notes

- Do not let generic compliance reasoning override actual contract language.
- If no live agreement commitments are relevant, say that clearly and proceed with a regulatory-only analysis.
- When other tools expose internal policies, RoPA/DPIA summaries, or trust/attestation artifacts, use them to strengthen the **Regulatory requirements** and **Operational actions** lanes—Oxels remains primary for **Contractual commitments**.

## Related Skills

- Use **Plan Scenario** when the question is primarily **scenario planning** (blockers, timing gates, pricing/packaging) rather than a compliance-style three-lane deliverable.

