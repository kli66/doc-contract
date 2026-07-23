"""Compatibility adapter for legacy ``PYTHONPATH=scripts python -m dag`` users."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (_REPO_ROOT / "src", _REPO_ROOT / ".doc-contract/vendor"):
    if _candidate.is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import config as _legacy_config  # noqa: E402
from doc_contract.config import Settings  # noqa: E402
from doc_contract.resolver import *  # noqa: E402, F403 - intentional compatibility API
from doc_contract.resolver import resolve as _resolve  # noqa: E402
from doc_contract.resolver import update_roadmap as _update_roadmap  # noqa: E402

REPO_ROOT = _legacy_config.REPO_ROOT
ROOT_NODES = _legacy_config.ROOT_NODES
_SETTINGS = Settings(
    repo_root=REPO_ROOT,
    repo_name=_legacy_config.REPO_NAME,
    root_nodes=dict(ROOT_NODES),
)


def _settings(root: Path) -> Settings:
    return replace(_SETTINGS, repo_root=root.resolve())


def resolve(root: Path = REPO_ROOT):  # noqa: ANN201 - compatibility surface
    return _resolve(root, _settings(root))


def update_roadmap(root: Path = REPO_ROOT) -> bool:
    return _update_roadmap(root, _settings(root))


def _main(argv: list[str]) -> int:
    if "--update" in argv:
        changed = update_roadmap()
        print("roadmap.md updated" if changed else "roadmap.md already current")
        return 0
    result = resolve()
    for finding in result.findings:
        print(f"{finding.level}: [{finding.code}] {finding.message}")
    print(
        f"\n{len(result.errors)} error(s), {len(result.warnings)} warning(s); "
        f"{len(result.nodes)} nodes"
    )
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
