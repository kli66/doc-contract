---
id: canonicalize-roadmap-status-transitions
persistence: ephemeral
status: proposed
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
---
# Canonicalize roadmap status during lifecycle transitions

Status: Proposed (not accepted) · Proposed 2026-08-03

**Upstream dependencies:** `accepted-change-state` is landed and owns the explicit `proposed -> accepted -> in-progress -> landed` lifecycle plus the resolver-owned acceptance/start projection. `landed-graph-transition-ownership` is landed and establishes that projected document state, roadmap rendering, and validation belong behind one resolver boundary. Both inputs are available. No ADR, external service, live input, or third-party dependency gates implementation.

**Dependents:** No in-repository change currently depends on this item. The active `review-bound-acceptance-plan` proposal changes the public acceptance-plan interface but does not depend on this roadmap-rewrite correction, and this item does not depend on that interface work.

**Files owned:** The resolver's roadmap status recognition and transition rewrite, focused resolver and lifecycle regressions, the existing `accept`/`begin` capability description, this proposal, and roadmap lineage. `review-bound-acceptance-plan` overlaps `tests/test_lifecycle.py`, `docs/spec/capabilities.md`, and `docs/roadmap.md`; this is a soft overlap with no shared runtime symbol, so whichever item lands second must rebase and preserve both behaviors. The other active proposals overlap only the roadmap.

## Why

Roadmap validation and lifecycle rewriting currently implement different status grammars. `_roadmap_status_for` accepts leading status markers such as `(proposed`, so a line containing `(Proposed, not accepted)` is valid and resolves as `proposed`. `_roadmap_transition_text` only replaces the exact closed token `(proposed)`, then marks the line as matched even when `re.sub` changed no bytes.

As a result, `doc-contract accept CHANGE` can start from an error-free repository, project the change front matter to `accepted`, leave the roadmap line unchanged, and abort with the generic `preflight-invalid: projected repository state fails validation`. The hidden projected finding is `roadmap-status-mismatch`. This violates the transaction's ownership contract: acceptance is supposed to update the selected change document, its roadmap prose and generated DAG, and affected dependent fingerprints as one validated plan.

## What changes

**Δ ADDED** — Add regression fixtures for annotated roadmap status forms, including the observed `(Proposed, not accepted)` spelling, and for an otherwise matched roadmap line whose status cannot be rewritten safely.

**Δ MODIFIED** — Make roadmap status recognition and lifecycle replacement use one compatible status-span contract. When `accept` or `begin` selects a valid roadmap line, replace the recognized source-status presentation with the canonical destination token `(accepted)` or `(in-progress)` while preserving the change reference and surrounding rationale. Treat a located line as rewritten only when the expected source status was actually replaced. Document that lifecycle transitions canonicalize the selected roadmap status as part of their atomic plan.

**Δ REMOVED** — Remove the false-success path in which the updater records a roadmap-line match after a zero-substitution regex call. Remove no supported lifecycle state, roadmap prose, CLI option, diagnostic code, or compatibility path.

## Tasks

1. Define the roadmap status span used by transition projection from the same supported source-status forms that validation recognizes for each permitted transition; do not create a second list that can drift independently.
2. Update `_roadmap_transition_text` so `accept` canonicalizes supported proposed presentations, including `(Proposed, not accepted)`, and `begin` canonicalizes supported accepted presentations while preserving all non-status prose on the selected line.
3. Require proof that exactly one unambiguous selected-node status span changed. If the node line is found but its current status cannot be rewritten safely, fail with a specific value-free `roadmap-invalid` planning error before projected repository validation rather than surfacing a generic `preflight-invalid` mismatch.
4. Add direct resolver tests covering canonical, annotated, case-varied, and currently supported non-parenthesized roadmap markers; retain ambiguity protection when a line names multiple active change folders.
5. Add lifecycle dry-run and apply regressions proving the observed annotated-proposed repository accepts successfully, produces a canonical `(accepted)` roadmap line and accepted DAG node, preserves surrounding roadmap prose, and leaves no journal after success. Add the corresponding accepted-to-in-progress coverage.
6. Update `docs/spec/capabilities.md` to state that `accept` and `begin` atomically canonicalize the selected roadmap status together with change metadata, generated DAG state, and dependent fingerprints. Do not broaden the CLI grammar or public diagnostic taxonomy.
7. Reconcile with `review-bound-acceptance-plan` if it lands first, run the focused and canonical gates, then archive this folder through the transactional lifecycle.

## Verify

- `uv run --group test pytest -q -p no:cacheprovider tests/test_resolver.py tests/test_lifecycle.py`
- `uv run --group test pytest -q -p no:cacheprovider`
- `uv run --group lint ruff check --no-cache .`
- `doc-contract check --repo-root . --offline --include-untracked`
- Focused reproduction: a temporary repository whose selected roadmap line is ``- `docs/changes/example/` (Proposed, not accepted) — rationale`` passes current resolution, `accept --dry-run` plans both change and roadmap writes, apply exits zero, and final resolution reports `accepted` with no errors.
- Failure-boundary check: a located but non-rewritable or ambiguous status presentation yields a specific value-free planning error and leaves document bytes, mtimes, Git index, and lifecycle journal state unchanged.
- Invariant spot-check: runtime remains stdlib-only; explicit user/reviewer authority is still required; only the selected roadmap line is changed; surrounding prose and unrelated changes remain byte-for-byte stable; dry-run remains mutation-free; and final projected validation still fails closed.
