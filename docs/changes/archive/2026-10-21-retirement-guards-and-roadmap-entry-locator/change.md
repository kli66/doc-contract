---
id: retirement-guards-and-roadmap-entry-locator
persistence: ephemeral
status: landed
track: lifecycle
depends_on:
  - supersede-unaccepted-proposal
  - canonicalize-roadmap-status-transitions
  - actionable-lifecycle-diagnostics
files_owned:
  - docs/changes/retirement-guards-and-roadmap-entry-locator/change.md
  - src/doc_contract/resolver.py
  - src/doc_contract/lifecycle.py
  - src/doc_contract/landing.py
  - tests/test_resolver.py
  - tests/test_lifecycle.py
  - tests/test_landing.py
  - tests/test_reconciliation.py
  - docs/spec/capabilities.md
  - README.md
  - SKILL.md
  - AGENTS.template.md
  - guides/new-change.md
  - docs/roadmap.md
accepted_at: 2026-10-20
started_at: 2026-10-20
landed_at: 2026-10-21
archive_path: docs/changes/archive/2026-10-21-retirement-guards-and-roadmap-entry-locator
---
# Guard retirement: one roadmap-entry locator across land, supersede, accept, and begin

Status: Landed · 2026-10-21

**Upstream dependencies:** `supersede-unaccepted-proposal` is landed and owns the `supersede` verb,
the folder-removal transaction, the `roadmap-line-dangling` finding, and the
`_roadmap_supersede_text` rewriter; this change closes the two residuals that landed with it — the
duplicated rewrite grammar and the multi-node folder retirement — and adds nothing to its frozen scope
except the guards below. `canonicalize-roadmap-status-transitions` is landed and owns the
`_roadmap_transition_text` contract — case-insensitive location of exactly one unambiguous roadmap
entry, failing closed with a value-free `roadmap-invalid` detail — which this change generalizes into
one locator shared by all three rewriters instead of three drifting matchers.
`actionable-lifecycle-diagnostics` is landed and owns the stable value-free lifecycle diagnostic
taxonomy the new refusal joins. All three inputs are available; no ADR exists in this repository and
no external service, live input, or third-party package gates implementation. The landing defect this
amendment folds in was reproduced against HEAD `5fd5944` (2026-10-16) and is recorded in the
working-tree incident note `doc-contract-incident-roadmap-rewrite-and-stamp.md` (issue 1); it adds no
dependency, because it is a defect in the landing copy of the same grammar.

**Dependents:** None. No active change in this repository depends on it. The four concrete callers
of the fixed behavior are the three rewriters themselves plus every operator who lands or retires a
change folder; no in-repository change folder is blocked by it.

**Files owned:** The resolver's roadmap-entry location and rewrite seams; the lifecycle
classification precondition that refuses a multi-node folder for the supersede request; the landing
refusal message that currently says only `change.md is missing`; focused resolver, lifecycle, and
landing tests; the capability, usage, skill, and portable-contract prose that states the folder
conventions; this proposal and roadmap lineage. The failure *rendering* for these codes is not owned
here — see the overlap note.

**Overlap check (reverse direction):** `actionable-preflight-diagnostics` (landed 2026-10-14) declares
`src/doc_contract/cli.py`, `src/doc_contract/reconciliation.py`, `tests/test_cli.py`,
`tests/test_reconciliation.py`, `docs/spec/capabilities.md`, and `docs/roadmap.md`. This change
deliberately does **not** claim `cli.py` or `tests/test_cli.py`: the new refusal and the improved
`change.md`-missing message are surfaced by the shared failure renderer that item introduced, and
this item rebases onto whatever form of it landed. **Sequencing:** this item is intended to land
*after* `actionable-preflight-diagnostics`, so its refusal tests assert the landed rendering and the
shared `capabilities.md` sentences are reconciled once against a settled neighbour. That ordering is
a reconciliation preference, not a functional prerequisite — the guards are correct with or without
that renderer, which is why no `depends_on` edge is declared and why a revised or replaced F-003
item cannot dangle this one. That neighbour has since landed, so the sequencing preference is
already satisfied. `review-bound-acceptance-plan` has also landed, so it is a landed baseline rather
than an active overlap. `docs/roadmap.md` is shared with `runtime-source-provenance`,
`proportional-accepted-work-contract`, and `optional-project-memory`; `docs/spec/capabilities.md`,
`README.md`, and `SKILL.md` with `runtime-source-provenance`; `AGENTS.template.md` with
`proportional-accepted-work-contract` and `optional-project-memory`; and `guides/new-change.md`,
which this item claims for the retirement-verb authoring convention, with
`proportional-accepted-work-contract` and `optional-project-memory`, which already own it. All of
those are additive-prose or lineage-region overlaps with no ordering dependency, so whichever item
lands second preserves all contracts. `src/doc_contract/resolver.py` and
`tests/test_resolver.py` were also owned historically by landed `reflect-project-evidence` and
`supersede-unaccepted-proposal`; both are landed baselines, not active conflicts. No shared symbol
with any active proposal: the locator, the landing retarget policy, and the multi-node precondition
are new. The stamp-side residuals recorded in the same incident note landed separately as
`stamp-untracked-and-suspect-link-wording` (2026-10-20; it shared `resolver.py`,
`tests/test_resolver.py`, `docs/spec/capabilities.md`, `README.md`, and `docs/roadmap.md` in disjoint
regions and declared this handoff back, with no ordering edge either way).

## Why

The `supersede` transition landed with two accepted residuals, and the landing rewrite carries a
third that this amendment folds in; this change closes all three rather than leaving them as
folklore.

*First, three roadmap rewriters that must agree, do not.* `accept`/`begin` rewrite the selected
roadmap entry through `_roadmap_transition_text`, which matches the entry case-insensitively and
fails closed with a value-free `roadmap-invalid` detail. `supersede` rewrites its entry through
`_roadmap_supersede_text`, which matches the folder path **case-sensitively**, understands wrapped
continuation entries, and applies a different replacement (path plus status presentation instead of
status presentation alone). `land` rewrites its entry through `_roadmap_prose_output` in
`landing.py`, which has no locator at all: it tests the un-slashed folder path (`docs/changes/alpha`)
as a bare substring on every pre-DAG line and rewrites each hit. All three are siblings with the same
job — locate exactly one unambiguous entry for one change and rewrite exactly that presentation — but
they are three implementations of the same matching grammar, so they can drift again, and the
landing copy has drifted four ways. It retargets another change's entry whose folder name merely
extends the landed change's (`docs/changes/alpha-beta/` matches `docs/changes/alpha`), it flips the
status presentation on every line that cites the landed folder at all (a `Deferred Work` register
reads `(landed)` afterwards), it is not dependency-scoped (a prefix sibling with no `depends_on` edge
is rewritten identically), and it relabels only the exact bare `(proposed)`/`(in-progress)`/`(blocked)`
forms, so a case-varied or annotated presentation (`(PROPOSED)`, `(proposed, depends on x)`,
`proposed 2026-08-03`) is retargeted to the archive path while keeping its stale status.

*Reproduction.* In a temporary repository holding active `alpha` plus proposed `alpha-beta`
(`depends_on: [alpha]`), both with roadmap entries, `land docs/changes/alpha --dry-run
--include-untracked` refuses with `[preflight-invalid]` wrapping `[no-roadmap-line] active change
alpha-beta has no line in docs/roadmap.md` — the message blames the dependent for the rewrite that
deleted its line — while `check --offline --include-untracked` on the same tree is green. When the
dependent's entry is located by its document basename instead (the multi-node `fix-*.md` form
`_has_roadmap_line` accepts), that guard passes, `land` succeeds, and the repository keeps a roadmap
that retargets the dependent's entry to a nonexistent archive folder and reads `(landed)` while the
generated DAG block below it still says `(proposed)`; `check` reports zero errors afterwards, because
`_STATUS_TOKENS` does not recognize `(landed)` and inactive nodes are not status-checked.

*Second, a change folder holding more than one change node can be retired wholesale, losing
siblings.* `project_supersede` deliberately removes every change node inside the retired folder, and
`_plan_supersede` then removes the folder in one `remove` mutation. That is correct for the one-node
folder every active change in this repository uses, and wrong for the multi-node `fix-*` layout the
resolver otherwise supports: the sibling document disappears with no lineage record of its own, its
per-document roadmap line survives pointing at nothing, and `check` reports zero findings — the new
`roadmap-line-dangling` guard recognizes the folder-path form only, and the folder's lineage record
satisfies it. Reproduction: a folder holding `change.md` (id `demo`) plus `fix-b.md`; `supersede
demo` succeeds, `fix-b.md` vanishes, `fix-b.md`'s roadmap line stays `(proposed)`, `check` stays
green.

*Third, the refusal that already protects a folder whose node document has an unexpected name says
nothing useful.* After each verb's own status precondition — `in-progress` for `land`, `proposed` for
`supersede` — a folder whose node document is `proposal.md` is refused with `change-invalid:
change.md is missing`, which names neither the folder nor the document that was actually found. The
resolver happily discovers and validates such a folder (its node document is a `_GENERIC_DOC` and a
legal node), so the trap is only visible when the retirement verb refuses.

All three are lifecycle-layer corrections on surfaces this repository already owns; none needs
resolver semantics beyond one matcher, one entry-retarget policy, one precondition, and one warning.
The layer stays thin.

## What changes

**Δ ADDED**

- **One roadmap-entry locator.** A single internal resolver seam that, given the roadmap prose text
  and a caller-supplied needle, locates exactly one entry — the matching line plus its indented
  continuation lines — or fails closed with a value-free `roadmap-invalid` detail. Its grammar is one
  rule, not a union of three: case-insensitive needle match; the generated region (begin marker
  through end marker, inclusive) is machine-owned and never scanned, while every other prose line is
  eligible; a candidate is any eligible line that carries the needle, with its continuation block
  attached; and zero candidates, more than one candidate, a sole candidate that also cites another
  change folder, and an entry block without exactly one rewritable status presentation each fail
  closed with a distinct value-free detail. The policy is uniform for all three callers — no
  per-verb tolerance switch — so `_roadmap_transition_text` (status-only) and the retarget policy
  (`_roadmap_supersede_text` plus the new landing policy: folder path and status presentation) differ
  only in what they substitute, never in what they accept or refuse. Landing adds one placement
  precondition *outside* the locator (next bullet): the matcher's eligible set is unchanged, but a
  landing entry must also live before the generated region. That makes three declared
  behaviour changes, each pinned by a new regression test: `accept`/`begin` newly refuse a duplicated
  or cross-referenced entry instead of rewriting the first clean line and leaving the rest stale;
  `supersede` newly accepts an entry whose indented continuation cites the folder (today that
  continuation commits as a second candidate); and a case-varied citation of the same folder counts
  as a candidate for every caller.
- **A landing rewrite owned by the projection.** `project_landing` derives the rewritten roadmap
  prose itself from the current text, exactly as `project_supersede` already does, and returns it on
  `LandingProjection`; `_plan_landing` stops computing prose and stops passing rewritten text in.
  The landing policy is the supersede policy with different data — needle `docs/changes/<folder>/`,
  replacement `docs/changes/archive/<date>-<folder>/`, source status the landed change's own,
  destination token `(landed)` — so the two retirement callers share one implementation rather than
  two lookalikes.
- **A fail-closed landing entry precondition.** A landed change whose entry is missing, duplicated,
  ambiguous against another change folder, statusless, unclosed, or placed only after the generated
  region refuses with a value-free `roadmap-invalid` detail during planning, before projected
  repository validation and before any mutation. The first four conditions come from the shared
  locator and fail-closed status check that `accept`, `begin`, and `supersede` already enforce; the
  post-generated-region condition is one landing-only placement check that runs after location and
  before projected validation, so the locator's grammar stays uniform and `accept`, `begin`, and
  `supersede` keep canonicalizing a post-generated-region citation exactly as they do today (pinned
  by a regression test). The documented entry convention follows: one entry per active change —
  a pre-DAG line plus its indented continuations — cites its folder path, with exactly one status
  presentation across the whole block. Declared residual: `check` does not yet warn about a statusless
  active entry (such a line remains legal and produces no `roadmap-status-mismatch`, because absence
  is not a contradiction), so this item tightens `land` only; a follow-on could add the WARN.
- **Distinct, counted fail-closed details.** The four location refusals stay distinct, and each names
  the candidate count it observed — no entry (`0 candidates`), several candidate entries (`N
  candidates`), a sole candidate that also cites another change folder, and an entry block without
  exactly one rewritable status presentation — so an operator can tell a missing line from a second
  citation of the same folder, or from a cross-reference, without reading the roadmap. Ids and counts
  only, still value-free. This is the item's one message-contract change; the pinned details in
  `tests/test_resolver.py` and `tests/test_lifecycle.py` move with it.
- **A precondition for multi-node folders on both retirement verbs.** Classifying a `supersede` or
  `land` request against a folder that holds more than one node-bearing Markdown document refuses
  with a new stable, value-free diagnostic naming the folder and the count. No plan, no journal, no
  mutation.
- **A `check` warning for the same layout.** The resolver reports the multi-node folder as a WARN
  naming the folder and node count, so an operator sees it before trying to retire it. WARN, not
  ERROR: the resolver's roadmap linkage deliberately supports a multi-node folder (its
  `_has_roadmap_line` matches the per-document basename in that case), so the layout is legal for the
  graph and only the retirement verbs cannot act on it.
- **Documented conventions.** `one change node per folder` for the retirement verbs, and
  `the folder's node document is change.md` for `land` and `supersede` — stated in the capability
  doc, `README.md`, `SKILL.md`, and the portable contract.

**Δ MODIFIED**

- `src/doc_contract/resolver.py`: the shared locator, its use by all three rewriters, the landing
  retarget policy invoked by `project_landing`, the new `LandingProjection.roadmap_text`, and the new
  multi-node WARN. No finding code, severity band, JSON shape, or `CHANGE_STATUSES`/`_STATUS_TOKENS`
  member changes; `roadmap-line-dangling`, its lineage-record lookup, and the generated-DAG-marker
  `roadmap-invalid` detail keep their current contract (only the four location details change, as
  declared above). `(landed)` and `(superseded)` stay caller literals: extending the roadmap-prose
  recognition grammar to the final statuses is deliberately out of scope, so post-land status remains
  guaranteed by the writer rather than re-checked by `validate`.
- `src/doc_contract/lifecycle.py`: the new classification diagnostic, raised for the `supersede`
  and `land` requests only and after the existing blocked/proposed/landed precedence, so every other
  verb's classification is untouched.
- `src/doc_contract/landing.py`: `_roadmap_prose_output` is deleted, `_plan_landing` passes the
  current roadmap prose to `project_landing` and consumes `projection.roadmap_text`, and the
  `_roadmap_output` DAG splice collapses into one helper that lives in `lifecycle.py` and is imported
  by `landing.py` — `landing.py` already imports private lifecycle symbols, while
  `tests/test_landing.py:523`'s no-private-resolver-symbols check forbids the alternative home, and
  `lifecycle._roadmap_with_block` currently hardcodes the marker literals the resolver owns. The
  `change.md is missing` refusal for `land` and `supersede` names the folder and the node document it
  found instead; the check itself stays exactly as strict.
- `docs/spec/capabilities.md`, `README.md`, `SKILL.md`, `AGENTS.template.md`: the conventions above
  (including the entry-block convention `land` now enforces); the landing `roadmap-invalid` refusal
  beside the `accept`/`begin` sentences (`capabilities.md:40`, `:92`), which are restated from
  line-scope to entry-block scope; the missing `supersede` `roadmap-invalid` sentence; and rows for
  the new lifecycle diagnostic and the new resolver WARN.
- `guides/new-change.md`: the `change.md`-only retirement convention conflicts with the guide's
  authorised `proposal.md`/`design.md`/`tasks.md` ceiling, so the guide states which authoring shapes
  the retirement verbs accept.
- `docs/roadmap.md`: this line and the regenerated generated DAG.

**Δ REMOVED** — `_roadmap_prose_output` and the duplicated DAG-splice helper. No command, lifecycle
state, finding, or lineage rule is removed. The three rewriters remain distinct policies over one
locator; only their duplicated matching grammar is retired.

## Tasks

1. Extract the shared entry locator in `resolver.py` and re-express `_roadmap_transition_text`,
   `_roadmap_supersede_text`, and the landing retarget policy over it, preserving each caller's
   replacement policy and its fail-closed behavior; confirm `accept`, `begin`, and `supersede`
   produce byte-identical roadmap text for every shape covered by the existing tests, that the
   divergence shapes named in the locator bullet each gain the declared refusal, and that `land` does
   so for every entry the old pass rewrote correctly (a single unambiguous status-bearing entry),
   except for the annotated and case-varied presentations it now canonicalizes.
2. Add locator parity tests in `tests/test_resolver.py`: case-insensitive match for all three
   callers; wrapped continuation entries; zero, multiple, and ambiguous entries fail closed with a
   value-free `roadmap-invalid` detail and candidate count for all three callers; generated-DAG
   exclusion; a cross-folder ambiguity case; and the three declared behaviour changes — duplicated
   entry refused by `accept`/`begin`, continuation-cited entry accepted by `supersede`, case-varied
   citation counted as a candidate.
3. Add the multi-node precondition to supersede classification with a stable, value-free diagnostic
   (`tests/test_lifecycle.py`): single-node folder classifies as today; two-node folder refuses with
   no plan and no mutation; the refusal does not leak document content; every other verb's
   classification for the same folder is unchanged.
4. Add the resolver multi-node WARN naming folder and count (`tests/test_resolver.py`): fires for a
   two-node folder, silent for every single-node folder, and does not change the folder's node set,
   topology, or DAG rendering.
5. Improve the `change.md`-missing refusal in `landing.py` so it names the folder and the node
   document found, for both `land` and `supersede` (`tests/test_landing.py`); keep it value-free and
   keep the strict membership check.
6. Move the landing prose rewrite into `project_landing`: derive the retarget from the current
   roadmap text with the shared locator, return it as `LandingProjection.roadmap_text`, wire
   `_plan_landing` to pass `current_roadmap` and consume the projection, delete
   `_roadmap_prose_output`, and collapse the DAG splice into one helper shared with `lifecycle.py`.
7. Add the landing regression tests in `tests/test_landing.py`, each on a temporary repository with a
   `check --offline` assertion: prefix siblings (`alpha` + `alpha-beta`, `alpha2`, `alpha.beta`) with
   and without a `depends_on` edge keep their entry paths and statuses byte-for-byte and land cleanly;
   a multi-node dependent (`docs/changes/alpha-beta/fix-link.md`) is untouched and the post-land
   roadmap stays consistent with the generated DAG; a case-varied or annotated presentation
   (`(PROPOSED)`, `(proposed, depends on x)`) is canonicalized to `(landed)` instead of being
   retargeted with a stale status; a second pre-DAG citation of the landed folder (a `Deferred Work`
   register), an entry whose only location is after the generated region, and a statusless, unclosed,
   or duplicated entry each refuse with the count and mutate nothing; the entry's rationale, wrapped
   continuation lines, and line terminator survive byte-for-byte at the prose seam, the rewrite never
   touches a generated line, and the landing planner then re-renders the generated DAG block from the
   projected graph, so the landed block equals the freshly rendered one rather than the pre-land
   bytes.
8. Document the conventions and the diagnostics in `docs/spec/capabilities.md`, `README.md`,
   `SKILL.md`, `AGENTS.template.md`, and `guides/new-change.md` — the entry-block convention `land`
   now enforces, the landing `roadmap-invalid` refusal beside `accept`/`begin`, the
   `accept`/`begin` sentences at `capabilities.md:40` and `:92` restated as entry-block scope, the
   missing `supersede` `roadmap-invalid` sentence, the new lifecycle diagnostic row, and the new
   resolver WARN row; confirm `scripts/test_capabilities_coverage.py` needs no change because no CLI
   command is added and the enumerated surface is `COMMANDS`.
9. Add the `docs/roadmap.md` Lifecycle line, then regenerate the DAG with
   `doc-contract update --repo-root .`.
10. On land: amend no ADR (this repository keeps none); archive this folder through
    `doc-contract land` and confirm the declared paths all exist.

## Verify

- `uv run --group test pytest -q` green, including the new resolver, lifecycle, and landing tests
  and `scripts/test_capabilities_coverage.py`; `uv run --group lint ruff check .` clean;
  `doc-contract check --repo-root . --offline` returns 0 errors with no new warning delta beyond the
  declared baseline.
- In a temporary repository, a folder holding `change.md` plus `fix-b.md` is refused by `supersede`
  and by `land` with the new code, the folder and its sibling are untouched, no journal is created,
  and `check --offline` reports the multi-node WARN naming the folder.
- In a temporary repository, a folder whose node document is `proposal.md` is refused with a message
  naming the folder and `proposal.md` rather than the bare `change.md is missing`: by `land` when the
  change is `in-progress`, and by `supersede` when it is `proposed`.
- In a temporary repository, `land` on `alpha` with a prefix sibling leaves the sibling's entry path
  and status byte-for-byte unchanged and the post-land `check --offline` green, with and without a
  dependency edge; the multi-node `fix-link.md` dependent (the shape that corrupts and green-lights
  today) is untouched; a case-varied or annotated entry is canonicalized to `(landed)`; a second
  pre-DAG citation of the landed folder, and a citation placed after the generated region, each
  refuse with the count and no mutation; and a statusless or duplicated entry refuses before
  projected validation and before any mutation.
- Locator parity: the same roadmap fixtures (exact match, different case, wrapped continuation,
  missing, duplicated, ambiguous, generated block) produce the same located entry and the same
  fail-closed code and candidate count for all three callers; the selected line's other bytes and all
  other lines are preserved.
- Invariant spot-check: runtime stays stdlib-only and cwd-independent; `--repo-root` stays explicit;
  diagnostics stay value-free (paths, ids, counts only — never document bodies, hashes, or the
  `--reason` text); `CHANGE_STATUSES`, `_STATUS_TOKENS`, and `roadmap-line-dangling` are unchanged, so
  roadmap-prose recognition of `(landed)`/`(superseded)` stays out of scope; `land`'s
  in-progress-only precondition is unchanged; `accept`, `begin`, and `supersede` keep byte-identical
  output for every shape their existing tests cover, and differ only in the three declared behaviour
  changes (duplicate/cross-reference refusal, entry-block scope, case-insensitive candidate
  matching); `land` differs only in the collision, ambiguity, statusless-entry,
  annotated-presentation, post-DAG-citation, multi-node-folder, and diagnostic-count cases this item
  declares.
