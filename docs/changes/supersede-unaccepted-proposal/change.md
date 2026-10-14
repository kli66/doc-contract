---
id: supersede-unaccepted-proposal
persistence: ephemeral
status: accepted
track: lifecycle
depends_on:
  - accepted-change-state
  - transactional-land-command
  - discovery-lifecycle-hardening
files_owned:
  - docs/changes/supersede-unaccepted-proposal/change.md
  - src/doc_contract/cli.py
  - src/doc_contract/lifecycle.py
  - src/doc_contract/resolver.py
  - src/doc_contract/landing.py
  - src/doc_contract/transaction.py
  - tests/test_cli.py
  - tests/test_lifecycle.py
  - tests/test_resolver.py
  - tests/test_landing.py
  - docs/spec/capabilities.md
  - README.md
  - SKILL.md
  - AGENTS.template.md
  - docs/roadmap.md
accepted_at: 2026-10-14
---
# Add a supersede verb for never-accepted proposals

Status: Accepted · Accepted 2026-10-14

**Upstream dependencies:** `accepted-change-state` is landed and owns the explicit lifecycle machine
`proposed → accepted → in-progress → landed`, the `accept`/`begin` transitions, and the
in-progress-only landing rule this change extends. `transactional-land-command` is landed and owns the
resumable, dry-runnable, hash-guarded archive transaction whose mutation machinery this change must
reuse rather than re-roll. `discovery-lifecycle-hardening` is landed and owns tracked/declared
discovery, the root-node policy, and the directory-frozen `docs/archive/` lineage tree with strict
`self_hash` that the contract already names as the destination for superseded history. All three
inputs are available; `landed-graph-transition-ownership` (resolver-owned graph/roadmap projection)
and `edge-fingerprint-policy` (strict frozen `self_hash`) are already transitively covered by the
first two and the third respectively. No ADR exists in this repository, and no external service,
live input, or third-party package gates implementation.

**Dependents:** No active change in this repository depends on this item. The two observed callers are
external: in the personal-pi repository, `docs/changes/pi-history-global-promotion-gate/` and
`docs/changes/pi-knowledge-plane/` were retired by a manual `git mv` precisely because this verb does
not exist. No back-link is possible here because those folders live in a different repository.

**Files owned:** The CLI command surface and the lifecycle classification machine that must admit the
new transition; the resolver's `CHANGE_STATUSES` and lineage handling that the open design questions
point at; the landing transaction machinery the verb mirrors; focused CLI/lifecycle/resolver/landing
tests; the capability, README, skill, and portable-contract surfaces; this proposal and roadmap
lineage. Overlaps with the other active folders are recorded below, not assumed absent.

**Overlap check (reverse direction):** `cli.py`, `tests/test_cli.py`, `docs/spec/capabilities.md`,
`README.md`, `SKILL.md`, and `docs/roadmap.md` are also owned by `runtime-source-provenance`,
`review-bound-acceptance-plan`, and `reflect-project-evidence`; those are additive-region soft
overlaps (one new verb, one new capability heading) with no ordering dependency, so whichever item
lands second rebases and preserves all contracts. `resolver.py` and `tests/test_resolver.py` are also
owned by `reflect-project-evidence`, which adds a pure resolver projection for a *new proposed change*
while this change touches `CHANGE_STATUSES` and the `docs/archive/`/`docs/changes/archive/` lineage
classification — a sequential soft overlap, not a shared-symbol conflict. `lifecycle.py` and
`tests/test_lifecycle.py` are also owned by `review-bound-acceptance-plan`, which touches acceptance
plan identity while this change touches the `classify_change` transition gate; again soft.
`AGENTS.template.md` is also owned by `review-bound-acceptance-plan`, `optional-project-memory`, and
`proportional-accepted-work-contract`; these are soft prose overlaps with no ordering dependency.
`managed-document-record-boundary` declares no `files_owned` because its folder currently contains no
node-bearing `change.md`, so it is not yet a resolver node. `landing.py` and `tests/test_landing.py`
are owned by no *active* node (only landed baselines own them historically). One shared-symbol risk is
flagged rather than hidden: `reflect-project-evidence` proposes a generic new-file transaction
primitive in `src/doc_contract/transaction.py`; if the supersede lineage record is written to the
frozen `docs/archive/` tree, it too is a new-file creation, and whoever lands second must reconcile
that primitive. `transaction.py` is therefore **not** claimed here so the two proposals stay
separable until that design question is settled.

## Why

The skill's own carrier rules say: *"Never hand-roll what a verb owns: no manual `git mv`, hash
stamp, roadmap update, or status edit."* The refusals section repeats the boundary. Yet the only
lifecycle terminal is `land`, and `land` refuses every change that is not `in-progress`:
`classify_change` in `src/doc_contract/lifecycle.py` rejects a `proposed` node for any request other
than `accept`, and rejects an `accepted` node for `RECONCILE_EXIT`/`LAND` with
`change-accepted-not-started`. The net effect is that a `proposed` change that was **superseded before
anyone accepted it** has no verb. The only way to retire it is a manual `git mv` of
`docs/changes/<name>/change.md` into a frozen archive record — the exact thing the skill forbids — so
the rule can only be honoured by not doing the task.

This is not hypothetical. On 2026-10-12, in the personal-pi repository, the proposal
`docs/changes/pi-history-global-promotion-gate/` was superseded by a successor design, had never been
accepted or begun, and was retired by manually writing `docs/archive/pi-history-global-promotion-gate.md`
and removing the active folder. The same pattern recurred hours later for
`docs/changes/pi-knowledge-plane/` → `docs/archive/pi-knowledge-plane.md`. Two independent callers of
the missing operation already exist.

The destination is not in doubt; what is missing is the transition that writes the lineage record and
removes the active node. The portable taxonomy already names `docs/archive/` as *"superseded history
kept for lineage"*, and `resolver.py` already treats that tree as directory-frozen with `self_hash`
guarding (its `discover` node-ifies every `docs/archive/*.md` as a `frozen` `archive` node). The
landed-change tree `docs/changes/archive/<date>-<name>/` exists too, but its `classify_change` and
resolver validation demand `status: landed` for archived lineage — false for a proposal that never
landed. `CHANGE_STATUSES` is the closed set `{proposed, accepted, in-progress, blocked, landed}`;
`superseded` is not a member.

`DESIGN-RATIONALE.md` bounds the response: we own a *thin* resolver layer over the SDD spine and keep
the layer thin. A supersede verb is a thin lifecycle extension that reuses the already-landed
transaction and frozen-lineage machinery, not a re-invention of the spine. The work is to close the
one lifecycle hole so the carrier rule becomes mechanically honour-able instead of self-defeating.

## Requirements

Settled intent (independent of the design questions below):

- There is one packaged, executable transition that retires a `proposed` change that was never
  accepted, writing a durable lineage record and removing the active `docs/changes/<name>/` node in a
  single hash-guarded, resumable, dry-runnable transaction.
- The transition requires an explicit `--reason` (or equivalent) so supersession is a reviewed
  human decision, never an inferred cleanup. It records which proposal superseded it, at minimum as
  prose, so lineage stays navigable.
- The transition is a resolver-owned mutation: no manual `git mv`, no hand-edited status, no
  hand-stamped `self_hash`, and no hand-edited roadmap. Roadmap prose and the generated DAG are
  rewritten by the same machinery that `land` uses.
- The transition refuses an `accepted`, `in-progress`, `blocked`, or already-`landed` change; it is
  for the `proposed → superseded` case only. Retiring accepted work is out of scope.
- After the transition, `doc-contract check` must not report the vanished active folder as a
  dangling/orphaned node, and the frozen lineage record must be a valid `frozen` node with a valid
  `self_hash`.
- Machine-refusal: `check` (or the transition preflight) must be able to detect an active change
  folder that disappeared without a corresponding lineage record, so the manual path the carrier rule
  forbids stops passing silently (this is the last design question; its exact shape is open but the
  requirement to close the hole is settled).

## Design questions to settle

These are raised, not silently decided. They are acceptance-relevant because they change the work
contract (paths, enum surface, front-matter grammar):

1. **Shape: new verb vs widened `land`.** Is the right shape `doc-contract supersede <change>
   --reason <text>` (a new command in `COMMANDS`), or an exit disposition on the existing `land`
   (e.g. `land --supersede`/`--disposition supersede`)? A new verb is additive and keeps `land`
   in-progress-only; a widened `land` avoids a second command but relaxes `land`'s precondition.
2. **Status of a superseded node.** `resolver.py`'s `CHANGE_STATUSES` has no `superseded`, and the
   only valid status for archived change lineage is `landed`. Should the enum gain a `superseded`
   member, or should archived lineage nodes stop carrying a change status? Note the frozen
   `docs/archive/` nodes are kind `archive` with no change `status` at all, while
   `docs/changes/archive/` nodes are kind `change` and require `status: landed`.
3. **Where the lineage record lives.** `docs/archive/<name>.md` (the frozen tree, kind `archive`,
   no change status) or `docs/changes/archive/<date>-<name>/` (the landed-change tree, kind
   `change`, requires `status: landed`)? The first matches the taxonomy's "superseded history kept
   for lineage" verbatim and matches how the two observed personal-pi records were manually written;
   the second is the transaction path `land` already owns.
4. **Successor edge.** `depends_on` is one-directional and no `supersedes` field exists in the
   front-matter grammar (`parse_front_matter` accepts only scalar/list/dict). Should a `supersedes`
   field be added to record the successor, or is `--reason` prose enough and the edge stays
   out-of-band?
5. **Machine-refusal of the manual path.** Should there be a check that detects an active change
   folder that vanished without a lineage record? If so, where: a `check` finding, a preflight
   condition, or both? This is the teeth that make the carrier rule enforceable rather than advisory.

### Settled 2026-10-14 (before acceptance)

These answers are part of the accepted contract.

1. **Shape — new verb.** `doc-contract supersede <change> --reason <text>` joins `COMMANDS`. `land`
   keeps its in-progress-only precondition: the exclusions below forbid relaxing it, so a
   `land --supersede` disposition is rejected.
2. **Status — no `CHANGE_STATUSES` member.** The closed set
   `{proposed, accepted, in-progress, blocked, landed}` is unchanged. The lineage record is kind
   `archive`, which the resolver discovers without a change status; a `status: superseded` scalar
   may appear in its front matter as inert documentation only, and no resolver path may validate or
   consume it as a change status.
3. **Location — `docs/archive/<name>.md`.** The directory-frozen tree the taxonomy already names
   (`archive/ superseded history kept for lineage`), matching the two observed manual records. The
   record keeps the retired change's `id`, declares `persistence: frozen`, records `superseded_at`
   and the `--reason` text, and carries a valid `self_hash`. `docs/changes/archive/` stays
   landed-only.
4. **Successor edge — prose only.** `--reason` is required and is recorded verbatim in the frozen
   record, whose body states the superseded date and reason. No `supersedes`/`superseded_by` field
   is added, so the front-matter grammar is unchanged; machine binding is the retained `id` plus
   the `docs/archive/<name>.md` path.
5. **Machine-refusal — resolver `check` ERROR.** A new `roadmap-line-dangling` finding fires when a
   roadmap prose line references a `docs/changes/<name>/` folder that no longer exists and has no
   lineage record. Because every transition preflight runs the same `resolve`, the finding equally
   blocks `supersede`, `land`, and the other lifecycle verbs; the manual `git rm` path stops passing
   silently.

Two consequences are settled with them:

- **Removal is a first-class mutation.** Retiring a change into a flat frozen record deletes the
  resolved `docs/changes/<name>/` working tree, which no existing mutation kind can express. The
  transaction module gains a hash-guarded, resume-idempotent `remove` kind (tracked → `git rm -r`,
  untracked → tree removal) so the supersede work keeps one resumable, dry-runnable transaction;
  `src/doc_contract/transaction.py` therefore joins `files_owned`.
- **Active dependents are not repaired.** A node that still `depends_on` the retired change would
  lose its target; the projection refuses the retirement through existing projected validation
  (`unknown-dependency`) instead of silently rewriting another change's edges.

## Preserved behavior and exclusions

- Preserve the existing `proposed → accept → accepted → begin → in-progress → land → landed`
  lifecycle unchanged for accepted work. This change adds a terminal for the never-accepted case; it
  does not re-litigate `land`, relax its `in-progress` precondition, or add a general "delete change"
  path.
- Preserve `CHANGE_STATUSES` as the machine-readable active/change status set unless design question
  2 is answered by adding a member; do not otherwise alter status validation, roadmap tokenization,
  or the `unknown-change-status` error.
- Preserve the zero-dependency stdlib-only runtime, the cwd-independent `--repo-root`/`--config`
  boundary, and the value-free diagnostics rule (path, ID, status, count only — never the `--reason`
  text echoed back in a failure).
- Preserve the existing `docs/archive/` frozen tree, `self_hash` strictness, and
  `docs/changes/archive/` class retention; do not add a third lineage location.
- Do not accept, begin, implement, or land anything here. This ticket is a proposal only; the verb is
  built in a later dispatched change, not in this one.

## What changes

**Δ ADDED** — One packaged lifecycle transition (new verb or widened `land` disposition — design
question 1) that, for a `proposed` change, writes a durable lineage record (location per design
question 3), records the `--reason`/superseding proposal, rewrites the roadmap prose and generated DAG
through the resolver-owned projection, and removes the active node in one resumable dry-runnable
transaction. A `superseded` enum member and/or a `supersedes` front-matter field, only if the design
questions resolve that way.

**Δ MODIFIED** — `cli.py` (the new verb/disposition in `COMMANDS` and the parser), `lifecycle.py`
(the `classify_change` gate so a `proposed` change can reach the new terminal), `resolver.py`
(`CHANGE_STATUSES` and/or archive-lineage handling per design questions 2–3, plus the
`roadmap-line-dangling` guard per question 5), `landing.py` (the archive transaction machinery,
widened or generalized rather than duplicated), `transaction.py` (the new `remove` mutation kind
the flat frozen record requires), and the coupled tests. `docs/spec/capabilities.md`, `README.md`, `SKILL.md`, and
`AGENTS.template.md` document the verb and the now-enforceable carrier rule.

**Δ REMOVED** — Remove the manual `git mv` path as the only means to retire a never-accepted
proposal. Remove no command, lifecycle state, resolver behavior, or frozen-lineage rule.

## Tasks

1. Settle the five design questions above and record the answers in this ticket before implementation
   begins; they change the work contract.
2. Add the CLI surface (verb or disposition) and its `COMMANDS`/parser entry; extend the focused CLI
   tests with dry-run, apply, refusal, and `--reason` cases.
3. Extend `classify_change` so a `proposed` node reaches the new terminal while `accepted`,
   `in-progress`, `blocked`, and `landed` nodes are still refused; extend the lifecycle diagnostics
   table and tests.
4. Implement the resolver-owned transition (status/enum, lineage destination, roadmap/DAG rewrite)
   reusing the landed transaction machinery; add resolver and landing tests proving the vanished
   active folder and the new frozen lineage node resolve cleanly.
5. If design question 5 resolves to a machine check, implement the vanished-folder-without-lineage
   detection and its `check`/preflight findings.
6. Document the verb in `docs/spec/capabilities.md`, `README.md`, `SKILL.md`, and `AGENTS.template.md`,
   and update the capability-coverage tripwire coupling (`scripts/test_capabilities_coverage.py`)
   accordingly.
7. Regenerate the roadmap DAG with `doc-contract update --repo-root .` after the roadmap line lands.
8. On land: amend no ADR (this repository keeps none); archive this folder through `doc-contract land`
   and confirm the declared not-yet-existing test paths, if any, clear.

## Verify

- `uv run pytest -q` green, including `scripts/test_capabilities_coverage.py`, which stays red until
  task 6 documents the new command — that coupling is the point.
- `doc-contract check --repo-root . --offline` returns 0 errors, with no new warning delta beyond this
  proposal's own baseline entries.
- In a temporary repository, author a `proposed` change, then run the supersede transition with
  `--dry-run` (no bytes, mtimes, or index change) and apply; `doc-contract check` reports no dangling
  node and the frozen lineage record carries a valid `self_hash`. A `proposed` change without
  `--reason` is refused before mutation; an `accepted` or `in-progress` change is refused.
- The manual path is refused: deleting `docs/changes/<name>/` without a lineage record is caught by
  `check`/preflight (if design question 5 resolves so), matching the carrier rule's teeth.
- Installed and synced vendored commands produce the same schema and exit codes from an unrelated
  cwd; no third-party dependency or target-project import enters the package.
- Invariant spot-check: runtime stays stdlib-only and cwd-independent; `--repo-root` is always
  explicit; value-free diagnostics never echo the `--reason` text; `land`'s in-progress-only
  precondition is unchanged for accepted work; `CHANGE_STATUSES` stays a closed machine-readable set;
  frozen `self_hash` strictness is preserved.
