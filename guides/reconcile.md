# `doc-contract reconcile` — the entry / exit drift-check

Invoked as `/doc-contract reconcile docs/changes/<name>/ [entry|exit]`. This is the **executable
mechanics** of the reconciliation step. The **contract** — that reconciliation is MANDATORY, and that
it fires on every change entry and exit — is owned by `AGENTS.md` → *"Change / handoff protocol
(MANDATORY)"*, which is auto-loaded into every agent and shared with the team. This does **not**
restate or replace that rule; it operationalizes the "how" the contract deliberately leaves terse.
`AGENTS.md` stays canonical.

**Two honest limits.** (1) This adds **no enforcement** — invocation is voluntary, like the prose it
operationalizes. Real enforcement is a hook (Stop / pre-commit) or the linkage tripwire
(`scripts/test_change_dag.py`, which asserts every `docs/changes/*/` folder has a roadmap line),
neither of which is a procedure. (2) It reconciles *linkage and consistency*, never *plan
correctness* — it cannot tell you the roadmap's schedule is *wise*, only that it *matches* the change
and the ADRs.

Lifecycle context: `/doc-contract new-change` authors → accept → **`/doc-contract reconcile … entry`**
→ you do the work → **`/doc-contract reconcile … exit`** → archive.

Pass the change folder and the phase. If the phase is omitted, infer it — an un-archived folder you
are about to work in is `entry`; a folder whose tasks are done and you are landing is `exit`.

## Entry — before touching code

Goal: start from an accurate map. Read the change's `change.md` (or `proposal.md` when split) and
extract its claims, then verify each against the durable docs.

1. **Pull the change's claims.** The `Status` line; the **Upstream dependencies / Dependents / Files
   owned** block; the task IDs; any `ADR-N` / roadmap references it cites.
2. **Cross-check each claim against the durable docs:**
   - **ADRs (`docs/adr/`)** — does each cited `ADR-N` still *say what the change claims*? (e.g. the
     change says "implements ADR-0010's pinned design" → confirm ADR-0010 exists and is design-pinned,
     not already built; the change says "amends ADR-0008" → confirm 0008 still owns that surface.)
   - **Roadmap (`docs/roadmap.md`)** — is there a line for this change? Does its status / track /
     dependency order match the change's own block? Do the dependents it names back-link to it?
   - **Code surface** — do the **Files owned** paths still exist, and is any of them already owned by
     another in-flight `docs/changes/*/` folder (an ownership conflict)?
3. **Classify each mismatch and act:**
   - **Drift** (a durable doc is stale — work landed, a decision changed, scope moved, and the
     ADR/roadmap was not updated) → **fix the ADR/roadmap first**, so you begin from a true map. Note
     what you fixed.
   - **Contradiction** (the change conflicts with a *live* ADR or a live importer — e.g. it trims a
     symbol something now imports, or violates an ADR-0003 invariant) → **STOP and surface it.**
     Do not paper over it by editing the change to match, or the ADR to match the change.
4. **Emit a short entry note** (spoken, not a file): what matched · what drifted + the fix you made ·
   any contradiction you stopped on. Then proceed to the work.

## Exit — before handing off or finishing

Goal: leave the durable docs true and the folder as lineage, not load-bearing.

1. **Mark task status in `change.md`** — done / superseded / moved; note anything descoped.
2. **Update the ADRs** — amend any decision you changed; flip a design-pinned ADR's status to
   built/accepted if this change built it; record choices the ADR had left "out of scope".
3. **Update `docs/roadmap.md`** — task completion status, move items between tracks, update this
   change's line (and strike a promoted deferred-register entry, if that's what it was).
4. **Re-home durable findings BEFORE archiving** — capture seams/decisions into ADRs / `docs/spec/` /
   project memory so the archived folder carries no unique knowledge (contract: archive is lineage).
5. **Honor the test couplings** — if the change touched the consumer surface, update
   `docs/spec/capabilities.md` (the `test_capabilities_coverage` tripwire) and any drift-guard the
   change tripped (e.g. a new `CurationAction` needs its `events.py` `_apply` fold branch). Keep
   `uv run pytest -q` + `uv run ruff check .` green.
6. **Archive** — `git mv docs/changes/<name>/` → `docs/changes/archive/<YYYY-MM-DD>-<name>/`
   (preserve history; do not delete).
7. **Emit a short exit note** — what landed, which durable docs you updated, what you captured to
   memory, the archive path.

## What this is not

- Not the contract (that's `AGENTS.md`, canonical and committed).
- Not enforcement (invocation is voluntary; use a hook or the linkage tripwire for that).
- Not a plan-quality judge (it checks consistency, not whether the schedule is right).
- Not for trivial edits — a one-line roadmap change has no folder and needs no reconciliation pass.
