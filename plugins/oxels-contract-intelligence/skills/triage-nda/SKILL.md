---
name: triage-nda
description: NDA pre-screen with a corpus-derived playbook baseline, GREEN/YELLOW/RED routing, and Oxels MCP for counterparty history and amendment-aware conflicts.
metadata:
  short-description: NDA triage vs corpus-derived playbook
---

# Triage NDA

Triage an incoming NDA by **deriving a typical playbook from your organization’s NDA and confidentiality agreements in the corpus**, then screening the incoming document against that baseline. Use `Oxels MCP` for the baseline, counterparty history, and amendment-aware conflicts—not generic “market defaults,” unless the corpus has no usable NDA sample.

**Important**: This skill supports legal workflows but does not provide legal advice. Use source text for material NDA findings.

## Invocation

```
/triage-nda
```

Accept the NDA as a file, URL, or pasted text. If the user has not provided the document, ask for it before classifying.

## Workflow

1. Accept the NDA in file, URL, or pasted-text form.
2. **Derive the playbook from corpus NDA paper** (before scoring the incoming doc):
   - Use `search_agreements` to build a **bounded set** of agreements that represent **your** standard confidentiality posture: e.g. your form NDA, template mutual NDAs, or recurring confidentiality agreements—prefer agreements you control or that appear as repeat starting points, not every random third-party NDA.
   - Use `retrieve_field_definitions` and `describe_fields` if the ontology exposes NDA-relevant structured concepts (term, mutual vs unilateral signals, or related field families).
   - Use `get_agreement_fields`, `retrieve_agreement_chunks`, and `get_agreement_text` on **representative** corpus NDAs to infer **typical** expectations: definition and confidentiality information scope, carveouts, use and disclosure duties, residual clause posture, term and survival, return and destruction, remedies and injunction language, IP / feedback / publicity hooks, non-solicit or non-compete riders, governing law and venue.
   - Summarize this as a short **internal baseline playbook** (bullet checklist or table) to use as the rubric for steps 3–5. If the user supplied an explicit written playbook, **prefer the user’s playbook** for criteria but still use Oxels to check counterparty-specific history.
   - If you **cannot** find a meaningful in-corpus NDA set, state that in the report and use a **conservative structural screen** only (no invented “market standard” claims); optionally ask the user for a single reference NDA or playbook link.
3. **Screen the incoming NDA** against the derived playbook and standard structure: parties, definitions, carveouts, obligations, term, return and destruction, remedies, problematic extras, governing law, and any IP or employment-adjacent riders.
4. If the counterparty or deal is identifiable, use `Oxels MCP` to look for existing NDA, MSA, order form, or amendment history for **that** relationship.
5. Use Oxels precedent to answer:
   - is there already operative confidentiality paper?
   - has this counterparty accepted corpus-typical or cleaner paper before?
   - is the incoming NDA **unusual relative to your derived playbook** and to similar agreements in the corpus?

## Oxels Rules

- **Playbook slice** (your typical NDA paper) and **counterparty slice** (this deal’s stack) may differ; build **two** bounded corpora when both apply, and label which conclusions come from which.
- Use `search_agreements`, `get_deal`, or `get_organization_deals` to resolve each slice.
- Use `get_amendment_chain` when the operative NDA position may have changed over time.
- Use `get_agreement_fields` where the ontology supports the concept.
- Use `retrieve_agreement_chunks` and `get_agreement_text` for residuals, exclusivity, non-solicit, non-compete, IP leakage, or other text-heavy issues.
- Separate `external NDA finding` (the file the user provided) from `Oxels playbook finding` (derived baseline) from `Oxels counterparty finding` (relationship-specific).

## Classification

Keep the three-way routing:

- `GREEN`: standard approval
- `YELLOW`: counsel review
- `RED`: full legal review

Escalate when the incoming NDA is problematic on its own or conflicts with what already appears operative in the corpus.

## Output Format

```markdown
## NDA Triage Report

### Classification
[GREEN / YELLOW / RED]

### Screening Results
[Core NDA criteria vs corpus-derived playbook]

### Oxels Findings
[Derived playbook signal, existing relationship paper, precedent, or conflicts]

### Issues Found
[What is wrong and why it matters]

### Recommendation
[Approve / review / counter / reject]

### Confidence and Gaps
[What is confirmed vs. what still needs manual review]
```

## Notes

- If the document is not really an NDA, route it to full contract review.
- If Oxels finds active confidentiality paper already in place, call that out early.
- The **derived playbook** is evidence-based inference from the corpus, not a substitute for approved legal policy; flag `manual review required` when the baseline sample is thin or contradictory.

