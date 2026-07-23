---
persistence: living
---

# Roadmap

## Remediation

- `docs/changes/archive/2026-07-23-secret-handling-guardrails/` (landed) — scanner and redacted
  diagnostics
- `docs/changes/archive/2026-07-23-global-cwd-independent-cli/` (landed) — packaged resolver with an
  explicit, fail-closed CLI; depends on the landed secret-handling guardrails
- `docs/changes/archive/2026-07-23-transactional-land-command/` (landed) — one resumable dry-runnable operation for
  preflight, archive, stamping, roadmap regeneration, and validation; depends on the packaged CLI
- `docs/changes/archive/2026-07-23-discovery-lifecycle-hardening/` (landed) — tracked/declared discovery, explicit
  untracked opt-in, root-node policy, repository-relative classification, actionable hash states,
  and baseline-vs-new warning reporting; depends on the landed transactional land command
- `docs/changes/edge-fingerprint-policy/` (proposed) — make dependency fingerprints advisory by
  default while retaining strict frozen-document `self_hash`; depends on the landed discovery and
  lifecycle hardening change

<!-- BEGIN GENERATED DAG (regenerate: doc-contract update --repo-root .) -->
```mermaid
flowchart TD
    discovery_lifecycle_hardening["discovery-lifecycle-hardening (landed)"]
    edge_fingerprint_policy["edge-fingerprint-policy (proposed)"]
    global_cwd_independent_cli["global-cwd-independent-cli (landed)"]
    secret_handling_guardrails["secret-handling-guardrails (landed)"]
    transactional_land_command["transactional-land-command (landed)"]
    discovery_lifecycle_hardening --> edge_fingerprint_policy
    global_cwd_independent_cli --> transactional_land_command
    secret_handling_guardrails --> global_cwd_independent_cli
    transactional_land_command --> discovery_lifecycle_hardening
```
<!-- END GENERATED DAG -->
