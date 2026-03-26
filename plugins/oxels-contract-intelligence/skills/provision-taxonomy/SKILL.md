---
name: provision-taxonomy
description: Normalize Oxels contract fields and clause extractions into canonical provision families such as termination, renewal, liability, indemnity, publicity, privacy mode, data residency, and payment mechanics. Use when the user needs a stable taxonomy over heterogeneous extracted fields.
metadata:
  short-description: Canonical taxonomy for contract provisions
---

# Provision Taxonomy

Use this skill when the user wants a stable conceptual layer over raw Oxels fields.

The dataset mixes:

- normalized scalar fields like `payment_terms`
- boolean policy markers like `publicity_rights`
- clause text fields like `t4c_clause`
- broad free-text overlays like `additional_terms`

Your job is to map them into canonical provision families.

## Canonical provision families

Use these families by default:

- `termination`
- `renewal`
- `pricing_and_price_protection`
- `payment_mechanics`
- `liability`
- `indemnity`
- `publicity_and_brand_use`
- `privacy_and_data_processing`
- `data_residency_and_subprocessors`
- `support_and_service_levels`
- `ip_and_confidentiality`
- `non_standard_overrides`

## Field-to-family mapping

Default mappings:

- `t4c_clause`, `termination_notice_period`, `extra_termination_clauses` -> `termination`
- `renewal_type`, `renewal_term`, `renewal_notification_days`, `renewal_caps_price_protection` -> `renewal`
- `total_amount`, `cursor_token_rate`, `credits_amount`, `on_demand_margin` -> `pricing_and_price_protection`
- `payment_terms`, `billing_frequency`, `true_up_frequency`, `true_up_frequency_text`, `payment_milestones` -> `payment_mechanics`
- `liability_cap` -> `liability`
- `indemnification` -> `indemnity`
- `publicity_rights` -> `publicity_and_brand_use`
- `contains_privacy_mode`, `includes_privacy_mode`, `processing_purposes`, `security_measures` -> `privacy_and_data_processing`
- `data_residency_requirements`, `sub_processors_allowed`, `governing_regulation` -> `data_residency_and_subprocessors`
- `uptime_commitment`, `service_credits`, `response_time_*`, `measurement_window`, support family fields -> `support_and_service_levels`
- `intellectual_property`, `confidentiality_term`, `confidentiality_period`, `return_of_information`, `permitted_disclosures` -> `ip_and_confidentiality`
- `additional_terms`, `modified_terms` -> `non_standard_overrides`

## Normalization rules

Apply these rules:

1. Prefer the narrowest explicit field over a broader free-text field.
2. Use `additional_terms` as an override bucket, not a substitute for the whole taxonomy.
3. If a concept appears in both a boolean field and free text, report both:
   explicit structured signal plus narrative override or nuance.
4. Treat `includes_privacy_mode` and `contains_privacy_mode` as one conceptual feature: `privacy mode`.
5. Treat clause text fields as evidence-bearing text, not already-normalized legal conclusions.

## Priority concepts

If the user does not specify scope, prioritize these concepts first because they are commercially important and reasonably extractable in the current ontology:

- termination for convenience
- renewal mechanics
- price protection
- payment terms and true-up mechanics
- publicity rights
- privacy mode
- data residency
- liability cap
- indemnification

## Risk posture

You may add a risk or exception layer, but keep it separate from the taxonomy itself.

Good examples of exception labels:

- `customer_favorable_t4c`
- `manual_renewal`
- `strict_publicity_opt_out`
- `residency_restriction`
- `non_standard_liability_cap`
- `heavy_additional_terms`

Do not invent a risk label unless the field text or extracted value supports it.

## Clause-heavy agreements

For `MSA`, `DPA`, and `ADDENDUM` records:

- expect fewer scalar commercial fields
- expect more meaning to live in clause text or `additional_terms`
- validate high-impact conclusions with `retrieve_agreement_chunks` and `get_agreement_text`

## Tool order

1. `retrieve_field_definitions` when the user starts from a concept like "net terms", "price protection", or "termination for convenience".
2. `describe_fields` when you need exact field metadata, categories, examples, or coverage.
3. `search_agreements`, `get_deal`, or `get_organization_deals` to scope the population.
4. `get_agreement_fields` for one-agreement structured taxonomy output.
5. `retrieve_agreement_chunks` for clause evidence and concept confirmation.
6. `get_agreement_text` only when chunk snippets are insufficient.

## Output format

When presenting a taxonomy summary, prefer:

- canonical family
- supporting raw field names
- extracted values
- evidence status: explicit, inferred, snippet-validated, or full-text-validated

Always distinguish:

- field-level fact
- taxonomy-level interpretation
- commercial or legal conclusion

If a canonical family is discovered through retrieval before you know the exact field name, say which field-definition hits drove the mapping.
