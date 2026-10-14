---
id: actionable-preflight-diagnostics
persistence: ephemeral
status: proposed
track: remediation
depends_on:
  - mechanical-reconciliation
  - actionable-lifecycle-diagnostics
files_owned:
  - docs/changes/actionable-preflight-diagnostics/change.md
  - src/doc_contract/reconciliation.py
  - src/doc_contract/cli.py
  - tests/test_reconciliation.py
  - tests/test_cli.py
  - docs/spec/capabilities.md
  - docs/roadmap.md
---
# Make `preflight-invalid` diagnostics name the offending node and fix

Status: Proposed (not accepted) · Proposed 2026-10-14

**Upstream dependencies:** `mechanical-reconciliation` is landed and owns the read-only
`ReconciliationReport`, `ScopedFinding`, `render_text`, and `reconcile_mechanical` surface this
change modifies; its `subjects` tuple already carries the offending node ids that the text renderer
drops. `actionable-lifecycle-diagnostics` is landed and establishes the stable value-free lifecycle
error taxonomy for acceptance, start, mechanical reconciliation, and landing; this change extends
the same ergonomics to the resolver `preflight-invalid` findings that currently render as a generic
code with no node, path, or fix. Both inputs are available. No ADR, external service, live input, or
third-party package gates implementation.

**Dependents:** None. This is an additive, rendering-only correction. It does not change resolver
semantics, finding codes, the JSON schema of `reconciliation`, the private journal, or any
transaction boundary, so no in-repository change depends on it. Soft overlaps with two active
proposals are recorded under **Files owned** and impose no ordering.

**Files owned:** `reconciliation.py` for `render_text` (print `subjects`, stop collapsing
repository-scope warnings), `_synthetic` (stop duplicating the `preflight-invalid` code prefix), and
the `reconcile_mechanical` `OSError`/`ValueError` handler (surface the real parse error instead of
the generic `repository preflight failed`). `cli.py` for the `_land` and `_supersede` transaction
catch blocks (print `exc.findings` and use the stable `exc.code` instead of relabelling a
`LandingError` as `[TransactionError]`). Focused regressions in `tests/test_reconciliation.py` and
`tests/test_cli.py`; the consumer-surface prose in `docs/spec/capabilities.md`; this proposal and
`docs/roadmap.md` lineage.

**Soft overlaps (no ordering, rebase whoever lands second):** `review-bound-acceptance-plan`
(proposed) declares `reconciliation.py`, `cli.py`, `test_reconciliation.py`, `test_cli.py`,
`docs/spec/capabilities.md`, and `docs/roadmap.md`. It touches `reconciliation.py` for the shared
content-free mutation projection and `cli.py` for `accept --format json`/`--expect-plan-id`, and it
explicitly does not broaden `land`. This change touches the text renderer, the synthetic
`preflight-invalid` line, the `OSError`/`ValueError` reconciliation branch, and the `land`/`supersede`
error catch — different regions and different symbols, so neither change edits the other's code.
`runtime-source-provenance` (proposed) declares `cli.py`, `test_cli.py`, `docs/spec/capabilities.md`,
and `docs/roadmap.md` for an additive `info` verb; again a different region. Both are soft and
additive; whichever lands second preserves both contracts. `retirement-guards-and-roadmap-entry-locator`
(proposed) deliberately does **not** claim `cli.py` or `tests/test_cli.py`: it adds the multi-node
supersede refusal and a clearer `change.md`-missing message, both of which this change's shared
failure renderer surfaces, and it overlaps only the additive `docs/spec/capabilities.md` prose and the
`docs/roadmap.md` lineage regions. **Sequencing:** this change lands first; nothing here waits on the
guards item, and that item reconciles its shared `capabilities.md` sentences onto this change's
landed rendering rather than the reverse.

## Why

The checker already computes everything the operator needs to fix a `preflight-invalid` failure, but
the rendering layer throws it away in text mode and in the `land`/`supersede` error paths. This is a
fix in this repository (the `doc-contracts` checkout at `/var/home/kai/Documents/Projects/doc-contracts`),
not in Pi upstream, and it is the one of the nine harness-friction candidates the operator's own
tooling owns. The probe observed `bash :: ERROR: [preflight-invalid] …` as a repeated friction
signature (16 + 8 sessions across 8 + 7 projects); per the probe's own verdict, those are
loosely-declared observed frequencies, not a measured ranking, and they are cited here only as the
trigger for the work, not as its priority.

Three concrete paths today drop structured evidence that is already present in memory:

1. `doc-contract reconcile mechanical <change> --phase exit --format text` (the AGENTS.md protocol
   path). `ReconciliationReport.render_text()` prints `{level} {scope}: [{code}] {message}` and never
   prints `ScopedFinding.subjects`. On a landing-preflight failure, `reconcile_mechanical`'s
   `except LandingError` branch appends the real `exc.findings` **plus** a synthetic
   `_synthetic("ERROR", exc.code, str(exc), change_id)`. Because `LandingError.__init__` parses
   `code` from the message prefix and `str(exc)` is the full message, that line renders as
   `ERROR change: [preflight-invalid] preflight-invalid: planned repository state fails validation`
   — the code appears twice, no node id, no path, no fix. `subjects` is dropped.
2. `doc-contract land <change>` / `doc-contract supersede <change>`. `cli._land` / `cli._supersede`
   catch `TransactionError` and do
   `error_name = "TransactionError" if type(exc) is LandingError else type(exc).__name__;
   print(f"ERROR: [{error_name}] {exc}")`. A `LandingError` with stable code `preflight-invalid` is
   relabelled `[TransactionError]`, and `exc.findings` — the actual resolver errors with node ids in
   `subjects` — is never printed. Maximum information available, minimum shown.
3. `doc-contract reconcile mechanical …` when `resolve()` itself raises `OSError`/`ValueError` (a
   malformed YAML front-matter block, a duplicate node id, a bad key line).
   `reconcile_mechanical` catches `(OSError, ValueError)` and emits
   `_synthetic("ERROR", "preflight-invalid", "repository preflight failed", change_id)`, swallowing
   the real exception message. A concrete parse error becomes a generic line with no detail.

The four `preflight-invalid` emission sites (verified by reading the source) are
`landing.py` (`repository has resolver errors`, `dependency graph contains a cycle`, and
`planned repository state fails validation`, each already carrying `findings=…`) and
`reconciliation.py:327` (`preflight-invalid` / `repository preflight failed`, with no findings). The
`landing.py` sites already attach findings correctly; the defect is downstream in the renderer and
the two CLI catch blocks, not in the planner.

Prior art for actionable graph/lint diagnostics (cited, not adopted — this is our own renderer, no
external tool to vendor):

- **Bazel** cycle errors name the node, the location, and the full cycle path:
  `ERROR: /path/BUILD:11:1: java_library rule //B: cycle in dependency graph: //A .-> //B | //C | //D '-- //B`
  (https://github.com/bazelbuild/bazel/issues/5976 · https://github.com/bazelbuild/bazel/pull/12272).
- **ESLint** separates a stable `ruleId` + `messageId` from prose, attaches `file:line:col`, and
  marks rules `fixable`/`hasSuggestions` so `--fix` can apply a minimal fix
  (https://eslint.org/docs/latest/extend/custom-rules).
- **npm ERESOLVE** names the resolver, the found version, the filesystem location, and the dependency
  chain (`While resolving: X … Found: Y … Could not resolve dependency: peer … from …`)
  (https://stackoverflow.com/questions/64573177/unable-to-resolve-dependency-tree-error-when-installing-npm-packages — secondary, illustrative).

The pattern to copy is "name the offending node and the minimal fix", not a new dependency.

## What changes

**Δ ADDED** — Focused regressions proving the text renderer names `subjects`, repository-scope
warnings are no longer silently collapsed to a count, the synthetic `preflight-invalid` line no
longer duplicates its code prefix, the `reconcile_mechanical` `OSError`/`ValueError` branch surfaces
the real exception message, and `land`/`supersede` print `exc.findings` with the stable `exc.code`
instead of `[TransactionError]`.

**Δ MODIFIED** — `reconciliation.py`:
- `render_text()` appends `subjects` to the rendered finding line (e.g. ` … (node: fix-b)` or a
  comma-separated `subjects:` suffix) and prints repository-scope warnings individually rather than
  collapsing them to `repository warnings: N unrelated warning(s)`.
- `_synthetic` / the `except LandingError` branch stops producing a line whose message repeats the
  code as a prefix; when `exc.findings` is non-empty the real findings carry the detail and no
  redundant synthetic line is emitted, and when it is empty the synthetic message is rendered from
  `exc.code` without duplicating it.
- `reconcile_mechanical`'s `except (OSError, ValueError)` branch preserves and surfaces the real
  exception message (still value-free, still under the `preflight-invalid` code) instead of replacing
  it with `repository preflight failed`.

`cli.py`: replace the two identical `TransactionError` catch blocks in `_land` and `_supersede`
with one shared failure-print helper used by both call sites. It prints the stable code — `exc.code`
for a `LandingError`, otherwise the existing exception type name — followed by each `exc.findings`
entry with its `code`, `message`, and `subjects`. This keeps the fix in one place instead of two
copies that can drift, and it stays rendering-only: `LifecycleError` handling and all success-path
output are unchanged, and the helper prints no document content or hashes.

`docs/spec/capabilities.md`: update the `reconcile`, `land`, and `supersede` surfaces to state that
text findings name their offending node ids and that landing/supersede preflight failures print the
resolver findings rather than a bare code. `docs/roadmap.md`: this line and the regenerated DAG.

**Δ REMOVED** — none. No finding code, resolver semantics, JSON schema, journal shape, or
transaction boundary is removed or renamed.

## Tasks

1. Add regression tests in `tests/test_reconciliation.py` covering: `render_text()` includes
   `subjects` for a scoped finding; repository-scope warnings are printed individually, not collapsed;
   the synthetic `preflight-invalid` finding no longer renders the code twice; and a monkeypatched
   `resolve` that raises `ValueError` yields a finding whose message preserves the real error text.
2. Add regression tests in `tests/test_cli.py` covering: `land` and `supersede` print
   `exc.findings` with their subjects and use the stable `exc.code` for a `LandingError`, while a
   non-landing `TransactionError` still reports its own type name.
3. Implement the `reconciliation.py` renderer and error-branch changes from **What changes**; keep
   the JSON `as_dict()` output (already complete) byte-for-byte unchanged.
4. Implement the shared `cli.py` failure-print helper and route both `_land` and `_supersede`
   through it, so the `[TransactionError]` relabel and the dropped findings are fixed in one place;
   keep `LifecycleError` handling and all success-path output unchanged.
5. Update `docs/spec/capabilities.md` prose for `reconcile`, `land`, and `supersede` to reflect the
   named-node diagnostics. `scripts/test_capabilities_coverage.py` only asserts the command headings
   exist, so this is a prose-accuracy update rather than a tripwire gate.
6. `docs/roadmap.md`: add the Remediation line, then regenerate the DAG with
   `doc-contract update --repo-root .`.
7. On land: archive this folder per the contract and confirm the declared new test edits clear with
   no `owned-file-missing` baseline delta (all owned files already exist).

## Verify

- `uv run --group test pytest -q -p no:cacheprovider` green, including the new reconciliation and
  CLI regressions and `scripts/test_capabilities_coverage.py`.
- `uv run --group lint ruff check --no-cache .` green.
- `doc-contract check --repo-root . --offline --include-untracked` returns 0 errors; the only warning
  delta is this proposal's own roadmap/finding baseline, reported as baseline rather than new.
- A malformed-front-matter fixture exercised through
  `doc-contract reconcile mechanical <change> --phase exit --format text` now shows the real parse
  error plus the offending node id, not `preflight-invalid: repository preflight failed`.
- A preflight-blocked `doc-contract land <change> --dry-run` now prints the resolver findings with
  node ids and the stable `preflight-invalid` code, not `ERROR: [TransactionError]
  preflight-invalid: planned repository state fails validation`.
- Invariant spot-checks: the runtime stays stdlib-only and cwd-independent; JSON reconciliation
  output is unchanged; no finding code or transaction boundary is renamed; diagnostics remain
  value-free (node ids, paths, and names only, never document bodies or hashes); and the
  front-matter-versus-operation-manifest distinction owned by `review-bound-acceptance-plan` is
  untouched.
