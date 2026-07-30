---
persistence: living
---

# Capabilities

## CLI commands

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
refresh one frozen node's strict `self_hash` after review.

### `accept`

Record explicit user or reviewer authorization by transitioning one proposed change to `accepted`.
The command never infers authority, does not accept blocked work, and is idempotent when already
accepted. `--dry-run` and `--include-untracked` use the immutable lifecycle plan boundary.

### `begin`

Start work on one accepted change by transitioning it to `in-progress`, preserving an existing
`accepted_at` date and recording `started_at`. It refuses proposed, blocked, and landed changes,
is idempotent when already in progress, and never runs the target capability subprocess.

### `reconcile`

The `mechanical` grammar reports deterministic entry or exit readiness without writing files, changing the Git index,
creating journals, moving archives, running capability subprocesses, or invoking project tests.
Entry reuses the `begin` planner exactly once; exit reuses the landing planner exactly once. The
schema-1 JSON and compact text formats expose only selected identity/status, scoped structured
findings, content-free mutation paths, provisional nodes, tracking/archive metadata, and the next
lifecycle command. They never expose mutation content, unified diffs, capability arguments/output,
secret values, or arbitrary `gated_on` text. A blocked change reports only whether that key is
present. Exit code `0` means mechanically ready, `1` means deterministic blockers remain, and `2`
means CLI or configuration failure.

### `sync`

Vendor the complete running package into `.doc-contract/vendor/` and write a deterministic
`.doc-contract-manifest.json` containing that package's version and SHA-256 pins. The installed
command, manifest, and vendored launcher expose the same version without requiring installed
distribution metadata in the target. Sync removes stale files from the owned vendored package tree,
and repeating the command without a package change does not rewrite files.

### `land`

Plan and apply a hash-guarded, resumable change landing. The default plan is a compact, deterministic scope review: it identifies the source, archive, tracking mode, provisional nodes, warning count, write/move totals, and every ordered mutation path without printing document content or transaction hashes. `--diff` appends the planner's complete patch to the same summary for line-level review; it changes presentation only. A dry run prints the value-free preflight warning details because no post-mutation warning report follows. Landing journals progress in Git metadata, updates the roadmap and dependent fingerprints, and archives tracked or intentionally untracked change folders atomically. New private journals retain the complete diff across resume; older journals remain resumable and report that the historical diff is unavailable when `--diff` is requested. A completed landing is an idempotent no-op. Intentionally untracked work requires `--include-untracked`, and the outcome reports baseline, new, and resolved warning counts. Landing continues to refresh advisory dependent fingerprints without treating their prior absence as an invalid preflight. Final verification uses the same capability execution and finding vocabulary as `check`; it runs after all mutations, retains the journal on offline or live failure, and does not run for `--dry-run` or an already-landed no-op. The private journal representation is not a public JSON output contract.

## Lifecycle diagnostics

`accept`, `begin`, both mechanical reconciliation phases, and `land` classify the selected change
before whole-repository preflight through one lifecycle interface. Text and schema-1 JSON preserve
the same code, message, and nullable next command.

| Code | Condition | Next command |
| --- | --- | --- |
| `change-proposed-unaccepted` | status is `proposed` but the action requires acceptance or execution | `doc-contract accept CHANGE --dry-run` |
| `change-accepted-not-started` | status is `accepted` but the action requires `in-progress` | `doc-contract begin CHANGE --dry-run` |
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
`land`. Mechanical readiness is evidence only: it never accepts work, judges meaning or task
completion, repairs drift, or authorizes mutation. Blocked changes remain under their existing
manual semantic process.

## Verification matrix

Offline resolution always runs. `check --offline` does not request live verification; ordinary `check` and a mutated landing do. Capability mode then determines the shared result:

| Capability mode | Live not requested | Live requested |
| --- | --- | --- |
| `skip` | `live skipped`, no live finding | `live skipped`, no live finding |
| `optional` | `live skipped`, no live finding | execute the command |
| `required` | `live skipped`, `capability-check-required` error | execute the command |

An executed command that exits zero reports `live passed`. A nonzero exit reports `live failed` with a `capability-check-failed` error. An unavailable process or timeout reports `live skipped` with the same error code. The default timeout is 300 seconds. The subprocess runs at the selected repository root with stdin, stdout, and stderr disconnected; diagnostics include only stable status classification, never command arguments, output, environment values, or exception text.

The composed outcome labels offline resolution `offline verified` or `offline failed`, combines offline and live findings, and reports baseline, introduced, and resolved warnings against the caller's baseline. `check` uses its current warnings as that baseline; landing uses its preflight warnings.
