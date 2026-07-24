"""Repository settings construction and adapter-parity regressions."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from doc_contract.config import ConfigError, Settings, load_settings


def _settings(root: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "repo_root": root,
        "repo_name": "fixture",
        "root_nodes": {"roadmap": "docs/roadmap.md"},
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def _toml(
    *,
    repo_name: str = '"fixture"',
    roadmap: str = '"docs/roadmap.md"',
    optional_roots: str = "[]",
    roots: str | None = 'roadmap = "docs/roadmap.md"',
    edge_fingerprints: str | None = None,
    capability_mode: str = '"skip"',
    capability_command: str | None = None,
    secret_env_names: str | None = None,
) -> str:
    lines = [
        "schema_version = 1",
        f"repo_name = {repo_name}",
        f"roadmap = {roadmap}",
        f"optional_roots = {optional_roots}",
    ]
    if edge_fingerprints is not None:
        lines.append(f"edge_fingerprints = {edge_fingerprints}")
    if secret_env_names is not None:
        lines.append(f"secret_env_names = {secret_env_names}")
    if roots is None:
        lines.append("root_nodes = []")
    else:
        lines.extend(["", "[root_nodes]", roots])
    lines.extend(["", "[capability]", f"mode = {capability_mode}"])
    if capability_command is not None:
        lines.append(f"command = {capability_command}")
    return "\n".join(lines) + "\n"


def test_direct_construction_normalizes_and_detaches_collections(tmp_path: Path) -> None:
    roots = {
        "roadmap": "docs//roadmap.md",
        "contract": "docs/./contract.md",
    }
    optional_roots = ["contract"]
    command = ["python", "-m", "fixture"]
    environment_names = ["INTERNAL_CREDENTIAL"]

    settings = _settings(
        tmp_path,
        root_nodes=roots,
        optional_root_ids=optional_roots,
        capability_mode="optional",
        capability_command=command,
        additional_environment_names=environment_names,
    )

    roots["roadmap"] = "elsewhere.md"
    optional_roots.append("roadmap")
    command.append("changed")
    environment_names.append("CHANGED")

    assert dict(settings.root_nodes) == {
        "roadmap": "docs/roadmap.md",
        "contract": "docs/contract.md",
    }
    assert settings.optional_root_ids == ("contract",)
    assert settings.capability_command == ("python", "-m", "fixture")
    assert settings.additional_environment_names == ("INTERNAL_CREDENTIAL",)
    assert settings.required_root_ids == ("roadmap",)
    with pytest.raises(TypeError):
        settings.root_nodes["other"] = "docs/other.md"  # type: ignore[index]


def test_toml_construction_produces_the_same_normalized_value(tmp_path: Path) -> None:
    config = tmp_path / ".doc-contract.toml"
    config.write_text(
        _toml(
            roots='roadmap = "docs//roadmap.md"\ncontract = "docs/./contract.md"',
            optional_roots='["contract"]',
            capability_mode='"optional"',
            capability_command='["python", "-m", "fixture"]',
            secret_env_names='["INTERNAL_CREDENTIAL"]',
        ),
        encoding="utf-8",
    )

    loaded = load_settings(tmp_path)
    direct = _settings(
        tmp_path,
        root_nodes={
            "roadmap": "docs/roadmap.md",
            "contract": "docs/contract.md",
        },
        optional_root_ids=("contract",),
        capability_mode="optional",
        capability_command=("python", "-m", "fixture"),
        additional_environment_names=("INTERNAL_CREDENTIAL",),
    )

    assert loaded == direct


@pytest.mark.parametrize(
    ("overrides", "config"),
    [
        ({"repo_name": ""}, _toml(repo_name='""')),
        ({"roadmap": ""}, _toml(roadmap='""')),
        ({"roadmap": "../roadmap.md"}, _toml(roadmap='"../roadmap.md"')),
        (
            {"root_nodes": []},
            _toml(roots=None),
        ),
        (
            {"root_nodes": {"": "docs/roadmap.md"}},
            _toml(roots='"" = "docs/roadmap.md"'),
        ),
        (
            {"root_nodes": {"roadmap": "/docs/roadmap.md"}},
            _toml(roots='roadmap = "/docs/roadmap.md"'),
        ),
        (
            {"root_nodes": {"roadmap": "../roadmap.md"}},
            _toml(roots='roadmap = "../roadmap.md"'),
        ),
        (
            {
                "root_nodes": {
                    "roadmap": "docs/roadmap.md",
                    "other": "docs/roadmap.md",
                }
            },
            _toml(
                roots='roadmap = "docs/roadmap.md"\nother = "docs/roadmap.md"'
            ),
        ),
        (
            {"optional_root_ids": "roadmap"},
            _toml(optional_roots='"roadmap"'),
        ),
        (
            {"optional_root_ids": ("unknown",)},
            _toml(optional_roots='["unknown"]'),
        ),
        (
            {"optional_root_ids": ("roadmap",)},
            _toml(optional_roots='["roadmap"]'),
        ),
        (
            {"capability_mode": "live"},
            _toml(capability_mode='"live"'),
        ),
        (
            {"capability_mode": []},
            _toml(capability_mode="[]"),
        ),
        (
            {"capability_mode": "optional"},
            _toml(capability_mode='"optional"'),
        ),
        (
            {"capability_command": "private-command-argument"},
            _toml(capability_command='"private-command-argument"'),
        ),
        (
            {"capability_command": ("private-command-argument", "")},
            _toml(capability_command='["private-command-argument", ""]'),
        ),
        (
            {"additional_environment_names": "PRIVATE_ENV"},
            _toml(secret_env_names='"PRIVATE_ENV"'),
        ),
        (
            {"additional_environment_names": ("PRIVATE_ENV", "")},
            _toml(secret_env_names='["PRIVATE_ENV", ""]'),
        ),
        (
            {"edge_fingerprint_policy": "strict"},
            _toml(edge_fingerprints='"strict"'),
        ),
        (
            {"edge_fingerprint_policy": []},
            _toml(edge_fingerprints="[]"),
        ),
    ],
    ids=[
        "empty-repo-name",
        "empty-roadmap",
        "escaping-roadmap",
        "non-mapping-roots",
        "empty-root-id",
        "absolute-root-path",
        "escaping-root-path",
        "duplicate-root-path",
        "non-sequence-optional-roots",
        "unknown-optional-root",
        "optional-roadmap",
        "unknown-capability-mode",
        "non-string-capability-mode",
        "missing-capability-command",
        "non-sequence-capability-command",
        "empty-capability-command-part",
        "non-sequence-environment-names",
        "empty-environment-name",
        "unknown-edge-policy",
        "non-string-edge-policy",
    ],
)
def test_direct_and_toml_construction_reject_equivalent_invalid_states(
    overrides: dict[str, object], config: str, tmp_path: Path
) -> None:
    with pytest.raises(ValueError):
        _settings(tmp_path, **overrides)

    config_path = tmp_path / ".doc-contract.toml"
    config_path.write_text(config, encoding="utf-8")
    with pytest.raises(ConfigError) as caught:
        load_settings(tmp_path)
    assert caught.value.code == "config-invalid"
    assert caught.value.path == config_path
    assert "private-command-argument" not in caught.value.detail


@pytest.mark.parametrize("repo_root", [Path("relative"), Path("/tmp/../outside")])
def test_direct_construction_requires_a_resolved_absolute_root(repo_root: Path) -> None:
    with pytest.raises(ValueError, match="repo_root"):
        _settings(repo_root)


def test_dataclasses_replace_revalidates_and_redetaches(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    replacement_roots = {
        "roadmap": "docs/roadmap.md",
        "contract": "docs/contract.md",
    }

    replaced = replace(settings, root_nodes=replacement_roots)
    replacement_roots["contract"] = "changed.md"

    assert replaced.root_nodes["contract"] == "docs/contract.md"
    with pytest.raises(ValueError, match="optional_root_ids"):
        replace(settings, optional_root_ids=("unknown",))
    with pytest.raises(ValueError, match="edge_fingerprint_policy"):
        replace(settings, edge_fingerprint_policy="strict")
