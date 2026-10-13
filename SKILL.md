---
name: doc-contract
description: "Route a documentation lifecycle: author a change, reconcile entry/exit, accept, begin, land, and check the doc graph. Use when a repo carries `.doc-contract.toml`, `docs/roadmap.md`, or `docs/changes/`, or the user says propose a change, start work on X, pick up / reconcile, land or archive a change, are the docs consistent, update the roadmap DAG, or set up doc-contract in this repo — and for the doc taxonomy, persistence classes, change DAG, or capability tripwire."
---

# doc-contract

## Carrier rules

1. The CLI is the only thing you execute: `check`, `update`, `stamp`, `sync`, `reconcile mechanical`,
   `accept`, `begin`, `land`, `reflect`.
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
| pick up / entry | mechanical entry report, the entry judgments in `guides/reconcile.md`, then `doc-contract begin <change>` | CLI + you | accepted |
| land / archive | mechanical exit report, the exit judgments in `guides/reconcile.md`, `land --dry-run`, then `land` | CLI + you | in-progress |
| frozen document edited | `doc-contract stamp <path> --repo-root <repo>` after review | CLI | any |
| set up in this repository | read `guides/install.md` | you | none |
| reflect on project evidence | `doc-contract reflect --repo-root <repo>` | CLI | any |
| author remediation proposal | `doc-contract reflect --write-proposal <id> --repo-root <repo>` | CLI | any |

Lifecycle: `proposed → accept → accepted → begin → in-progress → land → landed`. Entry reconciliation
is bracketed before `begin`; exit reconciliation before `land`. The mechanical half is evidence; the
semantic half is judgment.

## Refusals

- A live contradiction with an ADR or an importer stops the work and is surfaced; never edit the ADR
  or the change to match the other.
- An unaccepted folder never begins work; a blocked one stays under manual handling.
- A trivial edit earns a roadmap line and no folder.
- A not-ready mechanical report stops the transition instead of being improvised around.

## Always true

- Repository selection is always explicit (`--repo-root`) and never inferred.
- The runtime stays stdlib-only: never add a dependency; use `string.Template` and f-strings.
- Scanner output stays value-free: paths, lines, and names only, never values.
- Configuring a source adapter or analyzer authorizes that executable to read only what the operating environment permits; it does NOT make the executable trusted by doc-contract. Operators must review adapter behavior and evidence-store privacy before enabling it. Source adapters own source-specific redaction before output; the core adds structural validation, caps, safe diagnostics, and generated-document secret scanning but does not claim to prove a semantically sensitive non-secret sentence is safe to disclose. Configured argv and adapter/analyzer output never appear in reports or diagnostics. Raw evidence and raw analyzer output are never written to the repository, journal, report, or CLI output. `--allow-external-analysis` is a per-invocation authorization that is never persisted or inferred.

## Read next

`guides/new-change.md` · `guides/reconcile.md` · `guides/install.md` ·
`AGENTS.template.md` (the canonical contract) · `README.md` (configuration and runtime reference).
