---
id: unified-offline-live-verification
persistence: ephemeral
status: proposed
track: architecture
depends_on:
  - edge-fingerprint-policy
fingerprints:
  edge-fingerprint-policy: d905fcb4fb5d4745
files_owned:
  - src/doc_contract/verification.py
  - src/doc_contract/cli.py
  - src/doc_contract/landing.py
  - src/doc_contract/resolver.py
  - src/doc_contract/sync.py
  - tests/test_verification.py
  - tests/test_cli.py
  - tests/test_landing.py
  - tests/test_resolver.py
  - docs/spec/capabilities.md
  - README.md
  - docs/roadmap.md
---
# Unify offline and live verification

Status: Proposed (not accepted) · Proposed 2026-07-24

**Upstream dependencies:** `edge-fingerprint-policy` is landed and supplies the current
baseline-versus-new warning model and advisory fingerprint behavior that composed verification must
preserve. Transitively, it includes the packaged check command, transactional landing engine, and
value-free subprocess guardrails whose duplicated verification paths are being consolidated. Its
reviewed body fingerprint is recorded above. No ADR governs this internal boundary, and no external
infrastructure is gated: subprocess behavior is fully testable with local commands and doubles.
**Dependents:** None. The roadmap and active change set contain no work that waits on this seam.
`landed-graph-transition-ownership` is an independent candidate, not a prerequisite or dependent.
**Files owned:** One new internal verification module; the CLI and landing callers; the resolver's
current warning-delta types; vendored package closure; focused unit and caller regressions; and the
consumer behavior reference, README, and roadmap. `landed-graph-transition-ownership` also forecasts
changes to `resolver.py`, `landing.py`, `tests/test_resolver.py`, `tests/test_landing.py`, and the
roadmap. The overlap is soft because it owns graph projection while this change owns capability
execution and verification composition; whoever lands second must rebase and reconcile the shared
imports/call site. If both become in-progress concurrently, treat the shared `landing.py` call site
as a coordination boundary rather than adding a false DAG edge.

## Why

`check` and `land` currently implement the configured capability subprocess separately in
`cli._capability_status` and `landing._capability`. Both choose modes, suppress all subprocess I/O,
apply the same timeout, map execution facts into status strings and findings, and combine those
findings with resolver output. Their behavior already differs: subprocess exceptions and nonzero
exits produce different messages, only the CLI implements the required-plus-offline case, and each
caller composes warnings and errors itself.

That duplication sits on a security-sensitive boundary. A future mode, timeout, redaction, or
finding change must be made identically in the read-only check and post-mutation landing path, while
callers should only decide whether live verification is requested and how to render the structured
result. The stronger boundary is one deep in-process verification module with subprocess as its only
concrete adapter, not parallel helpers or a prematurely public adapter hierarchy.

## What changes

**Δ ADDED** — Add `src/doc_contract/verification.py` with immutable policy/outcome types and one
operation that composes an already-produced offline `Resolution`, the configured capability mode,
whether live execution was requested, and the caller's warning baseline. The outcome exposes
offline/live status, combined value-free findings, errors, and the baseline/introduced/resolved
warning delta. Keep one private subprocess adapter with null stdin/stdout/stderr, repository-root
cwd, the existing timeout, and no command or captured output in findings.

Add direct verification tests for the complete `skip|optional|required` by live-requested matrix,
success, nonzero exit, unavailable process, timeout, output suppression, warning composition, and
stable status/finding vocabulary. Add cross-caller regressions proving `check` and final landing map
the same execution fact to the same structured result.

**Δ MODIFIED** — Make `cli._check` resolve once, pass the result to the verification operation,
and restrict the CLI to discovery preview and rendering. Make `execute_landing` pass its final
resolution and preflight warning baseline to the same operation after all planned mutations are
present; preserve journal retention on any final offline or live error. Move `WarningDelta` and
`warning_delta` from the resolver into verification so warning composition has one owner, while
leaving graph discovery and validation in the resolver.

Add the new module to `sync.PACKAGE_FILES` and extend the clean-repository vendored smoke test so an
air-gapped launcher exercises the same verification path. Update the capability reference and README
to describe one mode/status matrix for `check` and `land`. Preserve command grammar, configuration
schema, summary vocabulary, default timeout, subprocess suppression, dry-run behavior, and the rule
that `land --dry-run` performs no live check.

**Δ REMOVED** — Remove `cli._capability_status`, `landing._capability`, direct capability
subprocess execution from those modules, and resolver ownership of warning-delta composition. Add no
public plugin/adapter API and do not move Git, filesystem, journal, roadmap, or graph-validation work
into verification.

## Tasks

1. Define the immutable verification policy and outcome boundary in
   `src/doc_contract/verification.py`, accepting resolved offline facts rather than importing target
   project modules or re-resolving the repository.
2. Implement the full capability mode/live-request matrix and one private redacted subprocess path;
   normalize success, skip, nonzero, unavailable, and timeout results into stable value-free status
   and finding records.
3. Move warning-delta types/composition from `resolver.py` into verification and have the operation
   return combined findings, errors, and warning deltas without mutating its input resolution or
   baseline.
4. Refactor `check` and final landing validation to consume the operation, delete both duplicated
   capability helpers, and keep output formatting, mutation, failure, and journal policy in their
   existing callers.
5. Add direct matrix/redaction/composition tests plus CLI/landing parity regressions, including
   required offline skip, failed final live verification, retained journals, and unchanged dry-run
   behavior.
6. Add `verification.py` to the vendored runtime closure and extend packaged-to-vendored smoke
   coverage to prove offline and local live checks work from an unrelated cwd.
7. Update `docs/spec/capabilities.md` and `README.md` with the shared observable verification rules;
   run the capability coverage tripwire and confirm the CLI command set remains unchanged.
8. On land: archive this folder through the transactional command and retain the roadmap lineage.

## Verify

- `uv run pytest -q`, `uv run ruff check .`, and the offline resolver gate pass, including the real
  document-DAG and capability coverage tripwires.
- Every capability mode/live-request combination has one pinned result; identical subprocess facts
  yield identical live status and finding codes through `check` and `land`.
- Capability stdin, stdout, and stderr remain disconnected, and unavailable/timeout/nonzero findings
  contain no command arguments, captured output, environment values, or exception text beyond a
  stable type/status classification.
- Check retains its current offline/live summary and exit semantics. Landing performs verification
  only after mutation, retains its journal on either offline or live failure, deletes it on success,
  and never executes capability work during dry-run or an already-landed no-op.
- A synced clean repository runs both offline and local live verification through the vendored
  launcher from an unrelated cwd, with `verification.py` present and pinned in the manifest.
- Invariant spot-check: runtime code remains stdlib-only; repository selection stays explicit and
  fail-closed; target project modules are never imported; graph resolution remains read-only;
  landing transaction boundaries are unchanged; and subprocess output cannot enter diagnostics.
