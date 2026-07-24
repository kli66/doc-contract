---
id: landed-graph-transition-ownership
persistence: ephemeral
status: proposed
track: architecture
depends_on:
  - edge-fingerprint-policy
fingerprints:
  edge-fingerprint-policy: d905fcb4fb5d4745
files_owned:
  - src/doc_contract/resolver.py
  - src/doc_contract/landing.py
  - tests/test_resolver.py
  - tests/test_landing.py
  - docs/roadmap.md
---
# Own the landed graph transition

Status: Proposed (not accepted) · Proposed 2026-07-24

**Upstream dependencies:** `edge-fingerprint-policy` is landed and supplies the current advisory
fingerprint behavior that the projection must preserve; transitively, it includes the transactional
landing engine and discovery/lifecycle rules whose graph transition is being consolidated. Its
reviewed body fingerprint is recorded above. No ADR governs this internal boundary, and no external
infrastructure is gated; the full stdlib-only refactor is available now.
**Dependents:** None. The roadmap and active change set contain no work that waits on this boundary.
The other architecture-review candidates are independent opportunities, not blocked dependents.
**Files owned:** The resolver's document-graph projection API, the landing planner that consumes it,
focused resolver and landing regressions, and this change's roadmap entry.
`unified-offline-live-verification` also forecasts changes to `resolver.py`, `landing.py`,
`tests/test_resolver.py`, `tests/test_landing.py`, and the roadmap. The overlap is soft because this
change owns graph projection while that change owns capability execution and verification
composition; whoever lands second must rebase and reconcile the shared imports/call site. If both
become in-progress concurrently, coordinate the shared `landing.py` call site rather than adding a
false DAG edge. The architecture-review HTML is an input to the proposal, not an owned or modified
artifact.

## Why

`plan_landing` currently performs the same landed-state projection twice. It deep-copies the
resolution, mutates node status and path, refreshes dependent fingerprints, clears and rebuilds
dependents, and topologically sorts the result before rendering the roadmap. `_simulate` then
deep-copies and repeats that transition before validation. The landing module therefore owns graph
rules that belong with resolver validation, and a future lifecycle-field or topology change can
diverge between rendering and preflight validation.

The current source imports five underscore-prefixed resolver names, not the six stated in the
architecture report's top-recommendation banner: `_as_map`, `_as_str`, `_compute_dependents`,
`_render_front_matter`, and `_topo_sort`. Two expose graph mechanics and three expose front-matter
implementation. The stronger boundary is not to rename those helpers public; it is to give landing
one supported operation that owns the complete projected document state while leaving filesystem,
journal, and mutation application concerns in `landing.py`.

## What changes

**Δ ADDED** — Add one public resolver-level landing projection operation and an immutable result
that contains the rewritten change/dependent document state, transitioned resolution, deterministic
roadmap graph block, and validation findings needed by the landing plan. Its inputs describe the
landed change facts and planned human-maintained roadmap text; caller-owned `Resolution` and nodes
remain unchanged.

Add focused resolver tests that exercise the operation directly across a landed status/path change,
active-dependent fingerprint refresh, dependent derivation, topology, roadmap rendering, validation,
and input immutability. Add a boundary regression that prevents `landing.py` from importing private
resolver names again.

**Δ MODIFIED** — Make `plan_landing` call the projection once and translate its returned document
state into hash-guarded file mutations. Keep repository discovery, source/archive selection, roadmap
prose path replacement, diff construction, journal persistence, filesystem writes/moves, recovery,
capability execution, and final on-disk resolution in the landing engine. Preserve the exact dry-run,
tracking, warning-delta, interruption/resume, concurrent-modification, and completed-rerun behavior.

Keep front-matter parsing/rendering and graph mutation details internal to the resolver-level
operation so eliminating the five private imports does not merely widen the resolver's helper API.
The CLI command set and consumer-visible capability text do not change.

**Δ REMOVED** — Remove `_simulate`, the duplicate inline graph mutation/topology block in
`plan_landing`, and all five private resolver imports from `landing.py`. Remove no standalone CLI
command, compatibility adapter, or validation rule.

## Tasks

1. Define the public landing-projection input/output boundary in `src/doc_contract/resolver.py`,
   keeping returned state immutable at the interface and keeping parsing, rendering, graph mutation,
   topology, and validation helpers private.
2. Implement the transition once: rewrite landed change metadata/body status, refresh active
   dependent fingerprints, clone and update node state, rebuild dependents and topological order,
   render the deterministic roadmap graph, and validate against the planned human roadmap text.
3. Refactor `plan_landing` to consume that projection when constructing change, dependent, and
   roadmap mutations; delete its inline graph projection and `_simulate` without moving transaction
   or filesystem policy into the resolver.
4. Add resolver tests for projection output, validation parity, active-versus-inactive dependent
   handling, unknown/cyclic graph findings, and proof that the input resolution is unchanged.
5. Update landing tests to retain the full transactional regression set and add a boundary assertion
   that `landing.py` imports no underscore-prefixed resolver symbols.
6. Run the full test and lint gates and confirm the public CLI/capability surface is byte-for-byte
   unchanged apart from internal implementation imports.
7. On land: archive this folder through the transactional command and retain the roadmap lineage.

## Verify

- `uv run pytest -q` and `uv run ruff check .` pass, including the real-corpus DAG tripwire.
- A direct resolver projection produces the same landed node path/status, dependent fingerprints,
  dependents, topological order, roadmap block, and findings that final on-disk `resolve` produces,
  while leaving the input `Resolution` unchanged.
- Existing landing tests remain green for dry-run immutability, tracked and untracked moves,
  interruption/resume, concurrent edits, destination collision, failed final validation, warning
  deltas, dependent fingerprint refresh, and idempotent completed reruns.
- `landing.py` has no private resolver imports, no `_simulate`, and only one call path that projects
  landed graph state; the five-name current baseline above is the count used by this change.
- Invariant spot-check: runtime code remains stdlib-only; repository selection stays explicit and
  fail-closed; secret-bearing subprocess output remains suppressed; the resolver performs no file,
  Git, journal, or capability mutation; and the documented `land` behavior does not change.
