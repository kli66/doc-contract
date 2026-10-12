---
id: skill-routing-surface
persistence: ephemeral
status: landed
track: lifecycle
depends_on:
  - accepted-change-state
  - mechanical-reconciliation
  - actionable-lifecycle-diagnostics
  - portable-install-contract-convergence
files_owned:
  - SKILL.md
  - guides/install.md
  - guides/new-change.md
  - guides/reconcile.md
  - docs/changes/skill-routing-surface/change.md
  - docs/roadmap.md
accepted_at: 2026-10-12
started_at: 2026-10-12
landed_at: 2026-10-12
archive_path: docs/changes/archive/2026-10-12-skill-routing-surface
---
# Route the skill by intent and state its gates

Status: Landed · 2026-10-12

**Upstream dependencies:** `accepted-change-state` and `mechanical-reconciliation` are landed and
supply the transitions (`accept`, `begin`, `land`), the mechanical entry/exit reports, and the
status preconditions the dispatcher must state. `actionable-lifecycle-diagnostics` is landed and
supplies the stable blocker vocabulary the refusal rules mirror (`change-proposed-unaccepted`,
`change-accepted-not-started`, `change-blocked`, `change-already-landed`). `portable-install-contract-convergence`
is landed and establishes the system-CLI-first installation boundary and the packaged/vendored
alternatives the setup guide sequences. All four inputs are available; no ADR exists in this
repository, no runtime behavior changes, and no network, live service, or third-party package gates
implementation.

**Dependents:** No change depends on this item; it changes prose and one new guide only, so it adds
no DAG edge. Soft prose overlaps, none ordering: `runtime-source-provenance`,
`reflect-project-evidence`, and `review-bound-acceptance-plan` all declare `SKILL.md` in
`files_owned`, and `optional-project-memory` declares both guides. This change touches different
regions (the dispatcher's structure, the guides' invocation note) and imposes no ordering, so
whichever item lands second rebases and preserves both contracts. `runtime-source-provenance`
retains sole ownership of the `doc-contract info` row: this change must not add that row, and the
dispatcher leaves the "which runtime am I running" intent to it. Refresh of the deployed per-client
skill copy (`~/.cc-switch/skills/doc-contract`, symlinked into `~/.pi/agent/skills/`) is an
out-of-repository operator step, not owned here; the copy is currently stale, which is exactly the
hazard `runtime-source-provenance` addresses.

**Files owned:** The portable skill's dispatcher (`SKILL.md`), the new setup guide, the invocation
note in the two existing guides, this proposal, and the roadmap entry/DAG. No runtime source, no
test, no capability document, no README, no `AGENTS.template.md`, no design rationale, and no
archived change is owned. `guides/install.md` does not exist yet, so this proposal adds one
`owned-file-missing` baseline warning that clears when the work lands.

## Why

`SKILL.md` is the always-loaded half of this skill: `name` and `description` are the only strings an
agent sees before deciding to load it, and the body is what it reads after. Both are currently
spending their budget on the wrong job, measurably:

- **The routing string is out of spec.** The frontmatter `description` is 1071 characters against
  the Agent Skills limit of 1024 (`MAX_DESCRIPTION_LENGTH`; Pi reports it as a load diagnostic and
  other clients enforce it). Its content is almost entirely an interface catalogue — a verb list
  plus one sentence about `.doc-contract.toml` — with no user-facing trigger phrasing.
- **The body grows to explain a naming collision.** Body-only, the dispatcher went from 1020 words
  across 121 lines at the initial commit to 1426 words across 159 lines (+40% words, +31% lines),
  while the routing description grew from 778 to 1071 characters — past the limit. The most recent
  change to the file, `docs: clarify skill and CLI boundaries`, added 25 lines whose only purpose was
  separating two interfaces that share a name; the dispatcher now carries a 131-word boundary essay,
  and the description that produced the confusion is unchanged.
- **Preconditions and refusals are one file away from the decision.** Status gates
  (proposed→`accept`, accepted→`begin`, in-progress→`land`, entry needs accepted, exit needs
  in-progress) and the stop rules (contradicts a live ADR or importer → stop; unaccepted → never
  begin; trivial → no folder) live only in the guides and in the CLI's diagnostic codes. An agent
  that loaded `SKILL.md` but no guide cannot refuse correctly; it discovers the rule from a failed
  command or not at all.
- **The always-loaded body caches facts that already have owners.** The `.doc-contract.toml` key
  table duplicates README *Configuration contract*; the six-step install duplicates README *Set up a
  fresh repository*; the console block duplicates README *Commands*; the scanner paragraph
  restates `docs/spec/capabilities.md` and the landed secret-handling change; the zero-dependency
  rationale restates `DESIGN-RATIONALE.md` ("Zero-dep is load-bearing"). Setup alone is 362 words —
  25% of the body — for a workflow that runs roughly once per repository.
- **Cached facts are the ones that rot.** `runtime-source-provenance` documents that a per-client
  copy of this skill ships identical prose beside a stale `resolver.py` and stale guides. Prose that
  restates the runtime ages with the copy; prose that routes to a command does not.

The fix is not more prose. It is a dispatcher whose paragraphs are all rules — a decision, a
precondition, or a refusal — with everything descriptive deleted or pointed at its owner.

## What changes

**Δ ADDED** — `guides/install.md`, the bundled once-per-repository setup procedure currently inline
in `SKILL.md` (inventory the CLI, write `.doc-contract.toml`, adapt `AGENTS.template.md`, seed the
roadmap, green the gate, vendor only on explicit request) plus the distribution/target layout
reference that currently has no other home. It states the system-CLI-first rule, the
`edge_fingerprints` and capability-mode choices in one sentence each, delegates the full key
reference to README *Configuration contract*, and ends by pointing at the two lifecycle guides.

The rewritten dispatcher itself is the rest of the delta, at roughly 65 lines and 600 words of body.
Its shape, to be reviewed as the substance of this change:

- **Description (routing only, ≤600 characters, no verb catalogue):** "Route a documentation
  lifecycle: author a change, reconcile entry/exit, accept, begin, land, and check the doc graph.
  Use when a repo carries `.doc-contract.toml`, `docs/roadmap.md`, or `docs/changes/`, or the user
  says propose a change, start work on X, pick up / reconcile, land or archive a change, are the docs
  consistent, update the roadmap DAG, or set up doc-contract in this repo — and for the doc taxonomy,
  persistence classes, change DAG, or capability tripwire."
- **Three carrier rules, replacing the boundary essay:** the CLI is the only thing you execute
  (`check`, `update`, `stamp`, `sync`, `reconcile mechanical`, `accept`, `begin`, `land`); the skill
  verbs `new-change`, `reconcile semantic`, and `install` have no shell form and must never be
  attempted as `doc-contract <verb>`; never hand-roll what a verb owns (no manual `git mv`, stamp,
  roadmap update, or status edit).
- **One invocation line, stated once:** the skill verbs are named by verb, and the per-client
  spelling is given once (Pi: `/skill:doc-contract <verb> …`; a client that exposes skills as slash
  commands: `/<skill> <verb> …`; the runtime: `doc-contract <cli-verb> …`). The compatibility alias
  that let the bare slash form mean the semantic workflow is no longer advertised; nothing
  executable changes.
- **An intent table**, one row per user intent with four columns — intent, the exact invocation or
  guide to read, carrier (you / CLI), and required status. Rows: docs consistent → `doc-contract
  check --repo-root <repo> --offline`; roadmap DAG stale → `doc-contract update`; propose / start
  work on X → `guides/new-change.md`, stopping at `Proposed`; review approved → `doc-contract accept
  <change>`; pick up / entry → mechanical report, `guides/reconcile.md` entry judgments,
  `doc-contract begin <change>`; land / archive → mechanical exit report, exit judgments, `land
  --dry-run` then `land`; frozen document edited → `doc-contract stamp <path>` after review; set up
  in this repository → `guides/install.md`.
- **The lifecycle on one line:** `proposed → accept → accepted → begin → in-progress → land →
  landed`, with entry reconciliation bracketed before `begin` and exit reconciliation before
  `land`, and the standing rule that the mechanical half is evidence while the semantic half is
  judgment.
- **Four refusal rules:** a live contradiction with an ADR or an importer stops the work and is
  surfaced, and neither the ADR nor the change is edited to match; an unaccepted folder never begins
  work and a blocked one stays under manual handling; a trivial edit earns a roadmap line and no
  folder; a not-ready mechanical report stops the transition rather than being improvised around.
- **Three always-true rules:** repository selection is always explicit and never inferred; the
  runtime stays stdlib-only (never add a dependency, use `string.Template` and f-strings); scanner
  output stays value-free (paths, lines, and names only, never values).
- **A read-next list:** `guides/new-change.md`, `guides/reconcile.md`, `guides/install.md`,
  `AGENTS.template.md` (the canonical contract), `README.md` (configuration and runtime reference).

**Δ MODIFIED** — `guides/new-change.md` and `guides/reconcile.md`: their three-line interface note
becomes one line naming the skill verb and referring to the dispatcher's invocation line for the
per-client spelling, so the guides stop asserting one client's syntax as *the* syntax. `SKILL.md`'s
remaining section skeleton is replaced by the shape above; nothing in the runtime, the CLI, the
configuration grammar, or the target-repository contract changes.

**Δ REMOVED** — From `SKILL.md` only, with each fact already owned elsewhere: the
`.doc-contract.toml` key table (README *Configuration contract*), the inline six-step install
(→ `guides/install.md`), the console command block beyond `check` and `update` (README *Commands*),
the `distribution/` and `target repository/` layout tree (→ `guides/install.md`), the secret-scan
scope exposition (README, `docs/spec/capabilities.md`), the zero-dependency rationale
(`DESIGN-RATIONALE.md`), the invariant-versus-parameter rationale and the runtime-source tree
(`DESIGN-RATIONALE.md`, README), the 131-word skill/CLI boundary essay (→ the three carrier rules),
and the distribution-specific `uv run pytest -q` gate line, which leaks this repository's development
command into every target repository that installs the skill.

Review points stated rather than silently decided: the dispatcher keeps `check` as a CLI row rather
than a skill workflow, so the skill's own verb list shrinks to `new-change`, `reconcile semantic`,
and `install` — the carrier column becomes the only taxonomy and no CLI command is re-labelled as a
skill sub-command. `install` remains a skill verb with no shell form, now backed by a guide rather
than inline prose. Prose deletion is re-homing, not loss: every removed fact is named above with its
surviving owner, and the two lifecycle guides keep their substance unchanged apart from the
invocation note.

## Tasks

1. [x] Rewrite `SKILL.md`: frontmatter description to the routing text above; body to the carrier
   rules, invocation line, intent table, lifecycle line, refusal rules, always-true rules, and
   read-next list. Assert the description is ≤600 characters and the body is ≤90 lines before
   continuing. (Description 471; body 51 lines.)
2. [x] Author `guides/install.md`: inventory the CLI first (`command -v doc-contract`,
   `doc-contract --version`), reuse a working system CLI and never install a second copy, write
   `.doc-contract.toml` with the minimum keys, adapt `AGENTS.template.md` to `AGENTS.md`, seed
   `docs/roadmap.md` with its two generated-DAG markers, green the gate with
   `doc-contract check --repo-root <repo> --offline`, and vendor only on explicit request. Include
   the distribution/target layout block and delegate the full key reference to README.
3. [x] Edit the interface note in `guides/new-change.md` and `guides/reconcile.md` to one line
   naming the skill verb and referring to the dispatcher for per-client spelling.
4. [x] Cross-check every invocation in the new dispatcher against `doc-contract --help`: each CLI
   verb named must exist, and each skill verb named must have no CLI counterpart. Record the
   comparison in the landing report. (`check`, `update`, `stamp`, `sync`, `reconcile mechanical`,
   `accept`, `begin`, `land` parse; `new-change`, `reconcile semantic`, `install` do not.)
5. [x] Add the roadmap line for this change under the Lifecycle track, then regenerate the DAG with
   `doc-contract update --repo-root .`.
6. [x] On land: archive this folder per the contract, and note for the operator that the deployed
   per-client skill copy must be refreshed (`~/.cc-switch/skills/doc-contract`) — an
   out-of-repository step this change does not own.

## Verify

- `doc-contract check --repo-root . --offline` returns 0 errors. The only warning delta is this
  proposal's `owned-file-missing` baseline entry for `guides/install.md`, which clears on landing;
  the four existing baseline warnings are unchanged.
- `uv run pytest -q` stays green. No test pins skill prose, so this is a regression guard on the
  runtime, not a check on the rewrite.
- Routing assertions on the rewritten file: `python -c` reads the frontmatter and asserts the
  description length is ≤1024 (the spec limit that currently fails) and ≤600 (this change's budget);
  `wc -l` on the body is ≤90 lines against today's 159.
- Invocation accuracy: for every verb written in the dispatcher, `doc-contract <verb> --help`
  succeeds for the CLI verbs and fails to parse for `new-change`, `reconcile semantic`, and
  `install` — the property the carrier rules assert.
- Manual read-through of the rewritten dispatcher for the three shapes this change exists to
  produce: no descriptive paragraph without a decision, precondition, or refusal; no fact restated
  from README, `docs/spec/capabilities.md`, or `DESIGN-RATIONALE.md`; every guide pointer reachable
  from the table.
- Invariant spot-checks: the zero-dependency runtime is untouched (`dependencies = []` unchanged, no
  new runtime import), the installed CLI surface is unchanged (`doc-contract --help` identical before
  and after), and the target-repository contract is unchanged (`AGENTS.template.md` byte-identical).
