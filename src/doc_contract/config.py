"""Explicit, stdlib-only configuration for the doc-contract engine."""

from __future__ import annotations

import subprocess
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
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


class SettingsError(ValueError):
    """A value-free failure to construct a valid settings value."""

    def __init__(self, detail: str, *, config_detail: str | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.config_detail = config_detail or detail


@dataclass(frozen=True, slots=True)
class Settings:
    repo_root: Path
    repo_name: str
    root_nodes: Mapping[str, str]
    optional_root_ids: tuple[str, ...] = ()
    roadmap: str = "docs/roadmap.md"
    capability_mode: str = "skip"
    capability_command: tuple[str, ...] = ()
    additional_environment_names: tuple[str, ...] = ()
    edge_fingerprint_policy: str = "advisory"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.repo_root, Path)
            or not self.repo_root.is_absolute()
            or ".." in self.repo_root.parts
        ):
            raise SettingsError("repo_root must be a resolved absolute path")
        if not isinstance(self.repo_name, str) or not self.repo_name.strip():
            raise SettingsError("repo_name must be a non-empty string")

        roadmap = _settings_relative_path(self.roadmap, key="roadmap")
        if not isinstance(self.root_nodes, Mapping):
            raise SettingsError(
                "root_nodes must be a mapping",
                config_detail="root_nodes must be a table",
            )
        root_nodes: dict[str, str] = {}
        for node_id, relative in self.root_nodes.items():
            if not isinstance(node_id, str) or not node_id.strip():
                raise SettingsError(
                    "root_nodes keys must be non-empty strings",
                    config_detail="root_nodes keys must be non-empty",
                )
            root_nodes[node_id] = _settings_relative_path(
                relative, key=f"root_nodes.{node_id}"
            )
        optional_root_ids = _settings_string_tuple(
            self.optional_root_ids,
            key="optional_root_ids",
            config_key="optional_roots",
        )
        unknown_optional = sorted(set(optional_root_ids) - set(root_nodes))
        if unknown_optional:
            raise SettingsError(
                "optional_root_ids contains an unknown root node id",
                config_detail="optional_roots contains an unknown root node id",
            )
        if len(set(root_nodes.values())) != len(root_nodes):
            raise SettingsError("root_nodes must not assign one path to multiple ids")
        if any(root_nodes[node_id] == roadmap for node_id in optional_root_ids):
            raise SettingsError("the roadmap root cannot be optional")

        if (
            not isinstance(self.capability_mode, str)
            or self.capability_mode not in {"skip", "optional", "required"}
        ):
            raise SettingsError(
                "capability_mode is invalid", config_detail="capability.mode is invalid"
            )
        capability_command = _settings_string_tuple(
            self.capability_command,
            key="capability_command",
            config_key="capability.command",
        )
        if self.capability_mode != "skip" and not capability_command:
            raise SettingsError(
                "capability_command is required for this mode",
                config_detail="capability.command is required for this mode",
            )
        environment_names = _settings_string_tuple(
            self.additional_environment_names,
            key="additional_environment_names",
            config_key="secret_env_names",
        )
        if (
            not isinstance(self.edge_fingerprint_policy, str)
            or self.edge_fingerprint_policy not in EDGE_FINGERPRINT_POLICIES
        ):
            raise SettingsError(
                "edge_fingerprint_policy must be 'advisory' or 'required'",
                config_detail="edge_fingerprints must be 'advisory' or 'required'",
            )

        object.__setattr__(self, "root_nodes", MappingProxyType(root_nodes))
        object.__setattr__(self, "optional_root_ids", optional_root_ids)
        object.__setattr__(self, "roadmap", roadmap)
        object.__setattr__(self, "capability_command", capability_command)
        object.__setattr__(self, "additional_environment_names", environment_names)

    @property
    def required_root_ids(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.root_nodes) - set(self.optional_root_ids)))


def _settings_relative_path(value: object, *, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SettingsError(f"{key} must be a non-empty path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise SettingsError(f"{key} must stay inside repo root")
    return path.as_posix()


def _settings_string_tuple(
    value: object, *, key: str, config_key: str
) -> tuple[str, ...]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise SettingsError(
            f"{key} must be a sequence of strings",
            config_detail=f"{config_key} must be an array of strings",
        )
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
    if "required_roots" in raw:
        raise ConfigError(
            "config-invalid",
            path,
            "required_roots is obsolete; roots are required by default, use optional_roots",
        )
    capability = raw.get("capability", {})
    if not isinstance(capability, dict):
        raise ConfigError("config-invalid", path, "capability must be a table")
    try:
        return Settings(
            repo_root=root,
            repo_name=raw.get("repo_name"),
            root_nodes=raw.get("root_nodes"),
            optional_root_ids=raw.get("optional_roots", ()),
            roadmap=raw.get("roadmap", "docs/roadmap.md"),
            edge_fingerprint_policy=raw.get("edge_fingerprints", "advisory"),
            capability_mode=capability.get("mode", "skip"),
            capability_command=capability.get("command", ()),
            additional_environment_names=raw.get("secret_env_names", ()),
        )
    except SettingsError as exc:
        raise ConfigError("config-invalid", path, exc.config_detail) from None


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
