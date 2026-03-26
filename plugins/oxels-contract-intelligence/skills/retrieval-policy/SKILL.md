---
name: retrieval-policy
description: Choose the correct Oxels retrieval mode for a question: exact structured fields, scoped agreement/deal graph traversal, chunk-level evidence retrieval, or full agreement text. Use when deciding how to answer broad portfolio questions, fuzzy legal concepts, or missing-field cases.
metadata:
  short-description: Retrieval policy and tool semantics
---

# Retrieval Policy

Use this skill when the main question is not the contract concept itself, but how to retrieve the right evidence safely and efficiently from the current Oxels MCP.

The current MCP surface is:

- `retrieve_field_definitions`
- `describe_fields`
- `search_agreements`
- `get_agreement_fields`
- `retrieve_agreement_chunks`
- `get_agreement_text`
- `list_organizations`
- `get_organization_deals`
- `get_deal`
- `get_agreement_versions`
- `get_amendment_chain`

## Retrieval modes

Think in five retrieval modes:

- exact structured terms
- scoped container traversal
- evidence scan (ranked)
- exhaustive corpus scan (agent-orchestrated)
- full-text confirmation

## When to use exact structured terms

Use `get_agreement_fields` when:

- the field names are already known
- the question is about normalized values, not open-ended clause wording
- the answer needs categorical, numeric, boolean, or date values

Examples:

- payment terms
- renewal type
- publicity rights
- privacy mode
- liability cap

Use `describe_fields` first if you know the concept but want exact field names, categories, required flags, or coverage.

Use `retrieve_field_definitions` first if the user starts with fuzzy language like:

- "net terms"
- "price protection"
- "termination for convenience"
- "data residency"

## When to use scoped container traversal

Use `list_organizations`, `get_organization_deals`, `get_deal`, and `search_agreements` when:

- the user asks about one customer, one deal, one agreement type, or one date window
- you need to narrow the candidate population before reading fields or evidence
- the user asks portfolio questions within an obvious scope
- you want amendment-aware or provenance-aware scoping before deeper review

Examples:

- all agreements for one customer
- all MSAs with active status
- all MSAs uploaded this month
- all agreements last modified last quarter
- agreements that have downstream amendments
- a specific deal package
- agreements expiring in the next 90 days

This is the closest thing the current MCP has to graph traversal. Treat it as container traversal, not a rich graph query language.

`search_agreements` also returns useful scope metadata including `document_uploaded_at`, `document_last_modified_at`, `has_amendments`, and `version_count`. Use that metadata to decide whether to escalate into amendment-chain or version-history review.

## When to use evidence scan

Use `retrieve_agreement_chunks` when:

- the question is clause-heavy or phrased conceptually
- the exact field name is unknown
- the answer depends on negotiated language or non-standard text
- you want fast evidence snippets before opening full text

Examples:

- uncapped liability
- termination for convenience with refund
- customer name/logo restrictions
- residency restrictions
- override language in additional terms

Important semantics:

- `top_k` is the number of agreements returned, not the number of chunks
- `candidate_count` controls how many chunk candidates are considered before agreement grouping; raise it for completeness-oriented scans
- `detailed_results` controls how many of the returned agreements include full snippets; the remainder are returned as compact metadata
- `is_current` defaults to true; keep it true unless you intentionally want to inspect superseded document versions
- snippets are compact evidence, not exhaustive clause reproductions
- `include_hits` should usually stay false unless debugging retrieval behavior
- `mode` can be `hybrid`, `bm25`, or `vector`, but default to `hybrid`
- the top-level `assessment` block tells you whether the result is exploratory, ranking-limited, or safe for absence claims

## Completeness assessment

When the user cares about corpus completeness, read the top-level retrieval counts before drawing conclusions:

- `total_scoped_agreements` = how many agreements were in scope before retrieval ranking
- `total_candidate_agreements` = how many of those agreements had at least one candidate chunk hit
- `coverage_ratio` = candidate agreements divided by scoped agreements
- `total_returned_agreements` = how many agreements were actually returned in this response
- `assessment.scope_type` = whether the result came from single-agreement, explicit-batch, or global-ranked scope
- `assessment.absence_claims_safe` = whether a missing hit can be treated as a safe absence claim
- `assessment.ranking_limited` = whether ranking can still suppress weaker matches
- `assessment.requires_full_text_confirmation` = whether full text should still be consulted before high-stakes conclusions

Interpretation:

- low `coverage_ratio` may mean the query is too narrow, the scope is too broad, or the concept is sparse in the corpus
- high `coverage_ratio` with low `total_returned_agreements` means the current response is only showing the top slice
- do not treat missing returned agreements as evidence of absence unless you have also reasoned about scope and coverage

## When to use exhaustive corpus scan

Use an agent-orchestrated exhaustive scan when:

- the user asks for "all" or "every" and the question is clause-heavy or textual
- the domain is legal, compliance, or audit and ranked search is not acceptable as the final step
- the answer requires a definitive per-agreement yes/no attestation
- coverage must be provably 100% of the scoped population, not "probably good enough"

The workflow is:

1. use `search_agreements` to enumerate the bounded set
2. call `retrieve_agreement_chunks` once per agreement, or in small `agreement_ids` batches
3. reconcile every requested ID into matched or excluded

When `agreement_ids` is explicitly provided to `retrieve_agreement_chunks`, every ID is accounted for in one of:

- `agreements`
- `compact_agreements`
- `excluded_agreements`

This makes the tool honest for bounded batches, while still keeping orchestration in the agent instead of the server.

For audit-grade work, prefer single-agreement calls or very small batches. Large `agreement_ids` batches are still ranked within that batch, so they are best for efficient review, not final attestation.

## When to use full agreement text

Use `get_agreement_text` only when:

- chunk evidence is ambiguous
- the question is high-stakes
- the answer depends on surrounding clause context
- you need to inspect the actual drafting, not just the retrieved snippet

Do not start with full text unless the user explicitly asks for a close reading or the result set is already narrow.

## Default decision policy

Use this order by default:

1. If the concept is fuzzy, start with `retrieve_field_definitions`.
2. If the scope is broad, narrow with `search_agreements` or container readers.
3. If the answer is normalized, read with `get_agreement_fields`.
4. If the answer is clause-heavy and the user wants ranked evidence, use `retrieve_agreement_chunks`.
5. If the answer is clause-heavy and the user asks for "all" or needs audit-grade completeness, use `search_agreements` plus `retrieve_agreement_chunks` per agreement or in very small batches.
6. If the snippets are insufficient, escalate to `get_agreement_text`.

## Policy for “all” queries

When the user asks for "all" results:

- do not immediately fetch every agreement text
- first identify whether "all" means:
  all agreements in the workspace
  all agreements for one org
  all agreements of one type
  all agreements matching a concept

Then:

1. use the narrowest possible scope tool first
2. summarize counts and candidate sets before deep reads
3. use retrieval snippets for portfolio-wide evidence gathering
4. escalate to full-text review only for the subset that matters

For very broad scans, prefer a two-pass workflow:

- pass 1: retrieve candidates
- pass 2: validate top candidates or exceptions

For corpus-complete workflows, prefer a scoped batching workflow:

1. use `search_agreements` to enumerate the exact agreement population
2. for time-bounded corpus questions like "this month" or "last quarter", prefer `created_basis` + `created_from` / `created_to` over extracted field dates when the user means corpus time rather than contractual time
3. for audit-grade work, call `retrieve_agreement_chunks agreement_id="..."` one agreement at a time
4. for faster review, use small `agreement_ids` batches and reconcile every ID from `agreements`, `compact_agreements`, and `excluded_agreements`
5. increase `candidate_count` when concept recall matters more than latency
6. use `coverage_ratio` and `total_scoped_agreements` to report what portion of the scope produced evidence

## Missing-field escalation

Use this escalation ladder when a field is absent or not good enough:

1. Check whether the exact field exists with `retrieve_field_definitions` or `describe_fields`.
2. If the field exists but is sparse, read the available value and report the coverage/limitations.
3. If the field does not exist or is too sparse, use `retrieve_agreement_chunks` with a concept query.
4. If chunk evidence is still ambiguous, inspect `get_agreement_text`.
5. If the concept still cannot be answered reliably, say the ontology does not currently support a confident answer.

Do not silently convert "field missing" into "term absent."

## Field absence semantics

Interpret missing values carefully:

- missing field value does not mean the contract lacks the concept
- missing extracted value may mean extraction coverage is incomplete
- missing agreement-level field may still be overridden or expressed in `additional_terms`
- contract end dates are stored per line-item family (`<product>_end_date`, `precommitted_usage_end_date`, `support_end_date`, `implementation_fee_end_date`); use `list_renewals` or `search_agreements date_field=<field>` to query them, or derive from `effective_date + term_length` as fallback

Always distinguish:

- field absent from schema
- field present in schema but null on this agreement
- field present but low-coverage or noisy
- concept only supported by clause text

## Broad question patterns

Recommended mode by question type:

- "What is the payment term for X?" -> scoped container traversal + exact structured terms
- "Which customers have T4C?" -> evidence scan first, structured follow-up if field exists; if the user wants a definitive answer across the entire portfolio, enumerate with `search_agreements` and inspect each agreement with `retrieve_agreement_chunks`
- "Do all our active MSAs have a limitation of liability clause?" -> exhaustive corpus scan: scope with `search_agreements`, then call `retrieve_agreement_chunks` per agreement
- "Show me all privacy mode deals" -> field-definition discovery, scoped traversal, then structured reads
- "What governs this customer?" -> scoped container traversal, then embedded-instrument reasoning
- "Do we have any weird liability terms?" -> evidence scan, then structured and full-text confirmation

## Output guidance

When reporting retrieval-backed conclusions, say which mode drove the answer:

- structured field
- container traversal
- retrieval snippet
- full-text review

Also say when you had to escalate because the ontology or field coverage was insufficient.
When the task is completeness-sensitive, also report the retrieval coverage numbers and whether the scan used `agreement_ids` batching or only a top-ranked slice.
