---
name: lifecycle-and-effective-terms
description: Reason about amendment composition, supersession, renewals, term windows, and as-of-date effective state in the Oxels ontology. Use when the user asks what terms are in force, how amendments should compose, or how to evaluate a contract portfolio over time.
metadata:
  short-description: Lifecycle and as-of-date reasoning
---

# Lifecycle And Effective Terms

Use this skill when the user asks:

- what terms are in force as of a date
- how amendments should modify a base agreement
- how renewal timing should be interpreted
- whether a contract is active, upcoming, expired, or unknown

## Current MCP behavior

The server currently has a narrow lifecycle model:

- `get_amendment_chain` composes explicitly linked chains using a simple last-wins rule
- `search_agreements` can surface `has_amendments`, corpus-time filters, and `version_count` for scoping

That is useful but incomplete. Treat it as baseline behavior, not final truth.

## Effective-state object

Use this conceptual object when answering lifecycle questions:

- scope: one agreement or one deal
- as_of_date: explicit or implied
- governing instruments: base agreement plus modifying overlays
- scalar terms in force
- line-item families in force
- clause overrides in force
- confidence level for explicit versus inferred relationships

This object is conceptual today. Construct it in reasoning; do not pretend it is stored.

## Relationship hierarchy

Build the effective state in this order:

1. Identify the primary instrument or deal.
2. Collect embedded instruments that appear to come from the same source file. Prefer explicit shared source identifiers when available; otherwise infer from shared deal context, titles, and `get_agreement_versions` metadata.
3. Identify amendment-like records:
   explicit `AMENDMENT` or `ADDENDUM`
   explicit `amends_agreement_id` if populated
   otherwise infer candidates from same org, same deal, title patterns, and modified-term text.
4. Apply overrides by term family.

Always label inferred amendment links as inferred.

## Default supersession rules

Use these composition rules unless the data clearly contradicts them:

- Scalar fields: latest explicit value supersedes prior value.
- Missing fields do not erase prior values; they inherit.
- Boolean flags: explicit `False` is meaningful and can override prior `True`.
- Clause text fields: latest explicit clause text controls that concept, but preserve prior evidence in the explanation.
- `additional_terms` and `modified_terms`: treat as overlay text that can override multiple canonical provision families.
- Line-item families such as `<product>`, `precommitted_usage`, `support`, `implementation_fee`: do not blindly apply scalar last-wins logic. Treat them as grouped commercial components.

## Line-item reasoning

For grouped commercial families:

- use the family-specific fields together
- key the group by family plus product or line name when available
- use start and end dates inside the family if present
- allow an amendment to add one family without replacing another

If the data is too sparse to distinguish replace-versus-add, say so and present both plausible interpretations.

## Renewal reasoning

Use this precedence order:

1. earliest populated line-item end date (`<product>_end_date>`, `precommitted_usage_end_date`, `support_end_date`, `implementation_fee_end_date`)
2. parseable `effective_date + term_length`
3. renewal fields such as `renewal_type`, `renewal_term`, and `renewal_notification_days`
4. otherwise `unknown`

`list_renewals` applies this precedence automatically and returns `expiry_field_name` to show which field drove the date.

Interpretation rules:

- `Automatic` renewal means continuing unless timely notice is given.
- `Manual` renewal means no automatic extension should be assumed.
- `renewal_caps_price_protection` affects economic continuation, not whether renewal exists.

## As-of-date reasoning

When the user gives an as-of date:

1. determine which instruments existed by that date
2. determine which terms were already effective by that date
3. determine which term windows had not yet expired
4. compose the effective-state object
5. state what is explicit and what is inferred

If the user does not give an as-of date, default to today.

## Important limitations

Current dataset limitations materially affect lifecycle reasoning:

- `amends_agreement_id` coverage may still be incomplete, so explicit amendment linkage cannot be assumed to capture every modifying relationship
- document version history depth varies by agreement, so draft-versus-final reasoning should start with `get_agreement_versions` rather than an assumption
- amendment linkage often must be inferred from titles, deal context, or free text
- many legal overrides live in `additional_terms` instead of dedicated structured fields

## Recommended workflow

1. `get_deal` or `search_agreements` to establish scope. For portfolio work, use `has_amendments = true` when you specifically want agreements that have downstream overlays.
2. `get_agreement_fields` for structured fields.
3. `retrieve_field_definitions` or `describe_fields` if the relevant families are unclear.
4. `retrieve_agreement_chunks` to find modification, supersession, renewal, or override language.
5. `get_agreement_text` when the chunk evidence is insufficient for a lifecycle conclusion.
6. Use `get_amendment_chain` only when explicit linkages exist or you want to compare the server's simplistic composition against a more careful manual one.

## Output guidance

For lifecycle answers, report:

- as-of date used
- governing agreements or candidate overlays
- current commercial terms
- current legal exceptions or overrides
- renewal and expiration interpretation
- confidence notes and missing links
- whether the conclusion was driven by structured fields, retrieval snippets, or full-text review
