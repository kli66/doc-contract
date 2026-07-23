---
persistence: living
---

# Capabilities

## CLI commands

### `check`

Resolve and validate the document graph, required repository boundary, frozen-document hashes, and
value-free secret scan. An optional project capability command runs in a subprocess unless
`--offline` is selected; target project modules are never imported into the resolver process.
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

Vendor the running package into `.doc-contract/vendor/` and write a deterministic
`.doc-contract-manifest.json` containing the package version and SHA-256 pins. Repeating the command
without a package change does not rewrite files.

### `land`

Plan and apply a hash-guarded, resumable change landing. It previews the complete write/move set with
`--dry-run`, journals progress in Git metadata, updates the roadmap and dependent fingerprints, and
archives tracked or intentionally untracked change folders atomically. A completed landing is an
idempotent no-op. Intentionally untracked work requires `--include-untracked`; the plan prints those
nodes before mutation, and the outcome reports baseline, new, and resolved warning counts. Landing
continues to refresh advisory dependent fingerprints without treating their prior absence as an
invalid preflight.
