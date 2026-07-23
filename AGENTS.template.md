---
persistence: living
---
<!--
  PORTABLE CONTRACT TEMPLATE — copy this to a new repo's AGENTS.md and fill the {{PLACEHOLDERS}}.
  This is the *invariant* scheme (the taxonomy, persistence model, change protocol, dependency-chain
  + hashing rules). It is repo-agnostic on purpose. Put project-specific managed-document paths and
  check commands in .doc-contract.toml; put project traps in the agent-client file your repo uses,
  if any. Delete this comment block after adapting.
-->

# AGENTS.md — how to work in this repo (the operating contract)

The durable operating contract for any agent touching this repo. Client-specific instruction files
are optional thin pointers here plus project traps; they do not configure doc-contract. The
stdlib-only packaged or vendored `doc-contract` CLI reads `.doc-contract.toml` and keeps this
contract's mechanically checkable parts honest.

## The doc taxonomy (where each kind of doc lives)

```
CONTEXT.md              glossary — domain language only
AGENTS.md               this file — the operating contract + change/handoff protocol
.doc-contract.toml      canonical resolver configuration
docs/
  adr/                  frozen WHY — decisions; supersede in place (append-only)
  roadmap.md            cross-change order — edges owned by change front-matter, rendered here (living)
  spec/                 the what-now tier: living surface + reference + deferred registers
    capabilities.md     living — optional project-check-guarded consumer surface
    README.md           what the spec tier is + the enforcement rule
    <reference>.md      frozen-ish durable evidence/reference behind the ADRs
    <register>.md       deferred backlog — entries gated by a per-entry Trigger
  changes/              substantial in-flight work (propose → apply → archive)
    <name>/             change.md  (split into proposal/design/tasks only if large)
    archive/<date>-<name>/   landed changes
  archive/              superseded history kept for lineage
.doc-contract/          optional vendored CLI + stdlib package written by `doc-contract sync`
```
<!-- Agent-client pointer files are optional and may be added to the tree when the repo uses them. -->

**Every managed doc carries a `persistence:` header and is a node in the change-DAG resolver** — so
none sits unclassified (`missing-persistence` is an ERROR). That includes the top-level docs above
(`CONTEXT.md`, `AGENTS.md`, `docs/roadmap.md`, `docs/spec/{capabilities,README}.md`) and
any other managed doc — enumerate them in `.doc-contract.toml` `root_nodes`. Roots are required by
default; only IDs explicitly listed in `optional_roots` may be absent, and their omission is still
reported. `docs/archive/` lineage is node-ified too (frozen, `self_hash`-guarded), so no managed doc
sits outside the node set.

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
tripwire-guarded living set stays small and specific: `capabilities.md` (the consumer surface, when
configured through `.doc-contract.toml`'s capability command) **and** the packaged change-DAG linkage
check, which makes the roadmap's edges a function of front-matter data — while the
glossary/ADRs/rationale stay human-judged. Tractability is the sorting function: if you can't test
it, it isn't an enforced-living doc. A doc whose content is *not* a function of code is not
homeless: forward-looking, trigger-gated work is `deferred`, and each entry's **Trigger** is its
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
3. Resolve the change with `--include-untracked` when it is still provisional. The preflight reports
   missing `files_owned` paths, untracked nodes, and dependency/hash drift before implementation.

**On exit, before handing off or finishing:**
1. Update the ADRs + `docs/roadmap.md` to reflect task completion status.
2. On land, `git mv docs/changes/<name>/` → `docs/changes/archive/<date>-<name>/`; capture durable
   findings into ADRs / `docs/spec/` / project memory first, so the archived folder is lineage.

**Dependency-chain rule.** Every change declares its **upstream dependencies** (`depends_on`, *one
direction only* — dependents are computed) and the **files it owns**, in YAML front-matter on its
`change.md`/`proposal.md`. That front-matter is the **canonical owner of order**: `doc-contract`
resolves it into the schedulable DAG (topo-sort + cycle/dangling/overlap/linkage checks) and
`docs/roadmap.md` carries a **generated** Mermaid view of it — the diagram is a rendered view, not the
hand-kept source. Enforced by `doc-contract check`. The roadmap prose stays the home for *rationale
and narrative*, not the edges.

**Hashing policy (advisory edge review + frozen `self_hash`).** Dependency topology is always
mandatory; its review fingerprints are metadata. With the default `edge_fingerprints = "advisory"`,
an absent edge hash is accepted, while an explicit empty, `PENDING`, malformed, or stale value is a
**WARN**. Repositories that set `edge_fingerprints = "required"` make absent and invalid active-edge
hashes **ERROR** again; stale valid hashes remain **WARN**. `stamp` can record or refresh edge review
metadata under either policy. Independently, every `frozen` doc's `self_hash` stays strict: empty,
`PENDING`, malformed, or mismatched values are **ERROR** (append-only enforced).

Both hashes use the *canonical body*: front matter, line-ending differences, per-line trailing
whitespace, and boundary blank lines are normalized. Prose reflow and Markdown syntax rewrites are
significant and change the hash. A fingerprint rides the *depender*; a `self_hash` rides the
*frozen target*.

## Executing a change → dispatch is one line

The entry/exit steps above are the *standing* protocol — identical for every change — so a dispatch
prompt never restates them. Work mechanics are also standing: `git mv` to preserve history; keep the
test + lint gate green at each boundary; preserve task detail verbatim; docs/conventions only unless
the change says otherwise; don't commit unless asked; stop and surface any instruction that
contradicts the ADRs / roadmap / code.

Once the repository's agent setup loads this contract, dispatch collapses to one line:
**"Execute `docs/changes/<name>/`."** Landing is completed
through `doc-contract land <folder> --dry-run` followed by the reviewed command without `--dry-run`.
Add `--include-untracked` only for explicitly provisional work; the command previews those nodes
before mutation and labels baseline warnings separately from new regressions. The transaction owns
the status, roadmap, fingerprint, journal, and archive boundaries.

<!-- Repo-specific traps (the {{PROJECT}} invariants that are easy to violate) belong in the
     client-specific agent file, if one exists. Keep this file the portable operating contract. -->
