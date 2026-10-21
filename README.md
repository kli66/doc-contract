---
persistence: living
---

# doc-contracts

`doc-contracts` is a stdlib-only resolver for documentation change graphs. The installed
`doc-contract` command validates an explicitly selected repository, so invoking it from another
working directory cannot silently resolve an empty or unrelated tree.

## Set up a fresh repository

Before installing anything, check whether a working system-level CLI is already available:

```console
command -v doc-contract
doc-contract --version
```

If both commands succeed, reuse that CLI and do not install another copy. Only when it is
unavailable or unusable should you install the package wherever the setup command will run:

```console
pip install /path/to/doc-contracts
doc-contract --version
```

Downstream setup should always prefer the system-level CLI. Do not create or use a repository-
vendored runtime unless the user specifically requests one. The runtime package has no third-party
dependencies. Python 3.12 or newer is required.

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

Only when the user specifically requests a vendored or air-gapped install, sync while the package
is available and then run the generated launcher. Otherwise, keep using the system-level CLI and
do not create `.doc-contract/` or `.doc-contract-manifest.json`. The second command needs only the
target repository and Python:

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

`check` and final landing use one verification boundary. Offline resolution always reports `offline verified` or `offline failed`. Live behavior is shared:

| Capability mode | `check --offline` | Ordinary `check` and final landing |
| --- | --- | --- |
| `skip` | `live skipped`, no live error | `live skipped`, no live error |
| `optional` | `live skipped`, no live error | run the configured command |
| `required` | `live skipped`, error | run the configured command |

An executed command reports `live passed` on zero exit, `live failed` on nonzero exit, and `live skipped` when unavailable or timed out. Every failure is value-free. The subprocess runs at the selected repository root with stdin, stdout, and stderr disconnected, so command arguments, output, environment values, and exception text cannot enter reports. `land --dry-run` and an already-landed no-op never request live work; a mutated landing verifies after its mutations and retains its journal on any final offline or live error.

## Reflection configuration

An optional `[reflection]` table configures project-scoped evidence reflection. When absent, `doc-contract reflect` exits 2 with `reflection-not-configured` and does not affect other commands.

```toml
[reflection]
source_timeout_seconds = 60
analyzer_timeout_seconds = 180
max_records_per_source = 500
max_total_records = 2000
instruction_targets = ["docs/instructions/"]
skill_targets = ["SKILL.md"]
spec_targets = ["docs/spec/"]
config_targets = [".doc-contract.toml"]

[[reflection.sources]]
name = "local"
argv = ["python", "-m", "local_adapter"]

[reflection.analyzer]
argv = ["python", "-m", "local_analyzer"]
trust = "local"
```

### Source adapters

Each `[[reflection.sources]]` entry declares a named source adapter. Adapters run in sorted name order at the repository root, receive a JSON request on stdin, and return newline-delimited JSON evidence records on stdout. The request includes repository identity, absolute root, optional `--since` date, and configured limits.

Adapters must return records with schema version 1, including adapter name, stable record ID, repository identity, observation timestamp, evidence kind, SHA-256 digest, and byte length. The core validates provenance, rejects duplicates and repository mismatches, and canonicalizes records.

### Analyzer

An optional `[reflection.analyzer]` declares a semantic analyzer. When `trust = "external"`, the analyzer runs only with `--allow-external-analysis`. The analyzer receives normalized evidence records and returns typed findings, recommendations, nominations, and optional remediation.

### Default limits

Schema-1 default limits (overridable with positive integers in `[reflection]`):

| Limit | Default |
| --- | --- |
| `source_timeout_seconds` | 60 |
| `analyzer_timeout_seconds` | 180 |
| `source_stdout_cap` | 1,048,576 |
| `analyzer_stdout_cap` | 1,048,576 |
| `max_records_per_source` | 500 |
| `max_total_records` | 2000 |
| `summary_cap` | 2048 |
| `max_findings` | 200 |
| `max_recommendations` | 100 |
| `max_nominations` | 50 |
| `max_candidate_requirements` | 50 |
| `max_candidate_tasks` | 50 |

### Authority and privacy

Configuring a source adapter or analyzer authorizes that executable to read only what the operating environment permits; it does NOT make the executable trusted by doc-contract. Operators must review adapter behavior and evidence-store privacy before enabling it.

Source adapters own source-specific redaction before output. The core adds structural validation, caps, safe diagnostics, and generated-document secret scanning but does not claim to prove a semantically sensitive non-secret sentence is safe to disclose. Configured argv and adapter/analyzer output never appear in reports or diagnostics. Raw evidence and raw analyzer output are never written to the repository, journal, report, or CLI output. `--allow-external-analysis` is a per-invocation authorization that is never persisted or inferred.

### Report schema

Schema-1 reports include: repository identity, selected adapters and evidence window, coverage/omission notes, evidence inventory (adapter/record ID, timestamp, kind, digest prefix), cited findings, recommendations, explicitly labelled nominations, and optional remediation. Text output is a rendering of the same object as `--format json`.

### Proposal mutation

Only `--write-proposal CHANGE_ID` writes `docs/changes/<id>/change.md` plus the roadmap remediation line and regenerated DAG block. The created item is always `status: proposed` / `Status: Proposed (not accepted)`. Reflection never edits `AGENTS.md`, `docs/spec/`, skills, `.doc-contract.toml`, source, or tests, never accepts, begins, executes, stages, or commits, and never promotes a global nomination. Promotion across projects is owned by a separate explicitly authorized system.

### Target paths

Repository-local target-path keys (`instruction_targets`, `skill_targets`, `spec_targets`, `config_targets`) are repository-relative arrays. They are the only durable paths handed to the analyzer as approved proposal targets.

## Commands

The commands below are the installed or vendored `doc-contract` executable's runtime interface.
The authoring workflow is separate: use `/doc-contract new-change <intent>` in an agent session.
`new-change` is intentionally not a shell subcommand and will not appear in `doc-contract --help`.

```console
doc-contract check --repo-root /path/to/repo --offline
doc-contract check --repo-root /path/to/repo --offline --include-untracked
doc-contract update --repo-root /path/to/repo
doc-contract update --repo-root /path/to/repo --include-untracked
doc-contract stamp CHANGE_ID --repo-root /path/to/repo
doc-contract stamp CHANGE_ID --repo-root /path/to/repo --include-untracked
doc-contract sync --repo-root /path/to/repo
doc-contract accept docs/changes/example --repo-root /path/to/repo --dry-run
doc-contract accept docs/changes/example --repo-root /path/to/repo --dry-run --format json
doc-contract accept docs/changes/example --repo-root /path/to/repo --dry-run --format json --expect-plan-id sha256:...
doc-contract begin docs/changes/example --repo-root /path/to/repo --dry-run
doc-contract reconcile mechanical docs/changes/example --phase entry --format json --repo-root /path/to/repo
doc-contract reconcile mechanical docs/changes/example --phase exit --repo-root /path/to/repo
doc-contract land docs/changes/example --repo-root /path/to/repo --dry-run
doc-contract land docs/changes/example --repo-root /path/to/repo --dry-run --diff
doc-contract land docs/changes/example --repo-root /path/to/repo --dry-run --include-untracked
doc-contract land docs/changes/example --repo-root /path/to/repo
doc-contract supersede docs/changes/example --reason "superseded by <successor>" --repo-root /path/to/repo --dry-run
doc-contract supersede docs/changes/example --reason "superseded by <successor>" --repo-root /path/to/repo
doc-contract reflect --repo-root /path/to/repo
doc-contract reflect --repo-root /path/to/repo --source local --since 2026-01-01
doc-contract reflect --repo-root /path/to/repo --format json
doc-contract reflect --repo-root /path/to/repo --allow-external-analysis
doc-contract reflect --repo-root /path/to/repo --write-proposal example-remediation
```

Discovery includes Git-tracked managed documents plus declared roots by default, including companion Markdown inside selected change folders. The resolver uses that one ordered path set for both graph validation and value-free secret scanning. Source, `.env`, generated output, dependency trees, and checked-out submodules are not scanned merely because they are below the repository root; use a dedicated security tool for repository-wide secret detection. `--include-untracked` previews provisional node IDs and paths before `update` or `land` mutates anything; without it, untracked candidates are reported and excluded from both validation and scanning. `stamp` also accepts `--include-untracked` for the one node the operator just named: it admits a provisional (untracked) change node to stamping without printing a preview, and without it an untracked node is reported as an unknown node id. For `reflect`, `--include-untracked` is accepted for grammar parity with other commands but does not broaden evidence scope; evidence comes only from configured adapters, and the proposal projection and post-write validation always consider the newly created proposal. `check` is read-only and labels tolerated baseline warnings separately from newly introduced warnings. `update` rewrites only the generated roadmap block after validation. `stamp` records or refreshes reviewed edge metadata even in advisory mode and refreshes strict frozen `self_hash` values. `sync` reconciles the complete vendored package and pin manifest, including removing stale generated runtime files, without rewriting current files.
`accept` and `begin` are explicit, hash-guarded, journaled transitions. `accept` records only an
explicit user/reviewer authorization and never infers approval; `begin` starts work only from
`accepted`. Both are offline and idempotent, preserve blocked state, and support dry-run and
provisional `--include-untracked` planning. `accept` additionally supports `--format json` for
machine-readable output and `--expect-plan-id` for optimistic concurrency control: the plan
identifier is computed from a domain-separated, schema-versioned canonical encoding of the public
plan plus each mutation's private preimage and postimage hashes, and a mismatch rejects before any
journal creation or mutation. The `plan_id` identifies the complete acceptance transaction,
including roadmap and dependent metadata; it is distinct from the accepted-document identity,
which is the exact `change.md` bytes plus their SHA-256 digest.

**Already-applied expectation limitation:** When a change is already accepted and no active journal
exists to prove the original plan, a supplied `--expect-plan-id` cannot be verified. The command
reports `execution.status: already-applied` and `execution.expectation: not-verifiable`, then exits
0.

**Path-scoped transfer or staging:** The mutation paths in the plan manifest describe what the
acceptance invocation will mutate, but they do not guarantee exact transfer or staging when a
planned path contains pre-existing mixed edits. Path-scoped transfer or staging is exact only from
an isolated or otherwise owned baseline, or when the caller controls patch transfer or staging.

**Optional checkpoint policy:** A downstream consumer may capture the accepted bytes and digest
outside the mutable index and proceed through `begin` and implementation without an intermediate
commit; acceptance remains logically prior to implementation, and the runtime never stages or
commits Git changes.

`land` accepts only `in-progress` changes, previews and then atomically applies the status, dependent fingerprints, roadmap, and archive
move; advisory hashes are refreshed but are not landing prerequisites. Before projected validation
`land` locates the change's roadmap entry with the same counted `roadmap-invalid` guard as `accept`,
`begin`, and `supersede` — refusing a missing, duplicated, cross-referenced, statusless, or unclosed
entry, plus an entry whose only location is after the generated DAG region. The documented entry
convention follows: one entry per active change, a pre-DAG line plus its indented continuations,
cites the folder path with exactly one status presentation across the whole block. The retirement
verbs act on one change node per folder, and `land`/`supersede` require the folder's node document
to be `change.md`. Rerunning a completed landing returns success without changing files or the Git
index. Interrupted landings resume from the journal under Git metadata, and concurrent edits fail
closed.

`supersede` retires a never-accepted `proposed` change into a frozen `docs/archive/<name>.md` record
in one resumable, dry-runnable transaction. It requires `--reason` (recorded verbatim in the record
body, never echoed in output), removes the active folder, retargets its roadmap line to the record
path with `(superseded)`, regenerates the DAG, and creates the record last (staged for tracked
plans). It refuses `accepted`, `in-progress`, `blocked`, and `landed` changes, refuses while an
active node still depends on the retired id, and refuses a folder holding more than one node-bearing
change document. Its roadmap entry retarget uses the same counted `roadmap-invalid` guard, failing
closed on a missing, duplicated, cross-referenced, statusless, or unclosed entry before any
mutation. The record keeps the retired `id`, declares `persistence: frozen`, records `superseded_at`
and a strict `self_hash`, and carries an inert `status: superseded` scalar. `doc-contract check`
reports a `roadmap-line-dangling` ERROR when a folder vanishes without a lineage record, and a
`multi-node-change-folder` WARN naming the folder and count when a folder holds more than one change
node, so the manual `git rm` path fails loudly.

Landing output is compact by default: the plan prints source/archive/tracking facts, provisional
nodes, warning count, mutation type totals, and every ordered write/move path, but no content patch
or tree hashes. Add `--diff` for the complete precomputed patch when line-level review is needed;
the flag does not change planning, mutation, verification, or exit behavior. Dry runs print baseline
warning details after the scope summary. New journals retain the diff for resumed output, while a
legacy journal resumes safely and reports that its historical diff is unavailable. The journal
schema remains private and is not a supported JSON interface.

`reconcile mechanical` is the read-only deterministic half of entry/exit reconciliation. It reuses
the `begin` or landing planner, emits schema-1 JSON or compact text, and reports scoped findings plus
content-free plan metadata. It never runs project capabilities or tests and never writes files, the
index, journals, or archives. A green report proves only mechanical readiness; the `/doc-contract
reconcile semantic ...` skill still decides whether ADR meaning, scope, task completion, and durable
knowledge are true before an explicit `begin` or `land` command.

Lifecycle callers classify the selected reference before whole-repository preflight and share these
stable codes: `change-proposed-unaccepted`, `change-accepted-not-started`, `change-not-proposed`,
`change-blocked`, `change-already-landed`, `change-untracked-excluded`, `change-front-matter-missing`,
`change-front-matter-invalid`, `change-ref-wrong-folder`, `change-ref-unknown`, and
`change-multi-node-folder`. Diagnostics contain only normalized IDs, repository-relative paths,
canonical status, node counts, and `gate_present=true|false`.
Proposed and accepted blockers point to dry-run `accept` or `begin`; excluded untracked work replays
the same normalized command with `--include-untracked`. Blocked, invalid, wrong-folder, unknown, and
already-landed states never invent a next command. Repeated `land` reports
`INFO: [change-already-landed]` and exits zero; other classified blockers report
`ERROR: [<code>]` and exit one.

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

## Dev dogfooding

run `uv tool install --editable . --reinstall` in the project
