"""Discovery, path-policy, hash-state, and warning-reporting regressions."""

from __future__ import annotations

import subprocess
from pathlib import Path

from doc_contract.config import Settings
from doc_contract.resolver import Finding, resolve, warning_delta


def _write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _settings(root: Path) -> Settings:
    return Settings(
        repo_root=root,
        repo_name="fixture",
        root_nodes={"roadmap": "docs/roadmap.md"},
    )


def _roadmap(*entries: str) -> str:
    body = "\n".join(f"- `docs/changes/{item}/` (proposed)" for item in entries)
    return f"---\npersistence: living\n---\n# Roadmap\n\n{body}\n"


def _change(node_id: str, *, fingerprint: str | None = None) -> str:
    edge = ""
    if fingerprint is not None:
        edge = (
            "depends_on:\n  - target\nfingerprints:\n"
            f"  target: {fingerprint}\n"
        )
    return (
        "---\n"
        f"id: {node_id}\n"
        "persistence: ephemeral\nstatus: proposed\ntrack: test\n"
        f"{edge}"
        "---\n# Change\n"
    )


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_discovery_defaults_to_tracked_and_declared_nodes(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root, "docs/roadmap.md", _roadmap("tracked"))
    _write(root, "docs/changes/tracked/change.md", _change("tracked"))
    _write(root, "docs/changes/provisional/change.md", _change("provisional"))
    _git(root, "init", "-q")
    _git(root, "add", "docs/roadmap.md", "docs/changes/tracked/change.md")

    default = resolve(root, _settings(root))
    assert set(default.nodes) == {"roadmap", "tracked"}
    assert [(item.node_id, item.included) for item in default.discovery] == [
        ("provisional", False)
    ]

    provisional = resolve(root, _settings(root), include_untracked=True)
    assert set(provisional.nodes) == {"provisional", "roadmap", "tracked"}
    assert [(item.node_id, item.included) for item in provisional.discovery] == [
        ("provisional", True)
    ]


def test_persistence_uses_repository_relative_paths(tmp_path: Path) -> None:
    root = tmp_path / "misleading-adr" / "archive" / "repo"
    _write(root, "docs/roadmap.md", _roadmap())
    _write(
        root,
        "docs/spec/reference.md",
        "---\npersistence: ephemeral\n---\n# Reference\n",
    )
    result = resolve(root, _settings(root))
    assert result.nodes["reference"].persistence == "ephemeral"
    assert not [finding for finding in result.findings if finding.code == "unstamped-frozen"]


def test_empty_and_pending_edge_hashes_are_actionable(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root, "docs/roadmap.md", _roadmap("source"))
    _write(
        root,
        "docs/changes/target/change.md",
        "---\nid: target\npersistence: ephemeral\nstatus: landed\ntrack: test\n---\n# Target\n",
    )
    source = _write(root, "docs/changes/source/change.md", _change("source", fingerprint=""))
    empty = resolve(root, _settings(root))
    assert "hash-empty" in {finding.code for finding in empty.errors}

    source.write_text(_change("source", fingerprint="PENDING"), encoding="utf-8")
    pending = resolve(root, _settings(root))
    assert "hash-pending" in {finding.code for finding in pending.errors}
    assert any("doc-contract stamp source" in finding.message for finding in pending.errors)


def test_pending_frozen_self_hash_is_error(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root, "docs/roadmap.md", _roadmap())
    _write(
        root,
        "docs/spec/reference.md",
        "---\npersistence: frozen\nself_hash: PENDING\n---\n# Ref\n",
    )
    result = resolve(root, _settings(root))
    assert "hash-pending" in {finding.code for finding in result.errors}


def test_warning_delta_tracks_same_untracked_node_across_archive_path() -> None:
    before = [
        Finding(
            "WARN",
            "untracked-node-included",
            "example (docs/changes/example/change.md) is included provisionally",
        )
    ]
    after = [
        Finding(
            "WARN",
            "untracked-node-included",
            "example (docs/changes/archive/2026-07-23-example/change.md) is included provisionally",
        )
    ]
    report = warning_delta(before, after)
    assert report.baseline == tuple(after)
    assert not report.introduced
    assert not report.resolved
