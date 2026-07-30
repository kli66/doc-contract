# `doc-contract reconcile semantic` — the entry / exit drift-check

Invoke as `/doc-contract reconcile semantic docs/changes/<name>/ [entry|exit]`. The existing slash
form without `semantic` is a compatibility alias for the same judgment-heavy workflow. The
packaged command has a separate explicit spelling:

```console
doc-contract reconcile mechanical docs/changes/<name> --phase entry --format json --repo-root <repo>
doc-contract reconcile mechanical docs/changes/<name> --phase exit --format json --repo-root <repo>
```

The packaged command is the read-only deterministic half. It reuses resolver, lifecycle, and landing
planners and reports evidence without writing, journaling, moving files, running capabilities, or
judging meaning. The semantic skill consumes that report and owns the human/model judgments. The
**contract** — that both halves run on every substantial change entry and exit — remains in
`AGENTS.md` → *"Change / handoff protocol (MANDATORY)"*. This guide operationalizes that contract;
`AGENTS.md` stays canonical.

**Two honest limits.** (1) This adds **no enforcement** — invocation is voluntary, like the prose it
operationalizes. Real enforcement is a hook (Stop / pre-commit) or the linkage tripwire
(`scripts/test_change_dag.py`, which asserts every `docs/changes/*/` folder has a roadmap line),
neither of which is a procedure. (2) Mechanical readiness proves only deterministic lifecycle and
graph conditions. It does not prove acceptance, semantic approval, task completion, implementation
correctness, or authorization to mutate.

Lifecycle context: `/doc-contract new-change` authors → explicit user/reviewer instruction →
`doc-contract accept` → mechanical entry report → **`/doc-contract reconcile semantic … entry`**
→ explicit `doc-contract begin` → work → mechanical exit report → **`/doc-contract reconcile
semantic … exit`** → landing preview → explicit `doc-contract land`. Reconciliation never decides
acceptance or performs a transition.

Pass the change folder and the phase. If the phase is omitted, infer it — an un-archived folder you
are about to work in is `entry`; a folder whose tasks are done and you are landing is `exit`.

## Entry — before touching code

Goal: start from mechanically ready evidence and an accurate semantic map.

1. **Run the mechanical entry report first.** Use JSON so the skill consumes stable fields. A
   proposed change still needs explicit acceptance; a blocked change stays under manual handling;
   any other blocker stops entry. `ready: true` proves only that the accepted change can be planned
   through `TransitionAction.BEGIN`; it does not approve the work or authorize `begin`.
2. **Read the change and make only the semantic judgments the command cannot make:**
   - Does each cited ADR's prose still mean what the change claims?
   - Is a mismatch stale durable documentation or a live contradiction?
   - Are scope, dependency ordering, ownership split, and tasks sufficient and wise?
   - Does the current code expose a live importer or invariant that contradicts the intended work?
3. **Act on semantic mismatches:**
   - **Drift** (a durable doc is stale — work landed, a decision changed, scope moved, and the
     ADR/roadmap was not updated) → **fix the ADR/roadmap first**, so you begin from a true map. Note
     what you fixed.
   - **Contradiction** (the change conflicts with a *live* ADR or a live importer — e.g. it trims a
     symbol something now imports, or violates an ADR-0003 invariant) → **STOP and surface it.**
     Do not paper over it by editing the change to match, or the ADR to match the change.
4. **Rerun the mechanical report after every semantic repair.** Require `ready: true`, review its
   content-free plan manifest, then invoke `doc-contract begin` explicitly. The report never performs
   that transition.
5. **Emit a short entry note** (spoken, not a file): mechanical result · semantic matches · drift
   repaired · any contradiction stopped on.

## Exit — before handing off or finishing

Goal: leave the durable docs true and the folder as lineage, not load-bearing.

1. **Run the mechanical exit report first.** A blocker stops landing; `ready: true` proves only that
   the current in-progress change can produce a landing plan. It does not prove implementation
   behavior or completion claims satisfy intent.
2. **Judge implementation and mark task status in `change.md`** — done / superseded / moved; make
   each claim honest, note anything descoped, and do not substitute touched files for satisfied intent.
3. **Update the ADRs** — amend any decision you changed; flip a design-pinned ADR's status to
   built/accepted if this change built it; record choices the ADR had left "out of scope".
4. **Update `docs/roadmap.md`** — task completion status, move items between tracks, update this
   change's line (and strike a promoted deferred-register entry, if that's what it was).
5. **Re-home durable findings BEFORE archiving** — capture seams/decisions into ADRs / `docs/spec/` /
   project memory so the archived folder carries no unique knowledge (contract: archive is lineage).
6. **Honor the test couplings** — if the change touched the consumer surface, update
   `docs/spec/capabilities.md` (the `test_capabilities_coverage` tripwire) and any drift-guard the
   change tripped (e.g. a new `CurationAction` needs its `events.py` `_apply` fold branch). Keep
   `uv run pytest -q` + `uv run ruff check .` green.
7. **Rerun the mechanical exit report after every semantic, code, or durable-document repair.**
   Require `ready: true` and review the final content-free plan manifest.
8. **Land transactionally** — run `doc-contract land docs/changes/<name> --repo-root <repo> --dry-run`,
   review the complete write/move plan and diff, then rerun without `--dry-run`. The command journals
   each boundary, hash-checks concurrent edits, updates the roadmap and dependent fingerprints, and
   preserves history for tracked or intentionally untracked folders. Do not hand-roll a separate
   `git mv`/stamp/update sequence.
9. **Emit a short exit note** — what landed, which durable docs you updated, what you captured to
   memory, the archive path.

## What this is not

- Not the contract (that's `AGENTS.md`, canonical and committed).
- Not enforcement (invocation is voluntary; use a hook or the linkage tripwire for that).
- Not a plan-quality judge (it checks consistency, not whether the schedule is right).
- Not for trivial edits — a one-line roadmap change has no folder and needs no reconciliation pass.
