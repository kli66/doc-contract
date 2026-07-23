<!--
  PORTABLE CONTRACT TEMPLATE — copy this to a new repo's AGENTS.md and fill the {{PLACEHOLDERS}}.
  This is the *invariant* scheme (the taxonomy, persistence model, change protocol, dependency-chain
  + hashing rules). It is repo-agnostic on purpose. Everything project-specific goes in two places,
  never here: (1) the parameter values in .claude/skills/doc-contract/scripts/config.py, and
  (2) the "project traps" in the repo's CLAUDE.md. Delete this comment block after adapting.
-->

# AGENTS.md — how to work in this repo (the operating contract)

The durable operating contract for any agent (Claude or otherwise) touching this repo. `CLAUDE.md`
is a thin pointer here; project-specific traps live there. The doc-contract scheme below is
enforced by the tracked skill at `.claude/skills/doc-contract/` (a stdlib change-DAG resolver + two
coverage tripwires); the contract you are reading is what those tools keep honest.

## The doc taxonomy (where each kind of doc lives)

```
CONTEXT.md              glossary — domain language only
AGENTS.md               this file — the operating contract + change/handoff protocol
CLAUDE.md               thin → @AGENTS.md + project traps
docs/
  adr/                  frozen WHY — decisions; supersede in place (append-only)
  roadmap.md            cross-change order — edges owned by change front-matter, rendered here (living)
  spec/                 the what-now tier: living surface + reference + deferred registers
    capabilities.md     living — tripwire-guarded consumer surface (scripts/test_capabilities_coverage.py)
    README.md           what the spec tier is + the enforcement rule
    <reference>.md      frozen-ish durable evidence/reference behind the ADRs
    <register>.md       deferred backlog — entries gated by a per-entry Trigger
  changes/              substantial in-flight work (propose → apply → archive)
    <name>/             change.md  (split into proposal/design/tasks only if large)
    archive/<date>-<name>/   landed changes
  archive/              superseded history kept for lineage
.claude/skills/
  doc-contract/       the enforcement tooling as a tracked, portable skill (NOT under docs/; docs/
    scripts/            is human-facing only). scripts/{dag.py, doc_tripwire.py} = invariant core;
                        scripts/config.py = this repo's parameter seam; test_*.py = the tripwires.
```
<!-- If this repo keeps its doc tree somewhere other than docs/, repoint DOC_ROOTS in config.py
     to match, and edit the tree above. -->

**Every managed doc carries a `persistence:` header and is a node in the change-DAG resolver** — so
none sits unclassified (`missing-persistence` is an ERROR). That includes the top-level docs above
(`CONTEXT.md`, `AGENTS.md`, `CLAUDE.md`, `docs/roadmap.md`, `docs/spec/{capabilities,README}.md`) and
any other managed doc — enumerate them in `config.ROOT_NODES`. `docs/archive/` lineage is node-ified
too (frozen, `self_hash`-guarded), so no managed doc sits outside the node set.

## What makes this cheap

Every doc carries four attributes; the maintenance model falls out of them:

1. **Question** — exactly one, stated in a header comment.
2. **Persistence** — `frozen` (adr/, archive/ — append-only, ~zero upkeep) · `living` (roadmap,
   capabilities — the *only* docs we keep true) · `ephemeral` (changes/ folders, design notes —
   cost is *disposal* on land, never "keep true") · `deferred` (backlog registers — low-upkeep like
   frozen, but entries accrete and are struck on promotion; never kept true to code).
3. **Canonical owner** — single source for its fact; never maintained in two places.
4. **Forcing function** — what drags the doc back to true. `frozen` → none. `ephemeral` →
   delete-on-land. `living` → a **tripwire** (an automated test — only when content is a function of
   code) or the **change-protocol reconciliation** (the roadmap, refreshed on every change
   entry/exit). `deferred` → a **per-entry Trigger** (a named condition that promotes the entry to a
   `changes/<name>/` folder and strikes it). There is no "review cadence" — every doc is forced by a
   tripwire or a trigger, never by good intentions.

**The rule:** minimise the living set, and no doc is "living on good intentions." A living doc earns
an automated tripwire **only if its content is a function of code** — which is why the
tripwire-guarded living set stays small and specific: `capabilities.md` (the consumer surface,
`scripts/test_capabilities_coverage.py`) **and** the change-DAG linkage
(`scripts/test_change_dag.py`, which makes the roadmap's edges a function of front-matter data) —
while the glossary/ADRs/rationale stay human-judged. Tractability is the sorting function: if you
can't test it, it isn't an enforced-living doc. A doc whose content is *not* a function of code is
not homeless: forward-looking, trigger-gated work is `deferred`, and each entry's **Trigger** is its
forcing function. The set is closed — every doc is `frozen`, `ephemeral`, `living`, or `deferred`.

## Deferred registers — the sanctioned home for trigger-gated backlogs

Forward-looking work parked until a condition makes it relevant — *not* a decision (not an ADR),
*not* the what-now surface (not `capabilities.md`), *not* in-flight (no `changes/` folder yet), and
*not* tripwire-testable. That is the `deferred` class, in a **register** under `docs/spec/`:

- **Canonical owner** — the register file (the *menu* of candidate work). Built behaviour lives
  elsewhere (project memory), never duplicated into the register.
- **Forcing function (per entry)** — a one-line **Trigger:** = the condition that makes the idea
  relevant. When it fires, promote the entry to a `docs/changes/<name>/` folder and strike it.
- **Resurfacing path** — (1) a line in `docs/roadmap.md` (the change protocol's reconciliation walks
  the roadmap, so any agent mid-change meets the register); (2) a line in whatever loads every
  session (e.g. project memory), so a fresh agent outside any change meets it too.

## Change weight — scale ceremony to the work

- **Trivial edit** → a `docs/roadmap.md` line + commit. No folder.
- **Substantial work** → a `docs/changes/<name>/` folder, default a **single `change.md`**
  (`## Why` · `## What changes` [Δ ADDED/MODIFIED/REMOVED] · `## Tasks` · `## Verify`).
- **Rare meta-change** → split into `proposal.md` / `design.md` / `tasks.md`, only when each section
  is genuinely large. Three files is the *ceiling*, not the default.

## Change / handoff protocol (MANDATORY)

Substantial open work lives in a `docs/changes/<name>/` folder — **not** in a root `HANDOFF-*.md`.
A `HANDOFF-*.md` (if one is ever handed to you) is ephemeral scaffolding for the next agent, never
the durable home for open work; ADRs + `docs/roadmap.md` are the source of truth.

**On entry, before touching code:**
1. Check the change's references for consistency against the ADRs (`docs/adr/`) and `docs/roadmap.md`
   — do the task IDs, decisions, file paths, and status claims still match?
2. If material drift has occurred, reconcile it (update the affected ADRs + roadmap first) so you
   start from an accurate map. If a change's detail *contradicts* an ADR, **stop and surface it**.

**On exit, before handing off or finishing:**
1. Update the ADRs + `docs/roadmap.md` to reflect task completion status.
2. On land, `git mv docs/changes/<name>/` → `docs/changes/archive/<date>-<name>/`; capture durable
   findings into ADRs / `docs/spec/` / project memory first, so the archived folder is lineage.

**Dependency-chain rule.** Every change declares its **upstream dependencies** (`depends_on`, *one
direction only* — dependents are computed) and the **files it owns**, in YAML front-matter on its
`change.md`/`proposal.md`. That front-matter is the **canonical owner of order**: `scripts/dag.py`
resolves it into the schedulable DAG (topo-sort + cycle/dangling/overlap/linkage checks) and
`docs/roadmap.md` carries a **generated** Mermaid view of it — the diagram is a rendered view, not the
hand-kept source. Enforced by the `test_change_dag.py` tripwire. The roadmap prose stays the home for
*rationale and narrative*, not the edges.

**Hashing policy (fingerprint-by-default + frozen `self_hash`).** Two content hashes, both over the
*canonical body* (front-matter stripped). (1) **Edge fingerprints:** every `depends_on` edge whose
target is a doc carries that target's content hash at review time — the **default, not opt-in**. A
*missing* fingerprint on an active doc-edge is an **ERROR**; a *stale* one (target moved) is a
**WARN** (re-review, then re-stamp). (2) **`self_hash`:** every `frozen` doc stamps a hash of its own
body; a body edit that doesn't re-stamp is an **ERROR** (append-only enforced). A fingerprint rides
the *depender*; a `self_hash` rides the *frozen target*.

## Executing a change → dispatch is one line

The entry/exit steps above are the *standing* protocol — identical for every change — so a dispatch
prompt never restates them. Work mechanics are also standing: `git mv` to preserve history; keep the
test + lint gate green at each boundary; preserve task detail verbatim; docs/conventions only unless
the change says otherwise; don't commit unless asked; stop and surface any instruction that
contradicts the ADRs / roadmap / code.

Because `CLAUDE.md` imports this file, all of the above is already in every agent's context.
**Dispatch therefore collapses to one line: "Execute `docs/changes/<name>/`."** Landing is completed
through `doc-contract land <folder> --dry-run` followed by the reviewed command without `--dry-run`;
the transaction owns the status, roadmap, fingerprint, journal, and archive boundaries.

<!-- Repo-specific traps (the {{PROJECT}} invariants that are easy to violate) go in CLAUDE.md, not
     here. Keep this file the portable contract; keep CLAUDE.md the thin @AGENTS.md pointer + traps. -->
