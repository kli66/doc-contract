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

It is **tool-agnostic** — plain Python run via `pytest` or the installed `doc-contract` command,
with zero third-party runtime dependencies.
Colleagues who don't use Claude still get the discipline through the tests + the `AGENTS.md`
contract. It is *not* a Claude plugin.

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
.claude/skills/doc-contract/
  SKILL.md                      this file — the sub-command dispatcher + how to run/install
  DESIGN-RATIONALE.md           why bespoke over OpenSpec/OpenLore (air-gap + the 3 deltas) — read before "why not just use X?"
  AGENTS.template.md            the portable, repo-agnostic contract to adapt into a new repo's AGENTS.md
  guides/
    new-change.md               the `new-change` procedure (author a change folder)
    reconcile.md                the `reconcile` procedure (entry/exit drift-check)
  src/doc_contract/
    cli.py                      explicit check/update/stamp/sync/land command boundary
    config.py                   `.doc-contract.toml` loader; never imports target code
    resolver.py                 change-DAG resolver + ERROR/WARN taxonomy + Mermaid render
    secret_scan.py              value-free repository scanner
    landing.py                  hash-guarded, journaled landing transaction engine
    sync.py                     vendored package + version/pin manifest writer
  scripts/
    dag.py                      compatibility adapter for the packaged resolver
    doc_tripwire.py             INVARIANT — the doc↔code coverage helper (+ CapabilityCheck contract)
    config.py                   PARAMETER  — the per-project seam (the only file a new repo edits)
    test_change_dag.py          INVARIANT — the change-DAG linkage tripwire
    test_capabilities_coverage.py  INVARIANT — the consumer-surface coverage tripwire
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
| `required_roots` | root-node IDs whose files must exist |
| `capability` | skipped, optional, or required subprocess boundary |
| `secret_env_names` | additional credential environment names, never values |

## Run it — `check` (in this repo)

```
# full gate
uv run pytest -q

# resolve + report findings from any cwd (0 exit iff no ERROR)
doc-contract check --repo-root /path/to/repo --offline

# regenerate the roadmap's Mermaid DAG block in place
doc-contract update --repo-root /path/to/repo
doc-contract land docs/changes/<name> --repo-root /path/to/repo --dry-run
doc-contract land docs/changes/<name> --repo-root /path/to/repo
```

## Install into a new repo — `install`

The materialize procedure — turning a bare repo into one under doc-contract:

1. **Install or vendor the package.** Use `pip install /path/to/doc-contracts`, or run
   `doc-contract sync --repo-root /path/to/repo` to create the air-gapped vendor tree and pin
   manifest. Neither path assumes a `~/.claude` checkout.
2. **Write `.doc-contract.toml`.** Declare `schema_version`, `repo_name`, `roadmap`, `root_nodes`,
   and the subset of `required_roots`. Configure capability mode as `skip`, `optional`, or
   `required`; non-skipped checks must be subprocess commands.
3. **Optionally retain the legacy pytest tripwires.** Repositories that vendor the compatibility
   `scripts/` tests can point their test configuration at those copies:
   ```toml
   [tool.pytest.ini_options]
   testpaths = ["tests", ".claude/skills/doc-contract/scripts"]
   pythonpath = ["src", ".claude/skills/doc-contract/scripts"]

   [tool.basedpyright]  # or mypy/pyright — the core is strict-clean stdlib
   include  = ["src", ".claude/skills/doc-contract/scripts"]
   extraPaths = ["src", ".claude/skills/doc-contract/scripts"]
   ```
   New automation invokes the installed command directly; these paths exist only for repositories
   retaining the flat-import compatibility suite.
4. **Adapt the contract.** Copy `AGENTS.template.md` → the repo's `AGENTS.md`, fill the
   `{{PLACEHOLDER}}` bits, and keep repo-specific traps in `CLAUDE.md` (thin `@AGENTS.md` pointer),
   never in `AGENTS.md`.
5. **Seed the roadmap.** Create `docs/roadmap.md` with a `persistence: living` header and the two
   generated-DAG markers (run `doc-contract update`; on first run it prints the block + where to
   paste it). The resolver needs a roadmap to run the linkage check.
6. **Green the gate.** Run `doc-contract check --repo-root ... --offline` plus the repository's
   test suite. The first run surfaces every
   unclassified doc (`missing-persistence`) — add the `persistence:` headers it names.

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
