# Why bespoke doc-contract, not OpenSpec / OpenLore

An ADR-style decision record for *this skill's existence*. It lives with the tooling (not in a
repo's `docs/adr/`) because doc-contract decisions belong to the workflow, not the product — and
because a repo installing this skill should get the "why not just use OpenSpec?" answer with it.

## Context

The scheme this skill enforces was **bootstrapped off OpenSpec conceptually** — the `specs/` +
`changes/` spine, the propose → apply → archive loop, the `ADDED`/`MODIFIED`/`REMOVED` delta format,
tool-agnostic AGENTS.md integration. OpenSpec (a Node CLI) and its companion **OpenLore** (a
TypeScript agent-memory harness that adds spec↔code drift detection) between them reconstruct an
estimated **70–80% of the SDD spine** off the shelf. On that spine alone, this skill is largely
re-invention — and honesty requires saying so.

## Decision

**Re-implement the subset we need as a zero-dependency, stdlib-only Python skill**, rather than adopt
OpenSpec/OpenLore as tools. Two independent reasons, either sufficient:

1. **The air-gap / constraint stack.** The consuming project (tkcs) is air-gapped, egress-blocked,
   OSS-vetted, Python + uv. OpenSpec needs Node 20+; OpenLore is TypeScript/npm. Introducing a Node
   toolchain + npm dependency tree into an egress-blocked environment is exactly the cost the project
   constraints exist to avoid (every dep + its telemetry must be vetted under the egress block). A
   stdlib reimplementation of the *needed subset* dodges that entirely — it drops into an air-gapped
   repo unchanged, run by the `pytest`/`python` already present.

2. **Three deltas neither tool provides.** These are the parts that are *not* re-invention:
   - **A dependency-scheduling change-DAG.** OpenSpec's `changes/` is **unordered** — no
     `depends_on`, topo-sort, cycle/ownership-overlap detection, or generated dependency view. Our
     front-matter resolver (`dag.py`) is a scheduling layer on top of the spine that neither OpenSpec
     nor OpenLore has.
   - **A 4-class persistence forcing-function model** (`frozen`/`living`/`ephemeral`/`deferred`,
     each with an explicit forcing function — tripwire, delete-on-land, reconciliation, or per-entry
     Trigger). A maintenance *model*, not a feature either tool encodes.
   - **`frozen` `self_hash` immutability** — append-only teeth on frozen docs (a body edit without a
     re-stamp is an ERROR). OpenLore detects code drift; neither flags a tampered frozen doc.

## Consequences

- We **own a thin layer** (the resolver + tripwires + the persistence/forcing-function model). The
  SDD-spine mechanics underneath it are deliberately re-rolled for the constraint, not because they
  are novel. Keep the layer thin; do not re-invent more of OpenSpec than the constraint forces.
- **Re-evaluate if the constraint lifts.** If the consuming repo ever gains a vetted Node toolchain
  (egress relaxed, or a mirror), adopting OpenSpec for the spine and keeping only the three deltas as
  a plugin/overlay becomes the cheaper path. This decision is contingent on the air-gap, not eternal.
- **Zero-dep is load-bearing** — it is *the* reason this is defensible over OpenSpec. Never add a
  third-party dependency to the resolver (a stdlib YAML-subset parser and f-string Mermaid render are
  in `dag.py` precisely to hold this line). The day it needs PyYAML/Jinja2, re-open reason (1).
- **Dependency topology is mandatory; review fingerprints are advisory by default.** The structural
  edge still drives ordering, dangling-edge, cycle, ownership, and roadmap-linkage checks. An edge
  fingerprint remains useful provenance that `stamp` and `land` can refresh, but a repository must
  set `edge_fingerprints = "required"` to make absent or invalid active-edge hashes fail the gate.
  This policy does not relax frozen `self_hash` tamper detection.
- **Canonicalization stays deliberately syntactic.** Front matter, line endings, per-line trailing
  whitespace, and boundary blank lines are normalized. Prose reflow and Markdown formatter syntax
  rewrites change the hash; the stdlib resolver does not embed a partial Markdown semantic parser.
- **Mechanical reconciliation is evidence, not judgment.** The packaged command composes the
  resolver with the existing lifecycle and landing planners and returns a read-only, content-free
  readiness report. The skill retains the semantic work: interpreting ADR meaning, classifying
  drift versus contradiction, judging scope and task completion, and ensuring the archive carries
  no unique durable knowledge. Keeping those seams separate makes the deterministic module deeper
  without pretending prose judgment is executable validation.
- The **product** positioning (tkcs vs OpenLore/OpenSpec/the RAG shortlist) is a separate decision,
  recorded in the consuming repo at `docs/adr/0011-positioning-vs-sdd-agent-memory-and-rag-landscape.md`.
