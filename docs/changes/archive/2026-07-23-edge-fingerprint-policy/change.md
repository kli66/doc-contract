---
id: edge-fingerprint-policy
persistence: ephemeral
status: landed
track: remediation
depends_on:
  - discovery-lifecycle-hardening
fingerprints:
  discovery-lifecycle-hardening: 71ee6ccdbfcb35b4
files_owned:
  - .doc-contract.toml
  - src/doc_contract/config.py
  - src/doc_contract/resolver.py
  - scripts/config.py
  - scripts/dag.py
  - scripts/test_change_dag.py
  - tests/test_cli.py
  - tests/test_landing.py
  - tests/test_resolver.py
  - AGENTS.template.md
  - DESIGN-RATIONALE.md
  - README.md
  - SKILL.md
  - docs/spec/capabilities.md
  - docs/roadmap.md
landed_at: 2026-07-23
archive_path: docs/changes/archive/2026-07-23-edge-fingerprint-policy
---
# Make edge fingerprints advisory

Status: Landed · 2026-07-23

**Upstream dependencies:** `discovery-lifecycle-hardening` is landed and supplies the structured
hash states, baseline-versus-new warning reporting, repository-relative archive policy, and
tracked/declared discovery boundary this change reclassifies. Its reviewed body fingerprint is
recorded above. `transactional-land-command` is inherited through that dependency and already
preserves archived `persistence: ephemeral` lineage while retaining strict frozen-document
protection. No ADR exists for this workflow surface; `DESIGN-RATIONALE.md` is the durable decision
record and currently requires frozen `self_hash` tamper detection. No external input is gated.
**Dependents:** None currently. This closes Workstream D in `HANDOFF.md`; no active change folder or
roadmap item declares a dependency on it, so no back-link is required.
**Files owned:** The manifest/settings policy seam, packaged resolver and legacy adapter, focused
resolver/CLI/landing and compatibility-tripwire tests, the portable operating contract and package
documentation, the workflow design rationale, capability reference, and roadmap. There are no
other active change folders, so no file or symbol ownership overlaps exist.

## Why

The resolver currently makes every active `depends_on` edge carry a fingerprint: an absent, empty,
`PENDING`, or malformed value is an error, while a stale valid value is a warning. This makes review
currency part of the mandatory green bar even though the structural dependency edge already
provides scheduling, dangling-edge, cycle, ownership, and roadmap-linkage enforcement. At the
current team size, routine edits to an upstream document create re-review and re-stamp work across
active dependents without changing their execution order.

Frozen-document `self_hash` solves a different and still valuable problem: it detects an agent
silently editing an append-only ADR or frozen reference. That protection must remain strict and
must not be coupled to any relaxation of edge review provenance. The policy boundary also needs to
state what canonicalization does with prose reflow and Markdown formatter rewrites instead of
leaving semantically similar edits as accidental behavior.

## What changes

**Δ ADDED** — Add a declarative edge-fingerprint policy with `advisory` as the default and
`required` as an explicit repository opt-in. Under `advisory`, a missing edge fingerprint is
accepted; a present empty, `PENDING`, malformed, or stale fingerprint is reported as a warning so
review provenance remains visible without failing the offline gate. Under `required`, retain the
current error behavior for absent or invalid active-edge hashes and the warning for stale hashes.

Add canonicalization tests for wrap-only prose edits and Markdown formatter-only rewrites. Record
the conservative policy explicitly: front matter, line-ending differences, per-line trailing
whitespace, and boundary blank lines are normalized; prose reflow and Markdown syntax rewrites are
not normalized and therefore change the fingerprint. This avoids embedding a partial Markdown
semantic parser in the stdlib-only core and keeps frozen-document mutations reviewable.

**Δ MODIFIED** — Thread the policy through `.doc-contract.toml`, `Settings`, the resolver, and the
legacy adapter. Keep `stamp` and transactional `land` able to record or refresh edge fingerprints
as useful review metadata in advisory mode; optionality changes enforcement, not the file format or
the ability to capture provenance. Update diagnostics and warning-delta behavior so edge-hash
warnings remain distinguishable from strict frozen-document failures.

Amend `DESIGN-RATIONALE.md`, `AGENTS.template.md`, `README.md`, `SKILL.md`, and the capability
reference to separate the mandatory structural change DAG from advisory review fingerprints and to
document repository opt-in to strict enforcement. Preserve `self_hash` mismatch and invalid-state
errors for frozen ADRs and frozen references. Preserve the upstream rule that archived ephemeral
change records do not become frozen merely because they live under `docs/changes/archive/`.

**Δ REMOVED** — Remove missing edge fingerprints from the default mandatory green-bar path and
remove wording that describes fingerprint-by-default as universal. Do not remove `depends_on`, DAG
validation, fingerprint storage/stamping, stale-link diagnostics, frozen `self_hash`, or the
transactional content hashes used internally by `land`.

## Tasks

1. [x] Add and validate an `advisory|required` edge-fingerprint setting in the package manifest loader
   and legacy adapter, defaulting existing unspecified repositories to `advisory` without changing
   the manifest schema version.
2. [x] Refactor edge-hash findings so advisory mode permits absent values and downgrades explicit
   empty, `PENDING`, or malformed values to warnings, while required mode retains the current
   errors; keep stale valid values visible in both modes.
3. [x] Keep frozen-document hash-state and mismatch findings strict and independent of the edge policy;
   verify ADRs and `docs/archive/` remain protected while archived ephemeral changes remain
   ephemeral.
4. [x] Add focused canonicalization tests for CRLF, trailing whitespace, boundary blank lines,
   wrap-only prose reflow, and Markdown formatter-only syntax changes, pinning the documented
   normalization/significance boundary.
5. [x] Add config, resolver, CLI, compatibility-adapter, and landing regressions for advisory default,
   required opt-in, warning deltas, optional stamping, dependent refresh during landing, and
   unchanged transactional hash guards.
6. [x] Update the operating contract, workflow rationale, package/skill docs, capability reference, and
   example manifest so dependency topology remains mandatory while edge review hashes are advisory
   unless strict mode is selected.
7. [x] On land: run the transactional command, preserve this record as ephemeral lineage, regenerate
   the roadmap DAG, and confirm a second landing invocation is a no-op.

## Verify

- `uv run pytest -q`, `uv run ruff check .`, and the offline resolver pass in the repository's
  default advisory mode; the legacy tripwire exercises the same policy boundary.
- An active dependency with no fingerprint passes in advisory mode and fails with
  `missing-fingerprint` in required mode. Explicit empty, `PENDING`, malformed, and stale values are
  deterministic warnings in advisory mode, while required mode retains the existing strict errors
  for invalid states.
- `stamp` can add or refresh advisory fingerprints, and `land` can refresh active dependents,
  without making those hashes prerequisites for an otherwise valid check.
- Line-ending, trailing-whitespace, front-matter, and boundary-blank-line-only edits preserve the
  canonical hash. Wrap-only prose changes and Markdown formatter rewrites change it by policy.
- A formatter-only edit to a stamped frozen ADR/reference therefore triggers
  `self-hash-mismatch` until intentionally reviewed and re-stamped; edge drift remains advisory by
  default.
- Invariant spot-check: structural DAG errors still fail, runtime code remains stdlib-only,
  archived ephemeral changes remain ephemeral, frozen-document tampering remains detected, and
  transactional landing content guards are unchanged.
