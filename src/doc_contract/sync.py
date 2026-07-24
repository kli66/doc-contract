"""Idempotent vendoring for air-gapped doc-contract installations."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import __version__

MANIFEST_NAME = ".doc-contract-manifest.json"
VENDOR_DIRECTORY = ".doc-contract/vendor/doc_contract"
LAUNCHER = ".doc-contract/doc_contract_cli.py"

_REQUIRED_ENTRY_MODULES = ("__init__.py", "cli.py")
_VERSION_MODULE = "_version.py"
_LAUNCHER_BYTES = (
    "from pathlib import Path\n"
    "import sys\n"
    "sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))\n"
    "from doc_contract.cli import main\n"
    "raise SystemExit(main())\n"
).encode("utf-8")


@dataclass(frozen=True, slots=True)
class _RuntimeFile:
    destination: Path
    manifest_path: str
    data: bytes
    digest: str


@dataclass(frozen=True, slots=True)
class _RuntimeImage:
    version: str
    package_files: tuple[_RuntimeFile, ...]
    launcher: _RuntimeFile
    manifest: bytes


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _runtime_file(destination: Path, manifest_path: str, data: bytes) -> _RuntimeFile:
    return _RuntimeFile(
        destination=destination,
        manifest_path=manifest_path,
        data=data,
        digest=_digest(data),
    )


def _package_source() -> Path:
    return Path(__file__).resolve().parent


def _generated_version() -> bytes:
    return f'"""Generated vendored package version."""\n\n__version__ = {__version__!r}\n'.encode(
        "utf-8"
    )


def _build_runtime_image(package_source: Path | None = None) -> _RuntimeImage:
    source = package_source if package_source is not None else _package_source()
    for name in _REQUIRED_ENTRY_MODULES:
        if not (source / name).is_file():
            raise RuntimeError(f"runtime image missing required entry module: {name}")

    discovered = {
        path.relative_to(source): path.read_bytes()
        for path in source.rglob("*.py")
        if path.is_file() and path.relative_to(source).as_posix() != _VERSION_MODULE
    }
    discovered[Path(_VERSION_MODULE)] = _generated_version()

    package_files = tuple(
        _runtime_file(
            Path(VENDOR_DIRECTORY) / relative,
            f"doc_contract/{relative.as_posix()}",
            data,
        )
        for relative, data in sorted(discovered.items(), key=lambda item: item[0].as_posix())
    )
    launcher = _runtime_file(Path(LAUNCHER), LAUNCHER, _LAUNCHER_BYTES)
    file_hashes = {
        runtime_file.manifest_path: runtime_file.digest
        for runtime_file in (*package_files, launcher)
    }
    manifest = {
        "schema_version": 1,
        "package": "doc-contracts",
        "version": __version__,
        "files": dict(sorted(file_hashes.items())),
    }
    rendered = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return _RuntimeImage(
        version=__version__,
        package_files=package_files,
        launcher=launcher,
        manifest=rendered,
    )


def _ensure_directory(root: Path, directory: Path) -> None:
    relative = directory.relative_to(root)
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise RuntimeError("vendored runtime directory contains a symbolic link")
        if current.exists() and not current.is_dir():
            raise RuntimeError("vendored runtime directory path is not a directory")
        current.mkdir(exist_ok=True)


def _replace_if_changed(path: Path, data: bytes) -> bool:
    if path.is_file() and not path.is_symlink() and path.read_bytes() == data:
        return False
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as stream:
            stream.write(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def _raise_walk_error(error: OSError) -> None:
    raise error


def _prune_stale_package_files(destination: Path, expected: frozenset[Path]) -> bool:
    changed = False
    expected_directories = {
        parent
        for path in expected
        for parent in path.parents
        if parent != Path(".")
    }
    for current, directories, filenames in os.walk(
        destination,
        topdown=False,
        onerror=_raise_walk_error,
        followlinks=False,
    ):
        current_path = Path(current)
        for name in filenames:
            candidate = current_path / name
            if candidate.relative_to(destination) not in expected:
                candidate.unlink()
                changed = True
        for name in directories:
            candidate = current_path / name
            relative = candidate.relative_to(destination)
            if candidate.is_symlink():
                candidate.unlink()
                changed = True
            elif relative not in expected_directories:
                candidate.rmdir()
                changed = True
    return changed


def sync_package(repo_root: Path) -> bool:
    """Vendor this exact package and write a deterministic version/pin manifest."""
    image = _build_runtime_image()
    destination = repo_root / VENDOR_DIRECTORY
    changed = False

    for runtime_file in (*image.package_files, image.launcher):
        target = repo_root / runtime_file.destination
        _ensure_directory(repo_root, target.parent)
        changed = _replace_if_changed(target, runtime_file.data) or changed

    expected = frozenset(
        runtime_file.destination.relative_to(Path(VENDOR_DIRECTORY))
        for runtime_file in image.package_files
    )
    changed = _prune_stale_package_files(destination, expected) or changed
    changed = _replace_if_changed(repo_root / MANIFEST_NAME, image.manifest) or changed
    return changed
