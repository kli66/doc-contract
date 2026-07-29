---
id: mechanical-reconciliation
persistence: ephemeral
status: proposed
track: lifecycle
depends_on:
  - accepted-change-state
requires_status:
  accepted-change-state: landed
files_owned:
  - src/doc_contract/reconciliation.py
  - src/doc_contract/resolver.py
  - src/doc_contract/landing.py
  - src/doc_contract/cli.py
  - tests/test_reconciliation.py
  - tests/test_resolver.py
  - tests/test_landing.py
  - tests/test_cli.py
  - docs/spec/capabilities.md
  - DESIGN-RATIONALE.md
  - README.md
  - SKILL.md
  - AGENTS.template.md
  - guides/reconcile.md
  - docs/roadmap.md
fingerprints:
  accepted-change-state: 32bc0f5591be9c6c
---
# Add deterministic mechanical reconciliation

Status: Proposed (not accepted) · Proposed 2026-07-28

**Upstream dependencies:** `accepted-change-state` is proposed and must land first. It owns the lifecycle state model `proposed --accept--> accepted --begin--> in-progress --land--> landed`, leaves the existing `blocked` state under semantic/manual handling, and supplies the canonical `src/doc_contract/lifecycle.py` interface: `TransitionAction`, immutable `LifecyclePlan`, `plan_transition(...)`, and `execute_transition(...)`. This change consumes `plan_transition(..., action=TransitionAction.BEGIN)` for entry readiness and must not recreate lifecycle selection, transition, mutation, or journal logic. Design and isolated report tests are available now; entry integration is gated until that interface lands. No ADR or external infrastructure gates the work.

**Dependents:** None currently. The semantic `/doc-contract reconcile` skill workflow will consume this command, but it is updated by this same change rather than represented as a separate DAG node.

**Files owned:** One new packaged reconciliation report module; structured resolver findings and typed landing-plan failures needed to scope that report; CLI and focused tests; the capability reference, workflow rationale, package/skill/operating-contract guidance, reconcile guide, and roadmap. `accepted-change-state` also owns `src/doc_contract/cli.py`, `tests/test_cli.py`, `docs/spec/capabilities.md`, `README.md`, `SKILL.md`, `AGENTS.template.md`, `guides/reconcile.md`, and `docs/roadmap.md`; this is a soft sequential overlap because that change must land first, after which this proposal rebases and adds the `reconcile` surface without changing its lifecycle model. The separately proposed `actionable-lifecycle-diagnostics` and landing-output changes may overlap `landing.py`, CLI rendering, tests, and documentation; reconcile their final typed error/output interfaces at entry rather than adding false dependency edges.

## Why

The skill currently asks an agent to perform entry and exit reconciliation by reading prose and improvising checks. Several of those checks are already deterministic: resolver validation owns dependencies, roadmap linkage/status, fingerprints, file declarations, and graph findings; the accepted-state `BEGIN` planner will own accepted-to-in-progress readiness and projected ownership conflicts; and `plan_landing` already owns archive destination, Git tracking, projected landed state, and final graph validity. Leaving the agent to regenerate those mechanics wastes context, permits inconsistent interpretations, and obscures the real human task: deciding whether the change, ADRs, roadmap, and implementation still agree in meaning.

The packaged CLI and the judgment-heavy skill also currently share the same `doc-contract reconcile` wording even though no packaged reconcile command exists. The interface should name the deterministic half explicitly, keep it read-only, and let the skill invoke and consume its structured result before performing semantic review.

## What changes

**Δ ADDED** — Add the packaged command `doc-contract reconcile mechanical <change-ref> --phase {entry,exit} [--format {text,json}] [--include-untracked]`, with the existing common `--repo-root` and `--config` options. It performs no writes, index changes, journals, moves, capability subprocesses, or project test commands. Exit status is `0` only when the requested phase is mechanically ready, `1` for deterministic blockers, and `2` for CLI/configuration errors; warnings do not block unless an existing strict repository policy classifies them as errors.

Add an immutable `ReconciliationReport` in `src/doc_contract/reconciliation.py` as the single interface for CLI rendering and tests. Its versioned JSON form contains `schema_version`, `kind: "mechanical"`, `phase`, `ready`, selected change identity/path/status, `next_command`, scoped findings, and a content-free manifest. A blocked selection exposes only value-free `gate_present: true|false`, derived from whether structured `gated_on` metadata is present; neither output format returns that field's value or scrapes body prose for a gate. Entry delegates exactly once to `plan_transition(..., BEGIN)` and summarizes its from/to state, provisional nodes, and ordered mutation paths without applying them. Exit delegates exactly once to `plan_landing` and summarizes tracking mode, archive target, provisional nodes, and ordered mutation paths without printing mutation content or the unified diff. Text output is the compact rendering of the same report: identity and phase, ready/blocked summary, blockers and selected/related warnings, unrelated repository warning count, manifest paths/archive target, and the next lifecycle command.

Add structured subjects to resolver `Finding` values so reconciliation can classify findings without parsing diagnostic prose. Each node/edge/ownership/cycle finding records its involved node IDs; repository-boundary findings remain unscoped. The report exposes scopes `change` when the selected ID is a subject, `related` for its direct dependencies, dependents, or projected ownership peers, and `repository` otherwise. All blocker findings are printed in text regardless of scope; unrelated non-blocking warnings are counted in text and retained in JSON. Extend `LandingError` with a stable code and attached resolver findings while preserving its current human-readable text, so failed exit planning remains structured rather than being converted from exception strings.

**Δ MODIFIED** — Define phase policy without duplicating validators. Entry requires actual `accepted` state and uses the upstream `BEGIN` plan as the authoritative proof that the selected change can transition to `in-progress`. A `proposed` change produces an actionable blocker with `next_command` set to `doc-contract accept <change-ref>`; an `in-progress` change reports that entry is already past without suggesting another transition. A `blocked` change reports its current status, value-free `gate_present: true|false`, and `next_command: null`; it never exposes arbitrary `gated_on` text or body prose, neither clears the block nor suggests an automated unblocking operation, and leaves unblocking to the semantic/manual workflow. Missing declared owned paths remain visible but non-blocking at entry because accepted proposals may own new files. Exit requires actual `in-progress` state and uses the landing plan as the authoritative proof of resolvable dependencies, tracking state, destination availability, projected roadmap/fingerprint updates, and final graph validity; a missing path declared in the selected change's `files_owned` is promoted to an exit blocker because the implementation is claiming completion. Advisory fingerprint warnings remain warnings, while `edge_fingerprints = "required"` retains its existing blocking semantics.

Make `/doc-contract reconcile semantic <folder> [entry|exit]` the explicit skill spelling while retaining `/doc-contract reconcile <folder> [entry|exit]` as a compatibility alias for the same semantic workflow. The skill runs `doc-contract reconcile mechanical ... --format json` first, then performs semantic review; after any semantic drift repair it reruns the mechanical command before invoking `doc-contract begin` at entry or `doc-contract land --dry-run` and `doc-contract land` at exit. The skill must treat `ready: true` as mechanical readiness only, never acceptance, semantic approval, task completion, or authorization to mutate.

State exactly what remains semantic: whether cited ADR prose still means what the change claims; whether a mismatch is stale durable documentation or a live contradiction; whether the proposed scope, dependency ordering, ownership split, and tasks are sufficient and wise; whether implementation behavior satisfies intent rather than merely touching declared files; whether completed/superseded/descoped task claims are honest; and whether durable repository documents contain all knowledge needed after archive. The packaged command reports evidence and lifecycle readiness but never classifies these judgments or edits documents to resolve them.

Update `COMMANDS`, CLI help, the capability heading/tripwire expectation, vendored-runtime smoke coverage, workflow rationale, README, skill dispatcher, operating-contract template, and reconciliation guide. Correct wording such as “executable mechanics” where it currently implies the semantic skill is itself a packaged command. The new Python module is included automatically by the existing sync runtime-image discovery; do not add a manual package inventory.

**Δ REMOVED** — Remove hand-generated dependency, ownership, roadmap, fingerprint, file, and archive-destination checks from the semantic reconcile procedure. Remove no existing resolver, lifecycle, landing, verification, update, stamp, or skill behavior, and add no model call or third-party dependency to the packaged runtime.

## Tasks

1. Land and reconcile `accepted-change-state`, then rebase this change and consume its exact `TransitionAction.BEGIN`/`LifecyclePlan` interface; do not duplicate ref selection, state validation, transition projection, mutations, or journaling.
2. Add subject IDs to resolver findings and focused regressions for edge, roadmap, owned-path, cycle, and ownership findings, keeping existing text and constructor compatibility where no subjects are supplied.
3. Make landing planning expose stable typed blocker codes and attached resolver findings while preserving current CLI text and transactional behavior; do not change `plan_landing` archive, projection, diff, tracking, or mutation semantics.
4. Implement `ReconciliationReport` and the read-only phase dispatcher: entry wraps one `BEGIN` plan, exit wraps one landing plan, phase-specific policy promotes selected missing owned paths only at exit, and both produce the same content-free manifest and scoped findings.
5. Add the nested CLI grammar, compact text renderer, versioned JSON renderer, exit-code policy, `--include-untracked` handling, and explicit refusal to run capability subprocesses or mutate any filesystem/Git state.
6. Update the semantic skill workflow and durable documentation with the mechanical-first sequence, explicit semantic-only judgments, compatibility alias, accepted/begin/in-progress/land ordering, and rerun requirement after semantic repairs.
7. Add unit and integration tests for report scoping and serialization, entry/exit planner parity, lifecycle-state diagnostics, advisory/required fingerprints, roadmap mismatch, dependency failure, projected ownership overlap, phase-specific file existence, untracked discovery, archive collision, partial tracking, global blockers, unrelated warning compaction, and byte/mtime/index/journal immutability.
8. Exercise installed and synced vendored commands from an unrelated cwd, verify the capability coverage tripwire and explicit `COMMANDS` assertion include only the top-level `reconcile` name, and confirm text/JSON contain no file contents, diffs, subprocess output, command arguments, or secret values.
9. On land: archive this folder through `doc-contract land`, regenerate the roadmap DAG, and retain the mechanical/semantic split in durable repository documentation; no external project-memory write is required.

## Verify

- `uv run --group test pytest -q -p no:cacheprovider` and `uv run --group lint ruff check --no-cache .` pass, including resolver, landing, CLI, capability coverage, real-corpus DAG, sync, and vendored-launcher tests.
- An accepted fixture that is ready to begin yields equivalent change identity, projected status, findings, and mutation paths from `reconcile mechanical --phase entry` and `plan_transition(..., BEGIN)`; a ready in-progress fixture yields equivalent tracking, archive target, findings, and mutation paths from exit reconciliation and `plan_landing`.
- Proposed, blocked, already in-progress, accepted-at-exit, and landed fixtures produce stable actionable state findings without mutation. Blocked fixtures with absent and arbitrary `gated_on` values emit only the correct `gate_present` boolean and `next_command: null`; neither text nor JSON contains the gate value or body prose. Entry reports missing future-owned files as warnings, while exit blocks the same missing paths. Projected concurrent ownership, unsatisfied dependencies, roadmap mismatch, strict fingerprints, archive collision, partial tracking, and repository resolver errors produce nonzero readiness.
- Text output remains compact and omits unrelated warning detail while showing every blocker; JSON schema 1 retains all scoped findings and content-free plan metadata. Neither format contains a unified diff, file content, capability command/output, environment values, or secret matches.
- Before and after every success and failure case, repository bytes, mtimes, Git index, archive paths, and `.git/doc-contract/` journals are unchanged. Repeating the command returns byte-identical JSON for unchanged inputs.
- The semantic skill invokes mechanical reconciliation, reruns it after any drift repair, and still requires human/model judgment plus explicit `begin` or `land`; a mechanical green result alone cannot mutate or accept work.
- Invariant spot-check: runtime remains stdlib-only and air-gap-safe; repository selection stays explicit and fail-closed; resolver/lifecycle/landing mechanics each retain one authoritative implementation; frozen-document and secret-redaction rules remain intact; the existing slash reconcile invocation remains a semantic compatibility alias.
