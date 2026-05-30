# Load or find Oxels skill

Plugin `SKILL.md` files name the skill, say when to use it, and point here. Workflow instructions live in the Oxels catalog after `get_object`.

Each plugin skill's YAML `name` maps to a discovered **catalog skill id** and **namespace** — both come from MCP, not from naming rules. Cache that pair locally so repeat runs skip discovery.

## Cache

```text
~/.oxels/config/bindings.json
```

Keyed by plugin skill `name`. Each value holds the catalog `skill_id` and `namespace` slug Oxels returned when this wrapper was last resolved:

```json
{
  "oxels-ask-legal": {
    "skill_id": "<id from list_objects>",
    "namespace": "<slug from available_namespaces>"
  }
}
```

Merge writes. The user never edits this file.

## Steps

1. Read `bindings.json` for this plugin skill's `name`.
2. **Cache hit** — When both `skill_id` and `namespace` are present:
  - `start_session({ namespace })`
  - `get_object({ session_id, id: skill_id })` and follow `body_md` alongside the user query. 
3. **Find namespace** — When `namespace` is missing:
  - `start_session()` (cold read).
  - From `available_namespaces`, pick the namespace most likely to host this skill.
  - `start_session({ namespace })`.
  - If step 4 fails, try the next likely namespace until exhausted.
4. **Find catalog skill** — `list_objects({ session_id, kinds: ["skill"] })` (use `query` from the plugin skill's name or description when helpful). Pick the object that best matches **this** plugin skill. Take `id` exactly as returned.
5. **Persist** — Write `{ "skill_id": <id>, "namespace": <namespace> }` under this plugin skill's `name` in `bindings.json` in the same turn.
6. **Load skill** — `get_object({ session_id, id: skill_id })` and follow `body_md` alongside the user query. 
7. **Other tools** — Pass `session_id`. Use `suppress_skills: true` on `get_context` unless exploring other skills.

## Invalidate

Delete this plugin skill's entry on namespace errors, empty skill lists. Rediscover `namespace` and `skill_id` from MCP.

