---
name: contract-ontology
description: Explain and navigate the Oxels contract ontology across organizations, deals, agreements, embedded instruments, document versions, extracted fields, and conceptual effective-state objects. Use when the user needs to understand how contract data is modeled or how to traverse it correctly.
metadata:
  short-description: Contract ontology and traversal rules
---

# Contract Ontology

Use this skill when the task is about what the Oxels contract model means, how entities relate, or which objects should be queried for a legal or commercial question.

## Core model

The persisted ontology has seven primary layers:

- `organizations`: customer or counterparty records. Current dataset uses `relationship_type = CUSTOMER`.
- `deals`: Salesforce-opportunity-shaped commercial containers.
- `agreements`: legal instruments split by type (`ORDER_FORM`, `MSA`, `DPA`, `SLA`, `AMENDMENT`, `ADDENDUM`, etc.).
- `deal_agreements`: many-to-many join linking agreements into a deal.
- `document_versions`: source-file metadata and raw text for an agreement.
- `schema_versions` and `schema_fields`: ontology definitions for each agreement type.
- `extracted_fields`: sparse key-value facts extracted from an agreement.

## Conceptual model

The conceptual model is richer than the persisted tables. When reasoning, distinguish these concepts:

- Commercial container: the `deal`.
- Legal instrument: an `agreement`.
- Embedded instrument set: multiple agreements that came from the same uploaded file and therefore share a `source_content_document_id`.
- Evidence-bearing source: the `document_version` row with raw text, file metadata, and DocuSign metadata.
- Normalized fact: one `extracted_field`.
- Effective state object: a synthesized view of the terms in force for one agreement or deal as of a date. This is mostly conceptual today; the MCP does not persist it directly.

## Traversal rules

Use these traversal rules by default:

1. Start from `organization` when the user asks about a customer portfolio.
2. Start from `deal` when the user asks about a commercial package, opportunity, or a bundle of related instruments.
3. Start from `agreement` when the user asks about one legal instrument type or one extracted clause.
4. Use `source_content_document_id` as the conceptual decomposition key, but remember the current MCP often exposes it only indirectly through document-version metadata, file paths, or titles.
5. Use `document_versions` only as evidence or provenance, not as the primary business object.
6. Use canonical field-definition retrieval before assuming field names.

## Embedded instruments

A single uploaded file can yield several agreement records. Common pattern:

- one `ORDER_FORM`
- one embedded `MSA`
- sometimes embedded `DPA`, `SLA`, or `ADDENDUM`

When agreements share a `source_content_document_id`, treat them as decomposed views of one source document unless evidence suggests otherwise. In current MCP workflows, recover this relationship indirectly through shared file metadata from `get_agreement_versions`, similar titles, and same-deal context.

## Agreement types

Current ontology is centered on:

- `ORDER_FORM` and `AMENDMENT`: commercially dense, with pricing, payment, product, support, and signer data.
- `MSA`: clause-heavy legal baseline.
- `DPA` and `SLA`: specialized legal overlays.
- `ADDENDUM`: focused modifications or references to another agreement.

## Field families

The ontology is not just scalar terms. It includes several repeated commercial families, such as:

- `precommitted_usage`
- `support`
- `implementation_fee`
- `signer`
- `customer_info`

Treat these as grouped structures, not isolated scalar fields.

## Source-of-truth hierarchy

When facts disagree, prefer this order:

1. Raw clause text from `get_agreement_text` or `retrieve_agreement_chunks`.
2. Structured extracted fields from `get_agreement_fields`.
3. Canonical field-definition records from `retrieve_field_definitions` and `describe_fields`.
4. Generic deal-level interpretation inferred from names or dates.

If the answer depends on an inference rather than an explicit field, say so.

## Current data limitations

Important limitations in the current dataset:

- `amends_agreement_id` is now preserved when valid source links exist, but linkage coverage can still vary by dataset slice. Treat explicit amendment links as strong positive evidence, not proof that every modifying relationship is linked.
- `document_versions` are real evidence-bearing rows with timestamps, file metadata, and raw text, but version depth varies by agreement. Inspect `get_agreement_versions` instead of assuming either rich history or single-version records.
- Clause extraction coverage is much stronger for some concepts than others.

Do not overstate certainty on amendment chains or draft-vs-executed comparisons.

## Recommended tool order

Use Oxels tools in this order:

1. `retrieve_field_definitions` for fuzzy ontology or field-concept discovery.
2. `describe_fields` for exact field metadata, coverage, and document-type organization.
3. `list_organizations`, `search_agreements`, `get_organization_deals`, or `get_deal` to establish container relationships and inspect scope metadata such as document timestamps, amendment presence, and version counts.
4. `get_agreement_fields` for normalized facts.
5. `retrieve_agreement_chunks` for compact clause evidence.
6. `get_agreement_text` only when full-text review is necessary.
7. `get_agreement_versions` for provenance, file paths, timestamps, DocuSign metadata, and indirect recovery of shared source-document relationships.

## Answering guidance

When explaining the ontology:

- Separate persisted tables from conceptual business objects.
- Name the join path you are using.
- Call out when a relation is explicit versus inferred.
- Mention embedded-instrument decomposition whenever `source_content_document_id` is doing important work.
- Prefer retrieval snippets for explanation and escalate to full text only when the snippets are insufficient.
