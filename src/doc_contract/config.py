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

# Schema-1 default limits (REQ-055)
DEFAULT_SOURCE_TIMEOUT_SECONDS = 60
DEFAULT_ANALYZER_TIMEOUT_SECONDS = 180
DEFAULT_SOURCE_STDOUT_CAP = 1_048_576
DEFAULT_ANALYZER_STDOUT_CAP = 1_048_576
DEFAULT_MAX_RECORDS_PER_SOURCE = 500
DEFAULT_MAX_TOTAL_RECORDS = 2000
DEFAULT_SUMMARY_CAP_UTF8_BYTES = 2048
DEFAULT_MAX_FINDINGS = 200
DEFAULT_MAX_RECOMMENDATIONS = 100
DEFAULT_MAX_NOMINATIONS = 50
DEFAULT_MAX_CANDIDATE_REQUIREMENTS = 50
DEFAULT_MAX_CANDIDATE_TASKS = 50

TRUST_MODES = frozenset({"local", "external"})


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
class SourceAdapter:
    """A configured source adapter for evidence collection."""

    name: str
    argv: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise SettingsError(
                "source adapter name must be a non-empty string",
                config_detail="source name must be a non-empty string",
            )
        if (
            not isinstance(self.argv, Sequence)
            or isinstance(self.argv, (str, bytes))
            or not all(isinstance(item, str) and item for item in self.argv)
        ):
            raise SettingsError(
                f"source adapter {self.name} argv must be a sequence of non-empty strings",
                config_detail=f"source {self.name} argv must be an array of strings",
            )
        object.__setattr__(self, "argv", tuple(self.argv))


@dataclass(frozen=True, slots=True)
class Analyzer:
    """A configured analyzer for semantic synthesis."""

    argv: tuple[str, ...]
    trust: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.argv, Sequence)
            or isinstance(self.argv, (str, bytes))
            or not all(isinstance(item, str) and item for item in self.argv)
        ):
            raise SettingsError(
                "analyzer argv must be a sequence of non-empty strings",
                config_detail="analyzer argv must be an array of strings",
            )
        if self.trust not in TRUST_MODES:
            raise SettingsError(
                f"analyzer trust must be one of {sorted(TRUST_MODES)}",
                config_detail="analyzer trust must be 'local' or 'external'",
            )
        object.__setattr__(self, "argv", tuple(self.argv))


@dataclass(frozen=True, slots=True)
class ReflectionSettings:
    """Optional reflection configuration."""

    sources: tuple[SourceAdapter, ...]
    analyzer: Analyzer | None
    instruction_targets: tuple[str, ...]
    skill_targets: tuple[str, ...]
    spec_targets: tuple[str, ...]
    config_targets: tuple[str, ...]
    source_timeout_seconds: int
    analyzer_timeout_seconds: int
    source_stdout_cap: int
    analyzer_stdout_cap: int
    max_records_per_source: int
    max_total_records: int
    summary_cap: int
    max_findings: int
    max_recommendations: int
    max_nominations: int
    max_candidate_requirements: int
    max_candidate_tasks: int

    def __post_init__(self) -> None:
        if not isinstance(self.sources, Sequence):
            raise SettingsError(
                "reflection sources must be a sequence",
                config_detail="reflection.sources must be an array",
            )
        sources = tuple(self.sources)
        names = [s.name for s in sources]
        if len(names) != len(set(names)):
            raise SettingsError(
                "reflection source names must be unique",
                config_detail="reflection source names must be unique",
            )
        object.__setattr__(self, "sources", sources)

        for key, value in (
            ("instruction_targets", self.instruction_targets),
            ("skill_targets", self.skill_targets),
            ("spec_targets", self.spec_targets),
            ("config_targets", self.config_targets),
        ):
            if not isinstance(value, Sequence):
                raise SettingsError(
                    f"reflection {key} must be a sequence",
                    config_detail=f"reflection.{key} must be an array",
                )
            validated = tuple(
                _settings_relative_path(p, key=f"reflection.{key}")
                for p in value
                if isinstance(p, str)
            )
            object.__setattr__(self, key, validated)

        for key, value, minimum in (
            ("source_timeout_seconds", self.source_timeout_seconds, 1),
            ("analyzer_timeout_seconds", self.analyzer_timeout_seconds, 1),
            ("source_stdout_cap", self.source_stdout_cap, 1),
            ("analyzer_stdout_cap", self.analyzer_stdout_cap, 1),
            ("max_records_per_source", self.max_records_per_source, 1),
            ("max_total_records", self.max_total_records, 1),
            ("summary_cap", self.summary_cap, 1),
            ("max_findings", self.max_findings, 1),
            ("max_recommendations", self.max_recommendations, 1),
            ("max_nominations", self.max_nominations, 1),
            ("max_candidate_requirements", self.max_candidate_requirements, 1),
            ("max_candidate_tasks", self.max_candidate_tasks, 1),
        ):
            if not isinstance(value, int) or value < minimum:
                raise SettingsError(
                    f"reflection {key} must be a positive integer",
                    config_detail=f"reflection.{key} must be a positive integer",
                )


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
    reflection: ReflectionSettings | None = None

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


def _parse_reflection_settings(
    raw: dict[str, Any], path: Path
) -> ReflectionSettings | None:
    """Parse the optional [reflection] table from raw TOML data."""
    reflection = raw.get("reflection")
    if reflection is None:
        return None
    if not isinstance(reflection, dict):
        raise ConfigError("config-invalid", path, "reflection must be a table")

    # Parse sources
    raw_sources = reflection.get("sources", [])
    if not isinstance(raw_sources, Sequence) or isinstance(raw_sources, (str, bytes)):
        raise ConfigError("config-invalid", path, "reflection.sources must be an array")
    sources: list[SourceAdapter] = []
    for i, src in enumerate(raw_sources):
        if not isinstance(src, dict):
            raise ConfigError(
                "config-invalid", path, f"reflection.sources[{i}] must be a table"
            )
        name = src.get("name")
        argv = src.get("argv")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError(
                "config-invalid", path, f"reflection.sources[{i}].name must be a non-empty string"
            )
        if (
            not isinstance(argv, Sequence)
            or isinstance(argv, (str, bytes))
            or not all(isinstance(item, str) and item for item in argv)
        ):
            raise ConfigError(
                "config-invalid", path, f"reflection.sources[{i}].argv must be an array of strings"
            )
        try:
            sources.append(SourceAdapter(name=name, argv=tuple(argv)))
        except SettingsError as exc:
            raise ConfigError("config-invalid", path, exc.config_detail) from None

    # Parse analyzer
    raw_analyzer = reflection.get("analyzer")
    analyzer: Analyzer | None = None
    if raw_analyzer is not None:
        if not isinstance(raw_analyzer, dict):
            raise ConfigError("config-invalid", path, "reflection.analyzer must be a table")
        argv = raw_analyzer.get("argv")
        trust = raw_analyzer.get("trust", "local")
        if (
            not isinstance(argv, Sequence)
            or isinstance(argv, (str, bytes))
            or not all(isinstance(item, str) and item for item in argv)
        ):
            raise ConfigError("config-invalid", path, "reflection.analyzer.argv must be an array of strings")
        if not isinstance(trust, str) or trust not in TRUST_MODES:
            raise ConfigError("config-invalid", path, "reflection.analyzer.trust must be 'local' or 'external'")
        try:
            analyzer = Analyzer(argv=tuple(argv), trust=trust)
        except SettingsError as exc:
            raise ConfigError("config-invalid", path, exc.config_detail) from None

    # Parse target paths
    instruction_targets = tuple(reflection.get("instruction_targets", []))
    skill_targets = tuple(reflection.get("skill_targets", []))
    spec_targets = tuple(reflection.get("spec_targets", []))
    config_targets = tuple(reflection.get("config_targets", []))

    # Parse limits with defaults
    def _positive_int(value: Any, default: int, key: str) -> int:
        if value is None:
            return default
        if not isinstance(value, int) or value < 1:
            raise ConfigError(
                "config-invalid", path, f"reflection.{key} must be a positive integer"
            )
        return value

    try:
        return ReflectionSettings(
            sources=tuple(sources),
            analyzer=analyzer,
            instruction_targets=instruction_targets,
            skill_targets=skill_targets,
            spec_targets=spec_targets,
            config_targets=config_targets,
            source_timeout_seconds=_positive_int(
                reflection.get("source_timeout_seconds"), DEFAULT_SOURCE_TIMEOUT_SECONDS,
                "source_timeout_seconds"
            ),
            analyzer_timeout_seconds=_positive_int(
                reflection.get("analyzer_timeout_seconds"), DEFAULT_ANALYZER_TIMEOUT_SECONDS,
                "analyzer_timeout_seconds"
            ),
            source_stdout_cap=_positive_int(
                reflection.get("source_stdout_cap"), DEFAULT_SOURCE_STDOUT_CAP,
                "source_stdout_cap"
            ),
            analyzer_stdout_cap=_positive_int(
                reflection.get("analyzer_stdout_cap"), DEFAULT_ANALYZER_STDOUT_CAP,
                "analyzer_stdout_cap"
            ),
            max_records_per_source=_positive_int(
                reflection.get("max_records_per_source"), DEFAULT_MAX_RECORDS_PER_SOURCE,
                "max_records_per_source"
            ),
            max_total_records=_positive_int(
                reflection.get("max_total_records"), DEFAULT_MAX_TOTAL_RECORDS,
                "max_total_records"
            ),
            summary_cap=_positive_int(
                reflection.get("summary_cap"), DEFAULT_SUMMARY_CAP_UTF8_BYTES,
                "summary_cap"
            ),
            max_findings=_positive_int(
                reflection.get("max_findings"), DEFAULT_MAX_FINDINGS,
                "max_findings"
            ),
            max_recommendations=_positive_int(
                reflection.get("max_recommendations"), DEFAULT_MAX_RECOMMENDATIONS,
                "max_recommendations"
            ),
            max_nominations=_positive_int(
                reflection.get("max_nominations"), DEFAULT_MAX_NOMINATIONS,
                "max_nominations"
            ),
            max_candidate_requirements=_positive_int(
                reflection.get("max_candidate_requirements"), DEFAULT_MAX_CANDIDATE_REQUIREMENTS,
                "max_candidate_requirements"
            ),
            max_candidate_tasks=_positive_int(
                reflection.get("max_candidate_tasks"), DEFAULT_MAX_CANDIDATE_TASKS,
                "max_candidate_tasks"
            ),
        )
    except SettingsError as exc:
        raise ConfigError("config-invalid", path, exc.config_detail) from None


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
    reflection = _parse_reflection_settings(raw, path)
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
            reflection=reflection,
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
