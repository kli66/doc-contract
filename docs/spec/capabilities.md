---
persistence: living
---

# Capabilities

## CLI commands

### `check`

Resolve and validate the document graph, required repository boundary, frozen-document hashes, and value-free secret scan. The shared verification boundary runs the configured project capability command unless `--offline` is selected; target project modules are never imported into the resolver process.
Discovery is tracked/declared by default. `--include-untracked` previews and includes provisional
nodes, and warning output separates the tolerated baseline from newly introduced findings.
Dependency topology is mandatory; edge review hashes are advisory unless the manifest selects
`edge_fingerprints = "required"`. Frozen-document `self_hash` validation is always strict.

### `update`

Regenerate the deterministic Mermaid block in the configured roadmap after a successful validation.
With `--include-untracked`, print the provisional node preview before writing the roadmap.

### `stamp`

Record or refresh one active node's dependency fingerprints, including under advisory policy, or
refresh one frozen node's strict `self_hash` after review.

### `sync`

Vendor the complete running package into `.doc-contract/vendor/` and write a deterministic
`.doc-contract-manifest.json` containing that package's version and SHA-256 pins. The installed
command, manifest, and vendored launcher expose the same version without requiring installed
distribution metadata in the target. Sync removes stale files from the owned vendored package tree,
and repeating the command without a package change does not rewrite files.

### `land`

Plan and apply a hash-guarded, resumable change landing. It previews the complete write/move set with `--dry-run`, journals progress in Git metadata, updates the roadmap and dependent fingerprints, and archives tracked or intentionally untracked change folders atomically. A completed landing is an idempotent no-op. Intentionally untracked work requires `--include-untracked`; the plan prints those nodes before mutation, and the outcome reports baseline, new, and resolved warning counts. Landing continues to refresh advisory dependent fingerprints without treating their prior absence as an invalid preflight. Final verification uses the same capability execution and finding vocabulary as `check`; it runs after all mutations, retains the journal on offline or live failure, and does not run for `--dry-run` or an already-landed no-op.

## Verification matrix

Offline resolution always runs. `check --offline` does not request live verification; ordinary `check` and a mutated landing do. Capability mode then determines the shared result:

| Capability mode | Live not requested | Live requested |
| --- | --- | --- |
| `skip` | `live skipped`, no live finding | `live skipped`, no live finding |
| `optional` | `live skipped`, no live finding | execute the command |
| `required` | `live skipped`, `capability-check-required` error | execute the command |

An executed command that exits zero reports `live passed`. A nonzero exit reports `live failed` with a `capability-check-failed` error. An unavailable process or timeout reports `live skipped` with the same error code. The default timeout is 300 seconds. The subprocess runs at the selected repository root with stdin, stdout, and stderr disconnected; diagnostics include only stable status classification, never command arguments, output, environment values, or exception text.

The composed outcome labels offline resolution `offline verified` or `offline failed`, combines offline and live findings, and reports baseline, introduced, and resolved warnings against the caller's baseline. `check` uses its current warnings as that baseline; landing uses its preflight warnings.
