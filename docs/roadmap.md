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
- `docs/changes/archive/2026-07-23-edge-fingerprint-policy/` (landed) — make dependency fingerprints advisory by
  default while retaining strict frozen-document `self_hash`; depends on the landed discovery and
  lifecycle hardening change
- `docs/changes/archive/2026-07-23-portable-install-contract-convergence/` — templates and install guidance now use
  `.doc-contract.toml` plus the packaged/vendored CLI, with sync-to-check proven in a clean
  temporary repository; depends on the landed edge-fingerprint policy

## Architecture

- `docs/changes/archive/2026-07-24-landed-graph-transition-ownership/` (landed) — move projected landed document
  state, topology, roadmap rendering, and validation behind one resolver-owned operation; depends on
  the landed edge-fingerprint policy
- `docs/changes/archive/2026-07-24-unified-offline-live-verification/` (landed) — consolidate check and landing
  capability policy, redacted execution, status/finding mapping, and warning composition behind one
  internal verification operation; depends on the landed edge-fingerprint policy
- `docs/changes/archive/2026-07-24-always-valid-repository-settings/` (landed) — make every direct or TOML-backed
  settings construction enforce the same immutable repository invariants; depends on the landed
  portable install contract convergence
- `docs/changes/archive/2026-07-24-vendored-runtime-closure/` (landed) — make sync materialize one deterministic,
  complete runtime image whose isolated launcher and manifest share the installed package identity;
  depends on the landed portable install contract convergence

<!-- BEGIN GENERATED DAG (regenerate: doc-contract update --repo-root .) -->
```mermaid
flowchart TD
    always_valid_repository_settings["always-valid-repository-settings (landed)"]
    discovery_lifecycle_hardening["discovery-lifecycle-hardening (landed)"]
    edge_fingerprint_policy["edge-fingerprint-policy (landed)"]
    global_cwd_independent_cli["global-cwd-independent-cli (landed)"]
    landed_graph_transition_ownership["landed-graph-transition-ownership (landed)"]
    portable_install_contract_convergence["portable-install-contract-convergence (landed)"]
    secret_handling_guardrails["secret-handling-guardrails (landed)"]
    transactional_land_command["transactional-land-command (landed)"]
    unified_offline_live_verification["unified-offline-live-verification (landed)"]
    vendored_runtime_closure["vendored-runtime-closure (landed)"]
    discovery_lifecycle_hardening --> edge_fingerprint_policy
    edge_fingerprint_policy --> landed_graph_transition_ownership
    edge_fingerprint_policy --> portable_install_contract_convergence
    edge_fingerprint_policy --> unified_offline_live_verification
    global_cwd_independent_cli --> transactional_land_command
    portable_install_contract_convergence --> always_valid_repository_settings
    portable_install_contract_convergence --> vendored_runtime_closure
    secret_handling_guardrails --> global_cwd_independent_cli
    transactional_land_command --> discovery_lifecycle_hardening
```
<!-- END GENERATED DAG -->
