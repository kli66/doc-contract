---
id: optional-project-memory
persistence: ephemeral
status: proposed
track: remediation
depends_on:
  - portable-install-contract-convergence
files_owned:
  - AGENTS.template.md
  - guides/new-change.md
  - guides/reconcile.md
  - docs/changes/optional-project-memory/change.md
  - docs/roadmap.md
---
# Make project memory optional operator state

Status: Proposed (not accepted) · Proposed 2026-07-28

**Upstream dependencies:** `portable-install-contract-convergence` is landed and establishes that
the portable operating contract, `.doc-contract.toml`, and the packaged or vendored CLI are the
complete repository-local installation boundary. That input is available. No ADR, runtime change,
external service, or memory provider gates this documentation correction.

**Dependents:** None. This policy is independent of the sibling `accepted-change-state`,
`mechanical-reconciliation`, `concise-landing-output`, and `actionable-lifecycle-diagnostics`
proposals, so no DAG edge is required. They are soft prose overlaps: `accepted-change-state` may
change the same lifecycle progression in the portable contract and authoring/reconciliation guides;
`mechanical-reconciliation` may change reconciliation responsibilities and wording;
`concise-landing-output` may change the reconciliation report/landing description; and
`actionable-lifecycle-diagnostics` may change nearby contract and guide instructions. All share the
roadmap landing surface. Whichever overlapping proposal lands later must reconcile the current
wording and preserve both policies rather than overwriting the earlier edit.

**Files owned:** This proposal; the portable operating-contract template; the proposal-authoring
and entry/exit reconciliation guides; and the roadmap entry/landing metadata. No distribution
README/skill text, design rationale, runtime source, capability surface, ADR, archived change,
target-repository copy of `AGENTS.md`, or automated prose tripwire is owned.

## Why

The portable contract currently makes external project memory part of required repository work in
three places: it names project memory as the canonical home of built behavior, requires it as a
second deferred-work resurfacing path, and requires durable findings to be captured there before a
change can land. The authoring guide repeats the canonical-source claim and puts a memory write in
every generated landing task. The reconciliation guide repeats the landing prerequisite and asks
the exit report to state what was captured to memory.

Those requirements are neither portable nor deterministic. A target repository may have no memory
provider, different agents may see different operator state, and updating such state can require
authority that the repository contract cannot grant. They also invert ownership: built behavior
must remain discoverable from source plus the repository's ADRs, living specifications, roadmap,
and change lineage. An external memory note may help an operator find that evidence, but it cannot
be the only durable owner or evidence that authoring, reconciliation, handoff, or landing is done.

The audit found no mandatory or canonical project-memory language in `SKILL.md` or `README.md`.
`DESIGN-RATIONALE.md` mentions OpenLore's agent-memory design only as factual historical comparison.
Those files need no policy duplication or modification. No current test pins the affected prose,
and the operating contract itself says human-judged documents do not earn code-derived tripwires.

## What changes

**Δ ADDED** — State one portable rule in the operating contract and its two lifecycle guides:
repository source and managed durable documents must be self-contained and sufficient to discover
current behavior, decisions, open work, and landed findings. External/project memory is optional
operator state. It may be consulted only as a noncanonical lead that is verified against repository
evidence, and it may be updated only when the user explicitly authorizes that update. Its absence or
staleness never blocks proposal authoring, acceptance, entry, exit, handoff, landing, deferred-work
resurfacing, or completion reporting.

**Δ MODIFIED** — In `AGENTS.template.md`, make the deferred register the owner only of unpromoted
candidate work; identify source plus ADRs/living specifications as the repository owners of built
behavior; and make the trigger plus `docs/roadmap.md` the complete mandatory resurfacing path.
Require handoffs and landing reconciliation to place every durable finding in the appropriate ADR,
living specification, roadmap entry, or other repository-owned artifact before ephemeral material
is removed or archived. In `guides/new-change.md`, ground current state in repository docs and code,
replace the generated memory-capture task with repository-local durable capture, and keep the
review handback self-contained. In `guides/reconcile.md`, make exit reconciliation and its report
name the repository artifacts updated and the archive path, without requiring a memory action.

**Δ REMOVED** — Remove every active instruction that makes project memory canonical, mandates a
memory read or write, presents memory as a required deferred resurfacing channel, makes it a landing
prerequisite, or asks lifecycle reports to prove memory capture. Do not rewrite frozen archived
changes that historically mention memory, modify the factual OpenLore comparison, duplicate policy
into unaffected distribution docs, or forbid an explicitly authorized operator from maintaining
optional memory outside the contract.

## Tasks

1. Confirm the audit result: active mandatory/canonical memory language exists only in
   `AGENTS.template.md`, `guides/new-change.md`, and `guides/reconcile.md`. Leave `SKILL.md`,
   `README.md`, the factual OpenLore comparison in `DESIGN-RATIONALE.md`, tests, and frozen archived
   change records unchanged.
2. Rewrite the portable deferred-register and change/handoff protocol so repository-local artifacts
   are sufficient: the trigger and roadmap resurface deferred work, and durable findings land in
   ADRs, living specifications, roadmap prose, or another explicitly owned repository document.
3. Rewrite proposal authoring so repository docs and code determine what is built, the standard
   landing task captures durable findings only in repository artifacts, and optional memory can be
   treated only as a verified hint or separately authorized operator action.
4. Rewrite entry/exit reconciliation so archive readiness and the exit report depend only on
   repository evidence. The report names the durable files updated, unresolved items, validation
   result, and archive path; it never requires a memory-capture claim.
5. Reconcile the final prose against any already-landed sibling lifecycle proposal. Preserve the
   accepted-state progression, mechanical/semantic reconciliation split, concise landing output,
   and actionable diagnostics while removing memory requirements; do not create DAG dependencies
   for these soft overlaps.
6. Do not add a prose-content test: this policy is human-judged and not a function of code. Run
   focused text audits plus the repository's existing test, lint, and doc-contract gates to prove
   active lifecycle instructions are consistent and no command/runtime surface changed.
7. On land, add/update the roadmap lineage and archive this folder through `doc-contract land`.
   Do not update any external or project memory unless the user separately and explicitly requests
   it; such an update is outside the landing transaction and cannot affect its result.

## Verify

- `rg -n -i "project memory|memory capture|captur.*memory|memory.*captur|whatever loads every
  session|whatever loads each session" AGENTS.template.md guides/new-change.md
  guides/reconcile.md SKILL.md README.md DESIGN-RATIONALE.md docs tests` finds no active mandatory or
  canonical-memory instruction. Any remaining match is explicitly optional/noncanonical or frozen
  historical evidence.
- A read-through of each lifecycle phase confirms that proposal authoring, acceptance, entry, exit,
  deferred promotion, handoff, landing, and the final report can complete using repository source
  and managed documents alone, with no memory provider configured.
- `uv run --group test pytest -q -p no:cacheprovider`, `uv run --group lint ruff check --no-cache
  .`, and `doc-contract check --repo-root . --offline --include-untracked` pass after the roadmap
  entry is added, with no capability-document update because no CLI command or runtime behavior
  changes.
- `git diff -- SKILL.md README.md DESIGN-RATIONALE.md src tests scripts
  docs/spec/capabilities.md` shows no distribution-guide, design-rationale, runtime, test,
  compatibility, or capability-surface mutation; the only `docs/changes/archive/` differences are
  those produced by the normal landing transaction.
- Invariant spot-check: every required current-state and completion claim has one repository-local
  canonical owner; handoffs and active change folders carry no unique durable knowledge at removal
  or archive time; optional memory remains user-authorized operator state and never a hidden
  prerequisite.
