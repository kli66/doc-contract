---
id: portable-install-contract-convergence
persistence: ephemeral
status: landed
track: remediation
depends_on:
  - edge-fingerprint-policy
fingerprints:
  edge-fingerprint-policy: d905fcb4fb5d4745
files_owned:
  - AGENTS.template.md
  - README.md
  - SKILL.md
  - scripts/config.py
  - tests/test_cli.py
  - docs/roadmap.md
landed_at: 2026-07-23
archive_path: docs/changes/archive/2026-07-23-portable-install-contract-convergence
---
# Converge the portable installation contract

Status: Landed · 2026-07-23

**Upstream dependencies:** `edge-fingerprint-policy` is landed and supplies the current
`.doc-contract.toml` schema, advisory-by-default dependency review policy, and strict frozen-document
guard that the portable instructions must teach. Its reviewed body fingerprint is recorded above.
The packaged CLI, vendored `sync` launcher, explicit repository boundary, and transactional landing
path are inherited through the landed remediation chain. There are no ADRs or external inputs; the
stdlib package and temporary-repository proof are available now.
**Dependents:** None currently. This is the next remediation item after the five landed workstreams;
no active change folder or roadmap item requires a back-link.
**Files owned:** The user-facing README, skill/install guide, portable operating-contract template,
legacy compatibility configuration example, one focused packaged-to-vendored CLI integration test,
and the roadmap. The packaged sync implementation and build metadata were inspected and already
provide the required launcher, package file set, entry point, and zero-runtime-dependency boundary;
no resolver, sync, packaging, capability-surface, or ADR change is planned. There are no other
active change folders and therefore no file or symbol ownership overlaps.

## Why

The installation story is split between two generations. `README.md` correctly leads with the
installed `doc-contract` command, `.doc-contract.toml`, and the `.doc-contract/` vendored launcher,
but `AGENTS.template.md` still says enforcement lives in a tracked
`.claude/skills/doc-contract/` tree and that repositories configure `scripts/config.py`. `SKILL.md`
describes the packaged configuration boundary while its layout and optional-test examples still
look like the old tracked-skill installation. `scripts/config.py` reinforces that ambiguity with
`.claude` parent-depth advice and a project-specific tkcs example.

The current focused sync test proves pins and idempotence, but it does not exercise the documented
portable outcome: a newly created target repository, configured only through `.doc-contract.toml`,
can use the packaged CLI to sync and then run the vendored launcher to check that repository from an
unrelated working directory. Without that proof, the docs can drift back toward assumptions that
are absent from the package and fail only for a new adopter.

## What changes

**Δ ADDED** — Add a clean temporary-repository integration proof that creates the minimum documented
contract and roadmap, invokes packaged `sync`, then invokes the generated vendored launcher for an
offline `check` from outside the target repository. Assert success, explicit target selection, and
the absence of any `.claude` installation prerequisite.

**Δ MODIFIED** — Make `README.md`, `SKILL.md`, and `AGENTS.template.md` tell one canonical setup:
install or otherwise make the package available, create `.doc-contract.toml`, adapt the portable
operating contract, seed the roadmap, optionally vendor with `sync`, and validate with the packaged
or vendored CLI. Clearly label the flat `scripts/` modules and pytest tripwires as compatibility
material rather than the configuration or execution boundary. Reduce `scripts/config.py` to a
generic compatibility seam for this checkout and remove tkcs-specific examples and `.claude`
placement assumptions.

**Δ REMOVED** — Remove installation claims that require `.claude/skills/doc-contract/`, treat
`scripts/config.py` as the canonical per-repository configuration, or present tkcs symbols as the
portable worked example. Do not remove the compatibility adapters or their tests.

## Tasks

1. **Done.** Rewrite `AGENTS.template.md` comments, enforcement description, layout, and configuration notes
   around `.doc-contract.toml` and the packaged/vendored CLI; keep agent-client files optional and
   keep the taxonomy and lifecycle invariants unchanged.
2. **Done.** Converge the `SKILL.md` layout and install procedure on the same package/config contract. Explain
   that `/doc-contract install` is the skill workflow while `doc-contract sync` is the CLI vendoring
   command, and quarantine flat-script paths as optional compatibility guidance.
3. **Done.** Tighten `README.md` into an executable fresh-repository sequence with the minimal manifest,
   operating-contract adaptation, roadmap seed, optional sync, and offline check commands in their
   actual order.
4. **Done.** Remove tkcs-specific and `.claude`-placement material from `scripts/config.py`; retain only the
   real checkout's compatibility settings and generic guidance for repositories intentionally
   keeping the legacy tripwires.
5. **Done.** Extend `tests/test_cli.py` with a clean temporary-repository integration test that runs packaged
   `sync`, executes `.doc-contract/doc_contract_cli.py check --repo-root <target> --offline` from an
   unrelated cwd, and proves the flow needs neither target-project imports nor a `.claude` tree.
6. **Done.** Run the full test, lint, and resolver gates; use focused text checks to ensure canonical
   installation prose no longer presents `.claude` or tkcs as requirements while intentional
   compatibility references remain explicitly labelled.
7. **Done through the transactional landing boundary.** On land, archive this folder through the transactional command and retain the roadmap lineage;
   no ADR or capability reference amendment is required because no CLI command or resolver
   semantics change.

## Verify

- `uv run pytest -q`, Ruff, and `make check` are green, including the new end-to-end
  temporary-repository proof.
- The proof invokes both the package entry point and the generated vendored launcher, checks the
  explicitly selected fresh repository from another cwd, and observes `offline verified` with no
  `.claude` directory present.
- `rg` confirms tkcs-specific examples are absent from the portable template/install surfaces and
  that any remaining `.claude` or flat-script references are clearly compatibility-only, not
  required configuration or execution paths.
- Invariant spot-check: the package remains stdlib-only, `.doc-contract.toml` remains the sole
  target-repository configuration input, repository selection remains explicit and fail-closed,
  and the resolver, sync manifest, command set, secret-redaction behavior, and fingerprint policy
  are unchanged.
