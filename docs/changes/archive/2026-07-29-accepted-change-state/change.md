---
id: accepted-change-state
persistence: ephemeral
status: landed
track: architecture
depends_on:
  - transactional-land-command
  - landed-graph-transition-ownership
fingerprints:
  transactional-land-command: f97111f3df934220
  landed-graph-transition-ownership: aff40dac7cdd2cf2
files_owned:
  - src/doc_contract/transaction.py
  - src/doc_contract/lifecycle.py
  - src/doc_contract/resolver.py
  - src/doc_contract/landing.py
  - src/doc_contract/cli.py
  - tests/test_lifecycle.py
  - tests/test_resolver.py
  - tests/test_landing.py
  - tests/test_cli.py
  - scripts/test_change_dag.py
  - docs/spec/capabilities.md
  - AGENTS.template.md
  - guides/new-change.md
  - guides/reconcile.md
  - README.md
  - SKILL.md
  - docs/roadmap.md
accepted_at: 2026-07-29
started_at: 2026-07-29
landed_at: 2026-07-29
archive_path: docs/changes/archive/2026-07-29-accepted-change-state
---
# Add an accepted change state and explicit lifecycle transitions

Status: Landed · 2026-07-29

**Upstream dependencies:** `transactional-land-command` is landed and supplies the existing
hash-guarded, journaled, resumable multi-file mutation boundary. `landed-graph-transition-ownership`
is landed and establishes that resolver-owned projection, rather than filesystem code, owns graph
and roadmap state changes. Their reviewed fingerprints are recorded above. No ADR or external input
gates this work.
**Dependents:** The planned `mechanical-reconciliation` and `actionable-lifecycle-diagnostics` changes must
declare `accepted-change-state` as an upstream dependency and consume its public transition planner
instead of re-resolving change references or inventing status rules. Their proposal agents are
authoring those back-links separately.
**Files owned:** The new generic transaction and lifecycle modules; resolver status/projection logic;
landing eligibility; CLI grammar; focused package and compatibility tests; the capability reference,
portable operating contract, authoring/reconcile guides, package documentation, skill dispatcher,
and roadmap. No active change folders exist in this isolated checkout, so there is no current owned-
path conflict; the dependent proposals will overlap the lifecycle call sites intentionally and must
land after this one.

## Why

The contract says authoring is not acceptance, but the machine has no accepted change state.
`ACTIVE_STATUSES` currently contains only `proposed`, `in-progress`, and `blocked`; the CLI exposes no
accept/start transition; and `land` selects any active change. The landing fixture therefore proves
that a literal `Status: Proposed (not accepted)` change can be archived as landed without an
acceptance or execution boundary.

This is not only missing metadata. Manual edits must keep front matter, the human `Status:` line,
roadmap prose, generated DAG, and active-dependent review fingerprints synchronized. A deterministic
lifecycle command should reuse the existing hash guards and journaling so agents do not regenerate
one-off editing logic, while preserving the non-mechanical rule that only explicit user/reviewer
authorization permits recording acceptance.

## What changes

**Δ ADDED** — Add the lifecycle graph:

```text
proposed --accept--> accepted --begin--> in-progress --land--> landed
```

`landed` is terminal. The existing `blocked` status remains outside this new transition path and
keeps its current manual handling; this change adds no block/resume verb or blocked-state metadata.
Both `accept` and `begin` refuse a blocked change with a status-specific error rather than clearing,
reclassifying, or inferring anything about the block.

Add flat packaged CLI verbs matching the current command grammar:

- `doc-contract accept CHANGE [--dry-run] [--include-untracked]`
- `doc-contract begin CHANGE [--dry-run] [--include-untracked]`

`accept` changes only `proposed` to `accepted`, returns an idempotent no-op for `accepted`, and
refuses `in-progress`, `blocked`, and `landed`. `begin` changes only `accepted` to `in-progress`,
returns an idempotent no-op for `in-progress`, and refuses `proposed`, `blocked`, and `landed`. The CLI
cannot infer authorization: documentation must state that agents invoke `accept` only after an
explicit user/reviewer acceptance instruction. Do not add a ceremonial `--approved-by` flag that
would falsely claim to verify authority.

Add `src/doc_contract/lifecycle.py` with public `TransitionAction`, immutable `LifecyclePlan` and
`LifecycleOutcome`, plus:

```python
plan_transition(
    root,
    settings,
    change_ref,
    *,
    action,
    include_untracked=False,
    date=None,
) -> LifecyclePlan

execute_transition(..., dry_run=False, on_plan=None, fault_after=None) -> LifecycleOutcome
```

`LifecyclePlan` is the single deterministic change-selection and dry-run interface for downstream
mechanical entry/exit tooling. It carries the resolved change ID/path, source and destination status,
provisional nodes, current and projected findings, ordered mutations, input and output hashes,
journal path, and unified diff. Downstream commands call
`plan_transition(..., action=TransitionAction.BEGIN)` rather than duplicate resolver or reference-
selection logic.

Add `src/doc_contract/transaction.py` by extracting the existing generic mutation, atomic-write,
hash-check, journal serialization, interruption, and resume primitives from `landing.py`. Preserve
the current land journal schema/path so an upgrade can resume an already-started landing. New
lifecycle journals live under Git metadata as
`doc-contract/lifecycle-<action>-<change-id>.json`; dry-run creates no journal, temporary file, or
mtime change. No public JSON output or repository manifest is added: the structured plan/journal is
an internal replay boundary, while CLI dry-run prints the full mutation summary and unified diff.

**Δ MODIFIED** — Make `accepted` an active, roadmap-linked status and validate the complete supported
change-state set: `proposed`, `accepted`, `in-progress`, `blocked`, and `landed`. Add unambiguous
roadmap parsing for `(accepted)` and `(in-progress)` as well as the existing proposed/blocked forms;
unknown change statuses are resolver errors. Keep ownership-overlap warnings limited to concurrent
`in-progress` changes.

Add a resolver-owned status projection parallel to `project_landing`. Each transition rewrites the
selected `change.md`, the exact roadmap prose line and generated DAG, and active dependents whose
fingerprints must follow the changed canonical body. It produces these canonical forms:

- `accept`: `status: accepted`, `accepted_at: YYYY-MM-DD`, and
  `Status: Accepted · Accepted YYYY-MM-DD`.
- `begin`: `status: in-progress`, preserved `accepted_at`, new `started_at: YYYY-MM-DD`, and an
  `In progress` body line carrying the available acceptance/start dates.
Each planner requires an error-free current resolution and a transition-compatible selected state,
then resolves and validates the complete projected repository state before returning a plan. In
particular, the `BEGIN` plan must expose the projected `in-progress` roadmap status, dependency graph,
and concurrent ownership findings; projected errors reject the plan and projected warnings remain
available to the downstream mechanical-entry report. The executor atomically publishes each file
with `os.replace`, hash-checks every planned input immediately before mutation, journals every
completed boundary, treats already-written planned output as resumable success, and fails closed on
concurrent edits. Final verification is offline resolution;
acceptance/start transitions do not execute the target repository's capability subprocess. This
change intentionally supplies lifecycle eligibility, not semantic judgment or the later full
mechanical reconciliation report.

Restrict `land` to actual `in-progress` changes. `proposed`, `accepted`, and `blocked` inputs fail
with an actionable lifecycle error; completed archived changes retain the existing idempotent no-op.
Landing preserves `accepted_at` and `started_at` in front matter while continuing to write
`landed_at`, `archive_path`, and the existing landed body status.

Compatibility is fail-safe and non-destructive: existing `proposed` changes remain unaccepted;
existing `in-progress` changes remain valid and landable without backfilled timestamps; existing
manual `accepted` changes become valid with optional `accepted_at`; and existing `blocked` changes
remain byte-for-byte unchanged under their current manual process. There is no bulk rewrite,
blocked-state migration, or inferred acceptance. A formerly permitted direct proposed-to-landed
invocation becomes an intentional error requiring `accept` then `begin`.

Update the capability enumeration and lifecycle documentation so the supported path is author →
explicit user acceptance → `accept` → mechanical/semantic entry reconciliation → `begin` → work →
exit reconciliation → `land`. Preserve the distinction between deterministic state transitions and
human/agent judgment.

**Δ REMOVED** — Remove direct landing eligibility for proposed, accepted, or blocked changes and
remove documented manual status/roadmap editing as the normal acceptance/start path. Do not remove
standalone `check`, `update`, `stamp`, or the semantic reconciliation workflow.

## Tasks

1. Extract the reusable hash-guarded mutation/journal engine into `transaction.py` without changing
   existing landing journal compatibility, interruption recovery, tracking modes, or error hygiene.
2. Extend resolver status validation, active-state and roadmap-token handling, and add a pure
   status-transition projection that updates change prose/front matter,
   roadmap prose/DAG, active-dependent fingerprints, and projected findings without mutating
   caller-owned resolution.
3. Implement `lifecycle.py` with the exact public planner/executor interface, accept/begin transition
   table, idempotent accepted/in-progress handling, status-specific blocked refusal, untracked
   preview, dry-run diff, hash guards, journal replay, and offline final validation.
4. Add the two flat CLI verbs, concise plan/error output, and `--dry-run`/`--include-untracked`
   plumbing; keep secret values and subprocess output out of plans, journals, and diagnostics.
5. Make landing selection report status-specific ineligibility and permit only `in-progress`, while
   preserving already-landed no-op detection and the complete existing landing regression suite.
6. Add focused lifecycle, resolver, landing, CLI, compatibility-adapter, capability-coverage, and
   vendored-sync regressions; update the portable contract, guides, README, skill, capabilities, and
   roadmap to state the explicit authorization and transition sequence.
7. On land: run exit reconciliation, dry-run and execute `doc-contract land` from this change's
   `in-progress` state, verify the archived record preserves acceptance/start timestamps, and archive
   this folder through the normal transaction.

## Verify

- `uv run pytest -q`, `uv run ruff check .`, and `make check` pass; the explicit CLI command-set and
  capability-document tripwires enumerate `accept` and `begin`.
- Resolver fixtures accept all five supported states, reject unknown states, distinguish roadmap
  tokens for accepted/in-progress, and preserve existing blocked behavior plus in-progress-only
  ownership warnings without introducing blocked metadata.
- Each transition's dry-run leaves file bytes, mtimes, Git index, and journal paths unchanged; apply
  changes exactly the planned change/dependent/roadmap files; interruption at every boundary resumes
  to identical bytes; a post-plan edit fails without overwrite.
- `accept` is a no-op when already accepted, refuses blocked/in-progress/landed states, and never
  silently accepts a proposed item as part of `begin` or `land`.
- `begin` accepts only an accepted change, is a no-op when already in-progress, and refuses
  proposed/blocked/landed states; neither command mutates existing blocked state.
- Landing rejects proposed, accepted, and blocked fixtures with actionable errors, lands existing
  legacy and newly begun in-progress fixtures, and retains dry-run, tracked/untracked, recovery,
  concurrent-edit, final-verification, and completed-rerun behavior.
- `sync` includes `transaction.py` and `lifecycle.py` in a clean vendored runtime whose installed and
  vendored commands execute the same transition grammar from an unrelated cwd.
- Invariant spot-check: runtime code stays stdlib-only; authoring never implies acceptance; only an
  explicit user/reviewer instruction authorizes `accept`; deterministic lifecycle mechanics do not
  claim to decide semantic correctness.
