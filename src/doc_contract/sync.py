"""Idempotent vendoring for air-gapped doc-contract installations."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from . import __version__

MANIFEST_NAME = ".doc-contract-manifest.json"
VENDOR_DIRECTORY = ".doc-contract/vendor/doc_contract"
LAUNCHER = ".doc-contract/doc_contract_cli.py"
PACKAGE_FILES = (
    "__init__.py",
    "cli.py",
    "config.py",
    "landing.py",
    "resolver.py",
    "secret_scan.py",
    "sync.py",
)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _replace_if_changed(path: Path, data: bytes) -> bool:
    if path.is_file() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(data)
    temporary.replace(path)
    return True


def sync_package(repo_root: Path) -> bool:
    """Vendor this exact package and write a deterministic version/pin manifest."""
    source = Path(__file__).resolve().parent
    destination = repo_root / VENDOR_DIRECTORY
    changed = False
    file_hashes: dict[str, str] = {}
    for name in PACKAGE_FILES:
        source_file = source / name
        relative = f"doc_contract/{name}"
        data = source_file.read_bytes()
        file_hashes[relative] = _digest(data)
        target = destination / name
        if not target.is_file() or _digest(target.read_bytes()) != file_hashes[relative]:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_file, target)
            changed = True

    launcher = (
        "from pathlib import Path\n"
        "import sys\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))\n"
        "from doc_contract.cli import main\n"
        "raise SystemExit(main())\n"
    ).encode("utf-8")
    changed = _replace_if_changed(repo_root / LAUNCHER, launcher) or changed
    file_hashes[LAUNCHER] = _digest(launcher)

    manifest = {
        "schema_version": 1,
        "package": "doc-contracts",
        "version": __version__,
        "files": dict(sorted(file_hashes.items())),
    }
    rendered = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    changed = _replace_if_changed(repo_root / MANIFEST_NAME, rendered) or changed
    return changed
