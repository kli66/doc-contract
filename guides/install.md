# `doc-contract install` — set up a repository

**Interface note:** `install` is a `doc-contract` **skill** verb with no shell form; see the
dispatcher (`SKILL.md`) for the per-client invocation spelling.

Turn a bare repository into one under doc-contract. Prefer a system-level `doc-contract` CLI over a
repository-vendored runtime; do not create or use a vendored install unless the user specifically
requests one. The runtime is stdlib-only and requires Python 3.12 or newer.

## 1. Inventory the CLI first

```console
command -v doc-contract
doc-contract --version
```

If both succeed, reuse that system-level command and do not install another copy. Only when it is
unavailable or unusable should you `pip install /path/to/doc-contracts` for setup and normal
automation.

## 2. Write `.doc-contract.toml`

Declare the minimum keys: `schema_version`, `repo_name`, `roadmap`, and `root_nodes`. Every declared
root is required unless its ID appears in `optional_roots`; the roadmap cannot be optional.
Dependency topology is always enforced. `edge_fingerprints` accepts `advisory` (the default) or
`required`, which make absent or invalid active-edge hashes errors instead of warnings. `[capability]
mode` is `skip`, `optional`, or `required`; a non-skipped check must be a subprocess command. README
*Configuration contract* is the full key reference and names the failure modes.

## 3. Adapt the contract

Copy `AGENTS.template.md` to the repository's `AGENTS.md`, fill its project placeholders, and keep
any client-specific pointer files optional and thin.

## 4. Seed the roadmap

Create `docs/roadmap.md` with a `persistence: living` header and the two generated-DAG markers, then
run `doc-contract update --repo-root <repo>` once the configuration and initial documents are valid.

## 5. Green the gate

Run `doc-contract check --repo-root <repo> --offline` from any directory, plus the repository's own
test suite. The first run surfaces every unclassified document (`missing-persistence`); add the
`persistence:` headers it names.

## 6. Vendor only on explicit request

Only when the user specifically requests a vendored or air-gapped install, run
`doc-contract sync --repo-root <repo>` while the package is available. The repository can then run
`python /path/to/repo/.doc-contract/doc_contract_cli.py …` without the installation. Otherwise, do
not run `sync` or create `.doc-contract/` or `.doc-contract-manifest.json`.

## Layout

```text
doc-contracts distribution/
  SKILL.md                      the workflow dispatcher
  AGENTS.template.md            portable operating contract
  guides/                       install, new-change, and reconciliation procedures
  src/doc_contract/             packaged CLI, config, resolver, scanner, landing, and sync code
  scripts/                      compatibility-only flat adapters and pytest tripwires

target repository/
  .doc-contract.toml            sole resolver configuration input
  AGENTS.md                     adapted portable operating contract
  docs/roadmap.md               living roadmap and generated DAG
  .doc-contract/                optional vendored CLI and package produced by `sync`
  .doc-contract-manifest.json   optional package version and content-hash pin
```

Repositories already using the flat modules in `scripts/` may retain them and their pytest
tripwires as an explicitly compatibility-only suite; do not use them, or a client-specific skill
directory, as the configuration or execution boundary for new installs.

Next: `guides/new-change.md` authors changes and `guides/reconcile.md` runs the entry/exit
drift-check.
