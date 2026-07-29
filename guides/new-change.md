# `doc-contract new-change` — author a change (inverse of dispatch)

Invoked as `/doc-contract new-change <intent>`. The contract (`AGENTS.md`) collapses *executing* a
change to one line — "Execute `docs/changes/<name>/`" — because the standing protocol is auto-loaded.
This sub-command is the missing other half: turning a raw intent into a well-formed change folder that
is *ready* to dispatch.

**This authors; it does not execute.** It stops at a `Status: Proposed (not accepted)` folder for
review. An explicit user or reviewer instruction authorizes `doc-contract accept`; lifecycle:
`/doc-contract new-change <intent>` → explicit acceptance → `doc-contract accept` → entry
reconciliation → `doc-contract begin` → "Execute `docs/changes/<name>/`".
Do **not** touch `src/` or write tests here — only `docs/`.

The template below is the cheap part. The value is **steps 1 and 4**: grounding the metadata block and
the Δ-classification in what the durable docs actually say, instead of inventing them. A change folder
with a hand-waved `Upstream dependencies` block is the failure mode this exists to prevent.

## Step 0 — read the map (always, before deciding anything)

The contract and project traps are already in context via the `CLAUDE.md → @AGENTS.md` import. Add the
live map:

- `docs/roadmap.md` — the DAG. Where does this intent sit? What does it depend on / block? Is it
  already listed (a deferred-register entry, a track item, a carried-over tail)?
- `docs/adr/` — which decisions govern this area? Grep the ADR titles; read the ones that bound the
  surface you're about to touch. A change that contradicts an ADR must **stop and surface it**, not
  paper over it (contract rule). **If the intent says "lands as ADR-N" / "new ADR", check first
  whether ADR-N already exists** — an ADR is often *design-pinned ahead of build* (status
  `proposed — implementation deferred`). If it exists, this is an **implement**, not an author: the
  change *builds* the pinned design and **amends the ADR on land** (status → accepted/built); it does
  not re-create it. Mis-reading implement-as-author is a common framing error.
- `docs/spec/*.md` deferred registers, if the repo keeps any — if the intent is *already* a parked
  entry there, this is a **promote-and-strike**, not a fresh idea: carry the entry's detail into the
  folder and strike it from the register.
- Project memory / whatever loads each session — what's already built? Built behaviour is canonical
  there, never duplicated into the change.

## Step 1 — decide the weight (contract: "scale ceremony to the work")

- **Trivial edit** (a doc tweak, a one-symbol rename, a deferred line) → **no folder.** Add a
  `docs/roadmap.md` line and stop. Say it's trivial and show the line.
- **Substantial work** (new behaviour, a new seam, a multi-file change) → a
  `docs/changes/<name>/` folder, **single `change.md`** (the default). Continue to step 2.
- **Rare meta-change** (each of Why/What/Tasks is genuinely large) → split into
  `proposal.md` / `design.md` / `tasks.md`. This is the *ceiling*, not the default — justify the
  split before reaching for it.

When unsure between trivial and substantial, default to substantial-but-minimal: a folder with a
short `change.md` beats a roadmap line that loses the dependency detail.

## Step 2 — name it

Kebab-case, matching the roadmap's existing naming. If it executes an already-decided ADR, prefix
with the ADR/track tag the roadmap uses. Create `docs/changes/<name>/`.

## Step 3 — scaffold `change.md` from the house skeleton

Match the established shape exactly (open a recent `docs/changes/<name>/change.md` as the worked
reference). The skeleton:

```markdown
# <Title>

Status: Proposed (not accepted) · Proposed <YYYY-MM-DD>

**Upstream dependencies:** <ADR(s) this extends · invariants it rides · gated infra inputs (mark
which are gated vs. available) · sibling changes that must land first>
**Dependents:** <what this blocks — name the change folders / roadmap items, and back-link them>
**Files owned:** <exact paths this change may write: src/… · tests/… · which ADR it amends on land>

## Why

<The problem, stated against the current code/ADR reality — not a feature wish. Why now, why this
shape, why it's safe against the invariants your ADRs name.>

## What changes

**Δ ADDED** — <new symbols/files/seams>
**Δ MODIFIED** — <touched surfaces; name files + the on-land ADR amendment>
**Δ REMOVED** — <deletions, or "none". Never delete superseded work — mark it superseded.>

## Tasks

1. <ordered, each independently checkable; type-checker-clean where code>
2. …
N. On land: amend ADR-XXXX; archive this folder per the contract; capture the seam in project memory.

## Verify

- the repo's test/lint/type gate green (new tests incl.).
- <behavioural check: an offline double demonstrates the change; a live test is gated + skipped when
  its infra input is unset, mirroring the existing gated tests>.
- Invariant spot-check: <which of the repo's core invariants (the ADR that lists them) this must not
  break, checked>.
```

Use today's date for `<YYYY-MM-DD>` (do not guess — read it from the session/context). Status is not
binary:
- **`Proposed (not accepted)`** — fully buildable now; waiting only on review.
- **`Blocked on <input>`** — no part can start until a named input lands.
- **Partially gated** — the common real case: part of the scope is buildable now, part waits on an
  input. Set `Proposed` and **say so in the dependency block** — name which slice is unblocked and
  which is gated (e.g. the offline path builds now; the live/full path is gated on an infra input or a
  prerequisite that hasn't landed). Do **not** mark the whole change `Blocked` when only a slice is.

## Step 4 — GROUND the metadata block (the part that earns this sub-command)

Do **not** fill the three metadata lines from imagination. Derive each:

- **Upstream dependencies** — for each ADR/invariant/infra-input, point at the actual line: which
  ADR number, which core invariant, which open-inputs bullet in the roadmap. Mark each input
  **gated** vs. **available** (an offline double often unblocks the build while the live path is
  gated — say so).
- **Dependents** — grep the roadmap + other `changes/` folders for work this unblocks. When you
  find one, **edit that change's `Dependents`/`Blocks` line to back-link this one** (the
  dependency-chain rule keeps the roadmap a schedulable DAG, not an unordered pile).
- **Files owned** — name the real paths by reading the code surface (`src/…`), not a guess. Then
  check ownership **in both directions**: (forward) what does this change *depend on / block* — the
  `Dependents` edge; (reverse) what *other* in-flight `docs/changes/*/` folder already lists any of
  these same paths in *its* `Files owned`. Grep the other change folders for your paths. A reverse
  overlap is usually soft (additive, different regions — note it + "rebase whoever lands second"); a
  shared *symbol* is a hard conflict — surface it. Recording the overlap now keeps the entry
  reconciliation (`/doc-contract reconcile … entry`) from being the first to discover it.
- **Test couplings (do not skip) — grep for the tripwires/guards your change trips.** A living doc or
  a drift-guard test will fail loud if you add a surface and don't update it; the change must *own*
  that update. Typical couplings: a new item on an enumerated code surface (a CLI command, a served
  tool) → the capability doc + its coverage tripwire; a new enum member → its handler/fold branch +
  the drift-guard test that pins the enum. Grep `tests/` + the skill's `scripts/` for the surfaces
  you touch and list each coupled doc/test in **Files owned** + **Verify**.

If grounding reveals the intent **contradicts an ADR** (e.g. it trims a symbol that now has a live
importer, or violates an invariant), **stop and surface it** rather than writing the folder.

## Step 5 — situate in the DAG

Add one `docs/roadmap.md` line placing the change in its track, with its status (Proposed /
Blocked-on-X) and a one-line hook. This is the resurfacing path: the change-protocol reconciliation
walks the roadmap, so the parked change comes back into view. If you promoted a deferred-register
entry, strike it there and note the promotion.

## Step 6 — hand back (do not execute)

Report:
1. The weight decision and why.
2. The folder path + a tight summary of the `change.md` (Why / Δ / key tasks).
3. The grounded dependency block — call out any gated inputs and any drift/contradiction found.
4. The roadmap line added.
5. The next step is the reviewer's: review/accept, then dispatch "Execute `docs/changes/<name>/`".

Leave `Status: Proposed (not accepted)`. Authoring ≠ acceptance ≠ execution.
