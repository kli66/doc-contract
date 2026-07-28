---
id: concise-landing-output
persistence: ephemeral
status: proposed
track: remediation
depends_on:
  - transactional-land-command
fingerprints:
  transactional-land-command: f97111f3df934220
files_owned:
  - src/doc_contract/cli.py
  - src/doc_contract/landing.py
  - tests/test_cli.py
  - tests/test_landing.py
  - docs/spec/capabilities.md
  - AGENTS.template.md
  - guides/reconcile.md
  - README.md
  - SKILL.md
  - docs/roadmap.md
---
# Make landing output concise by default

Status: Proposed (not accepted) · Proposed 2026-07-28

**Upstream dependencies:** `transactional-land-command` is landed and supplies the immutable
`LandingPlan`, complete precomputed diff, preflight warning baseline, provisional-node preview,
hash-guarded journal, and resumable apply engine this presentation change reuses. Its reviewed body
fingerprint is recorded above. No ADR governs CLI rendering, no external infrastructure is gated,
and the full stdlib-only change is available now.
**Dependents:** None. The accepted-state lifecycle and mechanical-reconciliation proposals being
authored concurrently may also touch `cli.py`, CLI tests, lifecycle guides, capability prose, and
the roadmap, but neither behavior depends on concise landing output. These are soft file overlaps:
whoever lands second must rebase and reconcile the shared parser, help text, and documentation
without adding a false DAG dependency.
**Files owned:** The packaged CLI's `land` option and renderer; the private landing-journal
serialization needed to retain a complete diff across resume; focused CLI and journal regressions;
and the capability, operating-contract, reconcile, README, skill, and roadmap descriptions of the
supported review path. Resolver projection, mutation planning/application, verification policy,
tracking classification, warning classification, and public JSON output are outside this change.

## Why

`doc-contract land` currently prints the complete unified diff on every invocation through
`_print_plan`, together with full input/output tree hashes. The diff is valuable for line-level
review but dominates routine agent output, while the hashes are transaction internals that do not
help an operator decide whether the planned paths and mutation types are correct. The compact facts
needed on every run already exist in `LandingPlan`: source and archive paths, tracking mode,
provisional nodes, ordered mutations, and baseline warnings.

The output must become smaller without weakening the safety boundary. A dry run still needs to show
every path that may change, distinguish writes from moves, identify intentionally untracked inputs,
surface value-free preflight warnings, and offer the exact complete diff on demand. Interrupted
landings also need honest output: `LandingPlan.as_dict()` currently serves the private journal and
stores full mutation content but omits `diff`, while `from_dict()` restores `diff=""`. Merely adding
a CLI flag would therefore claim a complete diff that disappears after resume.

The existing serialization does not justify a public JSON format. It is a recovery schema, not an
operator contract: it includes mutation contents, journal paths, hashes, and implementation-specific
fields; there are no repository callers consuming it; and exposing it would couple automation to
transaction internals while widening the content-output surface. Machine-readable output should be
designed only when a real caller can define a separate redacted, versioned view.

## What changes

**Δ ADDED** — Add `--diff` to `doc-contract land`. Without the flag, print a compact deterministic
plan containing the change ID, source and archive paths, tracking mode, provisional-node state,
total mutation count plus write/move counts, and one ordered path-only line per mutation (`write
<path>` or `move <source> -> <destination>`). Print the preflight warning count in the plan; for a
dry run, follow it with the existing value-free baseline warning diagnostics because there is no
post-mutation warning report. When the diff is omitted, print one short hint that `--diff` adds the
complete patch.

With `--diff`, append the existing `LandingPlan.diff` byte-for-byte after the same summary. The flag
changes presentation only: it does not alter planning, mutation order, journal creation, validation,
exit status, tracking behavior, or whether the command is a dry run. Plan and diff output remain on
stdout; errors and the existing final-validation-failed notice remain on stderr. Warning messages
retain their current value-free finding vocabulary and never include matched credential values.
An already-landed no-op has no active plan and therefore retains its current concise no-mutation
message; `--diff` does not reconstruct a historical patch from the archive.

Retain the precomputed diff in new private landing journals so an interrupted operation can display
the same complete patch when resumed with `--diff`. Read the new field as optional for backward
compatibility: an older journal without it must still resume normally, default compact output must
remain complete, and `--diff` must emit an explicit `complete diff unavailable for legacy journal`
warning on stdout using the existing value-free finding style rather than fabricate a partial patch
or block recovery. The internal journal schema remains private and accepts the additive field
without turning it into a supported external format.

**Δ MODIFIED** — Stop printing input/output tree hashes in ordinary CLI output. Keep both hashes in
`LandingPlan` and the journal because they remain operationally necessary for optimistic
concurrency, recovery, and already-applied mutation recognition. Keep the existing final outcome:
mutated landings report remaining baseline, introduced, and resolved warning counts plus capability
status; dry runs and already-landed no-ops perform no verification or mutation.

Update the documented review flow to distinguish scope review from line-level review: ordinary
`--dry-run` shows the complete mutation inventory, while `--dry-run --diff` adds the full content
patch. Documentation must not imply that the compact default includes a diff or that `--diff`
changes safety or execution semantics.

Explicitly defer `--json`. Do not expose `LandingPlan.as_dict()`, the journal schema, mutation
contents, hashes, or journal paths as a public output contract. A future machine caller may justify
a separately named, schema-versioned, redacted format with an explicit stdout/stderr and stability
policy; this change creates no such API.

**Δ REMOVED** — Remove unconditional full-diff and tree-hash printing from default `land` output.
Remove no plan fields, journal guards, warning details, dry-run behavior, command, compatibility
adapter, or transactional safety check.

## Tasks

1. Add the presentation-only `--diff` parser flag and refactor the CLI renderer into deterministic
   compact-summary, optional-diff, and warning-reporting paths without changing the command set or
   engine callback boundary.
2. Render every planned mutation path in order and aggregate write/move counts from the existing
   immutable `Mutation` objects; include source, archive, tracking, provisional nodes, and preflight
   warning count while omitting hashes and document contents from the default summary.
3. Preserve dry-run warning actionability by printing the existing value-free baseline findings
   after the compact plan; preserve the current post-apply baseline/new/resolved report without
   duplicating preflight warning details during a normal mutated landing.
4. Add the precomputed diff as an optional private journal field and restore it on resume. Keep old
   journals readable and resumable; make `--diff` on a legacy journal explicitly report that the
   complete historical patch is unavailable while continuing the transaction safely.
5. Add CLI tests for default and `--diff` dry runs, tracked and intentionally untracked plans,
   provisional-node and warning rendering, stdout/stderr placement, absence of hashes and diff
   hunks by default, exact diff presence when requested, and unchanged exit/mutation behavior.
6. Add landing serialization/resume tests proving new journals retain the exact diff, legacy
   journals remain readable, interruption recovery remains idempotent, and the presentation flag
   never changes mutation bytes, journal boundaries, or final verification.
7. Update `docs/spec/capabilities.md`, `AGENTS.template.md`, `guides/reconcile.md`, `README.md`, and
   `SKILL.md` with the compact-default and `--diff` review contract; keep `land` as the same
   capability heading because this is an option, not a new command.
8. Run the package and compatibility gates, then land through the transactional command and retain
   this proposal as archived lineage with the roadmap regenerated.

## Verify

- `uv run --group test pytest -q -p no:cacheprovider` and
  `uv run --group lint ruff check --no-cache .` pass, including the CLI command-set and capability
  coverage tripwires.
- A default dry run prints the change/source/archive/tracking facts, provisional nodes, exact
  mutation total and type counts, every ordered mutation path, warning summary/details, and the
  `--diff` hint; it prints no unified-diff hunk, document body, tree hash, journal path, or mutation
  content and leaves files, Git index, journal state, and mtimes unchanged.
- The same dry run with `--diff` prints an identical compact summary followed by the planner's exact
  complete diff, including the archive rename line, while remaining immutable and returning the
  same status.
- A fault-injected landing writes a new journal that restores the exact diff on resume. A fixture
  using the previous journal shape resumes to the same final bytes; default output remains complete,
  and `--diff` reports legacy unavailability without reconstructing misleading output.
- Normal apply, failed final validation, completed no-op, fully tracked, intentionally untracked,
  partial-tracking rejection, concurrent modification, destination collision, and warning-delta
  regressions retain their current behavior and exit codes.
- Invariant spot-check: runtime code remains stdlib-only; repository selection remains explicit and
  fail-closed; hashes stay available to transaction logic but out of routine output; error and
  warning diagnostics remain value-free; and no internal journal representation becomes a public
  JSON compatibility promise.
