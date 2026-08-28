# RELATIONSHIP MODEL (AI Audience)

Every relationship is a typed `GraphEdge` with `origin`, `confidence`, and
(source-backed) `location` evidence. Semantics are defined per type; no
relationship exists merely to sound useful.

Per relationship: meaning, source/target/kind, origin, evidence, whether
derived/reversible, false-positive risks, and examples.

## `defines`

- **Meaning:** a file symbolically contains a declaration.
- **source → target:** `file` → any declared symbol kind.
- **origin:** `extracted`. **confidence:** 1.0. Evidence: declaration location.
- **Derived/reversible:** derived; reverse (`is_defined_in`) not persisted.
- **False-positive risk:** none for structural extraction.

## `contains`

- **Meaning:** structural containment (e.g. class contains method scope).
- **source → target:** container kind → contained kind.
- **origin:** `extracted`. Evidence: ranges.
- **Reversible:** reverse (`in`) derivable.

## `includes`

- **Meaning:** file A `#include`s file B.
- **source → target:** `file` → `file` (resolved) or `file` (unresolved,
  `unresolved: true`).
- **origin:** `resolved`. Confidence: 1.0 when located;
  `0.35` (`CONFIDENCE_UNRESOLVED_INCLUDE`) when not.
- **Attributes:** `raw_target`, `system`.
- **Reversible:** `included_by` derived.
- **Diagnostic:** unresolved include emits `RESOLVE001`.
- **False-positive risk:** none for exact resolution.

## `calls`

- **Meaning:** a source-backed call from caller to callee.
- **source → target:** function/method/… → function/method/external_function.
- **origin:** `extracted` (unresolved external) or `resolved` (matched).
  Confidence: `1.0` resolved, `0.65` ambiguous, `0.5` unresolved.
- **Attributes:** `argument_count`, `qualifier`, `resolution_status`,
  `ambiguous`.
- **Not** used for runtime/event dispatch (`runtime_dispatches`).
- **False-positive risk:** mitigated by lexer string/comment immunity; control
  words (`if`, `for`, `for`) excluded; ambiguous kept as such.

## `references`

- **Meaning:** a symbol references another (e.g. uses a global).
- **origin:** `extracted` / `resolved`.
- **False-positive risk:** variable-resolution ambiguity — preserve state.

## `inherits`

- **Meaning:** class/struct inherits from a base.
- **source → target:** type → base type.
- **origin:** `extracted`. Confidence 1.0 (explicit) / lower if guessable.
- **False-positive risk:** only create when the base is identifiable; else
  leave unresolved.

## `runtime_dispatches`

- **Meaning:** the MetaTrader runtime will dispatch control to an event
  handler (e.g. `OnTick`, `OnInit`, `OnTimer`).
- **source → target:** `runtime` node → `event_handler`.
- **origin:** `runtime`. Confidence per `CONFIDENCE_RUNTIME` (0.9).
- **Reversible:** `dispatched_to` derived.
- **Must never** be represented as a source `calls` edge (Invariant 3).

## `may_trigger_event`

- **Meaning:** an operation may trigger a runtime event indirectly
  (e.g. `OrderSend` may fire `OnTradeTransaction`).
- **origin:** `runtime`. Confidence `0.9` direct, `0.7`
  (`CONFIDENCE_RUNTIME_WEAK`) indirect.
- **Reversible:** derived.

## `declares`

- Reserving: explicit declaration relationships where defined.

## Confidence policy (`evidence.py`)

| Constant | Value | Meaning |
|----------|-------|---------|
| `CONFIDENCE_EXACT` | 1.0 | single source-backed match |
| `CONFIDENCE_RUNTIME` | 0.9 | specific runtime trigger |
| `CONFIDENCE_RUNTIME_WEAK` | 0.7 | indirect runtime trigger |
| `CONFIDENCE_AMBIGUOUS` | 0.65 | multiple candidates kept |
| `CONFIDENCE_UNRESOLVED` | 0.5 | external/unresolved target |
| `CONFIDENCE_UNRESOLVED_INCLUDE` | 0.35 | include not located |
| `CONFIDENCE_INFERRED` | 0.0 | overlay sets its own |

## Rules

- Add a relationship to `RELATIONSHIP_MODEL.md` **before** emitting it.
- Never silently mix origins (Invariant 3).
- Never turn ambiguity into certainty (Invariant 4).