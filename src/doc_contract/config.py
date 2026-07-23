"""Explicit, stdlib-only configuration for the doc-contract engine."""

from __future__ import annotations

import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_NAME = ".doc-contract.toml"
SCHEMA_VERSION = 1
EDGE_FINGERPRINT_POLICIES = frozenset({"advisory", "required"})


class ConfigError(ValueError):
    """A value-free configuration or repository-boundary failure."""

    def __init__(self, code: str, path: Path, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.path = path
        self.detail = detail


@dataclass(frozen=True, slots=True)
class Settings:
    repo_root: Path
    repo_name: str
    root_nodes: dict[str, str]
    optional_root_ids: tuple[str, ...] = ()
    roadmap: str = "docs/roadmap.md"
    capability_mode: str = "skip"
    capability_command: tuple[str, ...] = ()
    additional_environment_names: tuple[str, ...] = ()
    edge_fingerprint_policy: str = "advisory"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.edge_fingerprint_policy, str)
            or self.edge_fingerprint_policy not in EDGE_FINGERPRINT_POLICIES
        ):
            raise ValueError("edge_fingerprint_policy must be 'advisory' or 'required'")

    @property
    def required_root_ids(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.root_nodes) - set(self.optional_root_ids)))


def _relative_path(value: object, *, key: str, config_path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError("config-invalid", config_path, f"{key} must be a non-empty path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ConfigError("config-invalid", config_path, f"{key} must stay inside repo root")
    return path.as_posix()


def _string_list(value: object, *, key: str, config_path: Path) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ConfigError("config-invalid", config_path, f"{key} must be an array of strings")
    return tuple(value)


def load_settings(repo_root: Path, config_path: Path | None = None) -> Settings:
    """Load settings without importing any code from the target repository."""
    root = repo_root.expanduser().resolve()
    path = config_path or root / CONFIG_NAME
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not path.is_file():
        raise ConfigError("repo-root-mismatch", path, f"missing {CONFIG_NAME}")
    try:
        raw: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError("config-invalid", path, type(exc).__name__) from None

    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ConfigError("config-invalid", path, "unsupported or missing schema_version")
    repo_name = raw.get("repo_name")
    if not isinstance(repo_name, str) or not repo_name.strip():
        raise ConfigError("config-invalid", path, "repo_name must be a non-empty string")
    roadmap = _relative_path(
        raw.get("roadmap", "docs/roadmap.md"), key="roadmap", config_path=path
    )
    edge_fingerprint_policy = raw.get("edge_fingerprints", "advisory")
    if (
        not isinstance(edge_fingerprint_policy, str)
        or edge_fingerprint_policy not in EDGE_FINGERPRINT_POLICIES
    ):
        raise ConfigError(
            "config-invalid", path, "edge_fingerprints must be 'advisory' or 'required'"
        )

    roots = raw.get("root_nodes")
    if not isinstance(roots, dict):
        raise ConfigError("config-invalid", path, "root_nodes must be a table")
    root_nodes: dict[str, str] = {}
    for node_id, relative in roots.items():
        if not isinstance(node_id, str) or not node_id.strip():
            raise ConfigError("config-invalid", path, "root_nodes keys must be non-empty")
        root_nodes[node_id] = _relative_path(
            relative, key=f"root_nodes.{node_id}", config_path=path
        )
    if "required_roots" in raw:
        raise ConfigError(
            "config-invalid",
            path,
            "required_roots is obsolete; roots are required by default, use optional_roots",
        )
    optional_root_ids = _string_list(
        raw.get("optional_roots"), key="optional_roots", config_path=path
    )
    unknown_optional = sorted(set(optional_root_ids) - set(root_nodes))
    if unknown_optional:
        raise ConfigError(
            "config-invalid", path, "optional_roots contains an unknown root node id"
        )
    if len(set(root_nodes.values())) != len(root_nodes):
        raise ConfigError(
            "config-invalid", path, "root_nodes must not assign one path to multiple ids"
        )
    if any(root_nodes[node_id] == roadmap for node_id in optional_root_ids):
        raise ConfigError("config-invalid", path, "the roadmap root cannot be optional")

    capability = raw.get("capability", {})
    if not isinstance(capability, dict):
        raise ConfigError("config-invalid", path, "capability must be a table")
    mode = capability.get("mode", "skip")
    if mode not in {"skip", "optional", "required"}:
        raise ConfigError("config-invalid", path, "capability.mode is invalid")
    command = _string_list(capability.get("command"), key="capability.command", config_path=path)
    if mode != "skip" and not command:
        raise ConfigError("config-invalid", path, "capability.command is required for this mode")

    environment_names = _string_list(
        raw.get("secret_env_names"), key="secret_env_names", config_path=path
    )
    return Settings(
        repo_root=root,
        repo_name=repo_name,
        root_nodes=root_nodes,
        optional_root_ids=optional_root_ids,
        roadmap=roadmap,
        edge_fingerprint_policy=edge_fingerprint_policy,
        capability_mode=mode,
        capability_command=command,
        additional_environment_names=environment_names,
    )


def resolve_repo_root(
    explicit_root: Path | None,
    explicit_config: Path | None,
    *,
    cwd: Path | None = None,
) -> Path:
    """Resolve the target boundary: root flag, then config location, then git root."""
    if explicit_root is not None:
        return explicit_root.expanduser().resolve()
    if explicit_config is not None:
        return explicit_config.expanduser().resolve().parent
    start = (cwd or Path.cwd()).resolve()
    try:
        result = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        raise ConfigError(
            "repo-root-mismatch", start, "no --repo-root, --config, or git root"
        ) from None
    root = Path(result.stdout.strip()).resolve()
    if not root.is_dir():
        raise ConfigError("repo-root-mismatch", root, "discovered git root is unavailable")
    return root
