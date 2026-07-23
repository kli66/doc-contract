"""Compatibility settings for this checkout's flat resolver and pytest tripwires.

New repositories use ``.doc-contract.toml`` and the packaged or vendored CLI. This module exists
only so the legacy flat adapters under ``scripts/`` keep exercising this repository's surfaces.

Contract (read by the invariant core):
  * ``REPO_ROOT``            — the repo being enforced.
  * ``REPO_NAME``            — cosmetic; used in messages/ids.
  * ``ROOT_NODES``           — managed docs outside changes/adr/spec that must still self-classify.
  * ``EDGE_FINGERPRINT_POLICY`` — advisory by default; required only by repository opt-in.
  * ``FINGERPRINT_TARGETS``  — which node kinds are fingerprintable (v1: docs only; never `src/`).
  * ``CAPABILITY_DOC``       — the living doc whose headings must mirror a code surface.
  * ``CAPABILITY_ENUMERATORS`` — the per-surface coverage checks (``CapabilityCheck``).
"""

from __future__ import annotations

from pathlib import Path

from doc_tripwire import CapabilityCheck

# The compatibility modules live directly under this checkout's ``scripts/`` directory.
REPO_ROOT = Path(__file__).resolve().parents[1]

REPO_NAME = "doc-contracts"

# Managed docs outside changes/adr/spec used by the compatibility resolver.
ROOT_NODES: dict[str, str] = {
    "agents": "AGENTS.md",
    "capabilities": "docs/spec/capabilities.md",
    "roadmap": "docs/roadmap.md",
}

# This checkout intentionally omits these optional contract surfaces.
OPTIONAL_ROOTS: tuple[str, ...] = ("agents", "capabilities")

# Dependency topology is mandatory; dependency review fingerprints are advisory unless a repository
# explicitly opts into the strict green-bar policy.
EDGE_FINGERPRINT_POLICY = "advisory"

# v1 fingerprint targets are docs only. Canonicalization ignores front matter and whitespace noise,
# but prose reflow and Markdown syntax rewrites remain significant; a `src/` symbol is never a v1
# target. Kept as an explicit knob so a future code-aware version flips it per-repo.
FINGERPRINT_TARGETS: tuple[str, ...] = ("doc",)

# ---- capability coverage (the one doc whose headings are a function of code) ---------------------

CAPABILITY_DOC = "docs/spec/capabilities.md"

# The compatibility tripwire mirrors this package's public command set.
def _cli_commands() -> set[str]:
    from doc_contract.cli import COMMANDS

    return set(COMMANDS)


CAPABILITY_ENUMERATORS: tuple[CapabilityCheck, ...] = (
    CapabilityCheck(
        name="CLI commands",
        surface=_cli_commands,
        section="CLI commands",
        label="CLI command",
    ),
)
