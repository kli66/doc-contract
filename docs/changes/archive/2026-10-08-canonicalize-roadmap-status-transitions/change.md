---
id: canonicalize-roadmap-status-transitions
persistence: ephemeral
status: landed
track: lifecycle
depends_on:
  - accepted-change-state
  - landed-graph-transition-ownership
files_owned:
  - docs/changes/canonicalize-roadmap-status-transitions/change.md
  - src/doc_contract/resolver.py
  - tests/test_resolver.py
  - tests/test_lifecycle.py
  - docs/spec/capabilities.md
  - docs/roadmap.md
accepted_at: 2026-10-08
started_at: 2026-10-08
landed_at: 2026-10-08
archive_path: docs/changes/archive/2026-10-08-canonicalize-roadmap-status-transitions
---
# Canonicalize roadmap status during lifecycle transitions

Status: Landed · 2026-10-08

**Upstream dependencies:** `accepted-change-state` is landed and owns the explicit `proposed -> accepted -> in-progress -> landed` lifecycle plus the resolver-owned acceptance/start projection. `landed-graph-transition-ownership` is landed and establishes that projected document state, roadmap rendering, and validation belong behind one resolver boundary. Both inputs are available. No ADR, external service, live input, or third-party dependency gates implementation.

**Dependents:** No in-repository change currently depends on this item. The active `review-bound-acceptance-plan` proposal changes the public acceptance-plan interface but does not depend on this roadmap-rewrite correction, and this item does not depend on that interface work.

**Files owned:** The resolver's roadmap status recognition and transition rewrite, focused resolver and lifecycle regressions, the existing `accept`/`begin` capability description, this proposal, and roadmap lineage. `review-bound-acceptance-plan` overlaps `tests/test_lifecycle.py`, `docs/spec/capabilities.md`, and `docs/roadmap.md`; this is a soft overlap with no shared runtime symbol, so whichever item lands second must rebase and preserve both behaviors. The other active proposals overlap only the roadmap.

## Why

Roadmap validation and lifecycle rewriting currently implement two different status grammars for the same line, and the mismatch is only discovered after a write has been planned. `_roadmap_status_for` (`src/doc_contract/resolver.py:695`) decides a line's status by matching the leading/prefix tokens in `_STATUS_TOKENS` (`src/doc_contract/resolver.py:89`), which include `("(proposed", "proposed")` and `("proposed 20", "proposed")`; any line that merely *starts* with a status marker therefore resolves cleanly, even when the marker is qualified by trailing text. `_roadmap_transition_text` (`src/doc_contract/resolver.py:1150`) rewrites the line with the exact closed-token pattern declared at `src/doc_contract/resolver.py:1172`, `r"\((?:proposed|accepted|in-progress|blocked)\)"`, and then sets `matched = True` unconditionally at `src/doc_contract/resolver.py:1178`, whether or not the `re.sub` changed any bytes. A qualified presentation is thus valid for resolution but non-rewritable for transition, and the zero-substitution call reports success.

The divergence was reproduced in production this session (2026-10-08) in `/var/home/kai/Documents/Projects/personal-pi`. `docs/changes/retire-pi-caffeinate/change.md` carried `status: proposed` while its roadmap line read ``- `docs/changes/retire-pi-caffeinate/` (proposed, depends on the landed `bump-vendored-extensions-2026-10`) — promote deferred-register entry 1: …``. `doc-contract accept docs/changes/retire-pi-caffeinate/ --repo-root . --dry-run` printed `ERROR: [preflight-invalid] preflight-invalid: projected repository state fails validation` and planned nothing, while `doc-contract reconcile mechanical docs/changes/retire-pi-caffeinate/ --phase entry --format json` reported only the expected `change-proposed-unaccepted` finding with `ready:false`. Replaying `resolver.resolve` and then `resolver.project_transition(action="accept")` in-process against the installed editable package showed the same split directly: the current resolution has zero errors, and the projected (post-accept) resolution carries the hidden error `roadmap-status-mismatch` — "front-matter status='accepted' but roadmap line reads 'proposed'".

The generic `preflight-invalid: projected repository state fails validation` message is what hides the real cause. Projected-state validation fails closed and reports only that the projection as a whole is invalid; the specific `roadmap-status-mismatch` finding that names the un-rewritable line never reaches the operator, so the failure looks like a repository defect rather than an unreachable transition.

The same grammar divergence affects every qualified-status presentation, not only the reproduced one. In the same repository, the space-qualified form `(proposed foundation)` still appears on the `` `docs/changes/nix-realized-package-pipeline/` `` line, and the comma-qualified form `(proposed, depends on …)` still appears on several others (for example `nix-native-platform-validation`, `nix-live-projection-readiness`, and `personal-pi-harness-controller-adapter`). Each of those lines passes current resolution and would fail `accept` the same way as `retire-pi-caffeinate` did.

The observed operator decision was to *not* fix the tool in that session and instead normalize the affected `personal-pi` roadmap line(s) to bare `(proposed)`, preserving the dependency rationale as prose after the em dash (the `retire-pi-caffeinate` line now reads bare `(proposed)` with `depends on …` after the dash). That workaround removes the symptom on the normalized lines only; it leaves the defect fully exposed for every remaining qualified-status line above until this item lands.

The underlying cause is unchanged: acceptance is supposed to update the selected change document, its roadmap prose and generated DAG, and affected dependent fingerprints as one validated plan, and a transition that cannot rewrite the status it recognized breaks that ownership contract.

## What changes

**Δ ADDED** — Add regression fixtures for annotated roadmap status forms, including the observed `(Proposed, not accepted)` spelling, and for an otherwise matched roadmap line whose status cannot be rewritten safely.

**Δ MODIFIED** — Make roadmap status recognition and lifecycle replacement use one compatible status-span contract. When `accept` or `begin` selects a valid roadmap line, replace the recognized source-status presentation with the canonical destination token `(accepted)` or `(in-progress)` while preserving the change reference and surrounding rationale. The recognized presentation is the whole parenthesized group from a supported source-status marker through its closing parenthesis, or the matched bare marker; it is replaced wholesale, so in-presentation annotations such as `depends on …` or `not accepted` are dropped while the change reference and the em-dash rationale are preserved byte-for-byte. Treat a located line as rewritten only when the expected source status was actually replaced. Document that lifecycle transitions canonicalize the selected roadmap status as part of their atomic plan.

**Δ REMOVED** — Remove the false-success path in which the updater records a roadmap-line match after a zero-substitution regex call. Remove no supported lifecycle state, roadmap prose, CLI option, diagnostic code, or compatibility path.

## Tasks

1. [x] Define the roadmap status span used by transition projection from the same supported source-status forms that validation recognizes for each permitted transition; do not create a second list that can drift independently.
2. [x] Update `_roadmap_transition_text` so `accept` canonicalizes supported proposed presentations — including the case-varied `(Proposed, not accepted)`, the comma-qualified `(proposed, depends on …)`, and the space-qualified `(proposed foundation)` forms observed in production — and `begin` canonicalizes supported accepted presentations, replacing the whole recognized presentation and preserving all prose outside it byte-for-byte.
3. [x] Require proof that exactly one unambiguous selected-node status span changed. If the node line is found but its current status cannot be rewritten safely, fail with a specific value-free `roadmap-invalid` planning error before projected repository validation rather than surfacing a generic `preflight-invalid` mismatch.
4. [x] Add direct resolver tests covering canonical, annotated (comma- and space-qualified), case-varied, and currently supported non-parenthesized roadmap markers; retain ambiguity protection when a line names multiple active change folders.
5. [x] Add lifecycle dry-run and apply regressions proving the observed annotated-proposed repository accepts successfully, produces a canonical `(accepted)` roadmap line and accepted DAG node, preserves surrounding roadmap prose, and leaves no journal after success. Add the corresponding accepted-to-in-progress coverage.
6. [x] Update `docs/spec/capabilities.md` to state that `accept` and `begin` atomically canonicalize the selected roadmap status together with change metadata, generated DAG state, and dependent fingerprints. Do not broaden the CLI grammar or public diagnostic taxonomy.
7. [x] Reconcile with `review-bound-acceptance-plan` if it lands first, run the focused and canonical gates, then archive this folder through the transactional lifecycle.

## Verify

- `uv run --group test pytest -q -p no:cacheprovider tests/test_resolver.py tests/test_lifecycle.py`
- `uv run --group test pytest -q -p no:cacheprovider`
- `uv run --group lint ruff check --no-cache .`
- `doc-contract check --repo-root . --offline --include-untracked`
- Focused reproduction: a temporary repository whose selected roadmap line carries an annotated status presentation — case-varied `(Proposed, not accepted)`, comma-qualified ``(proposed, depends on the landed `x`)``, or space-qualified `(proposed foundation)`, each followed by an em-dash rationale — passes current resolution, `accept --dry-run` plans both change and roadmap writes, apply exits zero, final resolution reports `accepted` with the line canonicalized to `(accepted)` and the rationale preserved.
- Failure-boundary check: a located but non-rewritable or ambiguous status presentation yields a specific value-free planning error and leaves document bytes, mtimes, Git index, and lifecycle journal state unchanged.
- Invariant spot-check: runtime remains stdlib-only; explicit user/reviewer authority is still required; only the selected roadmap line is changed; surrounding prose and unrelated changes remain byte-for-byte stable; dry-run remains mutation-free; and final projected validation still fails closed.
