---
id: discovery-lifecycle-hardening
persistence: ephemeral
status: landed
track: remediation
depends_on:
  - transactional-land-command
fingerprints:
  transactional-land-command: f97111f3df934220
files_owned:
  - src/doc_contract/config.py
  - src/doc_contract/resolver.py
  - src/doc_contract/cli.py
  - src/doc_contract/landing.py
  - scripts/dag.py
  - scripts/test_change_dag.py
  - tests/test_cli.py
  - tests/test_landing.py
  - tests/test_resolver.py
  - README.md
  - SKILL.md
  - AGENTS.template.md
  - docs/spec/capabilities.md
  - docs/roadmap.md
landed_at: 2026-07-23
archive_path: docs/changes/archive/2026-07-23-discovery-lifecycle-hardening
---
# Harden discovery and lifecycle diagnostics

Status: Landed · 2026-07-23

**Upstream dependencies:** `transactional-land-command` is landed and provides the explicit
repository/config boundary, resumable landing journal, tracked/untracked archive strategies, and
the final validation seam this change extends. Its reviewed body fingerprint is recorded above.
There are no ADRs or external infrastructure gates; the offline resolver and fixture tests are
available now. The live capability subprocess remains optional and must stay separately reported.
**Dependents:** None currently. This closes Workstream E from `HANDOFF.md`; a later hash-semantics
decision may consume its explicit hash-state and warning-reporting interfaces.
**Files owned:** Resolver/config discovery policy and CLI/landing diagnostics, the legacy `dag`
adapter and its DAG tripwire fixtures, focused package tests (including a new resolver test module),
and the README, skill, operating-contract template, capability reference, and roadmap that describe
the supported lifecycle. No ADR is amended on land and no application source is in scope.

## Why

The resolver still lets a configured root disappear from the graph when its file is missing
(`src/doc_contract/resolver.py:305`), unless a separate allowlist happens to mark it required. That
makes deletion look like an intentional optional node and weakens the repository boundary. Its
persistence classifier also searches every absolute path component (`src/doc_contract/resolver.py:288`),
so a checkout or parent directory named `adr` or `archive` can change a document's policy. Discovery
has no explicit tracked/untracked boundary, while empty or `PENDING` hashes are not actionable
states. Finally, check and landing output does not distinguish warnings already present at preflight
from warnings introduced by the proposed/current change, so reviewers cannot tell baseline drift
from new regressions.

## What changes

**Δ ADDED** — Add a tracked/declared discovery mode as the default, an explicit
`--include-untracked` path for provisional work, and a deterministic preview of newly discovered
nodes before `update` or landing mutates the roadmap. Add declarative required/optional root-node
semantics, structured hash-state findings for empty and `PENDING` values, and a baseline-versus-new
warning report that can be reused by `check` and the landing transaction.

**Δ MODIFIED** — Make discovery classify paths relative to the selected repository with exact
`docs/adr`, `docs/archive`, and `docs/changes/archive` policies; never infer policy from arbitrary
ancestor names. Make missing configured roots fail unless explicitly optional, while reporting
optional omissions and untracked nodes explicitly. Thread the discovery flag and warning delta
through the packaged CLI, landing preflight/final validation, and legacy adapter. Extend focused
resolver, CLI, landing, and DAG-tripwire tests, then update the README, skill, operating-contract
template, capability reference, and roadmap with the new lifecycle contract.

**Δ REMOVED** — Remove silent omission of configured roots, broad path-component classification,
and the treatment of empty/`PENDING` hashes as ordinary absent or opaque values. Do not weaken frozen
ADR/reference `self_hash` protection, transactional hash guards, or the existing value-free
diagnostics rule.

## Tasks

1. [x] Define the manifest/API shape for required roots by default, explicitly optional roots, discovery
   mode, and structured hash states; reject ambiguous configuration with deterministic findings.
2. [x] Implement repository-relative path classification and Git-aware tracked/declared discovery;
   thread `--include-untracked` through `check`, `update`, and landing preflight, previewing new
   nodes before any roadmap mutation.
3. [x] Make empty and `PENDING` edge/self hashes produce actionable ERROR or WARN findings with stable
   remediation text, while preserving canonical fingerprint behavior and frozen-document checks.
4. [x] Capture the preflight warning baseline and report only newly introduced warnings separately from
   tolerated baseline warnings in `check` and the transactional landing outcome; keep offline/live
   capability status distinct.
5. [x] Add fixture coverage for tracked, declared, untracked, optional, and missing roots; misleading
   parent-directory names; empty/`PENDING` hashes; baseline/new warning deltas; and update/landing
   immutability and idempotency. Keep the compatibility DAG tripwire green.
6. [x] Update the documented command/configuration contract and capability reference, then run the
   package tests, lint, offline resolver, and capability tripwire.
7. [x] On land: record the final discovery/hash-reporting decisions in durable docs or project memory,
   archive this folder through `doc-contract land`, and regenerate the roadmap DAG.

## Verify

- `uv run pytest -q` and `uv run ruff check .` pass, including the DAG and capability tripwires.
- Default discovery includes only tracked/declared managed files; `--include-untracked` reports
  provisional additions before `update` or landing writes anything.
- Missing configured roots are ERROR unless explicitly optional; optional omissions and untracked
  nodes are visible in deterministic diagnostics.
- Repository-relative classification is invariant under checkout/parent directory names containing
  `adr` or `archive`; exact frozen paths remain protected.
- Empty and `PENDING` hashes are actionable findings, and warning output labels baseline findings
  separately from warnings introduced by the current change.
- Invariant spot-check: the transactional land command remains resumable and idempotent, explicit
  repository selection stays fail-closed, frozen-document tamper detection remains active, and no
  credential values enter reports or generated docs.
