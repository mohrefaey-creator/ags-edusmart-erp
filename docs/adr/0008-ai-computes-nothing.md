# ADR 0008 — The language model never touches data

**Status:** Accepted · 2026-09-06

## Context

Handover §28 asks for "an actual decision-support layer, not only chatbot
search", with a hard constraint at the end of the section: *"AI should respect
role permissions and never expose data beyond the user's authorization scope."*

The obvious implementation — give a model database access and a system prompt
telling it to be careful about permissions — satisfies the first sentence and
fails the second.

## Decision

The layer is a registry of **analyzers**: named functions that answer one
question each with ordinary, permission-scoped SQL, returning a structured
`Finding`. A language model is optional, disabled by default, and may only
*rephrase a finished Finding*.

Concretely:

- **Numbers** come from the ledger. Always.
- **Routing** (question → analyzer) is deterministic keyword matching, in
  English and Arabic, that returns "I cannot answer that, here is what I can"
  below a confidence floor.
- **Scope** is resolved once, in `ags_ai/scope.py`, from the same
  `ags_core.permissions` machinery that scopes the desk and the portal. A
  requested campus is *intersected* with the caller's grant, never trusted.
- **Narration** is the only model-facing surface. It receives a Finding and no
  database access.

## Why

**Permissions.** A model with query access has to be *persuaded* not to cross a
boundary; a scoped SQL query *cannot*. Since the same question returns different
numbers to a CFO and a campus principal, and both answers are correct, the scope
is carried into the Finding and printed with every answer.

**Numbers.** A model that computes is a model that can be confidently wrong
about a fee balance. Here the worst a model outage can do is produce clumsy
prose over correct figures — and with narration off (the default) the
deterministic composer runs instead, so the feature works with no model
configured at all.

**Explanation without invention.** The §28.1 worked output (revenue down 4.2%,
payroll up 8.1%, maintenance up 21%) is *arithmetic*: a period-over-period
decomposition ranked by contribution to the total movement. That is
`rank_drivers`, not a guess about causes.

## Consequences

- The system can only answer questions someone implemented. This is a feature:
  it never bluffs, and the catalogue endpoint tells a user exactly what is
  available *to them*.
- Adding a question means writing an analyzer and a test, not editing a prompt.
- Every question, **including refusals**, is written to `AGS AI Query Log`.
  Refusals are the useful half — a run of them is how you notice someone probing
  outside their scope.
- Analyzers must answer honestly when data is thin. `insufficient_data` is a
  first-class field, and several analyzers correctly return it on a young site
  rather than reporting a meaningless zero.
