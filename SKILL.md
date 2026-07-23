---
name: doc-contract
description: The portable doc-contract system for a repo's docs — an enforcement resolver + coverage tripwires plus the change lifecycle, driven by a sub-command passed as the first arg. Sub-commands - `check` (run the change-DAG resolver + tripwires), `new-change <intent>` (author a docs/changes/<name>/ folder; triggers "propose a change", "new change", "start work on X"), `reconcile <folder> [entry|exit]` (the MANDATORY drift-check on picking up or landing a change; triggers "reconcile", "pick up the change", "land the change", "archive the change"), `install` (materialize the skill into another repo). Use for any of these, or when asked about the doc taxonomy / change-DAG / capability tripwire. The invariant core is copied verbatim between repos; only scripts/config.py changes.
---

# doc-contract — the doc-contract system as one skill

This skill *encapsulates the implementation* of the doc-contract scheme. The **contract** a person
reads lives in the repo's `AGENTS.md` (the taxonomy, persistence model, change/handoff protocol); this
skill is (a) the **machinery** that enforces it — a stdlib change-DAG resolver + coverage tripwires,
kept out of the human-facing `docs/` tree because a resolver is an implementation detail — and (b) the
**lifecycle verbs** that operationalize the protocol the contract states tersely.

It is **tool-agnostic** — plain Python run via `pytest` / `python -m`, zero third-party deps.
Colleagues who don't use Claude still get the discipline through the tests + the `AGENTS.md`
contract. It is *not* a Claude plugin.

## Sub-commands (dispatch on the first arg)

Invoke as `/doc-contract <sub-command> [args]`. The first token selects the operation:

| invocation | what it does |
|-----------|--------------|
| `/doc-contract check` | Run the resolver + tripwires; report ERROR/WARN findings. See **Run it** below. |
| `/doc-contract new-change <intent>` | Author a well-formed `docs/changes/<name>/` folder from a raw intent, grounded in the ADRs + roadmap + code, stopping at `Proposed`. **Read and follow `guides/new-change.md`.** |
| `/doc-contract reconcile <folder> [entry\|exit]` | The MANDATORY entry/exit drift-check against the ADRs + roadmap. **Read and follow `guides/reconcile.md`.** |
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
  scripts/
    dag.py                      INVARIANT — the change-DAG resolver + ERROR/WARN taxonomy + Mermaid render
    doc_tripwire.py             INVARIANT — the doc↔code coverage helper (+ CapabilityCheck contract)
    config.py                   PARAMETER  — the per-project seam (the only file a new repo edits)
    test_change_dag.py          INVARIANT — the change-DAG linkage tripwire
    test_capabilities_coverage.py  INVARIANT — the consumer-surface coverage tripwire
```

**Invariant vs. parameter is the whole design.** `dag.py` + `doc_tripwire.py` + the two `test_*.py`
are copied between repos *verbatim*. Everything project-specific — where the repo root is, which
managed docs are nodes, where the doc tree lives, and what code surface the capability doc must
mirror — is declared in `config.py`. If you find yourself editing an invariant file to fit a repo,
that value belongs in `config.py` instead (feed the correction back here). The `guides/` are
repo-agnostic procedure; their worked examples happen to be tkcs's but the steps are general.

`config.py` contract (all read by the invariant core):

| name | what it is |
|------|-----------|
| `REPO_ROOT` | the repo being enforced (derived from this file's location) |
| `REPO_NAME` | cosmetic label |
| `ROOT_NODES` | managed docs outside changes/adr/spec that must still self-classify (id → path) |
| `FINGERPRINT_TARGETS` | which node kinds are fingerprintable (v1: `("doc",)` — never `src/`) |
| `CAPABILITY_DOC` | the living doc whose headings must mirror a code surface |
| `CAPABILITY_ENUMERATORS` | the per-surface coverage checks (`CapabilityCheck` from `doc_tripwire`) |

## Run it — `check` (in this repo)

```
# full gate (tests are discovered from the scripts dir via pyproject testpaths)
uv run pytest -q .claude/skills/doc-contract/scripts

# resolve + report findings (0 exit iff no ERROR)
PYTHONPATH=.claude/skills/doc-contract/scripts python -m dag

# regenerate the roadmap's Mermaid DAG block in place
PYTHONPATH=.claude/skills/doc-contract/scripts python -m dag --update
```

## Install into a new repo — `install`

The materialize procedure — turning a bare repo into one under doc-contract:

1. **Copy the skill.** Drop `.claude/skills/doc-contract/` into the target repo (`.claude/` should
   be git-tracked, not ignored — the skill is part of the repo). Copy `scripts/dag.py`,
   `scripts/doc_tripwire.py`, `scripts/test_change_dag.py`, `scripts/test_capabilities_coverage.py`,
   and the `guides/` **verbatim** — do not edit them.
2. **Write `scripts/config.py`.** This is the only file you author. Start from this repo's copy and set:
   - `REPO_ROOT` — keep the `parents[N]` form if the skill sits at `.claude/skills/doc-contract/scripts/`
     (then `parents[4]` is correct); repoint if you install it elsewhere.
   - `REPO_NAME`, `ROOT_NODES` for the target's doc tree. A minimal repo can start with just
     `agents`/`roadmap` in `ROOT_NODES` and grow it. (`docs/` at the project root is assumed; no
     `DOC_ROOTS` entry needed.)
   - `CAPABILITY_DOC` + `CAPABILITY_ENUMERATORS` — the enumerators introspect *this repo's* code
     (its CLI parser, its tool registry). If the repo has no such surface yet, use an empty
     `CAPABILITY_ENUMERATORS = ()` and the coverage tripwire is a no-op until one exists.
3. **Repoint `pyproject.toml`** (or the repo's test/type config) so enforcement follows the code:
   ```toml
   [tool.pytest.ini_options]
   testpaths = ["tests", ".claude/skills/doc-contract/scripts"]
   pythonpath = ["src", ".claude/skills/doc-contract/scripts"]

   [tool.basedpyright]  # or mypy/pyright — the core is strict-clean stdlib
   include  = ["src", ".claude/skills/doc-contract/scripts"]
   extraPaths = ["src", ".claude/skills/doc-contract/scripts"]
   ```
   List the scripts dir on `pythonpath` so the tripwires resolve their flat `import config` /
   `from dag import …` against the skill (put it before any repo-root dir that might shadow `config`).
4. **Adapt the contract.** Copy `AGENTS.template.md` → the repo's `AGENTS.md`, fill the
   `{{PLACEHOLDER}}` bits, and keep repo-specific traps in `CLAUDE.md` (thin `@AGENTS.md` pointer),
   never in `AGENTS.md`.
5. **Seed the roadmap.** Create `docs/roadmap.md` with a `persistence: living` header and the two
   generated-DAG markers (run `python -m dag --update`; on first run it prints the block + where to
   paste it). The resolver needs a roadmap to run the linkage check.
6. **Green the gate.** `uv run pytest -q` + resolver `0 ERROR`. The first run surfaces every
   unclassified doc (`missing-persistence`) — add the `persistence:` headers it names.

## Zero-dep invariant

The core is **stdlib only** — no PyYAML (a total YAML *subset* parser is built into `dag.py`), no
Jinja2 (Mermaid render uses f-strings). Keep it that way: any doc-gen uses `string.Template`; never
add a dependency to the resolver. This is what lets the skill drop into an air-gapped repo unchanged.
