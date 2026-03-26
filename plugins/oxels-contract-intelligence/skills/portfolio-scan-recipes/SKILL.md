---
name: portfolio-scan-recipes
description: Run repeatable multi-step Oxels investigations across a contract portfolio, including renewal scans, payment-term exceptions, liability and clause searches, privacy/data residency reviews, and amendment-override analysis. Use when the user wants a reusable scan workflow rather than a one-off query.
metadata:
  short-description: Repeatable portfolio investigation recipes
---

# Portfolio Scan Recipes

Use this skill for repeatable investigation workflows. Optimize for:

- reproducible tool order
- clear filters
- human-readable findings
- explicit confidence on inferred conclusions

## General scan pattern

Use this base pattern for most scans:

1. Discover likely canonical fields with `retrieve_field_definitions`.
2. Confirm exact field metadata with `describe_fields` when needed.
3. Narrow the population with `search_agreements`, `list_organizations`, `get_organization_deals`, or `get_deal`.
   Use `search_agreements created_basis=...` for corpus-time questions and `has_amendments=true` when you want agreements that have downstream overlays.
4. For completeness-sensitive scans, enumerate the scoped agreement IDs and batch them into `retrieve_agreement_chunks agreement_ids=[...]`.
5. Read structured facts with `get_agreement_fields`.
6. Validate high-impact results with `retrieve_agreement_chunks`.
7. Use `get_agreement_text` only for ambiguous or high-stakes cases.
8. Summarize findings by agreement, org, and deal.

Completeness notes:

- raise `candidate_count` when recall matters more than latency
- keep `is_current = true` unless historical document versions are explicitly relevant
- read `total_scoped_agreements`, `total_candidate_agreements`, and `coverage_ratio` before claiming completeness
- read the `assessment` block to see whether the result is ranking-limited or safe for absence claims
- use `detailed_results` to keep broad scans compact while still getting rich snippets for the highest-ranked agreements

## Recipe: Renewal scan

Goal: find agreements approaching a decision point.

Steps:

1. Call `list_renewals horizon_days=<window>` to scan across all line-item end dates. Check `expiry_field_name` in each result to see which field drove the date. Or use `search_agreements date_field=<field> date_from=<ISO> date_to=<ISO>` to target a specific line item (e.g. `<product>_end_date`).
2. Pull `renewal_type`, `renewal_term`, and `renewal_notification_days` with `get_agreement_fields`.
3. If no end-date field is populated, derive from `effective_date + term_length` only if clearly parseable. Otherwise mark as missing.
4. Report:
   agreements expiring soon
   auto-renew versus manual
   notice risk
   missing-data cases

When the user instead means corpus time such as "agreements uploaded this month," use `search_agreements created_basis=document_uploaded_at` with `created_from` / `created_to` rather than extracted contract dates.

## Recipe: Payment-term exceptions

Goal: find off-policy payment mechanics.

Steps:

1. Use `retrieve_field_definitions` first if the exact payment field family is not known.
2. Scope the agreements you care about with `search_agreements`, `get_deal`, or `get_organization_deals`.
3. Read `payment_terms` with `get_agreement_fields`.
4. Compare against the expected baseline such as `Net 30`.
5. Add `billing_frequency`, `true_up_frequency`, and `true_up_frequency_text` through `get_agreement_fields` if needed.
6. Validate unusual terms with `retrieve_agreement_chunks` when structured values look noisy.

Useful patterns:

- scope the agreements first, then read `payment_terms`
- use retrieval for concepts like `invoice due net terms`
- use full text only when the structured values are inconsistent or overloaded

## Recipe: Uncapped or unusual liability scan

Goal: identify liability terms requiring legal review.

Steps:

1. Use `retrieve_field_definitions` with liability-oriented queries to confirm the relevant fields.
2. Use `describe_fields search="liability"` if you need exact schema placement.
3. Scope likely agreements with `retrieve_agreement_chunks` using phrases like `uncapped liability`, `limitation of liability`, or `notwithstanding`.
4. Read `liability_cap` and `additional_terms` with `get_agreement_fields`.
5. Treat `additional_terms` as a likely override source.

Do not label something uncapped unless clause text or structured extraction supports it.

## Recipe: T4C scan

Goal: locate customer-friendly termination for convenience rights.

Steps:

1. Use `retrieve_field_definitions` for `termination for convenience` if field names are not top of mind.
2. Use `retrieve_agreement_chunks` with queries such as `termination for convenience refund 30 days notice`.
3. Read `t4c_clause`, `extra_termination_clauses`, and `termination_notice_period` through `get_agreement_fields` on the candidate agreements.
4. Extract whether refunds, wind-down payments, or immediate payment obligations attach.
5. Separate:
   T4C exists
   who may exercise it
   economic consequence

## Recipe: Price protection scan

Goal: identify renewal economics and price-increase controls.

Steps:

1. Use `retrieve_agreement_chunks` with queries such as `renewal price increase cap` or `price protection renewal term`.
2. Pull `renewal_caps_price_protection`, `renewal_type`, and `renewal_notification_days` with `get_agreement_fields`.
3. Validate with `get_agreement_text` if the snippets are important or ambiguous.
4. Report:
   fixed pricing during term
   renewal increase cap
   notice requirement
   negotiation-only language

## Recipe: Exhaustive clause scan (audit-grade)

Goal: for a bounded set of agreements, definitively determine which ones do and do not contain a clause concept.

Steps:

1. Use `search_agreements` to define the exact population by org, type, status, deal, or date window.
   Use `created_basis` + `created_from` / `created_to` when the question is about when agreements entered or changed in the corpus.
2. Page through `search_agreements` until you have the full scoped agreement ID list.
3. For audit-grade work, call `retrieve_agreement_chunks` once per agreement using `agreement_id`.
4. Use the `assessment` block to confirm the result is absence-safe. For audit-grade work, prefer `assessment.scope_type = single_agreement`.
5. Classify each agreement as matched when evidence is returned, or unmatched when `assessment.absence_claims_safe = true` and the call comes back without a hit.
6. Read `get_agreement_text` only for agreements whose snippets need deeper review.
7. Report definitive counts such as: "73 of 200 active MSAs contain auto-renewal language. 127 do not."

For faster but still bounded review, use small `agreement_ids` batches. When `agreement_ids` is explicitly provided, every requested ID is accounted for in:

- `agreements`
- `compact_agreements`
- `excluded_agreements`

Use single-agreement calls instead of batches when:

- the domain is legal, compliance, or audit
- ranked search is not acceptable because a missed agreement could have real consequences
- you need a definitive per-agreement yes/no answer

## Recipe: Ranked evidence scan (exploratory)

Goal: survey an agreement population for a clause concept with ranked evidence and coverage statistics, not definitive per-agreement attestation.

Steps:

1. Use `search_agreements` to define the exact population by org, type, status, deal, or date window.
   Use `created_basis` when the user means corpus time like "this month" or "last quarter."
2. Page through `search_agreements` until you have the full scoped agreement ID list.
3. Batch those IDs into `retrieve_agreement_chunks agreement_ids=[...]`.
4. Use a higher `candidate_count` such as `1500-2000` for broad portfolio scans.
5. Keep `detailed_results` low and `snippets_per_agreement` low so you get breadth before depth.
6. Read `coverage_ratio`, `total_scoped_agreements`, and `assessment.ranking_limited` for each batch.
7. Escalate to `get_agreement_text` only for agreements that look ambiguous or high impact.

Use `retrieve_agreement_chunks` in ranked exploratory mode when:

- the user wants ranked evidence, not a definitive census
- speed matters more than exhaustive coverage
- the question is exploratory rather than compliance-driven

Recommended defaults for broad scans:

- `top_k`: 50
- `detailed_results`: 5-10
- `snippets_per_agreement`: 1
- `candidate_count`: 1500-2000
- `include_hits`: false
- `neighbor_chunks`: 0

## Recipe: Publicity, privacy mode, and data residency

Goal: review customer-facing controls and privacy commitments.

Steps:

1. Use `retrieve_field_definitions` to locate the right privacy and residency fields if needed.
2. Pull `publicity_rights`, `includes_privacy_mode`, `contains_privacy_mode`, and `data_residency_requirements` with `get_agreement_fields`.
3. Use `retrieve_agreement_chunks` for ambiguous residency or subprocessor language.
4. Normalize the results into:
   publicity allowed or restricted
   privacy mode present or absent
   residency restriction present or absent

## Recipe: Additional-terms override scan

Goal: find contracts where negotiated text likely overrides the standard form.

Steps:

1. Scope candidate agreements with `search_agreements`, `get_deal`, or retrieval queries that mention `additional terms`, `modified terms`, or `notwithstanding`.
   If you want likely override candidates first, prefer `search_agreements has_amendments=true` before the text scan.
2. Read `additional_terms` or `modified_terms` with `get_agreement_fields`.
3. Use `retrieve_agreement_chunks` on those agreements for terms such as `amended`, `replaced`, `notwithstanding`, `shall be revised`, or `prior written consent`.
4. Map the resulting text into canonical provision families using the `provision-taxonomy` skill.

This scan is often more informative than relying on clause-specific fields alone.

## Recipe: Embedded-instrument decomposition

Goal: understand one commercial package that was split into several agreements.

Steps:

1. Start with `get_deal`.
2. Group agreements that appear to share the same source document. Use `get_agreement_versions` metadata first, then same-deal context and title patterns.
3. Separate the `ORDER_FORM`, embedded `MSA`, `DPA`, `SLA`, and `ADDENDUM`.
4. Summarize which concepts live in which instrument.

Use this when a user asks "what governs this customer" or "where does this term live."

## Conditional recipe: Draft-vs-executed comparison

Do not treat this as a default first-class recipe.

Reason:

- version history depth varies by agreement
- current tools expose version metadata, but they do not auto-diff versions for you
- some agreements may still have only one meaningful current version

Only attempt it when `get_agreement_versions` shows a real multi-version chain worth comparing.

## Reporting guidance

For each scan, report:

- scope used
- fields and tools used
- scoped agreement count
- retrieval coverage ratio when chunk retrieval was used
- explicit findings
- inferred findings
- missing-data or ontology limitations

Prefer compact tables or flat lists over long prose when many agreements are involved.

When retrieval is used, note that:

- `top_k` applies to agreements, not chunks
- `detailed_results` controls how many returned agreements include full snippets; the rest may be compact metadata only
- `candidate_count` trades latency for broader evidence coverage
- snippets are compact evidence, not exhaustive clause reproductions
- `include_hits` is optional and mainly useful for debugging or deep reviews
