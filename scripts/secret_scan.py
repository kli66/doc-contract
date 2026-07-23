"""Compatibility adapter for the packaged value-free secret scanner."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (_REPO_ROOT / "src", _REPO_ROOT / ".doc-contract/vendor"):
    if _candidate.is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from doc_contract.secret_scan import *  # noqa: E402, F403 - intentional compatibility API
