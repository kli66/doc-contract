---
persistence: living
---

# doc-contracts

`doc-contracts` is a stdlib-only resolver for documentation change graphs. The installed
`doc-contract` command validates an explicitly selected repository, so invoking it from another
working directory cannot silently resolve an empty or unrelated tree.

## Set up a fresh repository

Install the package wherever the setup command will run:

```console
pip install /path/to/doc-contracts
doc-contract --version
```

The runtime package has no third-party dependencies. Python 3.12 or newer is required.

Create `.doc-contract.toml` in the target repository:

```toml
schema_version = 1
repo_name = "example"
roadmap = "docs/roadmap.md"
edge_fingerprints = "advisory"
optional_roots = ["capabilities"]

[root_nodes]
roadmap = "docs/roadmap.md"
capabilities = "docs/spec/capabilities.md"

[capability]
mode = "skip"
```

Copy `AGENTS.template.md` to the repository's `AGENTS.md` and adapt its project placeholders. Then
seed the configured roadmap:

````markdown
---
persistence: living
---

# Roadmap

<!-- BEGIN GENERATED DAG (regenerate: doc-contract update --repo-root .) -->
```mermaid
flowchart TD
```
<!-- END GENERATED DAG -->
````

From any working directory, validate the explicitly selected repository:

```console
doc-contract check --repo-root /path/to/repo --offline
```

To keep an air-gapped copy in the target, sync while the package is available and then run the
generated launcher. The second command needs only the target repository and Python:

```console
doc-contract sync --repo-root /path/to/repo
cd /an/unrelated/directory
python /path/to/repo/.doc-contract/doc_contract_cli.py check --repo-root /path/to/repo --offline
```

`sync` vendors the complete running Python package and writes `.doc-contract-manifest.json` with
that package's version and content hashes. The installed command, manifest, and vendored launcher
report the same version without installed distribution metadata. Rerunning sync is idempotent, and
modules no longer present in the running package are removed from the owned vendored package tree.

## Configuration contract

`root_nodes` classifies managed documents outside the normal change, ADR, and spec discovery tree.
Every declared root is required by default. `optional_roots` is the explicit exception list; the
roadmap cannot be optional. Missing required roots are errors, while optional omissions remain
visible as warnings. Paths must be unique, relative, and remain inside the selected repository.

Dependency topology is always enforced. `edge_fingerprints` controls only review metadata:
`advisory` (the default when omitted) accepts an absent fingerprint and warns on an explicit empty,
`PENDING`, malformed, or stale value; `required` makes absent and invalid active-edge values errors.
Frozen-document `self_hash` validation remains strict under both policies. Hashes ignore front
matter, line endings, trailing whitespace, and boundary blank lines; prose reflow and Markdown
syntax rewrites remain significant.

Repository selection precedence is explicit: `--repo-root`, then the parent of `--config`, then the
current Git root. Missing config, a missing roadmap, a missing required root, and zero discovered
nodes fail nonzero. The resolver never falls back to its installation directory.

An optional project check stays outside the stdlib resolver process. Its command is repository
specific; for example:

```toml
[capability]
mode = "optional" # skip, optional, or required
command = ["python", "-m", "pytest", "-q", "tests/test_documented_capabilities.py"]
```

Subprocess output is suppressed so a project check cannot copy credentials into resolver reports.
The summary reports `offline verified`, `live skipped`, `live passed`, or a failure distinctly.

## Commands

```console
doc-contract check --repo-root /path/to/repo --offline
doc-contract check --repo-root /path/to/repo --offline --include-untracked
doc-contract update --repo-root /path/to/repo
doc-contract update --repo-root /path/to/repo --include-untracked
doc-contract stamp CHANGE_ID --repo-root /path/to/repo
doc-contract sync --repo-root /path/to/repo
doc-contract land docs/changes/example --repo-root /path/to/repo --dry-run
doc-contract land docs/changes/example --repo-root /path/to/repo --dry-run --include-untracked
doc-contract land docs/changes/example --repo-root /path/to/repo
```

Discovery includes Git-tracked documents plus declared roots by default. `--include-untracked`
previews provisional node IDs and paths before `update` or `land` mutates anything; without it,
untracked candidates are reported and excluded. `check` is read-only and labels tolerated baseline
warnings separately from newly introduced warnings. `update` rewrites only the generated roadmap
block after validation. `stamp` records or refreshes reviewed edge metadata even in advisory mode
and refreshes strict frozen `self_hash` values. `sync` reconciles the complete vendored package and
pin manifest, including removing stale generated runtime files, without rewriting current files.
`land` previews and then atomically applies the status, dependent fingerprints, roadmap, and archive
move; advisory hashes are refreshed but are not landing prerequisites. Rerunning a completed landing
returns success without changing files or the Git index. Interrupted landings resume from the
journal under Git metadata, and concurrent edits fail closed.

The flat modules under `scripts/` and their pytest tripwires remain compatibility-only for existing
consumers. New repositories configure `.doc-contract.toml` and invoke the packaged or vendored CLI.

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
