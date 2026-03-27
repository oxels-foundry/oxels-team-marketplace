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
