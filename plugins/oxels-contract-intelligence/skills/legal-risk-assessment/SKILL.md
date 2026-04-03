---
name: legal-risk-assessment
description: Severity-by-likelihood legal risk scoring with Oxels MCP evidence when the risk depends on contract terms, precedent, amendments, or portfolio patterns.
metadata:
  short-description: Risk matrix grounded in the contract corpus
---

# Legal Risk Assessment

Assess legal risk using a **severity × likelihood** framework, but use `Oxels MCP` whenever the risk turns on actual contract terms, negotiated precedent, amendment history, or portfolio patterns.

**Important**: This skill supports legal workflows but does not provide legal advice. Risk calls should be reviewed by qualified legal professionals.

## Invocation

```
/legal-risk-assessment [matter summary]
```

If the matter is unclear, ask for the decision being made, timing, and whether the issue is primarily contractual, regulatory, or both.

## Risk Matrix

- `Score 1-4`: GREEN
- `Score 5-9`: YELLOW
- `Score 10-15`: ORANGE
- `Score 16-25`: RED

Use the normal **severity × likelihood** approach, but tie the scoring rationale to **source-backed evidence** where Oxels can answer it.

## Oxels Workflow

1. Define the matter, business impact, time pressure, and what decision the team is trying to make.
2. Decide whether the risk is `contract-backed`, `regulatory-backed`, or `mixed`.
3. For contract-backed or mixed questions, inspect `retrieve_field_definitions` and `describe_fields` for fuzzy concepts.
4. Build the bounded corpus with `search_agreements`, `get_deal`, or `get_organization_deals`.
5. Read structured signals with `get_agreement_fields`.
6. Pull clause evidence with `retrieve_agreement_chunks`.
7. Escalate to `get_agreement_text` when the risk depends on exact wording, override logic, or a high-stakes conclusion.
8. Compare the active paper to standard or precedent before finalizing likelihood.

## Scoring Rules

- **Severity** should reflect real economic, operational, reputational, and compliance impact.
- **Likelihood** should reflect what the paper allows, how often the pattern appears in the corpus, and whether triggering events are already present.
- Do not treat thin extraction as proof that a risk is absent.
- Distinguish `field-derived`, `retrieval-supported`, `full-text confirmed`, and `manual review required`.

## Output Format

```markdown
## Legal Risk Assessment

### Matter
[What is being assessed]

### Risk Score
[Severity] x [Likelihood] = [Score / Color]

### Evidence Base
[Contract text, precedent, or other basis]

### Contributing Factors
[What increases the risk]

### Mitigating Factors
[What reduces the risk]

### Recommended Approach
[Mitigation, escalation, or acceptance path]

### Confidence and Gaps
[What is confirmed and what still needs manual review]
```

## Escalation

Treat uncapped exposure, override-sensitive terms, active disputes, regulator contact, or unresolved source ambiguity as escalation triggers.
