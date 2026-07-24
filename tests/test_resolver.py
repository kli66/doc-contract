"""Discovery, path-policy, hash-state, and warning-reporting regressions."""

from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError
import subprocess
from pathlib import Path

import pytest

from doc_contract.config import Settings
from doc_contract.resolver import (
    Edge,
    Finding,
    Node,
    Resolution,
    fingerprint,
    project_landing,
    render_block,
    resolve,
    warning_delta,
)


def _write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _settings(
    root: Path,
    *,
    edge_fingerprints: str = "advisory",
    root_nodes: dict[str, str] | None = None,
) -> Settings:
    return Settings(
        repo_root=root,
        repo_name="fixture",
        root_nodes=(
            root_nodes if root_nodes is not None else {"roadmap": "docs/roadmap.md"}
        ),
        edge_fingerprint_policy=edge_fingerprints,
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


def test_resolver_fixture_cannot_construct_duplicate_root_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="one path to multiple ids"):
        _settings(
            tmp_path,
            root_nodes={
                "roadmap": "docs/roadmap.md",
                "duplicate": "docs/roadmap.md",
            },
        )


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


@pytest.mark.parametrize(
    ("value", "code"),
    [("", "edge-hash-empty"), ("PENDING", "edge-hash-pending"), ("bad", "edge-hash-invalid")],
)
def test_invalid_edge_hashes_warn_in_advisory_and_fail_when_required(
    value: str, code: str, tmp_path: Path
) -> None:
    root = tmp_path / "repo"
    _write(root, "docs/roadmap.md", _roadmap("source"))
    _write(
        root,
        "docs/changes/target/change.md",
        "---\nid: target\npersistence: ephemeral\nstatus: landed\ntrack: test\n---\n# Target\n",
    )
    _write(root, "docs/changes/source/change.md", _change("source", fingerprint=value))

    advisory = resolve(root, _settings(root))
    assert code in {finding.code for finding in advisory.warnings}
    assert code not in {finding.code for finding in advisory.errors}
    assert any("doc-contract stamp source" in finding.message for finding in advisory.warnings)
    assert code in {finding.code for finding in warning_delta([], advisory.warnings).introduced}

    required = resolve(root, _settings(root, edge_fingerprints="required"))
    assert code in {finding.code for finding in required.errors}


def test_missing_edge_hash_is_optional_in_advisory_and_required_on_opt_in(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    _write(root, "docs/roadmap.md", _roadmap("source"))
    _write(
        root,
        "docs/changes/target/change.md",
        "---\nid: target\npersistence: ephemeral\nstatus: landed\ntrack: test\n---\n# Target\n",
    )
    _write(
        root,
        "docs/changes/source/change.md",
        "---\nid: source\npersistence: ephemeral\nstatus: proposed\ntrack: test\n"
        "depends_on:\n  - target\n---\n# Source\n",
    )

    advisory = resolve(root, _settings(root))
    assert "missing-fingerprint" not in {finding.code for finding in advisory.findings}

    required = resolve(root, _settings(root, edge_fingerprints="required"))
    assert "missing-fingerprint" in {finding.code for finding in required.errors}


def test_stale_edge_hash_warns_under_both_policies(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root, "docs/roadmap.md", _roadmap("source"))
    _write(
        root,
        "docs/changes/target/change.md",
        "---\nid: target\npersistence: ephemeral\nstatus: landed\ntrack: test\n---\n# Target\n",
    )
    _write(root, "docs/changes/source/change.md", _change("source", fingerprint="0" * 16))

    for policy in ("advisory", "required"):
        result = resolve(root, _settings(root, edge_fingerprints=policy))
        assert "suspect-link" in {finding.code for finding in result.warnings}
        assert "suspect-link" not in {finding.code for finding in result.errors}


def test_fingerprint_canonicalization_boundary() -> None:
    normalized = "---\nid: first\n---\n\n# Heading\n\nBody\n"
    formatting_noise = (
        "---\r\nid: second\r\nextra: value\r\n---\r\n\r\n\r\n"
        "# Heading  \r\n\r\nBody\t\r\n\r\n"
    )
    assert fingerprint(normalized) == fingerprint(formatting_noise)

    reflowed = "---\nid: first\n---\n# Heading\n\nBo\ndy\n"
    markdown_rewritten = "---\nid: first\n---\n# Heading\n\n**Body**\n"
    assert fingerprint(normalized) != fingerprint(reflowed)
    assert fingerprint(normalized) != fingerprint(markdown_rewritten)


def test_markdown_syntax_rewrite_trips_frozen_self_hash(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root, "docs/roadmap.md", _roadmap())
    original = "---\npersistence: frozen\n---\n# Reference\n\n**Important**\n"
    reference = _write(root, "docs/spec/reference.md", original)
    stamp = fingerprint(original)
    reference.write_text(
        f"---\npersistence: frozen\nself_hash: {stamp}\n---\n# Reference\n\n__Important__\n",
        encoding="utf-8",
    )

    result = resolve(root, _settings(root))
    assert "self-hash-mismatch" in {finding.code for finding in result.errors}


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


def test_landing_projection_owns_rewrites_graph_and_validation(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    source_path = _write(
        root,
        "docs/changes/source/change.md",
        "---\nid: source\npersistence: ephemeral\nstatus: proposed\ntrack: test\n---\n"
        "# Source\n\nStatus: Proposed (not accepted) · Proposed 2026-07-24\n",
    )
    active_path = _write(
        root,
        "docs/changes/active/change.md",
        "---\nid: active\npersistence: ephemeral\nstatus: proposed\ntrack: test\n"
        "depends_on:\n  - source\n---\n# Active\n",
    )
    inactive_path = _write(
        root,
        "docs/changes/inactive/change.md",
        "---\nid: inactive\npersistence: ephemeral\nstatus: landed\ntrack: test\n"
        "depends_on:\n  - source\n---\n# Inactive\n",
    )
    nodes = {
        "source": Node(
            "source", "change", source_path, "ephemeral", "proposed", "test", [], [], None
        ),
        "active": Node(
            "active",
            "change",
            active_path,
            "ephemeral",
            "proposed",
            "test",
            [Edge("source")],
            [],
            None,
        ),
        "inactive": Node(
            "inactive",
            "change",
            inactive_path,
            "ephemeral",
            "landed",
            "test",
            [Edge("source")],
            [],
            None,
        ),
    }
    resolution = Resolution(nodes, [], ["source", "active", "inactive"])
    original = copy.deepcopy(resolution)
    archive = root / "docs/changes/archive/2026-07-24-source/change.md"
    roadmap = (
        "- `docs/changes/archive/2026-07-24-source/` (landed)\n"
        "- `docs/changes/active/` (proposed)\n"
    )

    projection = project_landing(
        root,
        _settings(root),
        resolution,
        change_id="source",
        archive_path=archive,
        archive_relative="docs/changes/archive/2026-07-24-source",
        landed_at="2026-07-24",
        planned_roadmap_text=roadmap,
    )

    projected = projection.resolution
    landed_hash = fingerprint(projection.change_document.content)
    assert projection.change_document.path == archive
    assert "status: landed" in projection.change_document.content
    assert "Status: Landed · 2026-07-24" in projection.change_document.content
    assert [document.path for document in projection.dependent_documents] == [active_path]
    assert f"source: {landed_hash}" in projection.dependent_documents[0].content
    assert projected.nodes["source"].path == archive
    assert projected.nodes["source"].status == "landed"
    assert projected.nodes["source"].dependents == ("active", "inactive")
    assert projected.nodes["active"].depends_on[0].fingerprint == landed_hash
    assert projected.nodes["inactive"].depends_on[0].fingerprint is None
    assert projected.topo_order.index("source") < projected.topo_order.index("active")
    assert 'source["source (landed)"]' in projection.roadmap_block
    assert "source --> active" in projection.roadmap_block
    assert not projected.errors
    assert resolution == original
    with pytest.raises(TypeError):
        projected.nodes["new"] = projected.nodes["source"]  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        projected.nodes["source"].status = "proposed"  # type: ignore[misc]


def test_landing_projection_reports_unknown_and_cyclic_graph(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    source_path = _write(root, "docs/changes/source/change.md", _change("source"))
    first_path = _write(
        root,
        "docs/changes/first/change.md",
        "---\nid: first\npersistence: ephemeral\nstatus: proposed\ntrack: test\n"
        "depends_on:\n  - second\n  - missing\n  - source\n---\n# First\n",
    )
    second_path = _write(
        root,
        "docs/changes/second/change.md",
        "---\nid: second\npersistence: ephemeral\nstatus: proposed\ntrack: test\n"
        "depends_on:\n  - first\n---\n# Second\n",
    )
    resolution = Resolution(
        {
            "source": Node(
                "source", "change", source_path, "ephemeral", "proposed", "test", [], [], None
            ),
            "first": Node(
                "first",
                "change",
                first_path,
                "ephemeral",
                "proposed",
                "test",
                [Edge("second"), Edge("missing"), Edge("source")],
                [],
                None,
            ),
            "second": Node(
                "second",
                "change",
                second_path,
                "ephemeral",
                "proposed",
                "test",
                [Edge("first")],
                [],
                None,
            ),
        },
        [],
        [],
    )
    roadmap = (
        "- `docs/changes/archive/2026-07-24-source/` (landed)\n"
        "- `docs/changes/first/` (proposed)\n"
        "- `docs/changes/second/` (proposed)\n"
    )

    projection = project_landing(
        root,
        _settings(root),
        resolution,
        change_id="source",
        archive_path=root / "docs/changes/archive/2026-07-24-source/change.md",
        archive_relative="docs/changes/archive/2026-07-24-source",
        landed_at="2026-07-24",
        planned_roadmap_text=roadmap,
    )

    assert {finding.code for finding in projection.findings} >= {"unknown-dependency", "cycle"}
    assert projection.resolution.topo_order == ("source",)


def test_landing_projection_matches_final_on_disk_resolution(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    roadmap_header = "---\npersistence: living\n---\n# Roadmap\n\n"
    generated = (
        "<!-- BEGIN GENERATED DAG (regenerate: doc-contract update --repo-root .) -->\n"
        "```mermaid\nflowchart TD\n```\n<!-- END GENERATED DAG -->\n"
    )
    _write(
        root,
        "docs/roadmap.md",
        roadmap_header
        + "- `docs/changes/source/` (proposed)\n"
        + "- `docs/changes/dependent/` (proposed)\n\n"
        + generated,
    )
    source_path = _write(root, "docs/changes/source/change.md", _change("source"))
    dependent_path = _write(
        root,
        "docs/changes/dependent/change.md",
        "---\nid: dependent\npersistence: ephemeral\nstatus: proposed\ntrack: test\n"
        "depends_on:\n  - source\n---\n# Dependent\n",
    )
    settings = _settings(root)
    resolution = resolve(root, settings)
    original = copy.deepcopy(resolution)
    archive = root / "docs/changes/archive/2026-07-24-source/change.md"
    planned_roadmap = (
        roadmap_header
        + "- `docs/changes/archive/2026-07-24-source/` (landed)\n"
        + "- `docs/changes/dependent/` (proposed)\n\n"
        + generated
    )

    projection = project_landing(
        root,
        settings,
        resolution,
        change_id="source",
        archive_path=archive,
        archive_relative="docs/changes/archive/2026-07-24-source",
        landed_at="2026-07-24",
        planned_roadmap_text=planned_roadmap,
    )

    archive.parent.mkdir(parents=True)
    archive.write_text(projection.change_document.content, encoding="utf-8")
    source_path.unlink()
    source_path.parent.rmdir()
    dependent_path.write_text(projection.dependent_documents[0].content, encoding="utf-8")
    (root / "docs/roadmap.md").write_text(
        planned_roadmap[: planned_roadmap.index("<!-- BEGIN GENERATED DAG")]
        + projection.roadmap_block
        + "\n",
        encoding="utf-8",
    )
    final = resolve(root, settings)

    projected = projection.resolution
    assert resolution == original
    assert set(projected.nodes) == set(final.nodes)
    for node_id, node in projected.nodes.items():
        final_node = final.nodes[node_id]
        assert (
            node.id,
            node.kind,
            node.path,
            node.persistence,
            node.status,
            node.track,
            node.depends_on,
            node.files_owned,
            node.gated_on,
            node.self_hash,
            node.dependents,
        ) == (
            final_node.id,
            final_node.kind,
            final_node.path,
            final_node.persistence,
            final_node.status,
            final_node.track,
            tuple(final_node.depends_on),
            tuple(final_node.files_owned),
            final_node.gated_on,
            final_node.self_hash,
            tuple(final_node.dependents),
        )
    assert projected.findings == tuple(final.findings)
    assert projected.topo_order == tuple(final.topo_order)
    assert projection.roadmap_block == render_block(final)
