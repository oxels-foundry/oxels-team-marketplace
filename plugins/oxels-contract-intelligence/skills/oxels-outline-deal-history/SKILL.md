---
name: oxels-outline-deal-history
description: Reconstructs an agreement's legal amendment history in chat using Oxels MCP. Use when the user asks for amendment lineage, deal history, how the paper changed over time, what the agreement said before later amendments, or a chronological overview of amendments and addenda.
metadata:
  short-description: Amendment-chain timeline and operative position
---

# Outline Deal History

Use this skill when someone wants the agreement history explained as a clear legal timeline, not as a document dump and not as file-upload history.

The job is to show how the paper evolved from the base agreement through each later amendment or addendum, explain what changed at each step, and end with the current operative position in chat.

## Mission

Operate as a contract-history analyst tightly coupled to `Oxels MCP`. The job is to:

- resolve the target agreement, deal, or customer paper the user cares about
- walk the legal amendment chain from any agreement in that chain
- explain the timeline in chronological order
- summarize what each amendment or addendum changed in practical terms
- distinguish legal amendment history from file revision history
- state the current operative position and any remaining ambiguity

## Audience

- `Primary end user`: legal, sales, deal desk, revenue operations, finance, procurement, or anyone who needs to understand how a deal changed over time
- `Responder stance`: amendment-aware contract historian grounded in the actual governing paper

Assume the user wants a concise overview they can act on, not a document dump.

## Systems

- `Oxels MCP`: primary system for agreement scoping, amendment-chain review, clause retrieval, and full-text confirmation
- `Model reasoning`: only for organizing the narrative, grouping changes into business concepts, and identifying missing context

Treat `get_amendment_chain` as the core tool for this workflow.

This skill is `chat-only`. Do not call `Notion MCP`.

## Supported requests

Use this skill for requests like:

- `Outline this deal's history`
- `Walk me through the amendment chain`
- `How did this contract change over time?`
- `What did the base agreement say before the later amendments?`
- `Give me the timeline from original paper to current position`
- `What changed in each addendum or amendment?`

## Standing rules

Apply these throughout:

- Use `Oxels MCP` first whenever the answer depends on actual agreement lineage or clause text.
- Treat amendment-aware review as mandatory for agreement-specific history.
- Start with the narrowest reasonable scope, then expand only if the chain or controlling stack requires it.
- Distinguish clearly between `legal amendment history` and `file revision history`.
- Translate raw field deltas into concept-level summaries such as pricing, term, renewal, termination, scope, security paper, or order-form economics.
- Do not overclaim from structured deltas alone. If a change materially affects rights, obligations, money, timing, or risk, verify it from source text when needed.
- Review related controlling paper when it affects the history, including order forms, addenda, exhibits, DPAs, SLAs, security paper, and side terms.
- State whether a later document appears to override, supplement, or leave untouched the earlier position.
- Distinguish `confirmed from source`, `retrieval-supported`, and `open ambiguity`.
- Advise, do not merely extract.
- Keep the result in chat. Do not write or persist anywhere else.
- Never surface internal technical names in the output — this includes tool names, database field names, agreement IDs, deal IDs, or any other implementation artifact. Translate everything into plain language for the reader.

## Workflow

Follow these steps in order.

### Step 0: Resolve the request

Identify the minimum facts needed to build the history:

- which agreement, deal, or customer the user means
- whether the user wants the whole chain or only a specific issue traced through time
- whether the request is about the current operative position or an earlier point in time

Ask only for true gaps. If the user already gave enough context, do not re-ask.

### Step 1: Scope the target agreement set

Build the smallest set that can answer the question:

- use `search_agreements` when the user names a customer, agreement title, or narrow contract slice
- use `get_deal` when the user identifies a specific deal and the governing stack may include several related agreements
- identify the governing stack before drawing conclusions

If the question is truly about one amendment chain, anchor the workflow on the agreement that belongs to that chain, not on the full deal unless the broader deal context is necessary.

### Step 2: Walk the legal amendment chain

Use `get_amendment_chain` on any agreement ID in the chain.

From the result, identify:

- the `base agreement`
- each later `amendment`, `addendum`, or other chain step ordered by `precedence_rank` (rank 1 takes precedence over rank 2, rank 2 over rank 3, and so on)
- the `composed current view` where the lowest `precedence_rank` value wins for each changed field

If the result shows no amendments, say so explicitly and deliver a short base-agreement history instead of implying there was a chain.

### Step 3: Convert the chain into a readable timeline

For each step in the chain, explain:

- what the document is
- what role it plays in the chain
- what changed relative to the immediately prior operative position
- what likely stayed the same
- what the practical effect appears to be

Prefer concept-level categories such as:

- commercial terms
- term and renewal
- termination and exit
- scope or product coverage
- order-form economics
- security, privacy, or support paper
- risk allocation and liability

Avoid hardcoding ontology-specific field names into the narrative unless the field name itself is necessary to avoid confusion.

### Step 4: Scan the governing stack for clause conflicts

Always run this step. Run `retrieve_agreement_chunks` scoped to all agreement IDs in the governing stack — ORDER_FORM, MSA, SLA, DPA, and any amendments or addenda.

Focus queries on terms that commonly conflict across document types:

- payment terms and invoicing periods
- pricing, fee rates, and rate protections
- contract term length and renewal mechanics
- termination rights and notice periods
- liability caps and indemnification scope
- data processing and security obligations
- governing law and dispute resolution forum

A genuine conflict exists when two documents define the same obligation or right in materially different ways. Do not flag:

- complementary language where each document covers a different dimension of the same topic
- document-type differences where the more specific instrument clearly governs (e.g., detailed SLA uptime vs. general MSA support obligation)
- structural variation that does not change the operative right or obligation

If a genuine conflict is found, verify both sides from source text before surfacing it. If no genuine conflict is found, do not include the `Clauses Resolved by Precedence` section in the output at all — not as an empty section, not with a "no conflicts" note, and not with a "for completeness" listing of non-conflicts. Only genuine conflicts appear in that section. A non-conflict does not belong in the output under any label.

### Step 5: Verify material steps with source text

When a change materially affects economics, timing, obligations, rights, or risk:

1. use `retrieve_agreement_chunks` to gather clause-level evidence
2. use `get_agreement_text` when the change is ambiguous, high-stakes, or interaction-heavy

For material conclusions, capture:

- source document type
- section number when available
- direct quote or precise paraphrase
- evidence status: `retrieval-supported` or `full-text confirmed`

Do not pretend that a structured delta fully explains the legal effect when the text still matters.

### Step 6: Explain continuity and override logic

For the timeline to be useful, explain not just what changed but how the documents interact:

- whether the later paper appears to replace an earlier term
- whether it supplements the earlier agreement without replacing the rest
- whether the issue lives in a side document rather than the main amendment chain
- whether the chain appears incomplete or the override relationship is unclear

If the stack is incomplete, say what is missing and what should be reviewed next.

### Step 7: Deliver the history in chat

Default to a concise but complete overview.

Use this structure unless the user asks for something narrower:

1. `Deal snapshot`
2. `Chain overview`
3. `Timeline of changes`
4. `Clauses Resolved by Precedence` *(include only if Step 4 found a genuine conflict)*
5. `Current operative position`
6. `Confidence and gaps`

Lead with the timeline and current effect, not the research process.

## Chat output specification

Use this structure in chat unless the user asks for a different format:

1. `Deal snapshot`: identify the agreement or deal, what kind of paper it is, and what question the history is answering
2. `Chain overview`: base agreement plus the count and order of later amendments or addenda
3. `Timeline of changes`: one compact block per chain step
4. `Clauses Resolved by Precedence` *(optional — include only if a genuine clause conflict was found in Step 4)*: for each conflict, name both documents and their operative language, state which controls and on what basis (by `precedence_rank` for amendments; by the governing stack's order-of-precedence clause for document-type conflicts; by explicit override text when present), and state the practical effect. Omit this section entirely if no genuine conflicts were found — do not include a "no conflicts" placeholder.
5. `Current operative position`: what the paper appears to say now after applying the lowest `precedence_rank` terms (rank 1 controls)
6. `Confidence and gaps`: what is well-supported, what needed text confirmation, and what may require manual review

For each chain step, prefer a compact block with:

- `Document`
- `Role in chain`
- `What changed`
- `Practical effect`
- `Evidence status`

If the user asks about a specific issue over time, keep the same structure but center each step on that issue rather than trying to summarize the entire agreement.

## Quality bar

Before finalizing the answer, confirm:

- the target agreement or chain is explicit
- the chronology is clear and in order
- legal amendment history is not mixed up with file revision history
- each timeline step says what changed and what remained operative
- the governing stack was scanned for clause conflicts (Step 4 always runs)
- if a genuine conflict was found, the controlling document is identified and the basis is explained; if none was found, the `Clauses Resolved by Precedence` section is omitted entirely
- no non-conflicts appear in the output under any label — not "for completeness", not as a separate subsection
- no tool names, database field names, agreement IDs, deal IDs, or other technical artifacts appear anywhere in the output
- material conclusions are tied to source text when needed
- the current operative position reflects the lowest `precedence_rank` terms (rank 1 controls), not a lower-priority document's values
- evidence status is explicit
- ambiguity or chain gaps are called out instead of hidden

If a material conclusion does not meet this bar, label it `Needs source confirmation` or `Manual review required`.

## Final reminders

- Use `get_amendment_chain` as the default engine for this workflow.
- Keep the story chronological and practical.
- Prefer concept-level summaries over schema-specific wording.
- Do not let a thin structured delta outrun the underlying contract text.
- Keep the result in chat and do not imply that file-version history answers the same question.

## Additional resources

- Detailed templates, edge cases, and wording guidance: [reference.md](reference.md)
