---
name: doc-contract
description: The portable doc-contract system for a repo's docs — an enforcement resolver + coverage tripwires plus the change lifecycle, driven by a sub-command passed as the first arg. Sub-commands - `check` (run the change-DAG resolver + tripwires), `new-change <intent>` (author a docs/changes/<name>/ folder; triggers "propose a change", "new change", "start work on X"), `reconcile <folder> [entry|exit]` (the MANDATORY drift-check on picking up or landing a change; triggers "reconcile", "pick up the change", "land the change", "archive the change"), `install` (materialize the skill into another repo). Use for any of these, or when asked about the doc taxonomy / change-DAG / capability tripwire. The invariant package is configured per repository by `.doc-contract.toml`.
---

# doc-contract — the doc-contract system as one skill

This skill *encapsulates the implementation* of the doc-contract scheme. The **contract** a person
reads lives in the repo's `AGENTS.md` (the taxonomy, persistence model, change/handoff protocol); this
skill is (a) the **machinery** that enforces it — a stdlib change-DAG resolver + coverage tripwires,
kept out of the human-facing `docs/` tree because a resolver is an implementation detail — and (b) the
**lifecycle verbs** that operationalize the protocol the contract states tersely.

It is **tool-agnostic** — the installed or vendored `doc-contract` command has zero third-party
runtime dependencies. Colleagues who do not use this skill still get the discipline through the
CLI and the `AGENTS.md` contract. The skill supplies authoring workflows; it is not the runtime.

## Sub-commands (dispatch on the first arg)

Invoke as `/doc-contract <sub-command> [args]`. The first token selects the operation:

| invocation | what it does |
|-----------|--------------|
| `/doc-contract check` | Run the resolver + tripwires; report ERROR/WARN findings. See **Run it** below. |
| `/doc-contract new-change <intent>` | Author a well-formed `docs/changes/<name>/` folder from a raw intent, grounded in the ADRs + roadmap + code, stopping at `Proposed`. **Read and follow `guides/new-change.md`.** |
| `/doc-contract reconcile <folder> [entry\|exit]` | The MANDATORY entry/exit drift-check against the ADRs + roadmap. **Read and follow `guides/reconcile.md`.** |
| `/doc-contract land <folder> [--dry-run]` | Apply the transactional landing boundary after reconciliation: status, roadmap, fingerprints, journaling, and archive movement. Preview first. |
| `/doc-contract install` | Materialize the skill into another repo. See **Install into a new repo** below. |

If no sub-command is given, infer intent from the request (a raw intent to build → `new-change`;
picking up or landing a change → `reconcile`; "are the docs consistent?" → `check`). The two lifecycle
guides are the authoring/reconcile front-end to the *same* machinery `check` runs — one system, one
skill, distinct verbs.

## Layout

```
doc-contracts distribution/
  SKILL.md                      this workflow dispatcher
  AGENTS.template.md            portable operating contract
  guides/                       new-change and reconciliation procedures
  src/doc_contract/             packaged CLI, config, resolver, scanner, landing, and sync code
  scripts/                      compatibility-only flat adapters and pytest tripwires

target repository/
  .doc-contract.toml            sole resolver configuration input
  AGENTS.md                     adapted portable operating contract
  docs/roadmap.md               living roadmap and generated DAG
  .doc-contract/                optional vendored CLI and package produced by `sync`
  .doc-contract-manifest.json   optional package version and content-hash pin
```

**Invariant vs. parameter is the whole design.** The package is invariant. Everything
project-specific is declared in `.doc-contract.toml`; the resolver loads data and never imports the
target repository. `scripts/config.py` remains only for legacy vendored tests and adapters.

`.doc-contract.toml` contract (all read by the invariant core):

| name | what it is |
|------|------------|
| `schema_version` | configuration grammar version; currently `1` |
| `repo_name` | cosmetic repository label |
| `roadmap` | repo-relative roadmap path; always required |
| `root_nodes` | managed docs outside changes/adr/spec that must self-classify |
| `optional_roots` | explicit exceptions to required-by-default root nodes |
| `edge_fingerprints` | `advisory` by default; `required` opts into strict active-edge hashes |
| `capability` | skipped, optional, or required subprocess boundary |
| `secret_env_names` | additional credential environment names, never values |

## Run it — `check` (in this repo)

```
# full gate
uv run pytest -q

# resolve + report findings from any cwd (0 exit iff no ERROR)
doc-contract check --repo-root /path/to/repo --offline
doc-contract check --repo-root /path/to/repo --offline --include-untracked

# regenerate the roadmap's Mermaid DAG block in place
doc-contract update --repo-root /path/to/repo
doc-contract update --repo-root /path/to/repo --include-untracked
doc-contract land docs/changes/<name> --repo-root /path/to/repo --dry-run
doc-contract land docs/changes/<name> --repo-root /path/to/repo --dry-run --include-untracked
doc-contract land docs/changes/<name> --repo-root /path/to/repo
```

## Install into a new repo — `install`

`/doc-contract install` is this skill's guided materialization workflow. `doc-contract sync` is a
CLI command within that workflow: it writes the optional vendored runtime, not the operating
contract or agent-client integration.

To turn a bare repository into one under doc-contract:

1. **Make the package available.** Use `pip install /path/to/doc-contracts` for setup and normal
   automation. A later `doc-contract sync --repo-root /path/to/repo` can create an air-gapped
   vendor tree and pin manifest.
2. **Write `.doc-contract.toml`.** Declare `schema_version`, `repo_name`, `roadmap`, and
   `root_nodes`. Every root is required unless its ID appears in `optional_roots`; the roadmap is
   always required. Dependency topology is mandatory, while review fingerprints default to
   `edge_fingerprints = "advisory"`; set `required` only when missing or invalid active-edge hashes
   should fail the gate. Frozen-document `self_hash` remains strict in either mode. Configure
   capability mode as `skip`, `optional`, or `required`; non-skipped checks must be subprocess
   commands.
3. **Adapt the contract.** Copy `AGENTS.template.md` to `AGENTS.md`, fill its project placeholders,
   and keep any client-specific pointer files optional and thin.
4. **Seed the roadmap.** Create `docs/roadmap.md` with a `persistence: living` header and the two
   generated-DAG markers. Run `doc-contract update --repo-root /path/to/repo` after the configuration and
   initial documents are valid.
5. **Optionally vendor the runtime.** Run `doc-contract sync --repo-root /path/to/repo` while the
   package is available. Thereafter the repository can run
   `python /path/to/repo/.doc-contract/doc_contract_cli.py ...` without the package installation.
6. **Green the gate.** From any directory, run
   `doc-contract check --repo-root /path/to/repo --offline` or the vendored equivalent, plus the
   repository's own test suite. The first run surfaces every
   unclassified doc (`missing-persistence`) — add the `persistence:` headers it names.

Repositories already using the flat modules in `scripts/` may retain them and their pytest
tripwires as an explicitly compatibility-only suite. Do not use `scripts/config.py`, flat imports,
or a client-specific skill directory as the configuration or execution boundary for new installs.

## Zero-dep invariant

The runtime is **stdlib only** — no PyYAML (a total YAML *subset* parser is built into the resolver), no
Jinja2 (Mermaid render uses f-strings). Keep it that way: any doc-gen uses `string.Template`; never
add a dependency to the resolver. This is what lets the skill drop into an air-gapped repo unchanged.

## Secret-handling guardrails

The resolver also runs `doc_contract.secret_scan` over repository text files, including generated
artifacts. It reports an `ERROR` with code `secret-detected` for credential-like assignments,
known secret environment names, and every assignment in `.env` files. VCS metadata, virtualenvs,
dependency/vendor caches, bytecode, and binary files are excluded; build and generated output is
not excluded.

Scanner findings are deliberately value-free. Diagnostics include only the relative path, line,
normalized variable name, finding kind, and `present`/`length` metadata. Do not copy matched values
into resolver output, reports, fixtures, handoffs, or change folders. A repository may extend the
known environment-name set by passing `secret_env_names` to `scan_file`, `scan_tree`, or `scan`;
store names, never their values.
