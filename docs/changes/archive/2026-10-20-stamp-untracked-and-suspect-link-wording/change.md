---
id: stamp-untracked-and-suspect-link-wording
persistence: ephemeral
status: landed
track: lifecycle
depends_on:
  - discovery-lifecycle-hardening
files_owned:
  - docs/changes/stamp-untracked-and-suspect-link-wording/change.md
  - src/doc_contract/cli.py
  - src/doc_contract/resolver.py
  - tests/test_cli.py
  - tests/test_resolver.py
  - docs/spec/capabilities.md
  - README.md
  - docs/roadmap.md
accepted_at: 2026-10-20
started_at: 2026-10-20
landed_at: 2026-10-20
archive_path: docs/changes/archive/2026-10-20-stamp-untracked-and-suspect-link-wording
---
# `stamp --include-untracked` and an actionable `[suspect-link]` remediation

Status: Landed · 2026-10-20

**Upstream dependencies:** `discovery-lifecycle-hardening` is landed and is the canonical owner of
the tracked/declared discovery boundary and of its explicit `--include-untracked` opt-in, which its
tasks record as threaded through "`check`, `update`, and landing preflight" and which it also owns
for the actionable hash-finding remediation text this change mirrors. That input is available;
`stamp` reads the same discovery seam through `discover_nodes` (`src/doc_contract/resolver.py:580-586`)
and only needs the flag threaded into it. `edge-fingerprint-policy` is landed and owns the advisory
default under which `[suspect-link]` stays a WARN; it is **not** a dependency, because the finding
fires under both policies (`tests/test_resolver.py::test_stale_edge_hash_warns_under_both_policies`)
and this change rewords its remediation clause without touching the policy switch. No ADR exists in
this repository, and no external service, live input, or third-party package gates implementation.

**Dependents:** None. No active change in this repository depends on it. The consumers of the fixed
behaviour are every operator who stamps a still-provisional change and every agent that reads a
`[suspect-link]` warning to find its remediation command; no in-repository change folder is blocked
by it.

**Files owned:** The `stamp` parser entry and handler in the packaged CLI; the discovery opt-in
plumbing in `stamp_node` plus the `[suspect-link]` remediation clause in the resolver's edge
findings; the focused CLI and resolver tests; the capability reference and README sentences that
document the verb and its flags; this proposal and the roadmap lineage line + regenerated DAG.

**Overlap check (reverse direction):** `retirement-guards-and-roadmap-entry-locator` (still
**proposed**) declares `src/doc_contract/resolver.py`, `tests/test_resolver.py`,
`docs/spec/capabilities.md`, `README.md`, and `docs/roadmap.md` — five of this change's eight paths.
The overlap is soft and region-disjoint: that item owns the roadmap-entry locator, the landing
retarget policy, the multi-node folder precondition, and the `change.md`-missing refusal, while this
item touches only the discovery opt-in read at `resolver.py:1883` and the `[suspect-link]` message at
`resolver.py:795-796`. No shared symbol changes, so **no `depends_on` edge is declared** and whichever
of the two lands second rebases: the later lander reconciles both edits in the four shared documents
and keeps both contracts. That item names this handoff explicitly in its own overlap paragraph — it
deliberately does not own "no `--include-untracked`, and a `[suspect-link]` remediation that does not
name the depender to re-stamp" — so this proposal is the promised sibling, not a competing owner.
`runtime-source-provenance` (proposed) declares `src/doc_contract/cli.py`, `tests/test_cli.py`,
`docs/spec/capabilities.md`, `README.md`, and `docs/roadmap.md`; it adds a new module and a new verb
region, this item edits the existing `stamp` parser and handler lines, so the overlap is additive and
whichever lands second rebases. `optional-project-memory` and `proportional-accepted-work-contract`
share only `docs/roadmap.md` (a lineage-prose region). No overlap with any landed baseline is a
conflict: `discovery-lifecycle-hardening` and `edge-fingerprint-policy` both historically owned the
resolver and its tests and are landed, not active.

**Test couplings checked:** `scripts/test_capabilities_coverage.py` enumerates `cli.COMMANDS` only
(`scripts/config.py::_cli_commands` → one `CapabilityCheck(name="CLI commands")`), so a new **flag**
on an existing command needs no tripwire edit and `tests/test_cli.py::test_capability_surface_is_explicit`
keeps passing; the `capabilities.md` prose is updated because it is the consumer-surface doc, not
because a tripwire demands it. `tests/test_landing.py:664` calls
`stamp_node(root, _settings(root), "transactional")`, which is why the new `stamp_node` parameter must
be keyword-only with a default: that call site stays untouched and this change does not own
`tests/test_landing.py`.

**Decisions recorded**

1. **`stamp` does not gain `--dry-run` (decided: no).** `--dry-run` exists on `accept`, `begin`,
   `land`, and `supersede` because each is a multi-mutation, journal-backed transaction whose
   planning step can refuse before a mutation set is applied. `stamp` performs exactly one
   idempotent front-matter rewrite on one named node — the whole `fingerprints` map, or `self_hash`
   for a frozen node — and already reports its own post-condition (`<id> stamped` /
   `<id> already current`, `cli.py:192`); `stamp_node` has no plan
   object, no journal, and no preflight to preview, so a `--dry-run` surface would add an option and
   an output contract while protecting the caller from nothing they cannot already see from the
   idempotent result. Reversal condition: if a later change makes `stamp` multi-node or journaled,
   preview is reconsidered there.
2. **`stamp --include-untracked` prints no untracked-discovery preview (decided: no).** The shared
   `_print_discovery_preview` exists for verbs that select a *set* of provisional nodes the operator
   never named (`check`, `update`, and landing). `stamp` takes one node id the operator just typed, so
   the flag's effect is already fully determined by the argument and reported by the outcome line.
   This also keeps `stamp_node` returning `bool` (no result-object churn at its existing call site).

## Why

Two residuals of the same consumer incident, both small and both currently misleading.

*First, `stamp` is the only graph-resolving verb without `--include-untracked`.* Its parser
accepts only the common `--repo-root`/`--config` pair plus the positional node id (`cli.py:71-72`), and
`stamp_node` calls `discover_nodes` without the opt-in (`resolver.py:1883`), so an untracked
(never-committed) change node is not in the node set at all and the verb refuses with a
discovery-miss masquerading as an identity-miss:

```console
$ doc-contract stamp example-change --repo-root .
ERROR: [stamp-failed] unknown node id 'example-change'
```

while `check --offline --include-untracked` on the same tree discovers that node (`cli.py:68, 70, 86,
91, 102, 107, 113, 120` are the other eight verbs' copies of the flag). Reproduced
in a temporary repository on the 2026-10-19 tree: a committed `docs/changes/dependent/` whose
`depends_on: [demo]` fingerprint is stale, plus an untracked `docs/changes/newthing/change.md`.
`stamp newthing` returns exit `1` with exactly the message above, `check --offline` reports
`untracked-node-excluded` for it, and `check --offline --include-untracked` includes it as
`newthing`. A change folder is untracked by default between `new-change` and its first commit —
precisely the window in which its author is stamping proactively — so the parity gap is the normal
path, not an edge case.

*Second, `[suspect-link]` names a remedy that cannot be performed.* The warning says:

```text
WARN BASELINE: [suspect-link] dependent → demo: target changed since review
  (recorded deadbeefdeadbeef, now 4c54acca9093b823); re-review and re-stamp
```

"re-stamp" names no subject and no command. Its sibling finding in the same loop already does it
right — `edge-hash-*` ends with ``review the target and run `doc-contract stamp {n.id}` ``
(`resolver.py:783-784`) — and the two findings differ only in *why* the recorded hash is out of date
(absent/unusable versus present-but-stale), not in *what fixes it*. The actionable metadata is
`fingerprints.<dep>` in the **depender's** front matter, so the only useful instruction names the
depender. Verified in the same temporary repository: after the dependency's body changes,
`stamp dependent` rewrites `fingerprints.demo` from `deadbeefdeadbeef` to the current hash and the
`[suspect-link]` warning disappears on the next `check`.

Both are one-seam corrections on surfaces the repository already owns; persistence of the fix stays
ephemeral and the layer stays thin. Neither needs a new verb, and neither changes the set of
findings — only a message's remediation clause and one command's input grammar.

## What changes

**Δ ADDED**

- **`stamp --include-untracked`.** The `stamp` subparser gains the same boolean flag the other eight
  verbs already accept (`check`, `update`, `reconcile mechanical`, `land`, `supersede`, `accept`,
  `begin`, `reflect` — the last for grammar parity only, since it forwards the flag to reflection
  planning rather than discovery) and threads it into the same discovery opt-in they use, so an
  untracked change node is discoverable and stampable instead of reported as unknown. The flag prints
  no `untracked-node-included` preview and no discovery preview at all: the operator named the node,
  and the outcome line already reports the result (decision 2). `sync` needs no copy of the flag: it
  vendors the package and never resolves the document graph. No default changes: without the flag,
  today's exclusion behaviour and message are unchanged.
- **An actionable `[suspect-link]` remediation clause.** The warning keeps its code, level, subjects,
  and recorded/current fingerprints and gains the depender-named command, mirroring the `edge-hash-*`
  sibling. Exact before/after of the message template (`{depender}` is `n.id`, `{dep}` is
  `e.target`):

  ```text
  before: {depender} → {dep}: target changed since review (recorded {recorded}, now {current}); re-review and re-stamp
  after:  {depender} → {dep}: target changed since review (recorded {recorded}, now {current}); review the target and run `doc-contract stamp {depender}` (add `--include-untracked` while it is provisional)
  ```

  Rendered on a real shape, only the trailing clause differs:

  ```text
  before: dependent → demo: target changed since review (recorded deadbeefdeadbeef, now 4c54acca9093b823); re-review and re-stamp
  after:  dependent → demo: target changed since review (recorded deadbeefdeadbeef, now 4c54acca9093b823); review the target and run `doc-contract stamp dependent` (add `--include-untracked` while it is provisional)
  ```

  The value-free boundary is unchanged — the message already carries two fingerprint hex strings and
  still carries nothing else.

**Δ MODIFIED**

- `src/doc_contract/cli.py`: `stamp.add_argument("--include-untracked", action="store_true")` beside
  the existing positional (`cli.py:71-72`), and `_stamp(context, node_id, *, include_untracked)`
  forwarding it (`cli.py:186-193`) from the dispatcher (`cli.py:745-746`). No other command's grammar
  or output moves.
- `src/doc_contract/resolver.py`: `stamp_node` gains a keyword-only `include_untracked: bool = False`
  and passes it to `discover_nodes(root.resolve(), settings, include_untracked=include_untracked)`
  (`resolver.py:1881-1883`); the `[suspect-link]` clause at `resolver.py:795-796` becomes the
  depender-named command. The default keeps the existing library call site and every current caller
  byte-identical.
- `tests/test_cli.py` and `tests/test_resolver.py`: extend the existing pins rather than adding a new
  module — the `stamp` CLI test (`tests/test_cli.py:345-371`) gains an untracked-node case with and
  without the flag, and the stale-hash test
  (`tests/test_resolver.py:280-293`) asserts the new remediation string.
- `docs/spec/capabilities.md`: the `stamp` section (`docs/spec/capabilities.md:25`, heading plus two
  prose lines today) states the flag and what it admits. `README.md`: the command-reference console
  block line for `stamp` (`README.md:207`) gains the flag, and the discovery paragraph that already
  explains `--include-untracked` for the other verbs (`README.md:228`) stops implying `stamp` is
  exempt. `SKILL.md` is deliberately **not** owned:
  it documents one path-shaped `stamp` invocation in its intent-routing table (`SKILL.md:34`) and
  enumerates no verb flags, so there is no flag list there to correct.
- `docs/roadmap.md`: this Lifecycle line and the regenerated generated DAG. While the new folder is
  untracked, the block is rendered with `--include-untracked` (the rendering a committed tree
  produces); re-verify with the plain `doc-contract update --repo-root .` once the folder is tracked.
  The block is never hand-edited.

**Δ REMOVED** — None. No command, flag, finding code, severity, subject tuple, JSON shape, or
lifecycle state is removed. The `[suspect-link]` code and its WARN level are preserved verbatim; only
the remediation clause changes, so no pinned code, filter, or downstream handler moves.

**Explicit non-goal — no fingerprint-refresh verb.** The same incident suggested a
`refresh-fingerprints <change>` verb (or flag) because "no verb refreshes a dependency fingerprint on
demand once its dependency has landed". That premise is false on the current tree, and this change
declines the verb rather than building around a defect that does not exist. Reproduced in a
temporary repository: `stamp <depender>` refreshes `fingerprints.<dep>` for any **active** node with
edges (`resolver.py:1894-1904`) regardless of the dependency's own state, and clears
`[suspect-link]` even after the dependency landed and was archived under
`docs/changes/archive/<date>-<name>/` (the archived node keeps its front-matter `id`, so the edge
still resolves and the target path still exists). Meanwhile `stamp <landed-dep>` legitimately
refuses, because a landed ephemeral node has no stampable contract
(`resolver.py:1912-1913`): `ERROR: [stamp-failed] node 'demo' has no stampable contract`, exit `1`.
That pairing is the intended design, not a gap — the fingerprint is recorded on the depender, so the
depender is where it is refreshed. Adding a second verb that does what `stamp <depender>` already
does would duplicate the write path, double the surface the capability doc must describe, and invite
the two implementations to drift; the fix the operator actually needs is the message naming the
command, which this change makes.

## Tasks

1. Add `--include-untracked` to the `stamp` subparser (`cli.py:71-72`), forward it through
   `_stamp` (`cli.py:186-193`) and the dispatcher (`cli.py:745-746`), and confirm `stamp --help`
   lists it in the same form the other verbs do.
2. Add the keyword-only `include_untracked: bool = False` parameter to `stamp_node`
   (`resolver.py:1881-1883`) and pass it to `discover_nodes`; confirm a default-argument call is
   byte-identical in behaviour and keeps `tests/test_landing.py:664` green unmodified.
3. Extend the `stamp` CLI test (`tests/test_cli.py:345-371`) with an untracked change folder that
   carries its phase-appropriate roadmap line, so the assertion isolates discovery rather than
   `no-roadmap-line`: `stamp <id>` without the flag still exits `1` with `[stamp-failed] … unknown
   node id`; with `--include-untracked` it exits `0`, writes `fingerprints.<dep>`, and the subsequent
   `check --offline --include-untracked` gains no new error or warning for that node.
4. Reword the `[suspect-link]` remediation clause (`resolver.py:795-796`) to the depender-named
   command, mirroring `resolver.py:783-784`.
5. Extend the stale-hash resolver test (`tests/test_resolver.py:280-293`) to pin the message under
   both fingerprint policies: it names the depender, contains ``doc-contract stamp <depender>``, and
   carries the `--include-untracked` hint for the provisional case; the code stays `suspect-link`,
   the level stays `WARN`, and the
   recorded/current fingerprints stay in the text. Add the archived-dependency variant so the
   non-goal above stays true: `stamp <depender>` clears the warning after the dependency is archived.
6. Update `docs/spec/capabilities.md` (the `stamp` section at `:25`) and `README.md` (the `stamp`
   console line and the discovery paragraph). Confirm `scripts/test_capabilities_coverage.py` needs no
   change — it enumerates `cli.COMMANDS`, and this change adds no command.
7. Add the `docs/roadmap.md` Lifecycle line and regenerate the DAG while the folder is still
   untracked with `doc-contract update --repo-root . --include-untracked`, then confirm that the
   plain `doc-contract update --repo-root .` produces the same block once the folder is tracked;
   never hand-edit the generated block.
8. On land: amend no ADR (this repository keeps none); archive this folder through
   `doc-contract land` and confirm every declared path exists.

## Verify

- `uv run --group test pytest -q` green, including the extended `stamp` CLI and stale-hash resolver
  tests and `tests/test_cli.py::test_capability_surface_is_explicit`; `uv run --group lint ruff check .`
  clean; `doc-contract check --repo-root . --offline` returns 0 errors with no warning growth beyond
  the declared baseline.
- In a temporary repository: an untracked change folder is refused by `stamp <id>` exactly as today
  and stamped by `stamp <id> --include-untracked`, with the resulting front matter carrying the
  current `fingerprints.<dep>`; a *tracked* node stamps identically with and without the flag, so the
  flag never changes a tracked node's outcome.
- In a temporary repository: a stale `fingerprints.<dep>` produces the new `[suspect-link]` text; the
  command it names, run verbatim, clears the warning on the next `check` — before and after the
  dependency is archived.
- Negative check on the non-goal: `stamp <landed-dep>` still exits `1` with
  `node … has no stampable contract`, and no `refresh-fingerprints` command appears in
  `doc-contract --help` or `cli.COMMANDS`.
- Invariant spot-check: runtime stays stdlib-only and cwd-independent; `--repo-root` stays explicit;
  diagnostics stay value-free (ids, paths, and the two fingerprint hex values already present — never
  document bodies); discovery stays tracked/declared by default with `--include-untracked` as the
  only opt-in; `suspect-link` keeps its code, WARN level, and subject tuple; `stamp`'s frozen
  `self_hash` path and `already current` idempotence are unchanged.
