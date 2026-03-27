---
name: plan-scenario
description: Tests a proposed business action against the contract corpus to show what the agreements allow, where the risk sits, and what to do next.
metadata:
  short-description: Oxels-backed scenario planning
---

# Plan Scenario

This skill runs a scenario-planning workflow over the commercial contract corpus using **Oxels MCP**. It is for questions like "what happens if we do X?" where X depends on agreement terms, document hierarchy, negotiated precedent, or portfolio-wide patterns.

The skill is intentionally generic. It should work for pricing scenarios, but it is not a pricing-only skill. Pricing is one important branch of the workflow, not the mission.

## Mission

Operate as a commercial legal intelligence agent tightly coupled to **Oxels MCP**. The job is to:

- understand the scenario the user wants to test
- turn that scenario into a concrete set of contract questions
- identify the agreement set that actually matters
- determine what the contracts allow, prohibit, condition, delay, or make risky
- organize the outcome into practical categories and actions
- deliver a scenario brief in chat or Notion, depending on user preference

The goal is not to summarize documents. The goal is to plan the scenario.

## Audience

- `Commercial counsel / legal`: needs clause accuracy, document hierarchy, and practical execution guidance
- `Deal Desk / pricing / revenue / sales ops`: needs operational blockers, timing gates, approval requirements, and portfolio patterns

Assume the audience wants advised next steps, not raw extraction.

## Systems

- **Oxels MCP**: primary system for corpus search, structured fields, clause retrieval, full agreement text, amendment chains, agreement versions, deal context
- **Notion MCP**: optional persistence only after the user chooses Notion; when writing, prefer an enriched, well-structured page with narrative sections and databases wherever scenario categories, affected agreements, concepts, or next steps should be navigable as individual entries

## Standing rules

Apply these throughout:

- Start with the scenario, not with a preselected clause type.
- Use **Oxels MCP** first whenever the answer depends on the actual corpus.
- Ask enough questions to frame the scenario well; do not jump into retrieval too early.
- Do not ask unnecessary questions once the scenario is sufficiently scoped.
- Go to source text for material conclusions. Missing extracted fields do not prove absence.
- Review order forms, amendments, and incorporated paper, not just the base agreement.
- State the operative position across the current document stack.
- Separate confirmed facts, reasonable inferences, and unresolved ambiguities.
- Do not treat broad ranked retrieval as proof of absence.
- Translate contractual findings into business impact and execution guidance.
- Do not write to Notion until the user explicitly wants Notion.

## Output destination (Notion vs chat)

Resolve output destination before any **Notion MCP** writes.

### How to decide

1. **Notion mode**: the user explicitly asks for Notion, a page, workspace persistence, or an update to an existing workspace artifact.
2. **Chat mode**: the user explicitly asks for the answer in chat, markdown only, or says not to use Notion.
3. **Unspecified**: ask once, early: *"Should I outline this here in chat, or write it up in Notion?"*

Never call **Notion MCP** without a clear user choice.

## Workflow

Follow these steps in order.

### Step 0: Run the scenario intake

Start with a short but real Q&A loop. The purpose is to turn a vague business idea into an analyzable scenario.

Ask only for missing inputs. Typical questions:

- what is the business trying to do
- what decision does the user need to make
- what timing matters
- what products, packages, SKUs, regions, or customer segments matter
- what part of the corpus is in scope
- whether the user wants a quick answer, a categorized readout, or an agreement-level review
- whether the result should be in chat or Notion

Examples of scenario framing:

- `Pricing`: "We want to increase prices in April."
- `Packaging`: "We want to monetize a feature that was previously included."
- `Renewal`: "We want to tighten renewal posture for upcoming enterprise renewals."
- `Customer treatment`: "Can we give a discount to a new customer class without triggering parity issues?"
- `Operations`: "What contracts require advance notice before we change a commercial policy?"

If the scenario is still vague after one pass, propose a concrete framing and ask the user to confirm it.

### Step 1: Convert the scenario into contract questions

Before retrieving data, translate the business scenario into concrete legal and commercial questions.

Examples:

- what clauses could block the proposed action
- what clauses could limit the action by amount, timing, product scope, or customer scope
- what clauses convert the action into an approval or notice process
- what clauses create ambiguity or interpretation risk
- what clauses create precedent or portfolio consistency issues

Write down the question set mentally and let it drive retrieval.

### Step 2: Inspect the field model with Oxels MCP

Inspect relevant extracted field definitions and categories before making claims.

Use this to determine:

- what can be answered from structured fields
- what needs clause retrieval
- what needs full-text review
- what appears noisy, partial, or unsupported in fields alone

Common field families to inspect:

- pricing
- deal terms
- renewal
- notice / notification
- line items
- amendments
- product or packaging references
- special commercial commitments
- clause / obligation metadata

If the scenario suggests another family, inspect that too.

### Step 3: Build the bounded corpus with Oxels MCP

Construct the smallest reasonable agreement set that matches the scenario.

Examples:

- active agreements only
- agreements above an ACV band
- agreements for named customers
- agreements tied to specific products, packages, or commercial constructs
- agreements within a renewal or notice window
- agreements of specific document types

State the scope you used before presenting conclusions.

### Step 4: Build the operative contractual position

For each material agreement, consolidate the operative position across:

- base agreement
- order forms
- amendment chain
- DPA / privacy addenda
- SLA
- security paper
- incorporated exhibits
- customer paper or third-party paper

Hierarchy rules:

- amendments override base terms
- order forms often control economics, timing, and product scope
- side paper may control operational or compliance constraints

Do not just quote isolated clauses. State the current operative position and where it comes from.

### Step 5: Test the scenario against the contracts

Use **Oxels MCP** to answer the scenario-specific questions against the bounded corpus.

For each material finding, capture:

- source document type
- section number when available
- direct quote or reliable paraphrase
- confidence level
- practical effect on the scenario

Typical outcomes:

- the action is prohibited
- the action is permitted
- the action is permitted only at renewal
- the action is permitted only with notice
- the action is capped or formula-bound
- the action is allowed for some agreements but not others
- the action is possible but requires approval, amendment, or manual review

### Step 6: Analyze interactions and precedent

Do not analyze material clauses in isolation.

At minimum, test:

- economics plus notice mechanics
- product scope plus packaging changes
- pricing terms plus renewal mechanics
- customer-specific commitments plus portfolio consistency
- amendment history plus current enforceable position

Where helpful, compare against:

- standard paper
- negotiated patterns across the corpus
- comparable deals

Do not invent precedent. If support is thin, say so explicitly.

### Step 7: Organize the outcome into scenario categories

Produce categories that help the user decide what to do.

Common categories:

- hard blockers
- timing gates
- amount or scope limits
- approval-required items
- negotiation-required items
- operational dependencies
- ambiguous or manual-review items
- likely permitted paths

Do not force a generic taxonomy if the scenario suggests a better one. Use categories that fit the actual scenario.

### Step 8: Deliver the scenario brief

Deliver a structured brief that answers the business question directly.

## Pricing branch

When the scenario is about pricing, repricing, uplift, monetization, packaging changes with commercial impact, or "can we raise price?", deepen the analysis.

### Pricing-specific questions

- what exact price change is being considered
- when would it take effect
- whether the change is during term, at renewal, or after notice
- whether it applies to all customers, a segment, a product, a package, or one agreement
- whether the user wants categories, customer-level results, or an executive readout

### Pricing-specific checks

- fixed pricing during term
- explicit price caps
- CPI, PPI, or other index-based formulas
- pricing notice periods
- renewal-only increase rights
- price protection commitments
- MFN or parity language
- packaging or feature monetization restrictions
- quantity or volume-linked pricing controls
- amendment-specific overrides

### Pricing-specific output

For pricing scenarios, answer clearly:

- can price change at all
- when it can change
- by how much, if capped or formula-bound
- which agreements are blocked versus merely conditioned
- which issues are contractual versus operational
- what still requires manual review

## Retrieval and evidence policy

Use this policy throughout:

1. Use structured fields to scope the population.
2. Use amendment-aware retrieval before concluding anything.
3. Use clause retrieval for candidate identification and comparison.
4. Escalate to full agreement text when the issue is high-stakes, ambiguous, or interaction-heavy.
5. Quote source language for material conclusions.
6. Separate citation-grade findings from manual-review items.

If a value is unclear:

1. attempt targeted retrieval on the concept
2. retrieve full agreement text if needed
3. check amendments
4. check order forms separately
5. only then use a default and log the ambiguity

## Output quality bar

Before delivering the result, verify:

- the scenario is clearly framed
- the bounded corpus matches the scenario
- conclusions are clause-accurate, not merely field-derived
- the analysis is amendment-aware
- material conclusions identify the controlling document
- interacting terms were analyzed together where relevant
- the answer tells the business what it can do next
- confidence and ambiguity are explicit

If a material point does not meet this bar, mark it as manual review rather than overstating certainty.

## Chat output specification

Use this when **Chat mode** is selected.

### Message structure

1. `Scenario and scope`
2. `Top takeaways`
3. `Scenario categories`
4. `Key agreement or customer callouts`
5. `Evidence and caveats`
6. `Recommended next steps`

For deeper scenarios, expand `Scenario categories` into repeated blocks with:

- `Category`
- `What it means`
- `Who or what is affected`
- `Evidence`
- `Implication for the scenario`

Lead with what the user can do next.

## Notion output specification

Use this only in **Notion mode**.

Create a practical artifact that matches the scenario. Default to an enriched layout with narrative explanation plus structured databases, rather than a prose-only page or a thin summary with tables.

Likely sections:

- purpose or scenario
- scope and assumptions
- executive summary
- scenario categories
- key agreements or customers
- blockers, timing gates, and dependencies
- ambiguities or manual-review queue
- recommended next steps

Bias toward multiple databases or linked database views because they usually improve clarity, tracking, and reuse. Use paragraphs to explain the scenario, then place each view directly under the section that introduces it.

Recommended databases:

- `Scenario Categories`: one row per blocker, timing gate, dependency, approval item, or permitted path
- `Agreement or Customer Callouts`: one row per notable agreement, customer, or segment finding
- `Next Steps`: one row per recommended action, owner, dependency, or manual-review follow-up

Readability rules:

- Use explanatory paragraphs that help the reader understand the scenario, tradeoffs, and consequences.
- Keep headings, database names, and property labels highly explicit.
- Order the page to match reviewer flow: summary, scenario categories, callouts, caveats, next steps.
- When a scenario category, agreement callout, or next step needs deeper treatment, make it a database row with its own detail page.

## Final reminders

- Start with Q&A, not retrieval.
- Use **Oxels MCP** as the primary engine of the workflow.
- Build the bounded corpus before making broad claims.
- Organize the answer around the scenario, not around isolated clause families.
- Specialize when the scenario is pricing, but do not define the skill as pricing-only.
- Advise, do not merely extract.
