---
name: legal-response
description: Generate recurring legal inquiry responses with Oxels MCP grounding when the answer depends on live agreement terms, status, or precedent.
metadata:
  short-description: Legal response drafts grounded in the contract corpus
---

# Legal Response

Generate a response to a recurring legal inquiry, but use `Oxels MCP` before drafting whenever the response depends on actual agreement terms, current contract status, or negotiated precedent.

**Important**: This skill supports legal workflows but does not provide legal advice. Drafts should be reviewed by qualified counsel before they are sent.

## Invocation

```
/legal-response [inquiry-type]
```

If no inquiry type is provided, ask the user what type of response they need and show available categories.

## Inquiry Types

Common categories include:

- `vendor`
- `nda`
- `privacy`
- `renewal`
- `contract-status`
- `dsr`
- `hold`
- `subpoena`
- `insurance`
- `custom`

## When Oxels Is Required

Use `Oxels MCP` first for:

- vendor legal questions tied to live paper
- NDA responses involving existing paper or precedent
- privacy or security responses tied to customer commitments
- renewal, notice, termination, refund, or pricing explanations
- contract-status or amendment-history responses

Oxels is optional for DSR, hold, subpoena, and insurance workflows unless contract obligations materially affect the response.

## Workflow

1. Identify the inquiry type and run escalation checks first.
2. Decide whether the response is `contract-backed` or `template-only`.
3. If contract-backed, use `retrieve_field_definitions` and `describe_fields` for fuzzy concepts.
4. Build the bounded corpus with `search_agreements`, `get_deal`, or `get_organization_deals`.
5. Read evidence with `get_agreement_fields`, `retrieve_agreement_chunks`, and `get_agreement_text` as needed.
6. Only after the legal position is grounded should you draft the response.
7. Label open ambiguity instead of drafting past it.

## Drafting Rules

- Give the user the legal answer first, then the draft.
- Keep customer-facing wording aligned with the actual paper.
- Quote controlling language internally for material claims.
- Distinguish `field-derived`, `retrieval-supported`, `full-text confirmed`, and `manual review required`.

## Output Format

```markdown
## Generated Response: [Inquiry Type]

### Legal Position
[What the paper supports]

### Draft Response
[Email or message draft]

### Evidence
[Agreement, section, quote, and evidence status]

### Escalation Check
[Triggers found or confirmation that none were found]

### Follow-Up Actions
1. [Action]
2. [Action]
```

## Notes

- If no relevant agreement or evidence is found, say so clearly and draft a narrower response.
- Do not let a polished draft outrun the contract evidence.
