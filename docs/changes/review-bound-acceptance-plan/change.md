---
id: review-bound-acceptance-plan
persistence: ephemeral
status: proposed
track: lifecycle
depends_on:
  - accepted-change-state
  - mechanical-reconciliation
  - actionable-lifecycle-diagnostics
files_owned:
  - docs/changes/review-bound-acceptance-plan/change.md
  - src/doc_contract/transaction.py
  - src/doc_contract/lifecycle.py
  - src/doc_contract/reconciliation.py
  - src/doc_contract/cli.py
  - tests/test_lifecycle.py
  - tests/test_reconciliation.py
  - tests/test_cli.py
  - docs/spec/capabilities.md
  - README.md
  - SKILL.md
  - AGENTS.template.md
  - docs/roadmap.md
---
# Bind reviewed acceptance plans to application

Status: Proposed (not accepted) · Proposed 2026-07-31

**Upstream dependencies:** `accepted-change-state` is landed and owns the deterministic `LifecyclePlan`, hash-guarded mutation execution, interruption journal, recovery, and idempotent acceptance behavior. `mechanical-reconciliation` is landed and establishes a versioned, content-free public manifest pattern distinct from private journal serialization. `actionable-lifecycle-diagnostics` is landed and supplies stable value-free lifecycle error fields for text and JSON callers. All inputs are available. No ADR, external service, live input, or third-party package gates implementation.

**Dependents:** No in-repository change currently depends on this item. The existing `reviewed-change-orchestration` workflow is a concrete external consumer: explicit `accept and execute` must inspect exactly one named acceptance transaction, reject unexplained paths before mutation, and checkpoint only the resulting lifecycle paths. Consumer adoption remains a separate change in that repository. The sibling `proportional-accepted-work-contract` proposal improves artifact meaning but is independent of this transaction interface.

**Files owned:** The generic transaction projection needed to share content-free mutation records, lifecycle plan identity and expectation enforcement, acceptance CLI rendering, focused lifecycle/reconciliation/CLI tests, public capability and usage documentation, the portable skill and operating contract, this proposal, and roadmap lineage. `proportional-accepted-work-contract` overlaps `AGENTS.template.md` and the roadmap; `optional-project-memory` also overlaps those files. These are soft prose overlaps with no ordering dependency. Existing archived lifecycle changes own the same runtime surfaces historically but are landed baselines, not active conflicts.

## Why

`doc-contract accept CHANGE --dry-run` already computes the complete deterministic acceptance transaction: the selected ticket's lifecycle rewrite, active dependent-ticket fingerprint refreshes, roadmap projection, ordered mutations, and preimage/postimage hashes. Its current CLI presentation prints a human summary, transaction hashes, and the complete diff, while the private `LifecyclePlan.as_dict()` includes mutation contents for journal recovery. Neither is a stable, content-free machine contract for an orchestrator.

A path-only JSON rendering would add little. It could enumerate dynamically affected lifecycle documents, but it would not ensure that the plan reviewed during dry-run is still the plan applied later. If repository state or the transition date changes between commands, apply can legitimately compute a different deterministic plan. Reporting a different identifier after mutation is retrospective evidence, not a pre-mutation guard. The useful interface therefore couples a public acceptance manifest with a content-free `plan_id` and an apply-time expectation check.

## Requirements

- Add `--format {text,json}` to `doc-contract accept`, retaining current text behavior as the default. Do not broaden `begin` or `land` in this change.
- JSON output must be one versioned object for dry-run, successful apply, idempotent no-op, expected-plan rejection, lifecycle blocker, and transaction failure; it must not interleave human text on stdout.
- The public plan must expose action, normalized change ID and repository-relative path, tracking mode, transition date, source and destination status, `include_untracked`, provisional nodes, and ordered mutation kind/path/destination. Value-free findings belong to the surrounding report rather than the transaction identity.
- Compute `plan_id` from a domain-separated, schema-versioned canonical encoding of the public plan plus each ordered mutation's private preimage and postimage hashes. Expose the resulting digest, not the individual mutation hashes or contents. Do not bind unrelated repository warnings that cannot alter the transaction; preflight errors continue to prevent a plan.
- Add `--expect-plan-id ID` to `accept`. Require the canonical `sha256:<64 lowercase hexadecimal characters>` form without echoing invalid input. When supplied on dry-run or apply, recompute or load the authoritative plan and report whether the expectation matches; a non-noop apply must reject a mismatch before creating a new journal or applying any mutation. A resumed transaction must validate the identifier of its journaled plan before continuing.
- The same unchanged repository state, transition date, and command arguments must produce the same `plan_id` in dry-run and apply. A changed planned path, preimage, postimage, option, or date must produce a different identifier and a pre-mutation rejection when an expectation was supplied. A changed surrounding finding set does not alter transaction identity; an error that prevents planning produces no plan and no `plan_id`.
- Preserve idempotency honestly. An already-accepted change remains a successful no-op and reports `execution.status: already-applied`; unless an active journal provides the original plan, it must not claim that a supplied historical expectation was verified.
- Keep `plan_id` distinct from accepted-artifact identity. It identifies the complete acceptance transaction, including roadmap and dependent metadata; the downstream acceptance checkpoint commit or an equivalent immutable artifact reference identifies the accepted work contract.
- Preserve current journals, recovery, concurrent-edit checks, tracked/untracked handling, final resolver validation, and exit-code behavior. The runtime must not stage or commit Git changes.

## Preserved behavior and exclusions

- Preserve current `accept` text output byte-for-byte unless a separately justified diagnostic correction is required; JSON is opt-in.
- Do not publish `LifecyclePlan.as_dict()` or private journal schema as the public interface. JSON must exclude document bodies, mutation contents, unified diffs, individual before/after hashes, journal paths, arbitrary gate text, capability arguments or output, and secret values.
- Do not claim that mutation paths identify implementation scope. Ticket front matter remains the persistent authored declaration of dependencies and `files_owned`; the operation manifest is an ephemeral computed description of what this acceptance invocation will mutate.
- Do not claim that path enumeration alone guarantees exact staging when a planned path contains pre-existing mixed edits. Documentation must require an isolated or otherwise owned baseline, or caller-controlled patch staging, before treating paths as a checkpoint boundary.
- Do not add a stored-plan service, runtime commit authority, generic workflow engine, or a JSON format for every lifecycle command. Consumer adoption and acceptance-checkpoint commit policy remain outside this repository.

## Evidence and side-effect controls

- **Reviewed transaction identity:** The authoritative source is the immutable `LifecyclePlan` and its ordered `Mutation` preimage/postimage hashes. Recompute or load that plan immediately before apply, compare the canonical identifier, and reject before a new journal or first mutation. Focused tests change each review-relevant plan input independently. No live authority is required.
- **Journaled resume:** The authoritative source after interruption is the existing private lifecycle journal. Re-observe its stored plan, derive the same public identifier, and reject an expected-identifier mismatch before resuming any remaining mutation. Preserve completed-boundary and concurrent-edit checks; focused interruption tests prove no parallel plan representation is introduced.
- **Value-free output:** The authoritative output fields are normalized IDs, repository-relative paths, lifecycle statuses, tracking/options, public mutation descriptors, safe findings, execution state, and a digest. Reject malformed or mismatched identifiers without echoing arbitrary input; never serialize mutation content, diffs, individual hashes, raw gate text, journal paths, capability arguments/output, or secret values. Focused marker tests cover both success and failure JSON.
- **Git side-effect boundary:** Acceptance may write lifecycle documents but must never stage or commit. The expectation check occurs before filesystem mutation, and documentation states that path-scoped staging is exact only from an isolated or otherwise owned baseline. The external consumer is the live authority for any acceptance checkpoint commit.

## What changes

**Δ ADDED** — Add a schema-1 content-free acceptance report with this stable outer shape:

```json
{
  "schema_version": 1,
  "kind": "acceptance-transition",
  "plan_id": "sha256:<digest>",
  "plan": {
    "action": "accept",
    "change": {
      "id": "change-a",
      "path": "docs/changes/change-a",
      "tracking": "tracked"
    },
    "transition": {
      "date": "2026-07-31",
      "source_status": "proposed",
      "destination_status": "accepted"
    },
    "options": {
      "include_untracked": false
    },
    "provisional_nodes": [],
    "mutations": [
      {
        "kind": "write",
        "path": "docs/changes/change-a/change.md",
        "destination": null
      },
      {
        "kind": "write",
        "path": "docs/roadmap.md",
        "destination": null
      }
    ]
  },
  "execution": {
    "mode": "dry-run",
    "status": "not-applied",
    "expectation": "not-provided"
  },
  "findings": [],
  "diagnostic": null
}
```

Dry-run and apply return the same `plan_id` and `plan` when their reviewed transaction is identical; only `execution` and final findings differ. Apply with a matching expectation reports `mode: apply`, `status: applied`, and `expectation: matched`. A mismatch returns the newly computed content-free plan with `status: rejected`, `expectation: mismatch`, and diagnostic code `accept-plan-mismatch` before mutation. A blocker that prevents planning returns `plan_id: null`, `plan: null`, a rejected execution, and the existing structured lifecycle diagnostic. An already-accepted no-op reports `status: already-applied` and `expectation: not-verifiable` when no active journal can prove the historical plan.

Add a canonical plan-identity function over domain-separated public fields and private mutation preimage/postimage hashes. Add the `--expect-plan-id` optimistic-concurrency boundary so a reviewed dry-run plan can be required before apply. A mismatch uses a stable value-free diagnostic such as `accept-plan-mismatch`, returns nonzero, does not echo arbitrary expected input, and leaves repository bytes, mtimes, index, and journal state unchanged.

**Δ MODIFIED** — Extract or reuse the smallest shared content-free mutation projection so reconciliation and acceptance JSON cannot drift while journal mutations retain their private contents and hashes. Extend acceptance execution to validate an expected identifier against a newly planned or resumed journaled transaction before mutation. Update capability documentation, README, skill command guidance, and the portable operating contract with the exact dry-run/review/apply sequence and the clean-baseline limitation of path-scoped staging.

**Δ REMOVED** — Remove the need for orchestration to parse unified diffs, infer dynamically refreshed dependent tickets, or guess acceptance paths from `git status`. Remove no existing text output, lifecycle transition, diff, hash guard, journal, recovery, resolver, reconciliation, landing, or verification behavior.

## Tasks

1. Define a versioned public acceptance-report type and the smallest shared content-free mutation projection; keep private `Mutation` and lifecycle journal serialization unchanged and resumable.
2. Define and document canonical `plan_id` encoding with an explicit domain separator, schema version, normalized plan fields, ordered mutation descriptors, and private preimage/postimage hashes; add deterministic unit tests that pin meaningful transaction changes without binding unrelated warnings.
3. Extend acceptance execution with an optional normalized expected identifier checked during dry-run, before any new journal or mutation during apply, and against a loaded journal before resume. Preserve existing internal hash guards after the expectation passes and keep malformed-input diagnostics value-free.
4. Add `accept --format json` and `--expect-plan-id`, producing exactly one JSON object with plan, execution status, and value-free diagnostic semantics across dry-run, apply, mismatch, interruption recovery, blockers, failures, and already-applied no-op behavior.
5. Add regressions proving that accepting `change-a` does not transition or rewrite unrelated `change-b`; a genuinely dependent proposal appears only when its fingerprint refresh is in the ordered manifest. Verify dry-run and apply expose identical planned mutations and identifier before execution status diverges.
6. Prove expected-plan mismatch on changed ticket bytes, dependent metadata, roadmap bytes, transition date, or options occurs before filesystem, mtime, index, or journal mutation. Retain concurrent-edit and interruption/resume tests after the expectation boundary, and prove an unrelated warning that cannot alter the transaction does not invalidate its identifier.
7. Prove JSON contains no document body marker, diff, individual transaction hash, private journal path, raw gate text, secret value, capability argument, or subprocess output. Preserve current text output and classified error exit semantics.
8. Exercise installed and synced vendored acceptance from an unrelated working directory, proving identical schema and `plan_id` behavior without distribution metadata or third-party dependencies.
9. Update `docs/spec/capabilities.md`, `README.md`, `SKILL.md`, and `AGENTS.template.md` with the public contract, front-matter-versus-operation-manifest distinction, apply-time expectation sequence, already-applied limitation, and exact-staging baseline requirement.
10. On land, archive this folder through the transactional command and retain the roadmap lineage. Do not modify the external orchestration consumer in this repository.

## Verify

- **Focused:** Lifecycle and CLI tests pin schema-1 JSON, canonical identifiers, expected-plan success and mismatch, selected versus unrelated proposals, dependent fingerprint paths, date and option changes, tracked/untracked plans, already-applied honesty, interrupted resume, concurrent edits, and value-free failures.
- **Canonical:** `uv run --group test pytest -q -p no:cacheprovider`, `uv run --group lint ruff check --no-cache .`, and `doc-contract check --repo-root . --offline --include-untracked` pass, including capability coverage and the real document DAG.
- **Live or operator-gated:** Not required; installed and synced vendored subprocess smoke tests use temporary local repositories and unrelated local working directories only.
- **Invariant spot-check:** Runtime remains stdlib-only and cwd-independent; the plan reviewed by identifier is rejected before mutation if it changes; private journal content remains private; acceptance stays explicit and single-target; idempotent no-op behavior remains honest; the runtime neither stages nor commits; and semantic artifact quality remains outside deterministic validation.
