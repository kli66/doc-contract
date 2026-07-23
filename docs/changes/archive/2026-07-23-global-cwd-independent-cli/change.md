---
id: global-cwd-independent-cli
persistence: ephemeral
status: landed
track: remediation
depends_on:
  - secret-handling-guardrails
fingerprints:
  secret-handling-guardrails: 2f33b0e10ac58019
files_owned:
  - src/doc_contract/__init__.py
  - src/doc_contract/cli.py
  - src/doc_contract/config.py
  - src/doc_contract/resolver.py
  - src/doc_contract/secret_scan.py
  - scripts/dag.py
  - scripts/config.py
  - scripts/secret_scan.py
  - scripts/test_change_dag.py
  - scripts/test_capabilities_coverage.py
  - scripts/test_secret_scan.py
  - tests/test_cli.py
  - docs/spec/capabilities.md
  - pyproject.toml
  - README.md
  - SKILL.md
  - docs/roadmap.md
self_hash: c2b091a2a80affd8
---
# Package the resolver behind an explicit, fail-closed CLI

Status: Landed · 2026-07-23

**Upstream dependencies:** `secret-handling-guardrails` is landed and its value-free diagnostics
contract is available; the prerequisite is recorded on the remediation roadmap. No ADRs or external
infrastructure gate this change. The offline stdlib resolver path is unblocked now; project-specific
capability checks remain explicitly optional and may require the target repository's environment.
**Dependents:** The future transactional `land`/archive/stamping change (Workstream C) depends on
the packaged command and should back-link this change when it is proposed. Discovery/lifecycle
hardening (Workstream E) also consumes the explicit root/config boundary.
**Files owned:** The new `src/doc_contract/` package and CLI tests; compatibility entry points and
tripwires under `scripts/`; package metadata and user-facing `README.md`/`SKILL.md`; the CLI
capability reference and roadmap. No application source outside this resolver package is in scope.

## Why

The resolver core is stdlib-only, but the documented global invocation is not safe or portable. It
derives `REPO_ROOT` from the installed module, imports a flat `config`, and relies on `PYTHONPATH`
and a project-local environment. A live run from `/tmp` returned `0 errors, 0 warnings, 0 nodes`,
while the project-local copy resolved 61 nodes and reported archive warnings. That false green can
silently validate the wrong repository. Packaging the engine under `doc_contract` and requiring an
explicit target boundary makes the command usable from any cwd and makes an invalid target fail
loudly.

## What changes

**Δ ADDED** — Add a stdlib-only `doc_contract` package with an explicit CLI exposing
`check`, `update`, and `stamp`, each accepting `--repo-root` and `--config`; add a declarative
`.doc-contract.toml`/config loader, optional plugin or subprocess capability boundary, a version/pin
manifest, and an update/sync path for vendored or air-gapped repositories. Add CLI smoke tests from
a non-repository cwd, including wrong-root and zero-node cases, plus the capability reference and
coverage wiring.

**Δ MODIFIED** — Move the resolver and secret-scan imports behind the package boundary while keeping
the existing script entry points as compatibility shims. Make git-root discovery a fallback only;
reject missing roots, missing roadmaps, required-root omissions, and zero discovered nodes with a
`repo-root-mismatch` error. Separate stdlib DAG checks from optional project-environment checks and
document installation, invocation, and synchronization without requiring `PYTHONPATH` or `~/.claude`.

**Δ REMOVED** — Remove the implicit flat-`config`/cwd-dependent invocation from the supported path;
do not remove compatibility shims until their replacement is verified.

## Tasks

1. [x] Define the package layout, console entry point, settings object, manifest format, and precedence
   rules for `--repo-root`, `--config`, git-root fallback, and optional capability subprocesses.
2. [x] Extract the invariant resolver and secret scanner into `doc_contract` without adding third-party
   dependencies; retain thin script wrappers for existing vendored installs.
3. [x] Implement `check`, `update`, and `stamp` with deterministic, value-free diagnostics and explicit
   nonzero failures for root mismatch, missing roadmap, missing required roots, and zero nodes.
4. [x] Add the version/pin manifest plus an idempotent update/sync command for vendored and air-gapped
   repositories; ensure the global command never assumes a `~/.claude` checkout.
5. [x] Add non-repo-cwd smoke tests, malformed/missing-config tests, optional-capability skip tests,
   and regression coverage for the existing DAG and secret-scan tripwires.
6. [x] Document the package install and invocation contract in `README.md` and `SKILL.md`; enumerate
   the CLI in `docs/spec/capabilities.md` and wire its coverage check.
7. [x] Regenerate the roadmap DAG, run the stdlib resolver and focused test gates, and capture any
   boundary decisions in durable docs before archiving this change.

## Verify

- From `/tmp`, the installed command resolves an explicit repository root, while an absent,
  mismatched, or zero-node root exits nonzero with `repo-root-mismatch` rather than a false green.
- `check`, `update`, and `stamp` run with stdlib Python alone; optional project capability checks
  report `offline verified`, `live skipped`, or `live passed` distinctly and never silently import
  the target project's environment.
- The package and compatibility wrappers preserve the secret scanner's value-free diagnostics; no
  credential values appear in reports, fixtures, or CLI output.
- Existing resolver, capability-coverage, and secret-scan tests remain green, and the capability
  reference enumerates every exposed CLI command.
- Invariant spot-check: the change-DAG linkage, frozen-document protection, and stdlib-only
  dependency boundary remain intact; the version/sync path works without `~/.claude`.
