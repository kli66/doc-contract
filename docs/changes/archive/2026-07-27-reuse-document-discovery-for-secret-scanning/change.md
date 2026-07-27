---
id: reuse-document-discovery-for-secret-scanning
persistence: ephemeral
status: landed
depends_on:
  - secret-handling-guardrails
  - discovery-lifecycle-hardening
files_owned:
  - src/doc_contract/resolver.py
  - tests/test_resolver.py
  - scripts/test_secret_scan.py
  - README.md
  - SKILL.md
  - AGENTS.template.md
  - docs/spec/capabilities.md
  - docs/roadmap.md
landed_at: 2026-07-27
archive_path: docs/changes/archive/2026-07-27-reuse-document-discovery-for-secret-scanning
---
# Reuse document discovery for secret scanning

Status: Landed · 2026-07-27

**Upstream dependencies:** `secret-handling-guardrails` is landed and owns value-free findings plus the invariant that credential values never enter resolver diagnostics. `discovery-lifecycle-hardening` is landed and owns Git-aware tracked/declared document discovery, configured root nodes, and the explicit `--include-untracked` preview path. Both inputs are available; no ADR or external infrastructure gates implementation.

**Dependents:** py_userapi's `docs/changes/doc-contract-config-migration/` depends on this correction so its checked-out `vendor/` submodule remains outside doc-contract without repository-specific scanner configuration.

**Files owned:** the resolver discovery/result seam and focused package/compatibility tests; the README, skill, operating-contract template, capability reference, and roadmap descriptions of the supported scan scope. This is a resolver behavior change, not a documentation-only edit. The scanner's existing explicit-path interface is reused; configuration and application source are not in scope.

## Why

The resolver currently performs two unrelated traversals. Document discovery selects declared roots and managed Markdown under the fixed documentation trees. Secret checking then ignores that result and separately calls `scan_tree(repo_root)`, walking source, fixtures, generated code, untracked dependency trees, and checked-out Git submodules that doc-contract neither classifies nor owns. In py_userapi that second traversal scans more than fourteen thousand vendor code/text files even though no vendor document participates in the change DAG.

The repository-wide pass came from a historical credential-handling remediation that combined two concerns: value-free resolver diagnostics and general repository secret detection. The diagnostic invariant belongs in doc-contract; a whole-repository security gate does not. Secret scanning should consume the exact file set selected by document discovery, so both checks share one traversal and one path policy.

## What changes

**Δ ADDED** — return the exact deterministic document-path set from the existing discovery operation, covering existing declared root documents and documentation candidates under the fixed ADR, spec, change, and archive trees. Preserve the established tracked/declared default and `--include-untracked` semantics for provisional documents.

**Δ MODIFIED** — run document discovery once, validate the document graph from its result, and pass that same ordered path set through the scanner's existing `scan(paths, root=...)` interface. Secret scanning must not start its own `os.walk`, `rglob`, or repository-root traversal. Keep secret findings value-free and fail-closed for every selected document.

**Δ REMOVED** — remove the resolver's repository-wide `scan_tree(repo_root)` pass. Source, `.env`, fixtures, generated code, dependency trees, and Git submodule contents are not scanned merely because they exist below the repository root. Repository-wide secret detection belongs to a dedicated security tool rather than doc-contract.

## Tasks

1. [x] Extend the existing document-discovery result with the exact ordered paths it traversed, including non-node companion Markdown considered inside managed change folders, without adding another filesystem walk.
2. [x] Apply the existing tracked/declared and `--include-untracked` decision once during discovery, while always retaining existing configured root documents; use the same selected paths for graph validation and secret scanning.
3. [x] Replace the resolver's `scan_tree(repo_root)` call with `scan(discovery.document_paths, root=repo_root, ...)`; prove the secret scanner receives no independently discovered files.
4. [x] Add package regressions proving managed and declared documents are scanned; ordinary source, `.env`, generated files, vendor trees, and checked-out submodules are not; and provisional documents follow `--include-untracked` consistently.
5. [x] Update the flat compatibility secret-scan tripwire to test the shared document traversal while retaining focused scanner-module tests for redaction, binary handling, and deterministic explicit-file scanning.
6. [x] Update `README.md`, `SKILL.md`, `AGENTS.template.md`, and `docs/spec/capabilities.md` to state that graph validation and secret scanning consume the same document-discovery result.
7. [x] Verify py_userapi with the installed CLI; confirm `vendor/` is never passed to the scanner, managed-document findings remain fail-closed, and no vendored `.doc-contract/` runtime is introduced.
8. [x] On land, archive this folder through the transactional command and regenerate the roadmap DAG.

## Verify

- `uv run --group test pytest -q -p no:cacheprovider` and `uv run --group lint ruff check --no-cache .` pass, including package resolver and flat compatibility tripwires.
- A resolver test records the paths selected by document discovery and the paths received by the secret scanner, proving they are identical and that only one filesystem traversal supplies them.
- A fixture repository containing credential-shaped values in source, `.env`, generated files, and a submodule-like vendor tree produces no secret findings unless those files enter the document-discovery result.
- Tracked/declared documents produce value-free `secret-detected` errors; provisional documents are excluded by default and included with `--include-untracked` using the same discovery decision reported by the CLI.
- `doc-contract check --repo-root . --offline --include-untracked` resolves the proposal with no new errors, and py_userapi resolves without scanner exclusion configuration or a vendored runtime.
- Invariant spot-check: repository selection remains fail-closed, change-DAG and frozen-document validation are unchanged, final landing uses the same discovery result as ordinary check, and no credential value enters diagnostics or generated output.

## Exit reconciliation

The resolver now exposes one deterministic managed-document path tuple and passes it unchanged to the explicit-path scanner. Focused tests prove companion Markdown and provisional discovery behavior, verify that source, `.env`, generated output, and a submodule-like vendor tree never enter the scanner input, and retain value-free fail-closed findings for selected documents.

Repository verification passed with 124 tests and a clean full ruff run. The installed CLI resolved py_userapi through a temporary equivalent config with its scanner exclusion omitted: 60 nodes, 0 errors, and only three pre-existing migration warnings. No `.doc-contract/` runtime or manifest was created. No ADR changed; the durable boundary is recorded in `README.md`, `SKILL.md`, `AGENTS.template.md`, and `docs/spec/capabilities.md`.
