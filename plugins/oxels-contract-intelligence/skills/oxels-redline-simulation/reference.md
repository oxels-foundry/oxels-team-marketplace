# Reference — oxels-redline-simulation

## Memory schema (`oxels_legal_memory` namespace)

Each row is one graded scenario. Deliberately minimal — this is signal collection for later playbook construction, not a structured product.

| field | type | filterable | notes |
|---|---|---|---|
| `id` | string (`mem:<uuid>`) | yes | primary key |
| `text` | string | full-text searchable | concat of clause + sector + scenario + feedback + tags |
| `vector` | float[] | ANN | embedding of `text` |
| `clause_concept` | string | yes | free-form, e.g. `liability_cap` |
| `sector` | string | yes | free-form, e.g. `financial_services` |
| `scenario_summary` | string | no | what was simulated, in prose |
| `reviewer_feedback` | string | no | reviewer's free-text take, verbatim |
| `tags` | []string | yes (`Contains` / `ContainsAny`) | open-ended labels |
| `source_agreement_ids` | []string | no | corpus agreements that grounded the scenario |
| `created_at` / `updated_at` | string (ISO) | yes | |

### What's deliberately *not* in the schema

- **No disposition enum** (approved/revised/rejected). The reviewer's actual words are the signal; bucketizing them throws information away.
- **No tier visibility / role-based read gates.** Permissions are a product concern; not relevant for accumulation.
- **No structured fallback ladder.** If a tiered redline was presented, it lives inline in `scenario_summary` as prose.
- **No counterparty archetype field.** If the archetype matters for an entry, it goes in `tags` (e.g. `archetype:public-bank`).
- **No reviewer name field.** Currently single-reviewer; add later if needed.

The point is to avoid presuming structure that hasn't proven itself yet. Tags absorb whatever pattern emerges; an LLM pass over accumulated entries can extract enums later when the right enums are obvious.

## Tag conventions (suggested, not enforced)

Use whatever the reviewer's feedback actually surfaces. These are starting points:

| tag | when to use |
|---|---|
| `precedent-setting` | Reviewer treated this as a decision that sets a bar for future deals |
| `sensitive` | Sensitive enough that the language shouldn't circulate broadly |
| `drift` | Corpus has moved away from a previously-held position |
| `cross-clause-conflict` | Interacts with another clause in a way that matters |
| `standardize-this` | Reviewer thinks this should become standard language |
| `not-the-real-question` | The redline framing missed the actual issue worth grading |
| `revisit-soon` | Reviewer wants this back in front of them later |
| `boring` | Reviewer rerolled — useful negative signal about saturation |
| `archetype:<value>` | Counterparty archetype if it shaped the scenario, e.g. `archetype:public-bank` |
| `concept:<value>` | Cross-cutting concept the reviewer named, e.g. `concept:audit-rights` |

Empty tags is fine. Don't invent labels just to fill the field.

## What makes a scenario worth pulling

Bias the slot machine toward clauses where:

- **No prior memory** for the clause × sector combination
- **Memory exists but conflicts** across sectors or across time (same clause graded differently)
- **Stale memory** + the corpus has shifted (new agreements introduce variance)
- **Cross-clause interaction** signals (e.g. liability cap + insurance minimums contradict in some agreements)
- **Recent corpus change** touching the clause (new agreements, amendments)
- **High deviation** in the sector cohort — many agreements vary widely on this clause

When in doubt, pick the clause with no memory. Coverage matters more than depth in the early phase.

## Cost guardrails

- One scenario per pull. The reviewer can pull again immediately if they want more.
- `retrieve_agreement_chunks.top_k` ≤ 10 per pull.
- Skip full-agreement-text fetches unless the reviewer explicitly asks for the source.
- Don't pre-fetch a queue of N scenarios — interactive pulls only. Saves token cost when the reviewer ends the session early.

## Future extraction (out of scope for the skill)

When `oxels_legal_memory` has 50–200 entries, run a separate pass to extract structure:

- Cluster by clause_concept × sector to find consistent positions vs. genuinely contested ones
- Mine `tags` for emergent taxonomy
- Read `reviewer_feedback` text to identify recurring rationales
- Promote stable patterns into a real playbook artifact

That's the playbook construction step. This skill exists to feed it.
