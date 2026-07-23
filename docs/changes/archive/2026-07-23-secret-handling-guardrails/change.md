---
id: secret-handling-guardrails
persistence: ephemeral
status: landed
track: remediation
self_hash: 2f33b0e10ac58019
files_owned:
  - scripts/secret_scan.py
  - scripts/test_secret_scan.py
  - scripts/dag.py
  - SKILL.md
  - docs/roadmap.md
---

# Secret-handling guardrails

Status: Landed · 2026-07-23

**Upstream dependencies:** None. The resolver remains stdlib-only; the offline scanner and its
fixtures are available immediately. This change precedes the global CLI/config boundary and should
establish the redaction contract before that packaging work consumes the diagnostics.
**Dependents:** `global-cwd-independent-cli` (future Workstream B, once proposed); its CLI and
generated-report paths must preserve this change's scan and redaction guarantees.
**Files owned:** `scripts/secret_scan.py`, `scripts/test_secret_scan.py`, `scripts/dag.py`,
`SKILL.md`, and `docs/roadmap.md`. The historical transcript is explicitly out of scope and must
not be copied, rewritten, or redistributed.

## Why

The package currently has no guard against credentials entering source, handoffs, change folders,
fixtures, diagnostics, or generated documents. A historical transcript exposed a credential in
captured command output; although that instance was explicitly permitted, the reusable rule is
missing from the implementation. Without a scanner and redaction convention, future diagnostics
can leak values while appearing to be ordinary resolver output.

## What changes

**Δ ADDED** — Add a stdlib-only scanner module and focused tests. The scanner covers tracked/package
files and generated artifacts, detects common API-key/token assignments and known secret environment
variable names, and returns structured findings without retaining secret values. Add fixtures proving
`.env` content and credential-like values do not appear in generated reports.

**Δ MODIFIED** — Integrate the scanner into the resolver/check path and make diagnostics print only
the variable name plus redacted presence/length metadata. Document the rule and the supported scan
boundary in `SKILL.md`; add the change to the remediation roadmap.

**Δ REMOVED** — None. Do not reproduce or redistribute the historical credential.

## Tasks

1. [x] Define the scanner's pattern set, path exclusions, finding shape, and redaction rules using
   only stdlib APIs.
2. [x] Implement `scripts/secret_scan.py` with deterministic findings and a safe diagnostic
   formatter; never include matched values in returned or printed data.
3. [x] Add fixture-based tests for API-key/token assignments, known secret environment names,
   `.env` content, false-positive-safe ordinary configuration, and generated-report exclusion of
   values.
4. [x] Wire secret findings into the resolver/check exit status without changing existing DAG
   finding codes or the stdlib-only dependency boundary.
5. [x] Document the convention in `SKILL.md`, including how diagnostics report presence/length and
   how repositories may add secret environment names without storing values.
6. [x] Run the focused scanner tests and the existing resolver tripwires; confirm no
   credential-like value appears in test output or generated artifacts.
7. [x] Update the roadmap status, capture pattern-policy decisions in durable docs, and archive
   this folder per the contract.

## Verify

- `python -m pytest` (or the repository's configured focused test command) passes for
  `scripts/test_secret_scan.py` and the existing `scripts/test_*.py` tripwires.
- A temporary fixture containing `.env` values and credential-like assignments produces findings
  that identify only names and redacted length/presence; serialized reports contain no values.
- Ordinary non-secret configuration remains clean, and scan exclusions cover VCS metadata, caches,
  bytecode, and binary files without weakening package/generated-artifact coverage.
- Invariant spot-check: the resolver remains stdlib-only, existing DAG finding semantics are
  unchanged, and a secret finding cannot be downgraded into a successful check.
