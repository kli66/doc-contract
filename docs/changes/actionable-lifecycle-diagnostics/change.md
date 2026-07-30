---
id: actionable-lifecycle-diagnostics
persistence: ephemeral
status: proposed
track: remediation
depends_on:
  - accepted-change-state
  - mechanical-reconciliation
requires_status:
  accepted-change-state: landed
  mechanical-reconciliation: landed
files_owned:
  - src/doc_contract/lifecycle.py
  - src/doc_contract/reconciliation.py
  - src/doc_contract/landing.py
  - src/doc_contract/cli.py
  - tests/test_lifecycle.py
  - tests/test_reconciliation.py
  - tests/test_landing.py
  - tests/test_cli.py
  - docs/spec/capabilities.md
  - README.md
  - docs/roadmap.md
fingerprints:
  accepted-change-state: 32bc0f5591be9c6c
  mechanical-reconciliation: af4a73462f7a0b94
---
# Make lifecycle diagnostics stable and actionable

Status: Proposed (not accepted) · Proposed 2026-07-28

**Upstream dependencies:** `accepted-change-state` is a proposed, gated prerequisite that adds the `accepted` state, the `accept` and `begin` transitions, and the shared lifecycle module this change extends. `mechanical-reconciliation` is a proposed, gated prerequisite that adds the read-only `reconcile mechanical` command, its schema-1 `ReconciliationReport`, and typed landing errors. Both must land first so diagnostics recommend only commands that actually exist and reuse the resulting lifecycle/reconciliation interfaces. No ADR governs this internal CLI behavior and no external infrastructure is required after those prerequisites land.
**Dependents:** None currently. No roadmap item or active change folder names this diagnostic taxonomy as a prerequisite.
**Files owned:** The prerequisite-created lifecycle and reconciliation modules; landing source selection; CLI rendering for lifecycle commands; focused lifecycle, reconciliation, landing, and CLI tests; the capability and README diagnostic contract; and this change's roadmap entry. The two upstream changes own overlapping regions in every source and test file listed here and in the consumer docs. This overlap is ordered rather than concurrent: land both prerequisites, then rebase and reconcile this change against their final interfaces before implementation. Transaction journaling, graph validation, transition rules, report schema, and semantic reconciliation remain owned by the prerequisites.

## Why

Lifecycle selection currently loses the reason a change cannot be used. `landing._locate_source` collapses a missing path, a path outside the active change tree, a folder without usable metadata, an inactive status, and an unknown ID into variants of `change-not-found`. `plan_landing` also runs whole-repository resolution before it classifies the requested reference, so malformed front matter can escape as an untyped `ValueError` and unrelated resolver failures can hide the selected change's state. The CLI then renders every typed landing failure as `[LandingError]`, leaving agents to inspect files or generate ad hoc probes to determine the next valid lifecycle command.

The accepted-state and mechanical-reconciliation changes add more lifecycle callers and provide the correct seam: one lifecycle module for reference/state classification, a reconciliation report with scoped findings and `next_command`, and command adapters that preserve the `0` success, `1` operational blocker, and `2` usage/configuration exit policy. Diagnostics should deepen those interfaces rather than give `accept`, `begin`, `reconcile mechanical`, and `land` separate lookup rules.

## What changes

**Δ ADDED** — Extend the lifecycle module with one pure change-reference classification interface, one immutable `LifecycleDiagnostic` carrying a stable `code`, deterministic value-free `message`, and nullable canonical `next_command`, and one `LifecycleError` that wraps a blocking diagnostic. Callers supply the requested lifecycle action and `include_untracked` policy; the module returns the prerequisite's selected change identity, path, status, tracking facts, and any informational diagnostic, or raises `LifecycleError` when the action cannot proceed. A repeated `land` receives `change-already-landed` as an informational result rather than an exception. Do not add one exception subclass per code.

Define this stable taxonomy:

| Code | Deterministic condition | Canonical hint | Exit behavior |
| --- | --- | --- | --- |
| `change-proposed-unaccepted` | Selected status is `proposed`, but the action requires acceptance or execution | `doc-contract accept CHANGE --dry-run` | blocker, `1` |
| `change-accepted-not-started` | Selected status is `accepted`, but the action requires `in-progress` | `doc-contract begin CHANGE --dry-run` | blocker, `1` |
| `change-blocked` | Selected status is `blocked` | none; report status and `gate_present=true|false` | blocker, `1` |
| `change-already-landed` | A valid archived record matches the normalized ID or archive path | none | repeated `land` is informational/no-op `0`; pre-land actions are blockers `1` |
| `change-untracked-excluded` | A correctly shaped candidate is excluded by tracked-only discovery | rerun the same normalized command with `--include-untracked` | blocker, `1` |
| `change-front-matter-missing` | A tracked change folder contains no node-bearing Markdown front matter | none | blocker, `1` |
| `change-front-matter-invalid` | Front matter is malformed, ambiguous, or lacks a valid required identity/status field | none | blocker, `1` |
| `change-ref-wrong-folder` | A path reference exists or is path-shaped but is not an exact active/archive change folder inside the selected repository | none | blocker, `1` |
| `change-ref-unknown` | No active candidate or valid archived record matches a normalized ID or correctly shaped missing path | none | blocker, `1` |

Classify in this order: normalize and contain the reference inside the selected repository; reject wrong folder shapes; identify a correctly shaped candidate; apply tracked-only exclusion before parsing excluded content; parse and validate node metadata; resolve active status; then search valid archive lineage before returning unknown. Run whole-repository preflight only after this reference-specific pass, preserving existing `preflight-invalid` reporting for graph errors unrelated to the selected reference. A folder under `docs/changes/<name>/` with Markdown but no node-bearing header is `change-front-matter-missing`; a present header rejected by the YAML-subset parser or required-field validation is `change-front-matter-invalid`.

Messages may contain only the normalized change ID, repository-relative path, canonical lifecycle status, and whether existing `gated_on` metadata is present. They must not quote raw front matter, parser fragments, document bodies, raw command input, environment values, subprocess output, secret-like values, or arbitrary `gated_on` text. Hints use the normalized ID and supported grammar. A blocked diagnostic reports `status=blocked` and `gate_present=true|false`, never an invented resume/unblock command; missing gate metadata remains a valid legacy blocked state.

**Δ MODIFIED** — Make `accept`, `begin`, `reconcile mechanical`, and `land` consume the same lifecycle classification result. Remove landing's independent `_locate_source` interpretation while keeping archive destination choice, tracking-mode enforcement, graph preflight, projection, journaling, mutation, recovery, and final verification in `landing.py`. Preserve completed landing idempotency and classify its existing no-op message as `INFO: [change-already-landed]`.

Render a blocking `LifecycleError` as `ERROR: [<stable-code>] <message>` on stderr and the repeated-land diagnostic as `INFO: [change-already-landed] <message>`. Text-mode mechanical reconciliation places the same code/message in its scoped findings and renders its existing `next_command`; `--format json` embeds the same code/message in the schema-1 report's existing `findings` and populates its existing nullable `next_command`. Do not create another JSON envelope or change the schema version. Exit `0` only for success/readiness and repeated-land no-op, `1` for every lifecycle blocker above, and `2` only for argparse or configuration failures.

Document the stable codes, safe fields, dry-run-first hints for proposed and accepted changes, exact `--include-untracked` replay rule, and no-command policy for blocked, invalid, wrong-folder, unknown, and already-landed states. Keep semantic reconciliation in the skill workflow; this change makes no machine claim that prose and implementation agree.

**Δ REMOVED** — Remove the generic `change-not-found: ref is not an active change...` variants and `[LandingError]` rendering for classified lifecycle failures. Remove duplicate reference/status classification from landing and reconciliation callers after they cross the shared lifecycle seam. Do not remove transaction errors such as concurrent modification, partial tracking, destination collision, or journal failure, and do not add acceptance, blocking, resume, or landing transitions.

## Tasks

1. Reconcile the landed `accepted-change-state` and `mechanical-reconciliation` interfaces and move their selected-change lookup behind one pure lifecycle classification interface without changing transition rules or report schema.
2. Implement `LifecycleDiagnostic`, `LifecycleError`, and the ordered taxonomy above, including repository containment, active/archive distinction, tracked-only short-circuiting, total front-matter failure mapping, canonical status handling, and value-free message/hint construction.
3. Replace landing's `_locate_source` interpretation with the shared classifier while retaining transaction-specific planning and completed-landing no-op behavior.
4. Adapt `accept`, `begin`, and both mechanical-reconciliation formats to render the same codes and hints through their existing text/JSON interfaces; preserve the `0`/`1`/`2` exit policy.
5. Add table-driven lifecycle tests for every code, classification precedence, ID and path forms, tracked and excluded-untracked candidates, malformed and missing front matter, archive matches, path traversal/out-of-repository references, and deterministic messages that never include raw content.
6. Add command-level tests proving proposed errors point only to `accept`, accepted errors point only to `begin`, excluded work replays the same command with `--include-untracked`, blocked work exposes status and gate presence without a command, repeated landing is coded success, and all other classified failures are coded blockers without tracebacks.
7. Update the capabilities and README diagnostic contract, including mechanical schema-1 embedding, then run the full test/lint/resolver gates and verify installed and vendored command behavior use the same taxonomy.
8. On land: archive this folder through the transactional command and retain its roadmap lineage.

## Verify

- `uv run pytest -q`, `uv run --group lint ruff check .`, and `uv run doc-contract check --repo-root . --offline --include-untracked` pass after both upstream changes have landed and this change has been reconciled against them.
- One table-driven test exercises all nine codes through the lifecycle interface, including the precedence `wrong folder -> excluded untracked -> front matter -> status -> archive -> unknown` and exact deterministic messages/hints.
- CLI tests assert stderr/stdout, code token, nullable hint, and exit status for `accept`, `begin`, `reconcile mechanical --phase entry`, `reconcile mechanical --phase exit`, and `land`; equivalent ID and repository-relative folder references produce equivalent classifications.
- Text and JSON mechanical reports carry identical lifecycle code/message/next-command facts inside the existing schema-1 interface; JSON remains parseable and contains no extra top-level envelope.
- Malformed headers, raw document prose, raw command input, subprocess output, environment values, and `gated_on` text never appear in diagnostics; blocked output includes only canonical status and `gate_present=true|false`.
- Repeated `land` remains an immutable `0` no-op with `change-already-landed`; all lifecycle blockers return `1`; argparse/configuration failures remain `2`; transaction errors retain their existing typed behavior.
- Invariant spot-check: runtime code remains stdlib-only, repository selection stays explicit and fail-closed, semantic reconciliation remains judgment-heavy skill work, and no lifecycle transition or command is introduced.
