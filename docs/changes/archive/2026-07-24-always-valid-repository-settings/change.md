---
id: always-valid-repository-settings
persistence: ephemeral
status: landed
track: architecture
depends_on:
  - portable-install-contract-convergence
fingerprints:
  portable-install-contract-convergence: 198e93dd0b4d7ca4
files_owned:
  - src/doc_contract/config.py
  - scripts/dag.py
  - scripts/test_change_dag.py
  - tests/test_config.py
  - tests/test_cli.py
  - tests/test_resolver.py
  - docs/roadmap.md
landed_at: 2026-07-24
archive_path: docs/changes/archive/2026-07-24-always-valid-repository-settings
---
# Make repository settings always valid

Status: Landed · 2026-07-24

**Upstream dependencies:** `portable-install-contract-convergence` is landed and establishes
`.doc-contract.toml` plus the packaged or vendored CLI as the canonical configuration boundary,
while retaining the flat scripts as compatibility-only adapters. Its reviewed body fingerprint is
recorded above. Transitively, it includes the current advisory edge-fingerprint policy and explicit,
fail-closed repository boundary that settings validation must preserve. No ADR governs this internal
boundary, and no external infrastructure is gated; the full stdlib-only change is available now.
**Dependents:** None. The roadmap and active change set contain no work that waits on repository
settings validation. The other architecture-review candidates are independent opportunities, not
blocked dependents.
**Files owned:** The packaged settings model and TOML loader; the legacy DAG adapter that directly
constructs and replaces settings; focused settings, packaged-loader, resolver-fixture, and
compatibility-adapter regressions; and this change's roadmap entry. The architecture-review HTML is
an input to the proposal, not an owned or modified artifact.
`unified-offline-live-verification` also forecasts changes to `tests/test_cli.py`,
`tests/test_resolver.py`, and the roadmap; `landed-graph-transition-ownership` forecasts changes to
`tests/test_resolver.py` and the roadmap. These overlaps are soft because this change owns settings
construction and invalid-state rejection while those changes own verification composition and graph
projection. Whoever lands second must rebase the shared test helpers and roadmap. No active change
owns `src/doc_contract/config.py`, `scripts/dag.py`, or the proposed focused settings tests.

## Why

`load_settings` currently validates repository names and paths, optional-root membership, duplicate
root paths, roadmap optionality, capability mode and command coupling, secret environment-name
shape, and edge-fingerprint policy before constructing `Settings`. `Settings.__post_init__` enforces
only the edge-fingerprint policy. A caller that constructs `Settings` directly can therefore create
states the TOML adapter rejects, and the frozen dataclass still exposes a mutable `root_nodes` dict
that can be invalidated after construction. Resolver, landing, and CLI code cannot trust the type's
own validity; correctness depends on which adapter produced it.

The compatibility path is one real instance of that leak. The architecture review's code-reference
line correctly points to `scripts/dag.py`, where `_SETTINGS = Settings(...)` is constructed and later
cloned with `dataclasses.replace`. The review's before-diagram label incorrectly names
`scripts/config.py`; that module only exports legacy constants. This change follows the source and
keeps `scripts/config.py` out of scope.

The same direct-construction boundary appears in `tests/test_resolver.py`, where fixtures can model
states impossible to load from `.doc-contract.toml`. Concentrating state invariants at construction
lets every downstream caller accept `Settings` as valid by definition, while keeping TOML parsing,
schema-version handling, repository selection, and path-aware `ConfigError` rendering at the
adapter boundary.

## What changes

**Δ ADDED** — Add one settings-level validation and normalization boundary that every
`Settings` construction, including `dataclasses.replace`, must cross. It validates the same
state-level invariants currently enforced by `load_settings`: a resolved repository root and
non-empty repository name; repository-relative roadmap and root paths; unique root paths; known
optional-root ids; a non-optional roadmap root; valid capability mode/command coupling; well-formed
secret environment names; and a supported edge-fingerprint policy.

Make collection-bearing state defensive and immutable after construction so mutating caller-owned
input mappings or sequences cannot invalidate an existing settings value. Add a focused settings
test module covering valid normalization, every invalid-state family, caller-input mutation, and
revalidation through `dataclasses.replace`. Add parity regressions proving the TOML and compatibility
adapters cannot expose an invalid settings value to the resolver.

**Δ MODIFIED** — Reduce `load_settings` to TOML decoding, schema and obsolete-key handling, and
translation of settings validation failures into the existing value-free `ConfigError` contract.
Preserve the current `config-invalid`/`repo-root-mismatch` CLI exit behavior and diagnostic
vocabulary; invalid configuration values and secret-bearing command arguments must not appear in
errors.

Keep `scripts/dag.py` as a shallow compatibility adapter, but make its direct construction and
root-replacement path rely on the same settings invariant boundary as the TOML loader. Keep resolver
fixtures concise while ensuring they construct only states that the canonical adapter could
represent. Do not add a second settings representation, adapter hierarchy, or third-party
validation dependency.

**Δ REMOVED** — Remove state-validity rules duplicated exclusively inside `load_settings` and
remove the possibility of mutating `root_nodes` after construction. Remove no configuration key,
CLI command, compatibility constant, flat adapter, or accepted valid manifest behavior.

## Tasks

1. Define the complete state-level invariant set in `src/doc_contract/config.py` and make
   `Settings` validate and defensively normalize all fields during direct construction and
   `dataclasses.replace`, without performing file, Git, TOML, or subprocess I/O.
2. Refactor `load_settings` to parse adapter-specific syntax and delegate state validity to
   `Settings`; map validation failures back to the existing path-aware, value-free `ConfigError`
   surface without changing CLI exit codes.
3. Update `scripts/dag.py` only as needed for the validated immutable settings value, preserving its
   legacy constants, wildcard resolver exports, default root, update behavior, and explicit status
   as a compatibility adapter.
4. Add `tests/test_config.py` coverage for valid direct and TOML construction, normalization and
   immutability, input detachment, invalid paths and root policy, capability coupling, environment
   names, edge policy, and `dataclasses.replace` revalidation.
5. Extend packaged CLI, resolver-fixture, and flat compatibility tripwires to prove both adapters
   reject equivalent invalid states and that resolver, landing, and CLI observe unchanged valid
   settings behavior.
6. Run the full test, lint, and resolver gates, including an include-untracked DAG check of this
   proposal, and confirm the packaged/vendored file closure and public CLI/capability text are
   unchanged.
7. On land: archive this folder through the transactional command and retain the roadmap lineage;
   no ADR or capability-reference amendment is required because configuration syntax and observable
   command behavior do not change.

## Verify

- `uv run pytest -q`, `uv run ruff check .`, and the offline doc-contract check pass, including the
  real-corpus DAG and compatibility tripwires.
- A table-driven settings test applies every state-level invalid input through direct construction
  and `.doc-contract.toml`; neither path returns a `Settings`, and the TOML path retains the current
  path-aware `config-invalid` diagnostic without echoing input values.
- Mutating the dict/list objects supplied by a caller cannot change an existing settings value, and
  direct mutation through `settings.root_nodes` is rejected. `dataclasses.replace` revalidates its
  result, including the root replacement used by `scripts/dag.py`.
- Existing valid manifests produce equivalent normalized settings and keep check, update, stamp,
  sync, and land behavior unchanged. The legacy adapter still resolves this repository with no DAG
  errors.
- `rg` confirms the only direct production construction outside `config.py` is the intentional
  compatibility build in `scripts/dag.py`; `scripts/config.py` remains a constants-only module and
  is neither mislabeled nor modified by this change.
- Invariant spot-check: runtime code remains stdlib-only; `.doc-contract.toml` remains the sole
  canonical target-repository input; repository selection stays explicit and fail-closed; settings
  validation performs no I/O; secret-bearing values remain absent from diagnostics; and fingerprint,
  resolver, landing, sync, and capability semantics do not change.
