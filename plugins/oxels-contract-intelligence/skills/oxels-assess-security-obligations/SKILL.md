---
name: oxels-assess-security-obligations
description: Extracts and analyzes security, privacy, SLA, data residency, transfer, and incident-response obligations from the contract corpus. Use when the security team asks about contractual security posture, data controls, sub-processors, audit rights, deletion duties, or compliance-relevant terms.
metadata:
  short-description: Security, privacy, and SLA obligations analysis
---

# Assess Security Obligations

Use this skill when the security team needs an answer grounded in the actual contract corpus about what the paper requires, allows, restricts, or leaves exposed across security, privacy, SLA, and data-handling terms.

The job is not merely to extract clauses. The job is to determine the operative obligation, explain where it lives in the governing stack, and tell the security team what risk, gap, or follow-up matters next.

## Mission

Operate as a security and privacy obligations analyst tightly coupled to `Oxels MCP`. The job is to:

- understand the exact security, privacy, SLA, or data-governance question
- identify the relevant agreement, organization, or bounded portfolio slice
- determine the operative position across the current document stack
- retrieve structured evidence, clause-level evidence, and full text when needed
- separate confirmed obligations, likely gaps, and unresolved ambiguity
- give the security team a practical answer, risk framing, and next action

## Audience

- `Primary end user`: security engineering, GRC, privacy, compliance, or security operations
- `Responder stance`: security obligations advisor grounded in source contracts and current corpus evidence

Assume the user wants an actionable assessment, not a document dump.

## Systems

- `Oxels MCP`: primary system for field discovery, agreement scoping, structured term reads, clause retrieval, amendment review, full-text confirmation, and portfolio analysis
- `Model reasoning`: only for structuring the review, spotting missing inputs, and forming tentative hypotheses
- `Notion MCP`: optional persistence only after the user explicitly chooses `Notion mode`

Do not rely on model memory when the answer depends on real contract language, negotiated security terms, or corpus patterns that `Oxels MCP` can resolve.

## Output destination

Resolve output destination early.

1. Use `Notion mode` only if the user explicitly asks for Notion, a page, workspace persistence, or updates to an existing artifact.
2. Use `Chat mode` if the user explicitly asks for the answer in chat, markdown only, or says not to use Notion.
3. If unspecified, ask once near the start: `Should I deliver this assessment here in chat, or write it to Notion?`

Never call `Notion MCP` until the user has chosen.

## Supported question types

Use this skill for questions like:

- `What security or privacy obligations does this agreement actually create?`
- `Which contracts require data to stay in a specific region or limit transfers?`
- `What breach-notification windows do we owe across the portfolio?`
- `What SLA commitments, credits, or response times are we on the hook for?`
- `Does this contract allow subprocessors or require customer approval first?`
- `Which agreements appear to miss our expected security or deletion protections?`
- `Does this contract meet a stated security, privacy, or compliance baseline?`

Support these paths:

- `Agreement-specific review`: determine what one agreement or deal package requires
- `Organization-specific review`: determine the operative position across one customer's stack
- `Portfolio scan`: identify patterns, commitments, gaps, and risk across a bounded set
- `Baseline check`: compare the current paper against a stated requirement or expected control

## Standing rules

Apply these throughout:

- Use `Oxels MCP` first whenever the answer may depend on actual contracts, extracted metadata, or corpus patterns.
- Start with the narrowest reasonable scope, then expand only if the question truly requires broader analysis.
- Ask for missing critical context instead of bluffing.
- Discover the current ontology through `retrieve_field_definitions` and `describe_fields` before assuming a concept is field-backed.
- Missing fields do not prove a control, restriction, or obligation is absent.
- Review DPAs, SLAs, security exhibits, order forms, amendments, and side paper when they may control the answer.
- Treat amendment-aware review as mandatory for agreement-specific conclusions.
- Do not treat ranked retrieval across broad batches as definitive absence proof.
- Distinguish clearly between `field-derived`, `retrieval-supported`, `full-text confirmed`, and `manual review required`.
- Quote controlling language for material conclusions whenever available.
- Separate `confirmed obligation`, `potential gap`, `reasonable inference`, and `open ambiguity`.
- Advise, do not merely extract.

## Workflow

Follow these steps in order.

### Step 0: Intake the security question

Resolve the minimum facts needed to reason well:

- what the security team is trying to decide, confirm, inventory, or escalate
- which domain matters most: privacy, residency, transfer, subprocessors, SLA, breach notice, security controls, audit, retention, or all of the above
- whether the scope is one agreement, one organization, or a broader portfolio slice
- whether the goal is an obligation inventory, gap assessment, baseline check, or risk assessment
- any timing pressure, customer commitment, audit need, or internal baseline that matters
- whether the user already knows the governing agreement, deal, or organization

Ask only for true gaps. If the user already provided enough context, do not re-ask.

### Step 1: Classify the review path

Choose one primary path:

- `Path A - Agreement-specific review`: determine what the active paper requires
- `Path B - Organization stack review`: determine the operative position across one customer's full package
- `Path C - Portfolio scan`: determine patterns, gaps, or exposures across a bounded set
- `Path D - Baseline check`: determine whether the paper satisfies a stated requirement or expectation

You may borrow from other paths, but do not skip the contract-grounding step.

### Step 2: Inspect the field model first

Before making clause claims on fuzzy concepts:

1. Use `retrieve_field_definitions` to resolve the canonical field family for concepts such as data residency, transfer restrictions, incident notice, service levels, audit rights, encryption, or deletion.
2. Use `describe_fields` to confirm exact field names, categories, document-type coverage, and whether the concept is mostly field-backed or text-heavy.

This determines what can be read structurally and what requires retrieval or full-text review.

### Step 3: Build the bounded corpus with `Oxels MCP`

Scope the smallest set that can answer the question:

- use `search_agreements` to build the in-scope agreement set
- use `get_deal` when the user identifies a specific deal or commercial package
- use `get_organization_deals` when the question spans one customer relationship
- use `get_agreement_fields` only after the agreement set is clear
- use `get_amendment_chain` when the operative position may have changed over time

For agreement-specific or organization-specific questions, identify the governing stack across:

- base agreement
- order form
- amendment chain
- DPA or privacy addenda
- SLA
- security exhibit or security paper
- incorporated exhibits, riders, or side terms

State the scope before drawing conclusions.

### Step 4: Read structured obligations first

Use `get_agreement_fields` for direct structured reads where the ontology supports the concept.

Capture normalized facts such as:

- whether a concept appears field-backed at all
- the current structured value or extracted signal
- which agreement or document type carries the value
- whether the signal appears complete, sparse, or likely override-sensitive

For portfolio scans, use `aggregate_agreements` to build the first-pass measurement layer before drilling into individual agreements. For example, group by a security or privacy field to see how many agreements carry a particular obligation value, which document types contribute, or where gaps cluster. Then use `get_agreement_fields` and text retrieval to explain the specific agreements driving the pattern.

### Step 5: Fill gaps with clause evidence and full text

Use `Oxels MCP` in this order when the issue is text-heavy, high-stakes, or incomplete:

1. `retrieve_agreement_chunks` for candidate clause evidence
2. `get_agreement_text` when the issue is ambiguous, interaction-heavy, or needs final confirmation
3. `get_amendment_chain` again when overrides or later paper may change the practical outcome

For material conclusions, capture:

- source document type
- section number when available
- direct quote or precise paraphrase
- whether the conclusion is `field-derived`, `retrieval-supported`, or `full-text confirmed`

Be especially careful with interacting issues such as:

- data residency plus transfer language plus subprocessor terms
- SLA commitments plus service credits plus exclusions
- breach notification timing plus cooperation duties plus regulatory carveouts
- deletion obligations plus retention carveouts plus backup exceptions
- security controls in side paper that modify the main agreement posture

### Step 6: Classify the operative position

For each material domain, separate:

1. `Confirmed obligations`: what the paper clearly requires
2. `Restrictions or conditions`: approvals, notice requirements, geographic limits, exclusions, or dependencies
3. `Potential gaps`: missing, weak, or non-obvious protections relative to the stated baseline or review goal
4. `Open ambiguity`: evidence conflicts, override sensitivity, thin support, or missing documents

When the user asks for a portfolio view, group findings into repeatable provision families rather than one-off clause summaries.

Do not collapse:

- `not found in extraction`
- `not found in the reviewed text`
- `confirmed absent`
- `manual review still needed`

### Step 7: Deliver the assessment

Adapt the output to the user’s purpose.

For `Obligation inventory`, deliver:

1. `Question and scope`
2. `Top takeaways`
3. `Obligations matrix`
4. `Document stack and evidence`
5. `Gaps and caveats`
6. `Recommended follow-up`

For `Gap assessment`, deliver:

1. `Question and scope`
2. `Baseline used`
3. `Gap summary`
4. `Gap-by-domain table`
5. `Evidence and confidence`
6. `Recommended follow-up`

For `Baseline check`, deliver:

1. `Question and scope`
2. `Requirement being tested`
3. `Pass, fail, or conditional result`
4. `Evidence`
5. `Risk and caveats`
6. `Recommended follow-up`

For `Risk assessment`, deliver:

1. `Question and scope`
2. `Highest-risk findings`
3. `Exposure by domain`
4. `Evidence and confidence`
5. `Immediate actions`
6. `Open ambiguities`

In `Notion mode`, prefer an enriched artifact, not a thin summary page and not a prose wall. Use well-written narrative sections with paragraphs, and add databases wherever the user should be able to click into a contract, obligation, evidence item, gap, or follow-up as its own structured entry. Keep the page readable top-down by aligning each section with the database or view that supports it.

## Quality bar

Before finalizing the answer, confirm:

- the question and review purpose are explicit
- the corpus scope is explicit
- agreement-specific conclusions are amendment-aware
- the governing document stack reflects where the obligation actually lives
- material conclusions are tied to source text when needed
- evidence source is clear: `field-derived`, `retrieval-supported`, or `full-text confirmed`
- gap flags distinguish weak extraction from confirmed contractual absence
- the answer tells the security team what to do next
- ambiguity is explicit rather than hidden

If a material conclusion does not meet this bar, label it `Manual review required` instead of overstating certainty.

## Final reminders

- Start by understanding what the security team needs to decide.
- Use `Oxels MCP` as the primary engine, not as a citation afterthought.
- Discover the current ontology instead of assuming one fixed field set.
- Build the bounded corpus before making broad claims about security posture or gaps.
- Do not let a gap finding outrun the evidence.
- Be clause-accurate, practical, and explicit about operational risk.

## Additional resources

- Detailed intake prompts, domain-family mapping, output templates, and evidence rules: [reference.md](reference.md)
