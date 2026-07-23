"""Per-project parameter seam for the doc-contract resolver + tripwires.

This is the **only** file a second repo edits. `dag.py` and `doc_tripwire.py` are the invariant,
zero-dep (stdlib-only) core — copied verbatim; everything project-specific (where the repo root is,
which managed docs are nodes, and what code surface the capability doc must mirror) is declared here.
The doc-tree layout (``docs/adr``, ``docs/spec``, etc.) is fixed by the scheme — ``docs/`` at the
project root is a hard requirement. See `../SKILL.md` for the install procedure.

This copy is the **generic template**. Out of the box it resolves as a no-op capability tripwire
(``CAPABILITY_ENUMERATORS = ()``) and a minimal ``ROOT_NODES`` (agents + roadmap) — enough to run
``python -m dag`` green in a fresh repo. Fill in the ``EDIT`` points below for the target repo; the
tkcs original is preserved verbatim in the commented block at the end as a worked example.

Contract (read by the invariant core):
  * ``REPO_ROOT``            — the repo being enforced.
  * ``REPO_NAME``            — cosmetic; used in messages/ids.
  * ``ROOT_NODES``           — managed docs outside changes/adr/spec that must still self-classify.
  * ``FINGERPRINT_TARGETS``  — which node kinds are fingerprintable (v1: docs only; never `src/`).
  * ``CAPABILITY_DOC``       — the living doc whose headings must mirror a code surface.
  * ``CAPABILITY_ENUMERATORS`` — the per-surface coverage checks (``CapabilityCheck``).
"""

from __future__ import annotations

from pathlib import Path

from doc_tripwire import CapabilityCheck

# This checkout keeps the skill's scripts at <repo>/scripts, so the repository root is two
# parents up. Repoint this seam if the skill is installed under `.claude/skills/...` elsewhere.
REPO_ROOT = Path(__file__).resolve().parents[1]

# EDIT: cosmetic label for this repo, surfaced in resolver messages/ids.
REPO_NAME = "doc-contracts"

# EDIT: managed docs outside changes/adr/spec that must still self-classify — promoted to first-class
# nodes so `missing-persistence` covers them and no managed doc sits loose. Persistence is read from
# each file's own header (single source of truth), never hard-coded. id -> path (repo-relative).
# A minimal repo starts with just agents + roadmap and grows this set as docs are added.
ROOT_NODES: dict[str, str] = {
    "agents": "AGENTS.md",
    "capabilities": "docs/spec/capabilities.md",
    "roadmap": "docs/roadmap.md",
}

# Root nodes are required by default. List intentionally absent installation-specific roots here.
OPTIONAL_ROOTS: tuple[str, ...] = ("agents", "capabilities")

# v1 fingerprint targets are docs only: a code formatter is language-specific and prose is not
# reflowed, so doc fingerprints are stable day-to-day; a `src/` symbol is never a v1 target. Kept as
# an explicit knob so a future code-aware version flips it per-repo.
FINGERPRINT_TARGETS: tuple[str, ...] = ("doc",)

# ---- capability coverage (the one doc whose headings are a function of code) ---------------------

CAPABILITY_DOC = "docs/spec/capabilities.md"

# EDIT: the per-surface coverage checks. Each enumerator introspects *this repo's* code (its CLI
# parser, its tool registry, ...) and returns the live name set the capability doc must mirror.
# Leave empty () and the coverage tripwire is a no-op until the repo has such a surface. See the
# commented tkcs example at the end of this file for the shape of a real enumerator.
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


# ------------------------------------------------------------------------------------------------
# WORKED EXAMPLE (tkcs) — delete or adapt. Two enumerators: the MCP serving-tool registry and the
# CLI command grammar introspected from argparse. Uncomment, repoint the imports to this repo's
# modules, and add the entries to CAPABILITY_ENUMERATORS above.
# ------------------------------------------------------------------------------------------------
#
# import argparse
# from typing import cast
#
# def _mcp_tools() -> set[str]:
#     """The live MCP serving-tool names."""
#     from tkcs.mcp_server import MCP_TOOLS
#
#     return set(MCP_TOOLS)
#
#
# def _cli_commands() -> set[str]:
#     """The live `tkcs` command grammar, introspected from argparse — every leaf ``group cmd``
#     (e.g. ``curate set-access``). The real surface, not a transcription."""
#     from tkcs.cli import build_parser
#
#     found: set[str] = set()
#
#     def walk(parser: argparse.ArgumentParser, prefix: str) -> None:
#         # argparse offers no public API for walking subparsers, so we read its documented-but-
#         # underscore-prefixed internals deliberately; the cast restores concrete types and the
#         # ignores scope the private access to just the lines naming `_SubParsersAction`.
#         for action in parser._actions:
#             if isinstance(action, argparse._SubParsersAction):  # pyright: ignore[reportPrivateUsage]
#                 choices = cast("dict[str, argparse.ArgumentParser]", action.choices)
#                 for name, sub in choices.items():
#                     full = f"{prefix} {name}".strip()
#                     if any(
#                         isinstance(a, argparse._SubParsersAction)  # pyright: ignore[reportPrivateUsage]
#                         for a in sub._actions
#                     ):
#                         walk(sub, full)
#                     else:
#                         found.add(full)
#
#     walk(build_parser(), "")
#     return found
#
#
# CAPABILITY_ENUMERATORS = (
#     CapabilityCheck(name="MCP tools", surface=_mcp_tools, section="MCP tools", label="MCP tool"),
#     CapabilityCheck(
#         name="CLI commands", surface=_cli_commands, section="CLI commands", label="CLI command"
#     ),
# )
