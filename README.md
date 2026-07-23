---
persistence: living
---

# doc-contracts

`doc-contracts` is a stdlib-only resolver for documentation change graphs. The installed
`doc-contract` command validates an explicitly selected repository, so invoking it from another
working directory cannot silently resolve an empty or unrelated tree.

## Install

```console
pip install /path/to/doc-contracts
doc-contract --version
```

The runtime package has no third-party dependencies and does not read `~/.claude`. Python 3.12 or
newer is required.

For an air-gapped or vendored installation, run `doc-contract sync --repo-root /path/to/repo` while
the package is available. The repository can then use:

```console
python /path/to/repo/.doc-contract/doc_contract_cli.py check --repo-root /path/to/repo
```

The sync command writes `.doc-contract-manifest.json` with the package version and content hashes.
It is idempotent and can be rerun to update a pin.

## Configure

Create `.doc-contract.toml` at the repository root:

```toml
schema_version = 1
repo_name = "example"
roadmap = "docs/roadmap.md"
required_roots = ["roadmap"]

[root_nodes]
roadmap = "docs/roadmap.md"
capabilities = "docs/spec/capabilities.md"

[capability]
mode = "skip"
```

`root_nodes` classifies managed documents outside the normal change, ADR, and spec discovery tree.
Only IDs listed by `required_roots` are mandatory. The roadmap itself is always mandatory. Paths
must be relative and remain inside the selected repository.

Repository selection precedence is explicit: `--repo-root`, then the parent of `--config`, then the
current Git root. Missing config, a missing roadmap, a missing required root, and zero discovered
nodes fail nonzero. The resolver never falls back to its installation directory.

An optional project check stays outside the stdlib resolver process:

```toml
[capability]
mode = "optional" # skip, optional, or required
command = ["python", "-m", "pytest", "-q", "scripts/test_capabilities_coverage.py"]
```

Subprocess output is suppressed so a project check cannot copy credentials into resolver reports.
The summary reports `offline verified`, `live skipped`, `live passed`, or a failure distinctly.

## Commands

```console
doc-contract check --repo-root /path/to/repo --offline
doc-contract update --repo-root /path/to/repo
doc-contract stamp CHANGE_ID --repo-root /path/to/repo
doc-contract sync --repo-root /path/to/repo
doc-contract land docs/changes/example --repo-root /path/to/repo --dry-run
doc-contract land docs/changes/example --repo-root /path/to/repo
```

`check` is read-only. `update` rewrites only the generated roadmap block after validation. `stamp`
refreshes reviewed hashes in one node. `sync` updates the vendored package and pin manifest. `land`
previews and then atomically applies the status, dependent fingerprints, roadmap, and archive move;
rerunning a completed landing returns success without changing files or the Git index. Interrupted
landings resume from the journal under Git metadata, and concurrent edits fail closed.

Legacy `PYTHONPATH=scripts python -m dag` and flat `secret_scan` imports remain compatibility paths;
new automation should use the installed command and `.doc-contract.toml`.

## Development

```console
uv run pytest -q
PYTHONPATH=src:scripts python -m doc_contract.cli check --repo-root . --offline
make check
```

## Releases

Versions come from Git tags matching `v<semver>`. Commitizen creates the next tag and updates
`CHANGELOG.md` from conventional commits; the build and CLI read the same VCS-derived version.

```console
make bump
make build
```

Use Conventional Commits such as `feat: add a command` or `fix: reject a stale journal` so
`make bump` can select the next release level automatically.
