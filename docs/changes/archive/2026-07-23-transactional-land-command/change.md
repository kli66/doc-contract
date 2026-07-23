---
id: transactional-land-command
persistence: ephemeral
status: landed
track: remediation
depends_on:
  - global-cwd-independent-cli
fingerprints:
  global-cwd-independent-cli: c2b091a2a80affd8
files_owned:
  - src/doc_contract/__init__.py
  - src/doc_contract/cli.py
  - src/doc_contract/landing.py
  - src/doc_contract/resolver.py
  - src/doc_contract/sync.py
  - tests/test_cli.py
  - tests/test_landing.py
  - scripts/test_change_dag.py
  - docs/spec/capabilities.md
  - AGENTS.template.md
  - guides/reconcile.md
  - README.md
  - SKILL.md
  - pyproject.toml
  - uv.lock
  - docs/roadmap.md
landed_at: 2026-07-23
archive_path: docs/changes/archive/2026-07-23-transactional-land-command
---
# Add a transactional land command

Status: Landed · 2026-07-23

**Upstream dependencies:** `global-cwd-independent-cli` is landed and provides the explicit
repository/config boundary, packaged command grammar, stamping primitives, and vendored sync path
this operation extends. Its reviewed body fingerprint is recorded above. The earlier
`secret-handling-guardrails` dependency is inherited through that change. No ADR exists for this
surface and no external infrastructure is gated; the full stdlib implementation is available now.
**Dependents:** Workstream D (hash semantics) and Workstream E (discovery/lifecycle hardening) in
`HANDOFF.md` consume the landing boundary and should depend on this change when promoted. Neither has
an in-flight change folder to back-link yet.
**Files owned:** A new `src/doc_contract/landing.py` transaction engine; the package CLI, resolver,
vendoring/version surfaces, focused CLI and transaction tests, and the archive-persistence tripwire;
the capability reference, operating-contract template, reconcile guide, package docs, and roadmap.
There are no other active change folders and therefore no current file-ownership overlap.

## Why

Landing still requires a manual sequence across status edits, archive movement, stamping, roadmap
regeneration, and validation. An interruption can leave those representations split, rerunning the
sequence can repeat or conflict with completed work, and plain `git mv` does not cover intentionally
untracked change folders. The current resolver also infers `frozen` whenever any path component is
named `archive` (`src/doc_contract/resolver.py`), so an archived change that explicitly declares
`persistence: ephemeral` unexpectedly acquires `self_hash` duties and routine
`unstamped-frozen` noise.

The packaged, cwd-independent CLI is now available, so one command can own this state transition.
It must show the entire write set before mutation, preserve reviewed inputs with optimistic content
hashes, journal progress at mutation boundaries, and make both recovery and an already-completed
rerun ordinary success paths.

## What changes

**Δ ADDED** — Add
`doc-contract land docs/changes/<name> --repo-root /path/to/repo [--dry-run]`. Add a pure landing
planner that resolves the source change, classifies its Git tracking state, chooses the dated archive
destination, and renders the complete ordered mutation plan and concise diff before any write. Add an
operation journal in the repository's Git metadata path containing the plan schema, source/archive
identity, expected input and output hashes, tracking mode, and completed mutation boundary so an
interrupted invocation can resume without reconstructing state from a moved file.

Add an apply engine that writes generated file content to same-directory temporary files and
publishes it with `os.replace`. Immediately before each publish or move, compare the current content
or tree hash with the planned input hash; accept the planned output hash as an already-applied step,
and otherwise stop with a concurrent-modification error instead of overwriting. Use `git mv` for a
fully tracked change folder and an atomic filesystem move for an intentionally untracked folder;
reject ambiguous partial-tracking and destination-collision states during preflight.

**Δ MODIFIED** — Make `land` preflight the selected repository and working tree, require a resolvable
active change and valid dependency graph, then plan status/date updates, the archive path, roadmap
prose and generated DAG, reviewed dependency fingerprints, affected active dependents, and any
required frozen-document hashes. Validate the planned in-memory repository state before applying it;
after apply, run the normal offline resolver and configured capability boundary once and report the
result plus the concise diff. A completed archive with no active source is recognized by change ID
and destination metadata and returns success without file, index, or journal changes.

Preserve archived change records as `persistence: ephemeral` lineage. Replace ancestor-name
inference with discovery-class policy: ADRs and `docs/archive/` records remain explicitly frozen and
`self_hash`-guarded, while `docs/changes/archive/...` keeps its declared change persistence. This is
the archive-policy decision for this change; the broader edge-fingerprint semantics remain deferred
to Workstream D.

Update the package sync manifest/file list and version pin for the new module. Add `land` to the CLI
command set, capability reference and coverage assertion, operating contract, reconcile procedure,
README, and skill documentation so the supported exit path is the transactional command rather than
a hand-executed move/stamp/update sequence.

**Δ REMOVED** — Remove path-component-based frozen inference for archived change folders and remove
manual `git mv` plus separate stamping/roadmap commands from the documented landing path. Do not
remove the standalone `stamp` or `update` commands, and do not weaken frozen ADR or
`docs/archive/` tamper detection.

## Tasks

1. [x] Define immutable plan, mutation, tracking-mode, and journal-schema types in
   `src/doc_contract/landing.py`; resolve journal storage through Git metadata so operation state is
   durable but never added to the worktree.
2. [x] Implement preflight and `--dry-run`: resolve the source by repository-relative path/change ID,
   reject invalid or partially tracked inputs, compute every input/output hash, simulate the final
   node graph, and print the complete ordered plan plus diff before creating a journal or temp file.
3. [x] Implement hash-guarded application with same-directory temporary files and `os.replace`, an
   atomically updated journal after every mutation boundary, tracked `git mv` and untracked atomic
   move strategies, and deterministic resume rules for input-present, output-present, and conflict
   states.
4. [x] Plan and apply the lifecycle mutations together: landed front matter/body status, dated archive
   path, roadmap prose and Mermaid DAG, refreshed fingerprints for affected active dependents, and
   required `self_hash` values for reviewed frozen documents changed by the landing set.
5. [x] Make completed landing detection return zero without mutations, and run one final offline plus
   configured capability validation only after every planned output is present; keep diagnostics
   deterministic and value-free.
6. [x] Change resolver persistence classification so archived ephemeral change records remain ephemeral
   while ADRs and `docs/archive/` records remain frozen; add focused regression tests for both sides
   of the policy.
7. [x] Add CLI/engine tests for dry-run immutability, fully tracked and intentionally untracked folders,
   partial-tracking rejection, injected interruption and recovery at every mutation boundary,
   concurrent input modification, destination collisions, failed final validation, and completed
   rerun idempotency including unchanged content and mtimes.
8. [x] Vendor the landing module through `sync`, update the package version/pin surfaces, enumerate
   `land` in `docs/spec/capabilities.md`, and update `AGENTS.template.md`, `guides/reconcile.md`,
   `README.md`, and `SKILL.md` to make it the canonical landing path.
9. [x] On land: run the new command against this change as the end-to-end bootstrap exercise, confirm
   the roadmap/archive/hash outputs and second-run no-op, then retain this folder as ephemeral
   lineage through the command's normal archive path.

## Verify

- `uv run pytest -q` and `uv run ruff check .` pass; the capability tripwire and explicit CLI
  command-set assertion both require the documented `land` command.
- `--dry-run` prints the full plan and diff while leaving source/archive paths, roadmap, Git index,
  journal location, file content, and mtimes unchanged.
- Equivalent fixtures land from fully tracked and intentionally untracked folders. A fault injected
  after each mutation boundary resumes to the same final bytes, while a hash mismatch introduced
  after planning fails without overwriting the concurrent edit.
- Running `land` twice returns success on the second invocation with no file, Git index, journal, or
  mtime changes; the first invocation performs one final validation and reports its concise diff.
- An archived `persistence: ephemeral` change produces no frozen/self-hash finding, while edits to a
  frozen ADR or `docs/archive/` record still trigger the existing tamper protection.
- Invariant spot-check: runtime code remains stdlib-only, explicit repository selection remains
  fail-closed from any cwd, secret-bearing subprocess output stays suppressed, and vendored/air-gapped
  installs contain the new landing engine with deterministic pins.
