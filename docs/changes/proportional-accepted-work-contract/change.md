---
id: proportional-accepted-work-contract
persistence: ephemeral
status: proposed
track: lifecycle
depends_on:
  - accepted-change-state
  - mechanical-reconciliation
files_owned:
  - docs/changes/proportional-accepted-work-contract/change.md
  - guides/new-change.md
  - guides/reconcile.md
  - AGENTS.template.md
  - docs/roadmap.md
---
# Make accepted work contracts explicit and proportional

Status: Proposed (not accepted) · Proposed 2026-07-31

**Upstream dependencies:** `accepted-change-state` is landed and owns explicit user-authorized acceptance plus the `proposed -> accepted -> in-progress -> landed` lifecycle. `mechanical-reconciliation` is landed and owns the boundary between deterministic readiness evidence and semantic review judgment. Both inputs are available. No ADR, runtime feature, external service, or live input gates this documentation and workflow change.

**Dependents:** No in-repository change currently depends on this item. The separately maintained `reviewed-change-orchestration` workflow is the named external consumer of the accepted work contract, but its dispatch, review, commit, integration, and cleanup policy remains outside this repository. The sibling `review-bound-acceptance-plan` proposal supplies a transaction manifest for that workflow but does not depend on this artifact-shape change, and this item does not depend on it.

**Files owned:** The portable operating contract and the authoring/semantic-reconciliation guides, plus this proposal and its roadmap lineage. The active `optional-project-memory` proposal overlaps all three durable prose surfaces and the roadmap; this is a soft sequential overlap with no ordering dependency, so whichever item lands second must reconcile current wording and preserve both policies. `review-bound-acceptance-plan` also overlaps `AGENTS.template.md` and the roadmap; it owns acceptance command output while this item owns artifact meaning.

## Why

The current substantial-change skeleton stabilizes `Why`, delta-oriented `What changes`, `Tasks`, and `Verify`, but it does not require normative requirements, preserved behavior, exclusions, or verification modes to be distinguishable from explanatory prose. That is cheap for an author but expensive for downstream implementation and review: a risk-bearing change can leave evidence acquisition, identity re-observation, rejection before side effects, secret-safe failure, recovery, or operator-gated live verification implicit until a reviewer discovers the obligation after code exists.

The missing information belongs in the accepted artifact rather than in an orchestration prompt. The artifact should state what was authorized; orchestration should decide how to dispatch and prove it. The stronger shape must remain proportional: a routine local refactor needs a short work contract, while an evidence-sensitive, destructive, concurrent, or externally integrated change must expose the controls that determine whether its implementation is acceptable.

Git history is not the acceptance boundary. A newly drafted provisional change may be accepted and begun before implementation in an isolated same-session workflow, then archived with the implementation in one final commit. The downstream consumer still needs an immutable work-contract identity: the exact accepted `change.md` bytes plus their SHA-256 digest are sufficient without an intermediate Git checkpoint.

## Requirements

- Every substantial proposal presented for acceptance must separate normative requirements from explanatory rationale and delta inventory.
- Every substantial proposal must state preserved behavior and explicit exclusions compactly; `none beyond the stated scope` is acceptable when honest.
- `## Verify` must distinguish focused regression checks, the repository's canonical gate, and live or operator-gated verification. An inapplicable live mode is stated as `not required`, not silently omitted when its absence could be ambiguous.
- Authoring must assess credentials or secrets, fail-closed behavior, evidence or identity binding, mutable external inputs, live integrations, import or source provenance, destructive effects, concurrency, and security-sensitive parsing before presenting the proposal for acceptance.
- When one of those signals creates material obligations, add an `## Evidence and side-effect controls` section. Use a compact table or bullets that identify the obligation, authoritative acquisition point, re-observation and decision point, failure or side-effect boundary, focused proof, and live authority. Add recovery, idempotency, atomicity, or compensation obligations when the risk requires them rather than forcing every risk into an evidence-only table.
- An unresolved decision that changes requirements, exclusions, safety boundaries, or verification authority prevents the proposal from being described as accept-ready. Non-blocking questions may remain only when they cannot change the authorized work contract.
- Semantic entry reconciliation must treat a discovered accepted-artifact gap or contradiction as a stop for user direction, not as permission to expand requirements silently. Mechanical readiness must continue to make no safety or completeness claim.
- A downstream consumer must bind execution to the exact accepted `change.md` bytes and their SHA-256 digest. A Git commit may provide that immutable reference, but is not required when the consumer captures the bytes and digest outside the mutable implementation tree.
- Acceptance remains logically before `begin` and implementation. In an isolated same-session flow, a provisional untracked proposal may be accepted, begun, implemented, landed, and archived before one final commit records the accepted lineage with the implementation, tests, and durable documentation.
- A separate acceptance checkpoint remains optional for explicit audit requirements, a multi-session or cross-operator handoff, or mixed state that cannot be transferred or isolated safely. `doc-contract` continues to own no staging or commit operation and must not require such a checkpoint.

## Preserved behavior and exclusions

- Preserve the current YAML subset and all existing front-matter fields; add no `review_profile`, risk enum, heading parser, or runtime schema in this change.
- Preserve `Why`, delta-oriented `What changes`, ordered `Tasks`, and one default `change.md` for substantial work. The new contract deepens that file rather than splitting ordinary proposals.
- Preserve the explicit acceptance transition and the semantic/mechanical reconciliation split. Authoring and review may judge risk; the packaged runtime must not infer it from keywords or claim that prose is complete or wise.
- Preserve the distinction between acceptance authority and Git history: omitting an intermediate checkpoint never permits implementation before successful acceptance and `begin`.
- Do not add orchestration prompts, model routing, worktree policy, evidence-log capture, commit behavior, or cleanup mechanics to this repository.
- Do not require the optional controls section for trivial edits or low-risk substantial work, and do not create automated prose-content tests for semantic quality.

## What changes

**Δ ADDED** — Add `## Requirements` and `## Preserved behavior and exclusions` to the default substantial-change contract. Define a compact verification-mode convention under `## Verify`, plus an optional `## Evidence and side-effect controls` section selected through semantic risk assessment. State that acceptance-blocking decisions must be resolved before presentation for acceptance and that downstream execution consumes the exact accepted artifact bytes plus a content digest.

**Δ MODIFIED** — Update `guides/new-change.md` to ask the risk questions while grounding a proposal, select only applicable control fields, and hand back an artifact whose requirements, exclusions, verification authority, and remaining decisions are explicit. Update `guides/reconcile.md` so entry review checks the accepted contract without silently repairing scope and exit review verifies the implementation against the same requirements and controls. Update `AGENTS.template.md` with the portable artifact contract while retaining the current cheap weight classes and one-line dispatch.

**Δ REMOVED** — Remove reliance on reviewers reconstructing normative obligations from `Why`, delta prose, and undifferentiated verification bullets. Remove no lifecycle state, front-matter field, command, resolver behavior, or existing archived artifact.

## Tasks

1. Revise the default substantial-change skeleton in `guides/new-change.md` with explicit requirements, preserved behavior and exclusions, compact focused/canonical/live verification labels, and an optional risk-controls section.
2. Add a semantic authoring pass for the named risk signals, including risk-specific recovery or concurrency controls where an evidence-only matrix would be misleading; do not infer or validate risk in the packaged runtime.
3. Define acceptance readiness honestly: surface acceptance-blocking decisions before handback, keep non-blocking questions explicit, and do not describe a semantically unresolved contract as ready merely because its structure is present.
4. Update semantic entry and exit reconciliation so accepted-artifact gaps, new scope, and contradictions stop for user direction, while implementation defects remain implementation work and mechanical readiness remains evidence only.
5. Update the portable operating contract with the proportional artifact shape, exact accepted-byte and digest expectation for downstream consumers, optional checkpoint fallback, same-session one-final-commit path, and the unchanged ownership boundary between doc-contract and orchestration.
6. Make the lifecycle order explicit: acceptance and `begin` still precede implementation even when Git records the accepted lineage only in the final landing commit.
7. Reconcile the final prose with `optional-project-memory` and `review-bound-acceptance-plan` if either lands first; preserve repository-local durability, explicit lifecycle authority, and the no-commit runtime boundary.
8. Run focused text audits, the repository test and lint gates, and `doc-contract check --repo-root . --offline --include-untracked`; add no runtime test that pretends to judge semantic adequacy.
9. On land, archive this folder through the transactional lifecycle and retain the resulting roadmap lineage.

## Verify

- **Focused:** Draft one low-risk local-refactor fixture and one evidence-sensitive fixture from the revised guide. The low-risk artifact remains short and contains no empty risk table; the evidence-sensitive artifact makes acquisition, re-observation, side-effect cutoff, secret-safe failure, regression, and live authority explicit. A concurrency or destructive fixture adds the applicable atomicity/recovery obligations rather than filling irrelevant evidence columns. A provisional same-session fixture captures accepted bytes and digest, begins before implementation, and produces one final commit without an intermediate checkpoint.
- **Canonical:** `uv run --group test pytest -q -p no:cacheprovider`, `uv run --group lint ruff check --no-cache .`, and `doc-contract check --repo-root . --offline --include-untracked` pass. Focused text audits confirm the active authoring, reconciliation, and portable-contract instructions use one consistent artifact shape and preserve the semantic/mechanical boundary.
- **Live or operator-gated:** Not required; this change modifies repository documentation and skill workflow only and introduces no live integration.
- **Invariant spot-check:** Ordinary substantial changes retain one concise `change.md`; no front-matter grammar or runtime behavior changes; accepted-artifact gaps cannot silently become implementation obligations; acceptance and `begin` remain logically before implementation; exact accepted bytes plus SHA-256 are sufficient identity; Git checkpoints remain optional; external orchestration remains responsible for artifact snapshots, dispatch, evidence collection, commits, integration, and cleanup.
