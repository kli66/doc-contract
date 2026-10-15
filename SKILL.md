---
name: doc-contract
description: "Route a documentation lifecycle: author a change, reconcile entry/exit, accept, begin, land, and check the doc graph. Use when a repo carries `.doc-contract.toml`, `docs/roadmap.md`, or `docs/changes/`, or the user says propose a change, start work on X, pick up / reconcile, land or archive a change, are the docs consistent, update the roadmap DAG, or set up doc-contract in this repo — and for the doc taxonomy, persistence classes, change DAG, or capability tripwire."
---

# doc-contract

## Carrier rules

1. The CLI is the only thing you execute: `check`, `update`, `stamp`, `sync`, `reconcile mechanical`,
   `accept`, `begin`, `land`, `supersede`, `reflect`.
2. The skill verbs `new-change`, `reconcile semantic`, and `install` have no shell form: never attempt
   `doc-contract <skill-verb>`.
3. Never hand-roll what a verb owns: no manual `git mv`, hash stamp, roadmap update, or status edit.

## Invocation

Name the verb, then use the client's spelling: Pi — `/skill:doc-contract <verb> …`; a client that
exposes skills as slash commands — `/<skill> <verb> …`; the runtime — `doc-contract <cli-verb> …`.

## Intent routing

| user intent | do this | carrier | required status |
| --- | --- | --- | --- |
| are the docs consistent? | `doc-contract check --repo-root <repo> --offline` | CLI | any |
| roadmap DAG stale | `doc-contract update --repo-root <repo>` | CLI | any |
| propose / start work on X | read `guides/new-change.md`; stop at `Proposed` | you | none |
| review approved | `doc-contract accept <change> --repo-root <repo>` | CLI | proposed |
| review approved (JSON) | `doc-contract accept <change> --repo-root <repo> --format json` | CLI | proposed |
| review approved (with expectation) | `doc-contract accept <change> --repo-root <repo> --format json --expect-plan-id <id>` | CLI | proposed |
| pick up / entry | mechanical entry report, the entry judgments in `guides/reconcile.md`, then `doc-contract begin <change>` | CLI + you | accepted |
| land / archive | mechanical exit report, the exit judgments in `guides/reconcile.md`, `land --dry-run`, then `land` | CLI + you | in-progress |
| retire a never-accepted proposal | `doc-contract supersede <change> --reason <text> --repo-root <repo>` | CLI | proposed |
| frozen document edited | `doc-contract stamp <path> --repo-root <repo>` after review | CLI | any |
| set up in this repository | read `guides/install.md` | you | none |
| reflect on project evidence | `doc-contract reflect --repo-root <repo>` | CLI | any |
| author remediation proposal | `doc-contract reflect --write-proposal <id> --repo-root <repo>` | CLI | any |

Lifecycle: `proposed → accept → accepted → begin → in-progress → land → landed`. A never-accepted
`proposed` change retires through `supersede` instead of `land`. Entry reconciliation
is bracketed before `begin`; exit reconciliation before `land`. The mechanical half is evidence; the
semantic half is judgment.

## Refusals

- A live contradiction with an ADR or an importer stops the work and is surfaced; never edit the ADR
  or the change to match the other.
- An unaccepted folder never begins work; a blocked one stays under manual handling.
- A never-accepted proposal retires through `supersede`, never a manual `git mv`; `check` flags a
  folder that vanished without a lineage record.
- A trivial edit earns a roadmap line and no folder.
- A not-ready mechanical report stops the transition instead of being improvised around.

## Always true

- Repository selection is always explicit (`--repo-root`) and never inferred.
- The runtime stays stdlib-only: never add a dependency; use `string.Template` and f-strings.
- Scanner output stays value-free: paths, lines, and names only, never values.
- Configuring a source adapter or analyzer authorizes that executable to read only what the operating environment permits; it does NOT make the executable trusted by doc-contract. Operators must review adapter behavior and evidence-store privacy before enabling it. Source adapters own source-specific redaction before output; the core adds structural validation, caps, safe diagnostics, and generated-document secret scanning but does not claim to prove a semantically sensitive non-secret sentence is safe to disclose. Configured argv and adapter/analyzer output never appear in reports or diagnostics. Raw evidence and raw analyzer output are never written to the repository, journal, report, or CLI output. `--allow-external-analysis` is a per-invocation authorization that is never persisted or inferred.
- **Already-applied expectation limitation:** When a change is already accepted and no active journal exists to prove the original plan, a supplied `--expect-plan-id` cannot be verified. The command reports `execution.status: already-applied` and `execution.expectation: not-verifiable`, then exits 0.
- **Path-scoped transfer or staging:** The mutation paths in the plan manifest describe what the acceptance invocation will mutate, but they do not guarantee exact transfer or staging when a planned path contains pre-existing mixed edits. Path-scoped transfer or staging is exact only from an isolated or otherwise owned baseline, or when the caller controls patch transfer or staging.
- **Optional checkpoint policy:** The provider never requires a checkpoint. A downstream consumer may capture the accepted bytes and digest outside the mutable index and proceed through `begin` and implementation without an intermediate commit.

## Read next

`guides/new-change.md` · `guides/reconcile.md` · `guides/install.md` ·
`AGENTS.template.md` (the canonical contract) · `README.md` (configuration and runtime reference).
