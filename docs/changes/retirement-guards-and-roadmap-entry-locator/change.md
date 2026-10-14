---
id: retirement-guards-and-roadmap-entry-locator
persistence: ephemeral
status: proposed
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
  - docs/spec/capabilities.md
  - README.md
  - SKILL.md
  - AGENTS.template.md
  - docs/roadmap.md
---
# Guard retirement: one roadmap-entry locator and explicit folder preconditions

Status: Proposed (not accepted) · Proposed 2026-10-14

**Upstream dependencies:** `supersede-unaccepted-proposal` is landed and owns the `supersede` verb,
the folder-removal transaction, the `roadmap-line-dangling` finding, and the
`_roadmap_supersede_text` rewriter; this change closes the two residuals that landing accepted
(recorded as `F-004` and `P-001` in its review record) and adds nothing to its frozen scope except
the guards below. `canonicalize-roadmap-status-transitions` is landed and owns the
`_roadmap_transition_text` contract — case-insensitive location of exactly one unambiguous roadmap
entry, failing closed with a value-free `roadmap-invalid` detail — which this change generalizes into
one locator shared by both rewriters instead of two drifting matchers.
`actionable-lifecycle-diagnostics` is landed and owns the stable value-free lifecycle diagnostic
taxonomy the new refusal joins. All three inputs are available; no ADR exists in this repository and
no external service, live input, or third-party package gates implementation.

**Dependents:** None. No active change in this repository depends on it. The three concrete callers
of the fixed behavior are the two rewriters themselves plus every operator who retires a change
folder; no in-repository change folder is blocked by it.

**Files owned:** The resolver's roadmap-entry location and rewrite seams; the lifecycle
classification precondition that refuses a multi-node folder for the supersede request; the landing
refusal message that currently says only `change.md is missing`; focused resolver, lifecycle, and
landing tests; the capability, usage, skill, and portable-contract prose that states the folder
conventions; this proposal and roadmap lineage. The failure *rendering* for these codes is not owned
here — see the overlap note.

**Overlap check (reverse direction):** `actionable-preflight-diagnostics` (proposed) is the
reviewer-authored F-003 remediation and declares `src/doc_contract/cli.py`,
`tests/test_cli.py`, `docs/spec/capabilities.md`, and `docs/roadmap.md`. This change deliberately
does **not** claim `cli.py` or `tests/test_cli.py`: the new refusal and the improved
`change.md`-missing message are surfaced by the shared failure renderer that item introduces, and
this item rebases onto whatever form of it has landed. **Sequencing:** this item is intended to land
*after* `actionable-preflight-diagnostics`, so its refusal tests assert the landed rendering and the
shared `capabilities.md` sentences are reconciled once against a settled neighbour. That ordering is
a reconciliation preference, not a functional prerequisite — the guards are correct with or without
that renderer, which is why no `depends_on` edge is declared and why a revised or replaced F-003
item cannot dangle this one. `docs/spec/capabilities.md` and `docs/roadmap.md` are shared with it and with `runtime-source-provenance`,
`review-bound-acceptance-plan`, `proportional-accepted-work-contract`, and `optional-project-memory`;
all of those are additive-prose or lineage-region overlaps with no ordering dependency, so whichever
item lands second preserves all contracts. `src/doc_contract/resolver.py` and
`tests/test_resolver.py` were also owned historically by landed `reflect-project-evidence` and
`supersede-unaccepted-proposal`; both are landed baselines, not active conflicts. No shared symbol
with any active proposal: the locator and the multi-node precondition are new.

## Why

The `supersede` transition landed with two accepted residuals, and this change closes them rather
than leaving them as folklore.

*First, two roadmap rewriters that must agree, do not.* `accept`/`begin` rewrite the selected roadmap
entry through `_roadmap_transition_text`, which matches the entry case-insensitively and fails closed
with a value-free `roadmap-invalid` detail. `supersede` rewrites its entry through
`_roadmap_supersede_text`, which matches the folder path **case-sensitively**, understands wrapped
continuation entries, and applies a different replacement (path plus status presentation instead of
status presentation alone). The two functions are siblings with the same job — locate exactly one
unambiguous entry for one change and rewrite exactly that presentation — but they are two
implementations of the same matching grammar, so they can drift again. The supersede copy is
already the stricter one; the fix is not "make the strict one lenient" but "have one matcher, so
there is nothing left to drift".

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
nothing useful.* `land` and `supersede` both refuse such a folder with `change-invalid: change.md is
missing`, which names neither the folder nor the document that was actually found. The resolver
happily discovers and validates a folder whose node document is `proposal.md` (it is a `_GENERIC_DOC`
and a legal node), so the trap is only visible when the retirement verb refuses.

All three are lifecycle-layer corrections on surfaces this repository already owns; none needs
resolver semantics beyond one matcher, one precondition, and one warning. The layer stays thin.

## What changes

**Δ ADDED**

- **One roadmap-entry locator.** A single internal resolver seam that, given the roadmap prose text
  and a caller-supplied needle, returns exactly one entry (the entry's line span, including wrapped
  continuation lines) or fails closed with a value-free `roadmap-invalid` detail. Its grammar is the
  union the two callers need: case-insensitive needle match, generated-DAG exclusion, ambiguity
  detection against every other change folder, and the rule that a located entry must contain
  exactly one rewritable status presentation. `_roadmap_transition_text` and
  `_roadmap_supersede_text` become thin replacement policies over it — status presentation only, and
  folder path plus status presentation respectively — with byte-for-byte identical output for the
  shapes they cover today.
- **A `supersede` precondition for multi-node folders.** Classifying a supersede request against a
  folder that holds more than one node-bearing Markdown document refuses with a new stable,
  value-free diagnostic naming the folder and the count. No plan, no journal, no mutation.
- **A `check` warning for the same layout.** The resolver reports the multi-node folder as a WARN
  naming the folder and node count, so an operator sees it before trying to retire it. WARN, not
  ERROR: the resolver's roadmap linkage deliberately supports a multi-node folder (its
  `_has_roadmap_line` matches the per-document basename in that case), so the layout is legal for the
  graph and only the retirement verbs cannot act on it.
- **Documented conventions.** `one change node per folder` for the retirement verbs, and
  `the folder's node document is change.md` for `land` and `supersede` — stated in the capability
  doc, `README.md`, `SKILL.md`, and the portable contract.

**Δ MODIFIED**

- `src/doc_contract/resolver.py`: the shared locator, its use by both rewriters, and the new
  multi-node WARN. No finding code, severity band, JSON shape, or `CHANGE_STATUSES`/`_STATUS_TOKENS`
  member changes; `roadmap-line-dangling`, its lineage-record lookup, and every existing
  `roadmap-invalid` detail keep their current contract.
- `src/doc_contract/lifecycle.py`: the new classification diagnostic, raised for the supersede
  request only and after the existing blocked/proposed/landed precedence, so every other verb's
  classification is untouched.
- `src/doc_contract/landing.py`: the `change.md is missing` refusal for `land` and `supersede` names
  the folder and the node document it found instead; the check itself stays exactly as strict.
- `docs/spec/capabilities.md`, `README.md`, `SKILL.md`, `AGENTS.template.md`: the conventions above
  plus the new diagnostic row.
- `docs/roadmap.md`: this line and the regenerated generated DAG.

**Δ REMOVED** — none. No command, lifecycle state, finding, or lineage rule is removed. The two
rewriters remain two functions; only their duplicated matching grammar is retired.

## Tasks

1. Extract the shared entry locator in `resolver.py` and re-express `_roadmap_transition_text` and
   `_roadmap_supersede_text` over it, preserving each caller's replacement policy and its fail-closed
   behavior; confirm `accept`, `begin`, and `supersede` produce byte-identical roadmap text for every
   shape covered by the existing tests.
2. Add locator parity tests in `tests/test_resolver.py`: case-insensitive match for both callers;
   wrapped continuation entries; zero, multiple, and ambiguous entries fail closed with a value-free
   `roadmap-invalid` detail for both callers; generated-DAG exclusion; and a cross-folder ambiguity
   case.
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
6. Document the conventions and the new diagnostic in `docs/spec/capabilities.md`, `README.md`,
   `SKILL.md`, and `AGENTS.template.md`; confirm `scripts/test_capabilities_coverage.py` needs no
   change because no CLI command is added and the enumerated surface is `COMMANDS`.
7. Add the `docs/roadmap.md` Lifecycle line, then regenerate the DAG with
   `doc-contract update --repo-root .`.
8. On land: amend no ADR (this repository keeps none); archive this folder through
   `doc-contract land` and confirm the declared paths all exist.

## Verify

- `uv run --group test pytest -q` green, including the new resolver, lifecycle, and landing tests
  and `scripts/test_capabilities_coverage.py`; `uv run --group lint ruff check .` clean;
  `doc-contract check --repo-root . --offline` returns 0 errors with no new warning delta beyond the
  declared baseline.
- In a temporary repository, a folder holding `change.md` plus `fix-b.md` is refused by `supersede`
  with the new code, the folder and its sibling are untouched, no journal is created, and
  `check --offline` reports the multi-node WARN naming the folder.
- In a temporary repository, a folder whose node document is `proposal.md` is refused by both `land`
  and `supersede` with a message naming the folder and `proposal.md` rather than the bare
  `change.md is missing`.
- Locator parity: the same roadmap fixtures (exact match, different case, wrapped continuation,
  missing, duplicated, ambiguous, generated block) produce the same located entry and the same
  fail-closed code for `accept`/`begin` and for `supersede`; the retired line's other bytes and all
  other lines are preserved.
- Invariant spot-check: runtime stays stdlib-only and cwd-independent; `--repo-root` stays explicit;
  diagnostics stay value-free (paths, ids, counts only — never document bodies, hashes, or the
  `--reason` text); `CHANGE_STATUSES`, `_STATUS_TOKENS`, and `roadmap-line-dangling` are unchanged;
  `land`'s in-progress-only precondition is unchanged; single-node folders behave byte-for-byte as
  they do today.
