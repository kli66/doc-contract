---
id: vendored-runtime-closure
persistence: ephemeral
status: landed
track: architecture
depends_on:
  - portable-install-contract-convergence
fingerprints:
  portable-install-contract-convergence: 198e93dd0b4d7ca4
files_owned:
  - src/doc_contract/sync.py
  - tests/test_cli.py
  - docs/spec/capabilities.md
  - README.md
  - docs/roadmap.md
landed_at: 2026-07-24
archive_path: docs/changes/archive/2026-07-24-vendored-runtime-closure
---
# Deepen the vendored runtime closure

Status: Landed · 2026-07-24

**Upstream dependencies:** `portable-install-contract-convergence` is landed and establishes the
packaged or vendored CLI as the portable execution boundary, including the clean-repository
sync-to-check proof this change must preserve. Its reviewed body fingerprint is recorded above.
Transitively, it supplies the stdlib-only runtime, explicit repository selection, deterministic pin
manifest, and idempotent sync contract. No ADR governs this internal packaging boundary, and no
external infrastructure is gated; source and installed-package fixtures make the full change
available now.
**Dependents:** None. The roadmap and active change set contain no work that must wait for a complete
vendored runtime image. `unified-offline-live-verification` can land independently by extending the
current manual package tuple, while this change can discover that module if verification lands
first.
**Files owned:** The vendored runtime-image implementation, existing sync and clean-repository CLI
regressions, the consumer-facing sync descriptions, and this change's roadmap entry. The generated,
Git-ignored `src/doc_contract/_version.py` is an input to the current failure, not a durable source
file owned by this change; the runtime-image builder must materialize an equivalent pinned version
module without tracking generated build output.
`unified-offline-live-verification` forecasts changes to all five owned files and specifically plans
to add `verification.py` to `sync.PACKAGE_FILES`. That is a shared-symbol conflict if both changes
execute concurrently: coordinate the runtime inventory and sync tests, and have whoever lands
second reconcile its task wording and implementation rather than restoring a manual tuple.
`always-valid-repository-settings` also forecasts `tests/test_cli.py` and the roadmap, while
`landed-graph-transition-ownership` forecasts only the roadmap; those overlaps are soft and require
the later change to rebase. The architecture-review HTML is proposal input, not an owned artifact.

## Why

`sync_package` claims to vendor the running package and pin a deterministic manifest, but its
`PACKAGE_FILES` tuple is a second, manually maintained description of the runtime topology. It omits
the setuptools-scm-generated `_version.py` that `doc_contract.__init__` prefers. In an isolated
target, the current installed CLI reports `0.0.1.dev1+g3bff361bb.d20260723` and writes that value to
the manifest, while the synced launcher cannot find either `_version.py` or installed distribution
metadata and reports the fallback `0.0.0`.

The same tuple will silently omit any future runtime module unless each feature remembers to update
the adapter. The active unified-verification proposal already contains exactly that coupled task for
its planned `verification.py`. Sync also leaves files behind when a module disappears from the
source package, so the target directory can contain executable code outside the manifest's claimed
closure. Hashing the files selected by a drifting tuple does not make the resulting package image
complete.

The stronger boundary is the existing `sync_package` seam with more depth inside it: one
deterministic runtime-image builder owns module inventory, generated version identity, launcher
content, hashes, stale-file removal, and manifest rendering. Installed and vendored commands remain
adapters over the same package behavior; no second packaging framework or public plugin API is
needed.

## What changes

**Δ ADDED** — Build one immutable in-memory runtime image from the running `doc_contract` package.
Inventory its runtime Python modules in deterministic path order, materialize a minimal generated
`_version.py` from the already-resolved package `__version__`, add the launcher, and derive the
manifest's sorted file hashes and version from those exact bytes. Validate the required package
entry modules before writing so a partial or malformed source closure fails closed.

Reconcile the generated destination to that image: replace changed files atomically, retain
byte-identical files, and remove stale files under the owned vendored package directory that are no
longer members of the runtime closure. Add regressions for automatic module inclusion, generated
version identity, exact manifest-to-vendor closure, stale-file pruning, deterministic ordering, and
second-run idempotence.

**Δ MODIFIED** — Make `sync_package` delegate closure construction, hashing, and materialization to
the single runtime-image implementation while preserving its `Path -> bool` interface and current
CLI messages. Strengthen the clean-repository integration test so the installed CLI version,
manifest version, and isolated vendored launcher `--version` are equal before the launcher performs
the existing offline check from an unrelated working directory.

Update `README.md` and `docs/spec/capabilities.md` to state the observable contract: sync vendors the
complete running package, pins the same version identity exposed by both launchers, removes stale
generated runtime files, and remains idempotent. Keep manifest schema version 1, paths, command
grammar, setup steps, and existing check behavior unchanged.

**Δ REMOVED** — Remove `PACKAGE_FILES` as a manually duplicated runtime inventory and remove stale
generated modules during reconciliation. Remove no source module, CLI command, configuration key,
compatibility adapter, manifest field, or setuptools-scm release behavior.

## Tasks

1. Define the internal immutable runtime-image representation in `src/doc_contract/sync.py`, with
   deterministic package-module discovery, required-entry validation, generated version bytes,
   launcher bytes, and hashes derived from one closure.
2. Refactor `sync_package` to materialize that image under its existing paths, atomically replace
   changed files, prune only stale files inside the owned vendored package directory, write the
   manifest after the runtime image, and preserve accurate changed-versus-current reporting.
3. Extend the focused sync regression to prove newly present package modules join the image without
   an inventory edit, every vendored runtime file is pinned, stale generated files are removed, and
   a second identical sync changes no bytes or mtimes.
4. Strengthen the clean-repository integration proof to compare installed `--version`, manifest
   `version`, and isolated vendored `--version`, then retain the unrelated-cwd offline check and
   absence of agent-client installation assumptions.
5. Update the README and capability reference with the complete-closure, package-identity,
   stale-pruning, and idempotence guarantees; keep the public command heading and manifest schema
   stable so no capability enumerator change is needed.
6. Reconcile the active `unified-offline-live-verification` overlap at execution time: if it landed
   first, verify `verification.py` is discovered automatically; if it remains open, update its
   `PACKAGE_FILES` task so it does not recreate the removed inventory.
7. Run the full test, lint, capability-coverage, and offline resolver gates, including an
   include-untracked DAG check while this proposal is provisional.
8. On land: archive this folder through the transactional command and retain the roadmap lineage;
   no ADR amendment is required because the change makes the existing portable sync contract true.

## Verify

- `uv run pytest -q`, `uv run ruff check .`, and the offline doc-contract check pass, including the
  real-corpus DAG and capability coverage tripwires.
- A synced clean repository satisfies `installed --version == manifest["version"] == vendored
  --version`, and its isolated launcher still completes the offline check from an unrelated cwd
  without an installed `doc-contracts` distribution or agent-client directory.
- The manifest's `doc_contract/` keys exactly match the regular files in the owned vendored package
  directory, every hash matches the materialized bytes, a synthetic runtime module is included
  without editing an inventory constant, and a synthetic stale target module is removed.
- Repeating sync from identical package bytes returns unchanged and preserves file contents and
  mtimes. Changing one source/runtime-image input rewrites only the affected generated artifacts and
  the manifest; ordering and rendered bytes are stable across runs.
- Failure to discover a required entry module produces a stable value-free error before the
  manifest is replaced, and stale pruning cannot escape `.doc-contract/vendor/doc_contract/` or
  touch target-repository files outside the generated package tree.
- Invariant spot-check: runtime code remains stdlib-only; setuptools-scm remains the installed
  package identity source; the vendored runtime needs no distribution metadata; repository
  selection stays explicit and fail-closed; sync imports no target project modules; and manifest,
  secret-redaction, resolver, landing, capability, and fingerprint semantics otherwise stay
  unchanged.
