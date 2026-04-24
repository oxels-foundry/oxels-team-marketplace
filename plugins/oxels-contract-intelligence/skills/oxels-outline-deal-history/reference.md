# Outline Deal History Reference

Use this reference for detailed output shaping, edge cases, and evidence discipline that should not bloat `SKILL.md`.

## Recommended intake prompts

Ask only for real gaps. Useful prompts include:

- `Which agreement or deal should I trace?`
- `Do you want the full amendment chain, or only one issue tracked through the chain?`
- `Are you trying to understand the current operative position, or what the paper looked like before a specific amendment?`

## Default chat template

Use this markdown shape unless the user asks for something narrower.

```markdown
## Deal snapshot
- Agreement or deal:
- Scope of history:
- What this answer is tracing:

## Chain overview
- Base agreement:
- Later chain steps:
- Overall story:

## Timeline of changes
### Step 0: Base agreement
- Document:
- Role in chain: Base agreement
- What it established:
- Evidence status:

### Step 1: [Amendment or addendum name]
- Document:
- Role in chain:
- What changed from the prior operative position:
- Practical effect:
- Evidence status:

### Step 2: [Next amendment or addendum]
- Document:
- Role in chain:
- What changed from the prior operative position:
- Practical effect:
- Evidence status:

<!--
  Include the section below ONLY if Step 4 (governing stack conflict scan) found a genuine conflict.
  If no genuine conflict was found, omit this section entirely — do not add a placeholder or "none found" line.
-->

## Clauses Resolved by Precedence
- [Term or concept]: [Document A] (type, precedence basis) says "[X]" — [Document B] says "[Y]" — [Document A/B] controls because [it carries the higher amendment priority / the order-of-precedence clause places it above the other document / it contains explicit override language in Section X] — Practical effect: [what this means operatively]
- [Term where precedence is unclear]: [Doc A] says "[X]" — [Doc B] says "[Y]" — Controlling document unclear: [reason, e.g. no order-of-precedence clause found] — Manual review required

## Current operative position
- What appears to control now:
- Key takeaways:

## Confidence and gaps
- Confirmed from source:
- Retrieval-supported:
- Open ambiguity:
- Recommended follow-up:
```

## Issue-tracking variant

When the user wants one issue traced through time, narrow the answer to that issue.

Useful issue families:

- pricing or discounting
- term or renewal
- termination and refund mechanics
- scope or product coverage
- privacy, security, or support obligations
- assignment or change of control

For issue-tracking, each timeline step should answer:

- what the prior operative position was
- what the new document changed for that issue
- whether the change looks additive, corrective, or overriding
- what the issue appears to mean now

## Conflict detection

Always run the governing-stack scan (Step 4). The `Clauses Resolved by Precedence` section is conditional on finding a real conflict — omit it entirely when none is found.

### What counts as a genuine conflict

A genuine conflict exists when two documents in the governing stack define the same obligation or right in materially different ways and at least one of them is operative (not merely recited as background). Examples:

- ORDER_FORM says Net 90; MSA says Net 60 for the same payment obligation
- Base agreement caps liability at 12 months of fees; an amendment sets a fixed dollar cap
- MSA requires 30 days' termination notice; an addendum reduces it to 14 days

Do not flag as a conflict:

- complementary language where each document covers a different dimension of the same topic (e.g., MSA sets general invoicing process; ORDER_FORM sets the specific fee amounts)
- expected document-type differentiation where the more specific instrument clearly governs
- structural variation in wording that does not change the operative obligation or right

### How to check

Run `retrieve_agreement_chunks` with all governing-stack agreement IDs. Focus queries on commercially sensitive terms listed in Step 4. Verify both sides of a suspected conflict from source text before surfacing it.

### How to present a conflict

For each genuine conflict:

1. state the term or concept in plain language
2. quote or precisely paraphrase what each document says, with document type and section where available
3. state which document controls and on what basis — use plain language in the output, not internal field names:
   - for amendment-chain conflicts: the amendment with the higher priority ranking controls (rank 1 outranks rank 2, and so on); express this as "the controlling amendment carries a higher priority" or similar
   - for document-type conflicts: the stack's order-of-precedence clause governs (e.g., order form terms take precedence over the MSA)
   - when explicit override language exists in the source text: quote or paraphrase it directly
4. state the practical difference — what it means operatively for the reader

### When the controlling document is unclear

Flag as `Controlling document unclear — manual review required` when:

- no order-of-precedence clause has been confirmed from source
- `precedence_rank` is absent or tied across conflicting amendments
- the scope of the later document is ambiguous about whether it was intended to amend the conflicting term

Do not silently pick a winner. Only `precedence_rank`, a confirmed order-of-precedence clause, or explicit override text in the source resolves a conflict definitively.

## Edge cases

### No amendments found

If `get_amendment_chain` returns only the base agreement:

- say clearly that no later amendments were found in the chain
- summarize the base agreement as the current known operative position
- do not imply there is a longer history unless another document set suggests otherwise

### Chain appears incomplete

If the result or surrounding context suggests missing paper:

- say which step appears missing or unclear
- identify likely related documents to review next, such as order forms, exhibits, side letters, DPAs, SLAs, or security paper
- label the current view as incomplete rather than forcing a full timeline

### Addendum does not fully replace earlier language

Some later documents supplement rather than replace the earlier agreement.

When that happens:

- say the later document appears to modify only a bounded topic
- explain that untouched terms likely remain governed by the earlier paper
- avoid phrasing that suggests the whole agreement was restated unless the text supports that

### Structured delta is too thin

If the chain result says a field changed but the legal effect is not obvious:

- use `retrieve_agreement_chunks`
- escalate to `get_agreement_text` if the effect is still ambiguous or material
- report the change as a tentative summary until the text is checked

### User asks for "version history"

If the user really means upload or revision history rather than legal amendment lineage:

- explain the distinction
- use the legal chain workflow only if they want the operative contractual history
- mention file-version history separately only if they ask for that specific concept

## Evidence wording

Use these labels consistently:

- `Confirmed from source`: the operative effect was checked against source text
- `Retrieval-supported`: clause retrieval supports the summary, but full text was not required
- `Structured chain only`: the summary comes from the amendment-chain output and may need source confirmation
- `Open ambiguity`: the chain or text does not yet resolve the point cleanly

Avoid:

- `not found` meaning `confirmed absent`
- `changed field` meaning `fully understood legal effect`
- `latest wins` meaning every earlier term was fully replaced

## Wording guidance

Prefer:

- `The base agreement established`
- `The next amendment appears to change`
- `This addendum seems to supplement`
- `The current composed view suggests`
- `This point still needs source confirmation`

Avoid:

- ontology-specific field names as the main user-facing explanation
- claiming a side document is part of the amendment chain unless the data or text supports that relationship
- treating upload history as the same thing as legal history

