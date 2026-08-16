---
id: reflect-project-evidence
persistence: ephemeral
status: proposed
track: architecture
depends_on:
  - portable-install-contract-convergence
  - unified-offline-live-verification
  - accepted-change-state
files_owned:
  - docs/changes/reflect-project-evidence/change.md
  - src/doc_contract/reflection.py
  - src/doc_contract/config.py
  - src/doc_contract/resolver.py
  - src/doc_contract/transaction.py
  - src/doc_contract/cli.py
  - tests/test_reflection.py
  - tests/test_config.py
  - tests/test_resolver.py
  - tests/test_cli.py
  - docs/spec/capabilities.md
  - README.md
  - SKILL.md
  - docs/roadmap.md
---
# Add project-scoped evidence reflection

Status: Proposed (not accepted) · Proposed 2026-08-06

**Upstream dependencies:** `portable-install-contract-convergence` is landed and establishes
`.doc-contract.toml`, the cwd-independent packaged or vendored CLI, and stdlib-only runtime as the
portable repository boundary. `unified-offline-live-verification` is landed and establishes the
current value-free external subprocess pattern; reflection needs a separate bounded-output adapter
because it must consume evidence, but must preserve that change's no-import, repository-root cwd,
timeout, and redacted-failure rules. `accepted-change-state` is landed and establishes that authored
remediation remains `proposed` until explicit user or reviewer acceptance. All inputs are available.
No ADR exists in this repository, no external evidence source or model provider is required to
implement the adapters and deterministic fixtures, and no live provider gates the local path.

**Dependents:** No current in-repository change or roadmap item depends on reflection. A reflection
may nominate a cross-project or global instruction candidate, but promotion is an external consumer
workflow and does not create a DAG edge or authority in this repository.

**Files owned:** One new reflection application module; reflection configuration; a pure resolver
projection for a new proposed change; the smallest generic transaction extension needed to create a
new proposal safely; CLI dispatch and focused reflection/config/resolver/CLI tests; the capability,
README, skill, and roadmap surfaces. Automatic package discovery means `src/doc_contract/sync.py`
does not need an inventory edit. `scripts/config.py` reads `COMMANDS` dynamically and
`scripts/test_capabilities_coverage.py` already enforces the coupled capability heading, so neither
compatibility file should change. `review-bound-acceptance-plan` overlaps `transaction.py`,
`cli.py`, `tests/test_cli.py`, `docs/spec/capabilities.md`, `README.md`, `SKILL.md`, and the roadmap,
including shared transaction and command-dispatch symbols; the two changes must not execute
concurrently, and whoever lands second must rebase and preserve both contracts.
`canonicalize-roadmap-status-transitions` overlaps `resolver.py`, `tests/test_resolver.py`, the
capability document, and the roadmap but touches different resolver behavior; this is a sequential
soft overlap. `optional-project-memory` and `proportional-accepted-work-contract` overlap only the
roadmap. No target repository's `AGENTS.md`, specification, local skill, or configuration file is an
implementation-owned mutation: reflection proposes those edits inside its governed output.

## Why

Coding agents repeatedly rediscover project-specific problems that are visible only across work
sessions: an instruction is missing or routinely misunderstood; the same build, test, environment,
or setup failure consumes time; a convention is violated repeatedly; or a workflow repeatedly needs
the user to correct the agent. Today doc-contract can validate the repository's declared document
graph and lifecycle mechanics, but it has no product surface for turning historical and current
agent evidence into reviewable project improvements.

Putting semantic reflection inside `resolver.py` would violate the architecture. The resolver is a
deterministic, stdlib-only syntactic engine over repository documents. It deliberately does not
judge prose meaning, import a target project, inspect operator-global state, or embed a model. The
existing capability subprocess cannot simply be reused either: its output streams are disconnected
by design, while reflection must consume bounded, typed evidence and analysis results. The clean
seam is therefore a separate reflection application layer: explicitly configured source adapters
normalize evidence for one selected repository; an explicitly configured analyzer may perform the
semantic synthesis; and stdlib code validates provenance, citations, paths, lifecycle state,
rendering, and proposed mutations deterministically.

The output must strengthen governance rather than bypass it. A reflection can report evidence,
recommend changes to repository instructions/specifications/local skills/configuration, and author a
substantial remediation proposal, but it cannot directly rewrite those durable targets, infer user
acceptance, begin work, or promote a project finding into global policy.

## Requirements

- Expose `doc-contract reflect` as a project-scoped command. Repository selection follows the
  existing `--repo-root`, `--config`, then Git-root precedence and never searches unrelated global
  evidence without passing the selected repository identity to an explicitly configured adapter.
- Keep `resolver.py`, lifecycle planning, and document checking deterministic and stdlib-only. Add no
  model SDK, network client, vector database, transcript parser dependency, or target-project import
  to the package.
- Put evidence collection and semantic analysis behind explicit subprocess contracts. Source
  adapters may understand Codex, Pi, Claude, or other evidence stores; the package knows only a
  versioned normalized record schema. An analyzer may be local or model-backed, but remains an
  external configured process and is never imported into the resolver.
- Treat source material as untrusted data, never as instructions to the deterministic runtime.
  Adapter output cannot choose commands, write paths, lifecycle actions, or raw Markdown. The core
  accepts only typed records and typed candidate fields, then renders its own report/proposal.
- Scope every evidence record to exactly one repository using an adapter name, stable record ID,
  repository identity, observation time, source kind, content digest, and bounded sanitized summary.
  Findings and recommendations must cite one or more accepted evidence IDs. Uncited claims cannot be
  rendered as findings or remediation tasks.
- Support the intended finding classes without making them a closed semantic ontology: repeated
  misunderstandings, ineffective or missing instructions, recurring build/test/environment
  failures, repeated convention violations, and workflows requiring repeated user correction.
  Analyzer-provided frequency/confidence remains evidence, not a deterministic truth claim.
- Produce a versioned reflection report containing the repository identity, selected adapters and
  evidence window, coverage/omission notes, evidence inventory, cited findings, proposed
  `AGENTS.md`/spec/local-skill/config improvements, substantial remediation, and explicitly labelled
  cross-project/global promotion nominations. Reports do not claim that a nomination was promoted.
- Default to read-only planning. An explicit `--write-proposal CHANGE_ID` may create only a new
  `docs/changes/<id>/change.md` plus the matching roadmap entry and generated DAG projection. The
  created item is always `status: proposed` and `Status: Proposed (not accepted)`; no option may
  combine reflection with `accept`, `begin`, implementation, landing, staging, or commit.
- Never apply a recommended edit directly to `AGENTS.md`, `docs/spec/`, a repository-local skill,
  `.doc-contract.toml`, source, or tests. Those paths appear only as proposed targets and
  `files_owned`/task declarations in the authored change item for later review and execution.
- Preserve small findings without forcing ceremony: a report may contain instruction proposals but
  no change item when remediation is not substantial. `--write-proposal` fails if the typed result
  does not contain substantial remediation with requirements, exclusions, owned files, tasks, and
  verification evidence.
- Keep diagnostics value-free. CLI errors may identify adapter name, stable record ID, schema field,
  count, status class, and repository-relative output path, but never raw transcript text, adapter
  stdout/stderr, configured command arguments, environment values, analyzer prompts/responses, or
  rejected candidate prose.

## Design and interfaces

### Architecture split

`src/doc_contract/reflection.py` is an application service beside verification, reconciliation, and
lifecycle code, not a resolver feature. It owns immutable evidence/report/plan types, adapter
execution, schema validation, deterministic normalization and rendering, and proposal execution.
The module calls existing public resolver/config/transaction interfaces and one new pure proposal
projection; `resolver.py` never calls reflection or an analyzer.

The runtime closure remains stdlib-only. A source or analyzer command may have its own dependencies,
but those are operator-selected external programs outside the installed/vendored package and outside
the deterministic checker. `sync` discovers `reflection.py` automatically and must not gain a second
module inventory.

### Configuration and adapter boundary

Extend `.doc-contract.toml` with an optional `[reflection]` table. Absence means the command reports
`reflection-not-configured` without affecting any other command. The table declares deterministic
limits, repository-local instruction/skill target paths, named `[[reflection.sources]]` entries,
and one `[reflection.analyzer]` entry. Each adapter has a non-empty name and an argv array; shell
strings are forbidden. The analyzer additionally declares `trust = "local" | "external"`.

Source adapters run in sorted name order at the selected repository root with a timeout, capped
stdout, and disconnected stderr. The core sends one canonical schema-1 JSON request on stdin with
repository identity, absolute root, the optional absolute `--since YYYY-MM-DD` boundary, and the
configured record/byte limits. They return newline-delimited schema-1 evidence records on stdout.
The core rejects an unknown field that could affect scope, duplicate `(adapter, record_id)` values,
repository mismatch, malformed or future schemas, invalid timestamps/digests, over-limit records,
and output beyond the configured cap.

The analyzer receives one canonical JSON document containing only normalized records and approved
repository-relative durable target paths. It returns schema-1 typed findings, recommendations,
nominations, and an optional remediation candidate. It never returns executable commands or file
contents. An analyzer declared `external` runs only with `--allow-external-analysis`; omitting that
flag is a deterministic refusal, not an offline fallback. Stdout is capped and parsed only after a
zero exit; stderr is always discarded.

### Evidence and report model

Normalized evidence retains enough provenance for independent review without persisting transcripts:

- adapter name and stable adapter-local record ID;
- selected repository identity and a repository-relative subject path when one exists;
- observation timestamp and evidence kind;
- SHA-256 digest and byte length of the source item;
- a bounded, source-sanitized summary plus redaction/omission flags;
- optional causal links such as command category or correction event, represented as typed metadata.

The core canonicalizes records by adapter/name/time/ID, rejects duplicates and out-of-scope records,
and computes a content-addressed reflection ID over the normalized evidence manifest, selected
options, analyzer identity, and typed analyzer result. Repeating an unchanged local run produces the
same JSON report and proposal plan. Dates used in an authored proposal come from an explicit plan
date or the existing date provider once, never from adapter prose.

Text output is a human rendering of the same schema-1 report as `--format json`. It includes
sanitized summaries only when explicitly marked safe by the source and revalidated for limits; the
default citation is adapter/record ID, timestamp, kind, and digest prefix. Raw evidence and raw
analyzer output are never written to the repository, journal, report, or CLI diagnostics.

### CLI and Python API

The command grammar is:

```text
doc-contract reflect [--source NAME ...] [--since YYYY-MM-DD]
                     [--format {text,json}] [--allow-external-analysis]
                     [--write-proposal CHANGE_ID] [--include-untracked]
                     [--repo-root PATH | --config PATH]
```

With no `--source`, all configured sources run in sorted order. Repeating `--source` selects a
deduplicated subset and an unknown name is an argument/configuration failure. Text is the default
format. `--since` is an absolute inclusive date; relative windows such as `7d` are intentionally
excluded from schema 1. `--include-untracked` controls repository preflight/projection exactly as on
existing commands and does not broaden evidence scope. JSON mode emits exactly one object on
stdout. Exit `0` means a valid report/plan (and, when requested, a valid written proposal); exit `1`
means an adapter, evidence, analysis, candidate, preflight, or transaction failure; exit `2` remains
argparse or configuration failure.

Expose immutable Python boundaries analogous to existing planners:

```python
plan_reflection(root, settings, *, sources=(), since=None,
                allow_external_analysis=False,
                proposal_id=None, include_untracked=False,
                date=None) -> ReflectionPlan

execute_reflection(root, settings, *, write_proposal=False,
                   on_plan=None, **plan_options) -> ReflectionOutcome
```

`ReflectionPlan` contains the versioned report, evidence/reflection digests, content-free adapter
statuses, optional proposed change identity, current/projected findings, provisional nodes, and
ordered proposal mutation paths. It contains rendered proposal content privately for execution but
its public JSON form omits raw evidence, candidate prose, document bodies, diffs, individual
preimage/postimage hashes, journal paths, commands, and environment values.

### Deterministic planning and proposal writes

Add a public pure resolver projection that accepts the already-rendered proposed `change.md`, its
new repository-relative path, and one roadmap prose entry. It parses the existing YAML subset,
requires `persistence: ephemeral` and `status: proposed`, verifies the ID/path/roadmap identity,
resolves declared dependencies and `files_owned`, computes the projected graph and Mermaid block,
and returns immutable projected findings without writing. It performs no semantic analysis and is
usable independently of reflection.

Extend the generic transaction layer only as needed to represent creation of a previously absent
regular file/directory alongside a hash-guarded roadmap write. Proposal apply must create a private
journal before the first mutation, reject destination collisions and concurrent roadmap edits,
resume or roll back safely at mutation boundaries, run final `resolve(...,
include_untracked=True)`, and retain failure evidence without staging. Dry-run creates no file,
directory, journal, index entry, or mtime change.

The deterministic renderer, using stdlib templates, owns all Markdown/front matter. Analyzer fields
populate bounded sections for reflection evidence, requirements, proposed instruction/spec/skill/
config improvements, preserved behavior and exclusions, tasks, and verification. The writer adds
the remediation line under the roadmap's existing `## Remediation` section and regenerates only the
marked DAG block. It refuses an existing ID/path, an ambiguous/missing roadmap section, unknown
dependencies, unsafe/absolute/escaping owned paths, duplicate owned paths, or a projected resolver
error. Missing proposed owned files remain the resolver's normal proposal warning.

Before returning or writing, run the existing value-free secret scanner over the rendered Markdown.
Any finding blocks the proposal and is reported only through safe scanner metadata. Final output
also records which source records were redacted or omitted so absence of text is not mistaken for
absence of evidence.

### Failure modes

- Missing reflection configuration, disabled/unknown source, malformed command declaration, or an
  external analyzer without explicit authority fails before adapter execution.
- Source unavailable, timeout, nonzero exit, oversized output, malformed JSONL, schema mismatch,
  duplicate ID, invalid provenance, or repository mismatch fails the run; schema 1 does not silently
  produce a partial report from a biased subset.
- Zero accepted in-scope records returns `insufficient-evidence`, no recommendations, and no
  proposal. The command never converts generic repository state into an evidence-free reflection.
- Analyzer unavailable, timeout, nonzero exit, oversized/malformed output, uncited finding,
  unrecognized evidence ID, unsupported target class, or executable/file-content field fails before
  rendering. Diagnostics do not echo rejected output.
- Secret detection, invalid proposal ID/front matter/dependency/path, existing destination,
  roadmap ambiguity, current resolver error, projected resolver error, or concurrent modification
  prevents proposal mutation or retains the journal for deterministic recovery.
- A successfully written proposal that fails final resolution remains `proposed`, is never accepted
  or begun, and reports the retained transaction state. No failure path applies any recommended
  durable-document edit or promotes a global nomination.

## Privacy, provenance, and authority

- Configuring an adapter authorizes that executable to read only what the operating environment
  permits; it does not make the executable trusted by doc-contract. Documentation must require
  operators to review adapter behavior and evidence-store privacy before enabling it.
- `--allow-external-analysis` is per invocation and cannot be persisted as inferred consent. The
  analyzer receives normalized bounded evidence, not raw source locations or complete transcripts.
- Source adapters own source-specific redaction before output. The core adds structural validation,
  caps, safe diagnostics, and generated-document secret scanning, but does not claim to prove that a
  semantically sensitive non-secret sentence is safe to disclose.
- Every finding, recommendation, task, and nomination carries evidence citations. The report states
  coverage windows, selected/failed sources, and omissions; it does not imply complete historical
  coverage.
- Project recommendations remain project-owned. A global candidate is a nomination with source
  project and evidence provenance only. Another explicitly authorized system owns aggregation,
  de-identification, policy review, acceptance, and promotion across projects.
- Only explicit `--write-proposal` authorizes proposal lifecycle metadata writes. Only the existing
  explicit user/reviewer acceptance workflow may later authorize `doc-contract accept`.

## Preserved behavior and non-goals

- Preserve all existing `check`, `update`, `stamp`, `sync`, `accept`, `begin`, `reconcile`, and
  `land` grammar, results, journals, capability behavior, and exit codes.
- Preserve `.doc-contract.toml` as the sole repository configuration input and the automatic
  vendored runtime closure. Add no client-specific `~/.claude`, Codex, Pi, or project-memory path to
  the deterministic package.
- Preserve the distinction between semantic judgment and mechanical evidence. The analyzer may
  synthesize meaning; the core validates structure/provenance and never claims that a recommendation
  is wise merely because it is well formed.
- Do not make the resolver scan agent histories, general source trees, home directories, model
  caches, or network services. Evidence discovery belongs entirely to configured source adapters.
- Do not build a transcript database, vector index, model host, prompt framework, cross-project
  aggregator, global instruction registry, telemetry service, background daemon, or scheduled job.
- Do not automatically edit durable instructions/specifications/skills/configuration, accept or
  begin generated work, execute remediation, stage/commit files, upload evidence, or promote global
  candidates.
- Do not promise arbitrary source-adapter compatibility in schema 1. Ship protocol fixtures and one
  local deterministic adapter double; source-specific production adapters may live in their owning
  integrations.

## What changes

**Δ ADDED** — Add `doc-contract reflect`, optional reflection adapter configuration, immutable
evidence/report/plan types, bounded source/analyzer subprocess protocols, deterministic report and
proposal rendering, a pure resolver proposal projection, safe proposed-file creation, and focused
privacy/provenance/transaction/installed-vendored tests.

**Δ MODIFIED** — Add `reflect` to the explicit command surface and capability reference; extend
settings validation for the optional reflection table; extend the generic transaction boundary for
new-file creation; document configuration, authority, privacy, report schemas, proposal-only
mutation, and external promotion ownership in `README.md` and `SKILL.md`; situate the change in the
architecture roadmap.

**Δ REMOVED** — Remove no command, lifecycle state, validator, scanner scope, or compatibility path.
Do not move semantic analysis into `resolver.py` or `verification.py`, and do not weaken their
deterministic or value-free contracts.

## Tasks

1. Define immutable reflection settings and validate optional source/analyzer declarations, argv
   arrays, names, trust mode, target paths, limits, and timeouts without exposing configured values
   in failures; preserve equality/replace validation and existing configuration defaults.
2. Implement schema-1 source and analyzer envelopes plus bounded subprocess execution in
   `reflection.py`: explicit repository scope, canonical JSON, stable ordering, no shell, timeout and
   output caps, disconnected stderr, typed redacted failures, external-analysis authority, and no
   target-project imports.
3. Implement evidence normalization, provenance/citation validation, deterministic reflection IDs,
   typed finding/recommendation/nomination models, schema-1 text/JSON reports, coverage and omission
   reporting, and secret-safe rendering without persisting raw source or analyzer output.
4. Add the pure resolver projection for one new proposed change and roadmap line. Keep it generic,
   deterministic, immutable, and independent of reflection semantics; prove projected findings and
   Mermaid output match final on-disk resolution.
5. Extend the transaction primitive for absent-path creation, then implement reflection dry-run,
   content-free planning, explicit proposal apply, journaling/recovery, collision/concurrency
   checks, final include-untracked validation, and no staging. Reconcile the shared transaction
   symbols if `review-bound-acceptance-plan` lands first.
6. Render a substantial remediation as one `docs/changes/<id>/change.md` with evidence citations,
   requirements, proposed durable target improvements, exclusions, files owned, ordered tasks, and
   focused/canonical/live verification. Force proposed status and refuse thin or evidence-free
   remediation. Add only the governed roadmap/DAG metadata required to surface it.
7. Add CLI grammar, text/JSON rendering, safe error/exit mapping, command-set enumeration, and
   unrelated-cwd installed/vendored smoke coverage. Keep every existing command byte-compatible
   unless a separately reviewed shared helper refactor is required.
8. Update `docs/spec/capabilities.md`, `README.md`, and `SKILL.md`; verify the dynamic compatibility
   enumerator and capability tripwire require a new anchored `reflect` heading without changing
   compatibility code. Document that source-specific adapters and global promotion live elsewhere.
9. Run focused reflection/config/resolver/CLI tests, the complete test and lint gates, and the
   include-untracked doc-contract gate. Verify no implementation change reaches `AGENTS.template.md`,
   `guides/`, archived changes, or a target project's proposed durable files.
10. On land, reconcile against any overlapping active CLI/transaction/resolver proposal, archive
    this folder through `doc-contract land`, and retain the report/proposal seam in durable package
    documentation. Do not accept, begin, or execute a reflection-generated remediation as part of
    this change.

## Verify

- **Focused adapter/provenance tests:** local doubles cover stable source ordering, repository
  mismatch, duplicates, invalid/future schemas, timestamp/digest/path checks, output caps, timeout,
  nonzero exits, no-shell execution, disconnected stderr, safe failures, external-analysis consent,
  canonical analyzer input, uncited/unknown evidence rejection, and absence of raw markers from
  reports and diagnostics.
- **Focused report tests:** unchanged normalized evidence and candidate fields yield byte-identical
  schema-1 JSON/text, reflection ID, and proposal plan; every finding/recommendation/task/nomination
  resolves to accepted evidence IDs; zero evidence yields no proposal; coverage and redaction flags
  remain visible without transcript content.
- **Focused proposal tests:** default invocation changes no bytes, mtimes, index, directories, or
  journals. Explicit proposal writing creates only the new proposed `change.md` and roadmap/DAG
  mutations; target `AGENTS.md`/spec/skill/config/source/test bytes remain unchanged. Existing IDs,
  unsafe paths, secrets, malformed/thin remediation, roadmap ambiguity, resolver errors,
  concurrent edits, interruption, and final-validation failure all fail closed and remain
  resumable or cleanly recoverable.
- **Resolver/transaction parity:** the in-memory new-proposal projection equals final on-disk
  resolution; the generic create mutation cannot overwrite an existing path or escape the
  repository and does not weaken lifecycle/landing hash guards or old journal compatibility.
- **CLI and vendoring:** `COMMANDS` and `docs/spec/capabilities.md` both enumerate `reflect`;
  `scripts/test_capabilities_coverage.py` passes; installed and synced vendored commands produce the
  same schema and IDs from an unrelated cwd; `sync` includes `reflection.py` without an inventory
  edit; no model or adapter package enters the manifest.
- **Canonical:** `uv run --group test pytest -q -p no:cacheprovider`, `uv run --group lint ruff
  check --no-cache .`, and `doc-contract check --repo-root . --offline --include-untracked` pass.
- **Live or operator-gated:** no external provider is required for the canonical gate. One explicitly
  authorized external-analyzer smoke may be documented as optional and skipped when its adapter or
  authority is absent; it must use synthetic non-sensitive evidence.
- **Invariant spot-check:** runtime remains stdlib-only, cwd-independent, deterministic outside
  explicit adapters, and value-free on failure; evidence remains repository-scoped and cited;
  recommendations remain proposals; durable targets, lifecycle acceptance, implementation, and
  global promotion all remain outside reflection's authority.

## Residual decisions

No acceptance-blocking product or architecture decision remains. Implementation may choose exact
default byte/record/timeout limits, but must pin bounded values in schema 1, document them, and cover
them with compatibility tests; changing those values later is a versioned interface change, not an
analyzer discretion.
