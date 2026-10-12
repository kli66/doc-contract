---
id: runtime-source-provenance
persistence: ephemeral
status: proposed
track: architecture
depends_on:
  - vendored-runtime-closure
  - portable-install-contract-convergence
  - global-cwd-independent-cli
files_owned:
  - docs/changes/runtime-source-provenance/change.md
  - src/doc_contract/provenance.py
  - src/doc_contract/cli.py
  - src/doc_contract/sync.py
  - pyproject.toml
  - tests/test_provenance.py
  - tests/test_cli.py
  - docs/spec/capabilities.md
  - README.md
  - SKILL.md
  - docs/roadmap.md
---
# Point the runtime at its own source

Status: Proposed (not accepted) · Proposed 2026-10-12

**Upstream dependencies:** `vendored-runtime-closure` is landed and owns the deterministic vendored
runtime image plus `.doc-contract-manifest.json` identity — this change extends that manifest rather
than introducing a second one. `portable-install-contract-convergence` is landed and establishes that
a downstream repository runs either the system-level command or a vendored launcher, with no
client-specific skill directory as an execution boundary. `global-cwd-independent-cli` is landed and
establishes the explicit, fail-closed CLI surface this change adds one verb to. All three inputs are
available; no ADR exists in this repository, and no network, live service, or third-party package
gates implementation.

**Dependents:** No change depends on this item; it is additive to the runtime surface. Soft
overlaps: `reflect-project-evidence` and `review-bound-acceptance-plan` both declare `cli.py`,
`docs/spec/capabilities.md`, `README.md`, `SKILL.md`, and `docs/roadmap.md` in their `files_owned`.
This change touches different regions of those files (one new verb, one manifest field set, one
capability heading) and imposes no ordering, so whichever item lands second rebases and preserves
both contracts; back-links were added to both proposals' `Files owned` paragraphs when this folder
was authored.

**Files owned:** The new provenance module and its tests; `cli.py` for the `info` verb and its
`COMMANDS` entry; `sync.py` for the manifest's provenance keys and vendored version generation;
`pyproject.toml` for project URLs; the capability, README, and skill surfaces for the new verb; this
proposal and roadmap lineage. `scripts/config.py` reads `COMMANDS` dynamically and
`scripts/test_capabilities_coverage.py` already enforces the coupled capability heading, so neither
compatibility file changes. Declaring `src/doc_contract/provenance.py` and `tests/test_provenance.py`
before they exist adds two `owned-file-missing` baseline warnings for the duration of this proposal,
matching the existing convention in `reflect-project-evidence`; they clear when the work lands.

## Why

An agent that must resolve a detail of this workflow reads the prose verbatim in every client — the
skill text is identical whether it is loaded from pi or from a shared client directory. The code it
executes is not: it is a copy, and today no part of the runtime can say which copy it is or where the
canonical source lives. Concretely, in this checkout:

- `cli.py`'s `--version` prints the version string alone, and `COMMANDS` contains no provenance verb.
- `sync.py::_build_runtime_image` writes `.doc-contract-manifest.json` with `schema_version`,
  `package`, `version`, and `files` only — no source, no commit — and `_generated_version()` reduces
  the vendored `_version.py` to `__version__`, discarding the `__commit_id__` that setuptools-scm
  writes. A vendored runtime therefore cannot name its own commit even structurally.
- `pyproject.toml` declares no `[project.urls]`, so installed distribution metadata answers
  `Project-URL: None` and `Home-page: None` (measured against this checkout's uv editable install).
- Measured on the authoring host: `command -v doc-contract` resolves to
  `~/.local/bin/doc-contract`, whose package actually imports from
  `<checkout>/src/doc_contract/__init__.py`. That fact is reachable only out-of-band, through
  `uv-receipt.toml` and `__editable__*.pth`; the CLI cannot report it.

The failure this predicts is already observable. A per-client skill copy of the whole distribution
(`~/.pi/agent/skills/doc-contract` → `~/.cc-switch/skills/doc-contract`) ships verbatim-identical
prose alongside a stale `src/doc_contract/resolver.py`, `_version.py`, and `guides/new-change.md`
that differ from this checkout. An agent that does the reasonable thing — read the source next to the
skill it loaded — gets older behaviour with no staleness signal from any command, and cannot tell
whether the copy is canonical, a pinned vendor image, or simply neglected.

The fix is not more prose. It is making the running runtime able to name the source it is executing
and the revision it corresponds to, so that "examine the doc-contract sources" becomes a command
instead of a guess.

## What changes

**Δ ADDED** — `src/doc_contract/provenance.py`, one stdlib-only module holding the upstream constant
(`https://github.com/kli66/doc-contract`) and a single `describe_runtime()` resolver returning
`source` (the directory the executing `doc_contract` package resolves to, when that is a local
working copy or a vendored runtime; `None` when it is not resolvable), `mode`
(`local-checkout` | `vendored` | `installed`), `commit` (from `_version.__commit_id__` when present,
never synthesized), and `upstream` (always). Local source takes priority; `upstream` is the fallback
that is always present. Plus `tests/test_provenance.py` covering the resolution table (local
checkout, vendored image, site-packages install, unresolvable import) and commit present/absent. Plus
the `doc-contract info` verb: version, commit when known, resolved source when known, `upstream`, and
`mode`, printed as stable labeled lines.

**Δ MODIFIED** — `sync.py`: the manifest gains `upstream` always and `source`/`commit` when
resolvable, and `_generated_version()` preserves `commit_id`; `schema_version` stays `1` (additive),
and the write stays deterministic per host and idempotent. `cli.py`: `info` added to `COMMANDS` and
the parser; `--version` keeps its current bare shape so machine consumers of that string are
unaffected. `pyproject.toml`: `[project.urls]` with `Repository` and `Homepage`. The capability,
README, and skill surfaces document the new verb. `docs/roadmap.md`: this line and the regenerated
DAG. No ADR amendment (this repository keeps no `docs/adr/`).

Review points stated rather than silently decided: `info` deliberately takes no `--repo-root` and
reads no repository — it reports the runtime in hand, so it cannot infer or invent a repository
boundary; reporting a target repository's pinned manifest is a separate additive flag and is out of
scope here. `--version` stays bare rather than growing a provenance suffix, so `info` is the single
place provenance is rendered for humans.

**Δ REMOVED** — none.

## Tasks

1. `provenance.py` + `tests/test_provenance.py`: resolution table green, stdlib only, no URL fetch
   (the upstream value is a constant string, so the module stays offline by construction).
2. `cli.py`: add `info` to `COMMANDS`, the parser, and dispatch; leave `--version`'s output shape
   unchanged; extend `tests/test_cli.py` with an `info` invocation asserting the labeled lines.
3. `sync.py`: manifest provenance keys plus `commit_id` retention; extend the existing sync tests for
   the new keys and re-assert byte-identical repeat runs.
4. `pyproject.toml`: `[project.urls]`; confirm the editable install's metadata now answers
   `Project-URL` after a rebuild.
5. `docs/spec/capabilities.md`: add the anchored `### \`info\`` heading under `## CLI commands` and
   note the manifest provenance keys under `### \`sync\``; expose `doc-contract info` in `README.md`
   and, in `SKILL.md`, route "read the code you are executing" to it in one sentence beside the
   existing command block.
6. `docs/roadmap.md`: add the Architecture line, then regenerate the DAG with
   `doc-contract update --repo-root .`.
7. On land: archive this folder per the contract and confirm the two `owned-file-missing` baseline
   warnings from the declared new files have cleared.

## Verify

- `uv run pytest -q` green, including `scripts/test_capabilities_coverage.py`, which stays red until
  task 5 documents the new verb — that coupling is the point, not an obstacle.
- `doc-contract check --repo-root . --offline` returns 0 errors; the only warning delta is this
  proposal's two `owned-file-missing` baseline entries for the files it creates.
- In this checkout, `doc-contract info` prints a `source:` under
  `<checkout>/src/doc_contract`, `mode: local-checkout`, and a commit matching
  `git rev-parse --short HEAD`.
- In a temporary repository, `doc-contract sync --repo-root <tmp>` followed by
  `python <tmp>/.doc-contract/doc_contract_cli.py info` prints the vendored path and the same
  version; the manifest carries `upstream`; a second `sync` leaves the manifest byte-identical.
- Fallback behaviour: with the package source unresolvable (import outside a filesystem checkout),
  `info` omits `source:` and still prints `upstream:`, never a fabricated path.
- Invariant spot-checks: the zero-dependency stdlib runtime (`dependencies = []` unchanged, no new
  runtime import outside the standard library) and the fail-closed CLI boundary (`info` performs no
  repository discovery and no implicit `--repo-root` inference).
