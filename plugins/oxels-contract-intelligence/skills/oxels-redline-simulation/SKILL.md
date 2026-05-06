---
name: oxels-redline-simulation
description: Run a simulated redline scenario against the Oxels corpus, present it to a legal reviewer, and capture their free-text take into the oxels_legal_memory namespace. Used as a learning instrument — accumulates raw signal for building proper playbooks later, not a production playbook itself. Works as a slot machine: run it repeatedly, each pull surfaces a clause × sector worth a reviewer's attention.
metadata:
  short-description: One-shot redline simulation that captures reviewer signal as legal memory
---

# Oxels Redline Simulation

This is a **learning instrument**, not a production playbook. The goal is to accumulate enough graded scenarios in `oxels_legal_memory` that a real playbook can be extracted from the signal later.

Each run picks one clause × sector worth a reviewer's attention, builds a scenario from corpus precedent, presents it, and captures the reviewer's free-text take via `update_legal_memory`. No structured grading — just the actual words the reviewer says.

**Important**: This skill supports legal workflows but does not provide legal advice. Use source text for material findings.

## Invocation

```
/oxels-redline-simulation
```

Inputs (ask if missing, but accept "surprise me" defaults):

| Input | Required | Default | Notes |
|---|---|---|---|
| `sector` | no | reviewer's choice or rolled | Free-form string. Use a value the reviewer recognizes; consistency across sessions matters more than fitting a taxonomy. |
| `clause_concept` | no | rolled | Free-form string, e.g. `liability_cap`. If omitted, the skill picks one based on corpus deviation + memory gaps. |
| `target_agreement_id` | no | — | Optional single-agreement scope to ground the scenario in. |

If the reviewer just says "give me one," roll the sector and clause yourself. State both before doing the corpus work so they can swap.

## Workflow

### 1 — Pick the scenario

If sector and clause_concept were provided, use them. Otherwise:

- Use `retrieve_field_definitions` and `describe_fields` to surface candidate clause concepts.
- Use `search_agreements` filtered by sector (when one's chosen) or across the corpus to pick a peer cohort. Use `aggregate_agreements` and `get_agreement_fields` to find clauses with high deviation.
- Pull a `get_legal_memory` query to see what's been graded already. **Bias toward clauses with no memory entry, stale entries, or entries with conflicting signals across sectors** — that's where the next pull pays off.
- Surface 2–3 candidate clauses with one-line "why this one" hooks; let the reviewer pick or roll one.

State the pick explicitly before running the simulation.

### 2 — Build the scenario

For the chosen clause × sector:

- `retrieve_agreement_chunks` filtered by clause + sector cohort, top_k 5–8. Pull the actual market language.
- If a `target_agreement_id` was provided, also pull chunks from that agreement.
- Construct a scenario in plain prose: counterparty posture, what the corpus typically says here, where the proposed redline sits relative to that, what the tradeoffs are.
- If a fallback ladder is useful, write it inline as part of the scenario summary — no need for structured tiers. The point is the reviewer's reaction, not the ladder shape.
- Surface any prior memory for this clause × sector inline so the reviewer can compare.

### 3 — Present and capture

Show the reviewer:

1. **The scenario** — corpus context + proposed redline(s) + the question being put to them.
2. **Why this is interesting** — one line of provenance ("never graded before" / "graded for healthcare 2 months ago, sector has shifted" / "3 deals last quarter went non-standard here").
3. **Prior memory** — if any, with the prior take and a link to the entry id.
4. **The ask** — explicitly pose the question that needs the reviewer's judgment, not "grade tiers." Examples:
   - Should this even live in the playbook?
   - Is the corpus drift here worth a policy update?
   - Does this concession deserve a different bar going forward?

Capture the reviewer's response verbatim or close to it.

### 4 — Persist via `update_legal_memory`

Call `update_legal_memory` with:

```
{
  clause_concept: "<chosen>",
  sector: "<chosen>",
  scenario_summary: "<the prose scenario you presented, including any inline ladder>",
  reviewer_feedback: "<the reviewer's actual words — verbatim is best>",
  tags: ["<emergent labels>"],
  source_agreement_ids: ["<uuid>", ...]
}
```

If you're updating an existing entry from Phase 1, pass its `id`.

**Tags are open-ended.** Don't pick from a fixed list. Use whatever pattern the reviewer's feedback surfaces:
- `precedent-setting` — they treated this as a precedent decision
- `sensitive` — not for general circulation; treat as exception, not precedent
- `drift` — corpus has moved away from a prior position
- `cross-clause-conflict` — interacts with another clause in a way that matters
- `standardize-this` — they think this should become standard
- `not-the-real-question` — the redline framing missed the actual issue
- `revisit-soon` — they want this back in front of them later

Add tags only when something specific shows up. Empty tags is fine. Schema can be extracted later from accumulated entries; don't force it now.

### 5 — Confirm and offer another pull

Print:

- Memory entry id (created or updated) and the tags written
- One-line summary of what was captured
- "Pull again?" — offer to run another scenario. The slot-machine framing is intentional; the value is in volume of graded scenarios, not depth on any one.

## Oxels MCP rules

- **Read tools**: `retrieve_field_definitions`, `describe_fields`, `search_agreements`, `aggregate_agreements`, `get_agreement_fields`, `retrieve_agreement_chunks`, `get_agreement_text`, `retrieve_similar_organizations`, `get_amendment_chain` when amendments matter.
- **Memory tools**: `get_legal_memory` (Phase 1 + inline in Phase 3), `update_legal_memory` (Phase 4).
- **Cost guardrails**: one scenario per pull. `retrieve_agreement_chunks.top_k` ≤ 10. Skip full agreement text unless the reviewer explicitly asks.
- **Don't dedupe aggressively.** Recently-graded clauses are still fair game if the corpus has shifted, if there's a memory conflict across sectors, or if the reviewer wants a re-pull. The system isn't trying to converge.

## Output format

```markdown
## Pull — <clause_concept> × <sector>

### Why this one
<one-line provenance>

### Scenario
<prose: corpus context, proposed redline, tradeoffs>

### Prior memory
<entries from get_legal_memory or "none">

### Question for you
<the GC-judgment question>

---

(after reviewer responds)

### Captured
- Memory id: <id> (<created|updated>)
- Tags: [<tags or "none">]
- Source agreements: <count>

### Pull again?
```

## Conversational use

The skill isn't only a 5-phase pull. The reviewer should be able to ask about memory or add to it freely, in the middle of a session or as a standalone request. Map intents to tools without ceremony — don't announce the call, don't recite the schema, just do the thing and report back in their language.

### Read intents → `get_legal_memory`

| What the reviewer says | What to call |
|---|---|
| "What's in memory?" / "What have we graded?" | `get_legal_memory({ top_k: 25 })` — return a compact list (clause × sector × one-line feedback × tags). Group by clause if the list is long. |
| "Show me everything for financial services" | `get_legal_memory({ sector: "financial_services", top_k: 25 })` |
| "What did I say about liability caps?" | `get_legal_memory({ clause_concept: "liability_cap", top_k: 25 })` |
| "Find that one where the customer wanted uncapped damages…" | `get_legal_memory({ query: "uncapped damages", top_k: 10 })` — hybrid search |
| "Anything tagged sensitive?" | `get_legal_memory({ tag: "sensitive", top_k: 25 })` |
| "Show me the precedent-setting and drift entries" | `get_legal_memory({ tags_any: ["precedent-setting", "drift"], top_k: 25 })` |
| "What did I grade last week?" | `get_legal_memory({ top_k: 25 })` and filter the result by `updated_at` in the response |
| "Pull up entry mem:abc-…" | `get_legal_memory({ query: "<exact id snippet>" })` — id appears in `text` for hybrid hit; or surface it from a recent listing |

When summarizing memory, lead with what's *interesting* to a GC — conflicts across sectors on the same clause, stale entries, tag clusters — not a flat dump.

### Surface memory mid-simulation, naturally

- **Before presenting a scenario**: pull related memory once (`clause_concept` + `sector`), keep it ready. If anything relevant exists, weave it into the scenario framing in plain language: *"You graded a similar liability-cap question for healthcare last month and tagged it `precedent-setting` — here's that take, then here's what's different about this one."* Don't print the full memory entry unless asked.
- **When the reviewer's response echoes a prior take**: name it. *"This is consistent with what you said for `saas_enterprise` — want me to tag both with `consistent-position`?"*
- **When the reviewer's response contradicts a prior take**: name that too. *"Heads up — this conflicts with the `sensitive` entry from 3 weeks ago. Should I update that one, or are these genuinely different cases?"*

### Write intents → `update_legal_memory`

The standard write happens in Phase 4. Beyond that:

| What the reviewer says | What to call |
|---|---|
| "Just remember this — for financial services we never accept uncapped liability" | `update_legal_memory` directly, no simulation shell. `scenario_summary` = the rule they stated; `reviewer_feedback` = their words verbatim; tags emerge from the framing (e.g. `["standardize-this", "hard-line"]`). Confirm: "captured as memory entry mem:…". |
| "That one we graded last week — I want to revise it" | Pull the entry, present it, capture the new take, call `update_legal_memory` with the existing `id`. Tag with `revised` if the take materially changed. |
| "This applies broadly, not just fin services" | Either widen the existing entry (update `sector` or write a sibling entry per sector), or capture a meta-entry with `clause_concept` set and `sector: "all"` plus tag `cross-sector`. Ask once which they prefer; default to the meta-entry. |
| "Tag this `precedent-setting`" | Pull the most-recent or named entry, append the tag, update. |

Confirmations should be one line: *"Captured: mem:abc — tagged `precedent-setting`, `sensitive`."* Not a recap of the full schema.

### When the reviewer asks something the schema can't answer

If they ask "how many times have I flagged something as an exception?" or "what's my most common position?" — there's no enum to count. Say so plainly, then offer to scan the entries: *"There's no `disposition` field, but I can read the feedback on tagged-`sensitive` entries and summarize. Want me to?"* This is the moment when the simplification cost is real and worth being honest about.

### Standalone memory mode

If the reviewer invokes the skill with a memory question and no simulation intent ("what's in memory for fin services?"), skip Phases 1–4 entirely. Just call `get_legal_memory`, summarize, and offer follow-ups: *"want me to pull a fresh scenario on any of these?"*

## See also

- [reference.md](reference.md) — memory schema, tag examples, what makes a scenario "interesting."
- [oxels-find-non-standard-clauses](../oxels-find-non-standard-clauses/SKILL.md) — deviation detection used in Phase 1.
- [oxels-plan-scenario](../oxels-plan-scenario/SKILL.md) — scenario construction patterns.
