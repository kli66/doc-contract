---
persistence: living
---

# Capabilities

## CLI commands

This section documents only the installed or vendored `doc-contract` executable. The
`/doc-contract new-change <intent>` authoring workflow belongs to the agent skill and is
intentionally not an executable CLI command; it will not appear in `doc-contract --help`.

### `check`

Resolve and validate the document graph, required repository boundary, frozen-document hashes, and value-free secret scan. One ordered managed-document discovery result supplies both graph validation and scanning; repository source, `.env`, generated output, dependency trees, and checked-out submodules are not separate scan inputs. The shared verification boundary runs the configured project capability command unless `--offline` is selected; target project modules are never imported into the resolver process.
Discovery is tracked/declared by default and includes companion Markdown inside selected change folders. `--include-untracked` previews and includes provisional nodes in both validation and scanning, and warning output separates the tolerated baseline from newly introduced findings.
Dependency topology is mandatory; edge review hashes are advisory unless the manifest selects
`edge_fingerprints = "required"`. Frozen-document `self_hash` validation is always strict.

### `update`

Regenerate the deterministic Mermaid block in the configured roadmap after a successful validation.
With `--include-untracked`, print the provisional node preview before writing the roadmap.

### `stamp`

Record or refresh one active node's dependency fingerprints, including under advisory policy, or
refresh one frozen node's strict `self_hash` after review. The operator names the single node, so
`--include-untracked` admits one provisional (untracked) change node to discovery without printing
a preview; the outcome line reports the result. Without the flag, an untracked node is reported as
an unknown node id and nothing is written.

### `accept`

Record explicit user or reviewer authorization by transitioning one proposed change to `accepted`.
The command never infers authority, does not accept blocked work, and is idempotent when already
accepted. `--dry-run` and `--include-untracked` use the immutable lifecycle plan boundary.
One validated plan atomically canonicalizes the selected roadmap status presentation together with
the change metadata, the generated DAG state, and the affected dependent fingerprints. The
recognized source-status presentation is replaced wholesale by `(accepted)`, so an in-presentation
annotation such as `depends on …` or `not accepted` is dropped while the change reference and the
surrounding rationale are preserved byte-for-byte. A located roadmap line whose status has no
single unambiguous rewritable presentation is rejected as `roadmap-invalid` during planning, before
projected repository validation and before any mutation.

`--format {text,json}` selects the output format. The default `text` produces the existing
human-readable summary. `json` produces exactly one versioned JSON object with schema_version=1,
kind=acceptance-transition, a content-free plan projection, and execution status. JSON output
excludes document bodies, mutation contents, unified diffs, individual before/after hashes,
journal paths, arbitrary gate text, capability arguments or output, and secret values.

`--expect-plan-id ID` enables optimistic concurrency control. The identifier must be in canonical
form `sha256:<64 lowercase hex>`. When supplied, the command recomputes the plan identifier and
compares it to the expected value before any mutation. A mismatch reports execution.status=rejected,
expectation=mismatch, and exits nonzero without creating a journal or applying any mutation.
A malformed identifier is rejected without echoing the supplied string. A dry-run with a matching
expectation reports not-applied/matched and exits 0.

The `plan_id` identifies the complete acceptance transaction, including the selected change,
transition date, options, roadmap projection, and dependent fingerprint refreshes. It is distinct
from the accepted-document identity: the exact accepted `change.md` bytes plus their SHA-256 digest
identify the accepted work contract, while `plan_id` identifies the ephemeral operation manifest.
A downstream consumer may capture the accepted bytes and digest outside the mutable index and
proceed through `begin` and implementation without an intermediate commit; acceptance remains
logically prior to implementation, and the runtime never stages or commits Git changes.

**Already-applied expectation limitation:** When a change is already accepted and no active journal
exists to prove the original plan, a supplied `--expect-plan-id` cannot be verified. The command
reports `execution.status: already-applied` and `execution.expectation: not-verifiable`, then exits
0. The expectation is not compared against a recomputed plan because the original transaction
context is unavailable.

**Path-scoped transfer or staging:** The mutation paths in the plan manifest describe what the
acceptance invocation will mutate, but they do not guarantee exact transfer or staging when a
planned path contains pre-existing mixed edits. Path-scoped transfer or staging is exact only from
an isolated or otherwise owned baseline, or when the caller controls patch transfer or staging.
Documentation must state this limitation; the operation manifest is an ephemeral computed
description, not an ownership boundary.

**Optional checkpoint policy:** The provider never requires a checkpoint. A downstream consumer may
capture the accepted bytes and digest outside the mutable index and proceed through `begin` and
implementation without an intermediate commit. Acceptance remains logically prior to implementation,
and the runtime neither stages nor commits Git changes.

### `begin`

Start work on one accepted change by transitioning it to `in-progress`, preserving an existing
`accepted_at` date and recording `started_at`. It refuses proposed, blocked, and landed changes,
is idempotent when already in progress, and never runs the target capability subprocess.
The same atomic plan canonicalizes the selected roadmap status presentation together with the
change metadata, the generated DAG state, and the affected dependent fingerprints, replacing the
recognized accepted presentation wholesale with `(in-progress)`. In-presentation annotations are
dropped while the change reference and the surrounding rationale are preserved byte-for-byte, and a
located roadmap line without a single unambiguous rewritable presentation is rejected as
`roadmap-invalid` during planning, before projected repository validation and before any mutation.

### `reconcile`

The `mechanical` grammar reports deterministic entry or exit readiness without writing files, changing the Git index,
creating journals, moving archives, running capability subprocesses, or invoking project tests.
Entry reuses the `begin` planner exactly once; exit reuses the landing planner exactly once. The
schema-1 JSON and compact text formats expose only selected identity/status, scoped structured
findings, content-free mutation paths, provisional nodes, tracking/archive metadata, and the next
lifecycle command. They never expose mutation content, unified diffs, capability arguments/output,
secret values, or arbitrary `gated_on` text. Text findings name their offending node ids in a
trailing `subjects: …` suffix, repository-scope warnings are printed individually instead of being
collapsed into a count, and a code-prefixed restatement is suppressed for display when another
ERROR-level finding already carries the detail. A repository preflight failure surfaces the
value-free real error kind (node ids, paths, and error names only) instead of a generic placeholder;
a parse failure whose exception carries no offender identity is not attributed to any node. A
blocked change reports only whether that key is
present. Exit code `0` means mechanically ready, `1` means deterministic blockers remain, and `2`
means CLI or configuration failure.

### `sync`

Vendor the complete running package into `.doc-contract/vendor/` and write a deterministic
`.doc-contract-manifest.json` containing that package's version and SHA-256 pins. The installed
command, manifest, and vendored launcher expose the same version without requiring installed
distribution metadata in the target. Sync removes stale files from the owned vendored package tree,
and repeating the command without a package change does not rewrite files.

### `land`

Plan and apply a hash-guarded, resumable change landing. The default plan is a compact, deterministic scope review: it identifies the source, archive, tracking mode, provisional nodes, warning count, write/move totals, and every ordered mutation path without printing document content or transaction hashes. `--diff` appends the planner's complete patch to the same summary for line-level review; it changes presentation only. A dry run prints the value-free preflight warning details because no post-mutation warning report follows. Landing journals progress in Git metadata, updates the roadmap and dependent fingerprints, and archives tracked or intentionally untracked change folders atomically. New private journals retain the complete diff across resume; older journals remain resumable and report that the historical diff is unavailable when `--diff` is requested. A completed landing is an idempotent no-op. Intentionally untracked work requires `--include-untracked`, and the outcome reports baseline, new, and resolved warning counts. A landing blocked by a `LandingError` reports the failure under its stable code (never relabelled as a transaction type) and prints each attached resolver finding with its code, message, and node-id subjects. Landing continues to refresh advisory dependent fingerprints without treating their prior absence as an invalid preflight. Final verification uses the same capability execution and finding vocabulary as `check`; it runs after all mutations, retains the journal on offline or live failure, and does not run for `--dry-run` or an already-landed no-op. The private journal representation is not a public JSON output contract.

### `supersede`

Retire a never-accepted `proposed` change into a frozen lineage record in one hash-guarded,
resumable, dry-runnable transaction. `--reason` is required and is recorded verbatim in the record
body; it never appears in CLI output. The transition removes the active `docs/changes/<name>/` tree,
retargets its roadmap prose line to `docs/archive/<name>.md` with `(superseded)`, regenerates the
generated DAG, and creates the frozen record last (staged in the Git index for tracked plans) —
removal first, record creation last, so every interruption boundary is resolvable or fails closed.
It refuses `accepted`, `in-progress`, `blocked`, and `landed` changes, and refuses while any active
node still `depends_on` the retired id; a preflight-blocking `LandingError` is reported under its
stable code with each attached resolver finding's code, message, and node-id subjects, never
relabelled as a transaction type. `--dry-run` prints a value-free plan summary and mutates
nothing; `--include-untracked` governs provisional work. A `roadmap-line-dangling` ERROR blocks the
manual `git rm` path that this verb replaces. The record carries `persistence: frozen`, a strict
`self_hash`, and an inert `status: superseded` scalar that no resolver path consumes as a change
status.

### `reflect`

Reflect on project-scoped evidence and optionally author a remediation proposal. The command runs configured source adapters to collect normalized evidence records, optionally runs a configured analyzer for semantic synthesis, and produces a versioned reflection report. Evidence collection and analysis are external subprocesses that are never imported into the resolver; the runtime remains stdlib-only.

`--source` selects a subset of configured adapters; omitting it runs all sources in sorted order. `--since` provides an inclusive date boundary for evidence. `--format` selects text or JSON output. `--allow-external-analysis` authorizes an analyzer declared with `trust = "external"` for this invocation only; omitting it is a deterministic refusal, not an offline fallback.

With `--write-proposal CHANGE_ID`, the command may create a new proposed change item if the reflection produces substantial remediation with requirements, tasks, and files owned. The created item is always `status: proposed` and `Status: Proposed (not accepted)`; no option combines reflection with `accept`, `begin`, implementation, or landing. The proposal is written transactionally with a private journal; secrets detected in the rendered proposal block creation. Zero accepted in-scope evidence returns `status: insufficient-evidence` with no recommendations or proposal; requesting `--write-proposal` in this state exits 1.

Absence of a `[reflection]` table in `.doc-contract.toml` exits 2 with `reflection-not-configured` before any adapter execution. An unknown `--source` name or malformed adapter declaration also exits 2. Adapter timeout, nonzero exit, oversized output, malformed JSONL, schema mismatch, duplicate record ID, repository mismatch, or evidence over limit exits 1 with a value-free diagnostic. Diagnostics identify adapter name, record ID, schema field, count, and status class only; they never include raw transcript text, adapter stdout/stderr, configured command arguments, environment values, analyzer prompts/responses, or rejected candidate prose.

## Lifecycle diagnostics

`accept`, `begin`, `supersede`, both mechanical reconciliation phases, and `land` classify the
selected change before whole-repository preflight through one lifecycle interface. Text and
schema-1 JSON preserve the same code, message, and nullable next command.

| Code | Condition | Next command |
| --- | --- | --- |
| `change-proposed-unaccepted` | status is `proposed` but the action requires acceptance or execution | `doc-contract accept CHANGE --dry-run` |
| `change-accepted-not-started` | status is `accepted` but the action requires `in-progress` | `doc-contract begin CHANGE --dry-run` |
| `change-not-proposed` | `supersede` requested a change whose status is `accepted` or `in-progress` | none |
| `change-blocked` | status is `blocked` | none |
| `change-already-landed` | valid archive lineage matches the normalized ID or archive path | none |
| `change-untracked-excluded` | the selected candidate is excluded by tracked-only discovery | replay the same normalized command with `--include-untracked` |
| `change-front-matter-missing` | the selected folder has no node-bearing Markdown front matter | none |
| `change-front-matter-invalid` | selected front matter is malformed, ambiguous, or lacks valid identity/status | none |
| `change-ref-wrong-folder` | a path-shaped reference is not an exact contained active/archive folder | none |
| `change-ref-unknown` | no active candidate or valid archive lineage matches | none |

Messages contain only normalized change ID, repository-relative path, canonical lifecycle status,
and `gate_present=true|false`; they never include raw input, front matter, parser fragments, body
content, gate text, environment values, or subprocess output. Repeated `land` emits
`INFO: [change-already-landed]` and exits `0`. Every classified blocker emits
`ERROR: [<stable-code>]` and exits `1`; argparse and configuration failures alone use exit `2`.

The supported lifecycle is author → explicit user/reviewer acceptance → `accept` → mechanical then
semantic entry reconciliation → `begin` → work → mechanical then semantic exit reconciliation →
`land`. A never-accepted `proposed` change retires through `supersede` with a required `--reason`;
`land` stays `in-progress`-only. Mechanical readiness is evidence only: it never accepts work,
judges meaning or task completion, repairs drift, or authorizes mutation. Blocked changes remain
under their existing manual semantic process.

## Verification matrix

Offline resolution always runs. `check --offline` does not request live verification; ordinary `check` and a mutated landing do. Capability mode then determines the shared result:

| Capability mode | Live not requested | Live requested |
| --- | --- | --- |
| `skip` | `live skipped`, no live finding | `live skipped`, no live finding |
| `optional` | `live skipped`, no live finding | execute the command |
| `required` | `live skipped`, `capability-check-required` error | execute the command |

An executed command that exits zero reports `live passed`. A nonzero exit reports `live failed` with a `capability-check-failed` error. An unavailable process or timeout reports `live skipped` with the same error code. The default timeout is 300 seconds. The subprocess runs at the selected repository root with stdin, stdout, and stderr disconnected; diagnostics include only stable status classification, never command arguments, output, environment values, or exception text.

The composed outcome labels offline resolution `offline verified` or `offline failed`, combines offline and live findings, and reports baseline, introduced, and resolved warnings against the caller's baseline. `check` uses its current warnings as that baseline; landing uses its preflight warnings.
