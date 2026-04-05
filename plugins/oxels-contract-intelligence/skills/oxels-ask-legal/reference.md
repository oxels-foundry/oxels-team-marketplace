# Ask Legal Reference

Use this file for reusable Q&A structure and evidence standards that do not need to live in `SKILL.md`.

## Evidence ladder

Use the strongest applicable label for each material conclusion:

| Label | Meaning | When it is enough |
| --- | --- | --- |
| `Field-derived` | Supported by extracted `Oxels MCP` fields | Low-risk, direct, well-defined values |
| `Retrieval-supported` | Supported by clause retrieval snippets | Candidate interpretation, comparison, or quick answer with visible text support |
| `Full-text confirmed` | Supported by full agreement text review | High-stakes, ambiguous, interaction-heavy, or customer-facing guidance |
| `Manual review required` | Evidence is incomplete, conflicting, or too thin | Final answer should be qualified and escalated |

Rules:

- Do not use `Field-derived` alone when the issue turns on clause nuance or document interaction.
- Do not treat `Retrieval-supported` as final absence proof across a broad corpus.
- Use `Full-text confirmed` before giving firm guidance on termination, pricing changes, renewal mechanics, liability, indemnity, privacy, security, or other high-risk topics.

## Answer rubric

Every strong answer should separate:

1. `Holding`: the direct answer to the question
2. `Basis`: why that answer follows from the contract or precedent
3. `Action for sales`: what the seller should say, do, or avoid
4. `Risk`: what could go wrong if the position is overstated
5. `Fallback or escalation`: safest alternative, trade, or reviewer
6. `Evidence`: quote, section, and source type
7. `Confidence`: how solid the conclusion is

## Core answer templates

### Agreement-specific Q&A

Use this when the answer turns on a named customer, deal, or agreement.

```markdown
## Question and scope
[What the seller is asking, plus the agreement or deal scope used]

## Short answer
[Direct answer]

## What sales should do or say next
[Practical guidance]

## Legal / commercial rationale
- Holding: [What the paper allows, prohibits, or conditions]
- Basis: [Why this follows from the operative document stack]
- Risk: [What risk exists if sales over-commits]
- Fallback / escalation: [Best alternative or required reviewer]

## Evidence
- [Document type], [section]: "[Quote]"
- Evidence level: [Field-derived / Retrieval-supported / Full-text confirmed]

## Confidence and gaps
[Any ambiguity, missing document, or needed follow-up]
```

### Standard / precedent Q&A

Use this when the question is about what is typical, standard, or previously accepted.

```markdown
## Question and scope
[What standardness question is being answered and what comparable set was used]

## Short answer
[Direct answer]

## What sales should do or say next
[How to position this with the customer or internally]

## Standard-position context
- Active agreement: [If relevant]
- Standard paper: [What baseline paper appears to say]
- Precedent-backed exceptions: [What the corpus shows has been done]
- Recommended commercial response: [What sales should actually propose, hold, or escalate]
- Thin spots: [What is still uncertain]

## Evidence
- Comparable example: [Customer or agreement context if appropriate]
- Quote: "[Relevant language]"
- Evidence level: [Retrieval-supported / Full-text confirmed]

## Confidence and gaps
[Comparator limits, missing peer definition, or weak support]
```

### Response drafting

Use this only after the legal answer is already grounded.

```markdown
## Internal legal answer
[Direct answer with risk and fallback]

## Sales-safe wording
[Customer-facing language that stays within the legal answer]

## Do not say
- [Overstatement 1]
- [Overstatement 2]

## Evidence
- [Document type], [section]: "[Quote]"
```

## Escalation triggers

Escalate to `Needs legal review` or `Manual review required` when:

- the controlling agreement cannot be identified confidently
- the amendment chain may change the answer and has not been reviewed
- the answer depends on text outside the currently reviewed document
- ranked retrieval suggests a result but full confirmation is still missing
- the requested customer-facing language would imply a promise broader than the paper supports
- precedent support is thin but the user is asking for a firm policy-level statement
- the issue involves a high-risk family such as termination, liability, indemnity, privacy, security, or pricing mechanics

## Sales-facing phrasing rules

When drafting language for sales:

- prefer `based on the current agreement` over absolute statements
- distinguish `we can usually accept` from `our contract requires`
- avoid promising outcomes that depend on future approval, amendment, or legal review
- keep commercial guidance practical and narrow
- if the support is mixed, say that directly instead of smoothing it over
