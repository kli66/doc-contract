"""Small, deterministic secret-presence scanner used by the doc-contract resolver.

The scanner deliberately keeps only metadata: a finding never contains the matched value.  It is
intended to catch accidental assignments in source, docs, fixtures, and generated artifacts, not
to replace a provider-specific secret scanner.
"""

from __future__ import annotations

import re
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_SECRET_ENV_NAMES = frozenset(
    {
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AZURE_CLIENT_SECRET",
        "GITHUB_TOKEN",
        "GITLAB_TOKEN",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "HUGGINGFACE_TOKEN",
        "DATABASE_URL",
        "PRIVATE_KEY",
        "GEMINI_API_KEY",
        "COHERE_API_KEY",
        "NPM_TOKEN",
        "PYPI_TOKEN",
        "SLACK_BOT_TOKEN",
        "STRIPE_SECRET_KEY",
        "SENTRY_AUTH_TOKEN",
    }
)

EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
    }
)

_SENSITIVE_PARTS = frozenset(
    {
        "accesskey",
        "apikey",
        "authtoken",
        "clientsecret",
        "password",
        "passwd",
        "privatekey",
        "secret",
        "token",
    }
)
_NON_SECRET_SUFFIXES = frozenset(
    {
        "bucket", "count", "field", "length", "limit", "name", "path", "prefix", "suffix", "ttl"
    }
)
_ASSIGNMENT = re.compile(
    r"^\s*(?:export\s+)?[\{\[]?\s*[\"']?(?P<name>[A-Za-z_][A-Za-z0-9_-]*)"
    r"[\"']?\s*(?P<operator>=|:)\s*(?P<value>.*?)\s*[,}\]]?\s*$"
)
_ENV_NAME = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")
_DYNAMIC_VALUE = re.compile(
    r"^(?:None|null|nil|true|false|os\.|process\.|getenv\(|env\(|\$\{|\$\(|"
    r"frozenset\(|re\.compile\(|\{|\[|\()",
    re.IGNORECASE,
)
_BINARY_SUFFIXES = frozenset(
    {".7z", ".class", ".dll", ".eot", ".exe", ".gif", ".ico", ".jpg", ".npy", ".pdf",
     ".png", ".pyc", ".so", ".tar", ".ttf", ".wasm", ".webp", ".woff", ".woff2", ".zip"}
)


@dataclass(frozen=True, slots=True)
class SecretFinding:
    """A safe finding that contains no secret material."""

    path: str
    line: int
    variable: str
    kind: str
    present: bool
    length: int

    @property
    def value_length(self) -> int:
        return self.length

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _normalise_name(name: str) -> str:
    return name.replace("-", "_").upper()


def _sensitive_name(name: str, known_env_names: set[str]) -> bool:
    normalised = _normalise_name(name)
    if normalised in known_env_names:
        return True
    if normalised.replace("_", "").lower() in _SENSITIVE_PARTS:
        return True
    parts = re.split(r"[_-]+", normalised)
    if len(parts) > 1 and parts[-1].lower() in _NON_SECRET_SUFFIXES:
        return False
    return any(part.lower() in _SENSITIVE_PARTS for part in parts)


def _display_path(path: Path, root: Path | None) -> str:
    if root is not None:
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            pass
    return path.as_posix()


def _value_metadata(raw_value: str) -> tuple[bool, int]:
    value = raw_value.strip().rstrip(",")
    if value[:1] in {'"', "'"}:
        quote = value[0]
        closing = value.find(quote, 1)
        value = value[1:closing] if closing > 0 else value[1:]
    else:
        value = re.split(r"[,}\]]", value, maxsplit=1)[0].strip()
    if not value or _DYNAMIC_VALUE.match(value):
        return False, 0
    return True, len(value)


def _is_env_file(path: Path) -> bool:
    return path.name == ".env" or path.name.startswith(".env.")


def _is_binary(data: bytes) -> bool:
    if b"\x00" in data:
        return True
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def scan_file(
    path: Path,
    *,
    root: Path | None = None,
    secret_env_names: Iterable[str] = (),
) -> list[SecretFinding]:
    """Scan one UTF-8 text file, returning sorted, value-free findings."""
    if path.suffix.lower() in _BINARY_SUFFIXES:
        return []
    try:
        data = path.read_bytes()
    except (OSError, PermissionError):
        return []
    if _is_binary(data):
        return []
    text = data.decode("utf-8")
    known = {_normalise_name(name) for name in DEFAULT_SECRET_ENV_NAMES}
    known.update(_normalise_name(name) for name in secret_env_names)
    findings: list[SecretFinding] = []
    seen: set[tuple[int, str]] = set()
    env_file = _is_env_file(path)
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith(("#", ";")):
            continue
        match = _ASSIGNMENT.match(line)
        if match is not None:
            name = match.group("name")
            if match.group("operator") == ":":
                # YAML/TOML-style mapping keys are metadata, not credential assignments. Only
                # quoted JSON/Python-like keys use colon assignment syntax in the supported scan.
                stripped = line.lstrip()
                if line[:1].isspace() and stripped[:1] not in {'"', "'", "{"}:
                    continue
                if "=" in match.group("value"):
                    continue
            normalised_name = _normalise_name(name)
            if env_file or _sensitive_name(name, known):
                present, length = _value_metadata(match.group("value"))
                if not present and not env_file and normalised_name not in known:
                    continue
                finding = SecretFinding(
                    _display_path(path, root), line_number, normalised_name,
                    "assignment", present, length,
                )
                findings.append(finding)
                seen.add((line_number, finding.variable))

        # Report references to known environment names only when the line actually interacts with
        # the environment; a list of supported names in this module or in documentation is not a
        # credential finding.
        environment_context = re.search(
            r"getenv\s*\(|(?:os\.)?environ(?:\[|\.)|process\.env|\$[A-Z_]",
            line,
            re.I,
        )
        if environment_context is not None:
            for name in sorted(set(_ENV_NAME.findall(line)) & known):
                if (line_number, name) in seen:
                    continue
                findings.append(
                    SecretFinding(_display_path(path, root), line_number, name,
                                  "environment-reference", False, 0)
                )
                seen.add((line_number, name))
    return sorted(findings, key=lambda item: (item.path, item.line, item.variable, item.kind))


def _iter_files(root: Path) -> Iterable[Path]:
    for directory, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        directories[:] = sorted(
            name for name in directories if name.lower() not in EXCLUDED_DIRS
        )
        for name in sorted(filenames):
            path = Path(directory) / name
            if not path.is_symlink():
                yield path


def scan_tree(
    root: Path,
    *,
    secret_env_names: Iterable[str] = (),
) -> list[SecretFinding]:
    """Scan package and generated files below *root* with deterministic output."""
    findings: list[SecretFinding] = []
    for path in _iter_files(root):
        findings.extend(scan_file(path, root=root, secret_env_names=secret_env_names))
    return sorted(findings, key=lambda item: (item.path, item.line, item.variable, item.kind))


def scan(paths: Iterable[Path], *, root: Path | None = None,
         secret_env_names: Iterable[str] = ()) -> list[SecretFinding]:
    """Scan explicit files or directories; useful for callers with a package allow-list."""
    findings: list[SecretFinding] = []
    for path in sorted({Path(path) for path in paths}, key=lambda item: item.as_posix()):
        if path.is_dir():
            findings.extend(scan_tree(path, secret_env_names=secret_env_names))
        elif path.is_file():
            findings.extend(scan_file(path, root=root, secret_env_names=secret_env_names))
    return sorted(findings, key=lambda item: (item.path, item.line, item.variable, item.kind))


def format_finding(finding: SecretFinding) -> str:
    presence = "present" if finding.present else "absent"
    return (
        f"{finding.path}:{finding.line}: {finding.variable} "
        f"{presence} (length={finding.length}, kind={finding.kind})"
    )


def format_findings(findings: Iterable[SecretFinding]) -> str:
    return "\n".join(format_finding(finding) for finding in findings)
