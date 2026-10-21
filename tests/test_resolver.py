"""Discovery, path-policy, hash-state, and warning-reporting regressions."""

from __future__ import annotations

import ast
import copy
from collections.abc import Iterable
from dataclasses import FrozenInstanceError
import subprocess
from pathlib import Path

import pytest

import doc_contract.resolver as resolver_module
from doc_contract.cli import main
from doc_contract.config import Settings
from doc_contract.resolver import (
    Edge,
    Node,
    Resolution,
    fingerprint,
    parse_front_matter,
    project_landing,
    project_proposal,
    project_supersede,
    render_block,
    resolve,
    stamp_node,
    validate,
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


def _config() -> str:
    return (
        "schema_version = 1\n"
        'repo_name = "fixture"\n'
        'roadmap = "docs/roadmap.md"\n'
        "\n[root_nodes]\n"
        'roadmap = "docs/roadmap.md"\n'
        "\n[capability]\n"
        'mode = "skip"\n'
    )


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_discovery_defaults_to_tracked_and_declared_nodes(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root, "docs/roadmap.md", _roadmap("tracked"))
    _write(root, "docs/changes/tracked/change.md", _change("tracked"))
    _write(root, "docs/changes/tracked/tasks.md", "# Tracked tasks\n")
    _write(root, "docs/changes/provisional/change.md", _change("provisional"))
    _write(root, "docs/changes/provisional/tasks.md", "# Provisional tasks\n")
    _git(root, "init", "-q")
    _git(
        root,
        "add",
        "docs/roadmap.md",
        "docs/changes/tracked/change.md",
        "docs/changes/tracked/tasks.md",
    )

    default = resolve(root, _settings(root))
    assert set(default.nodes) == {"roadmap", "tracked"}
    assert [(item.node_id, item.included) for item in default.discovery] == [
        ("provisional", False)
    ]
    assert [path.relative_to(root).as_posix() for path in default.document_paths] == [
        "docs/changes/tracked/change.md",
        "docs/changes/tracked/tasks.md",
        "docs/roadmap.md",
    ]

    provisional = resolve(root, _settings(root), include_untracked=True)
    assert set(provisional.nodes) == {"provisional", "roadmap", "tracked"}
    assert [(item.node_id, item.included) for item in provisional.discovery] == [
        ("provisional", True)
    ]
    assert [path.relative_to(root).as_posix() for path in provisional.document_paths] == [
        "docs/changes/provisional/change.md",
        "docs/changes/provisional/tasks.md",
        "docs/changes/tracked/change.md",
        "docs/changes/tracked/tasks.md",
        "docs/roadmap.md",
    ]


@pytest.mark.parametrize("status", ["proposed", "accepted", "in-progress", "blocked", "landed"])
def test_supported_change_statuses_resolve(tmp_path: Path, status: str) -> None:
    root = tmp_path / "repo"
    _write(root, "docs/roadmap.md", _roadmap("item").replace("(proposed)", f"({status})"))
    _write(
        root,
        "docs/changes/item/change.md",
        _change("item").replace("status: proposed", f"status: {status}"),
    )
    result = resolve(root, _settings(root))
    assert not [finding for finding in result.errors if finding.code == "unknown-change-status"]


def test_unknown_change_status_is_an_error(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root, "docs/roadmap.md", _roadmap("item"))
    _write(
        root,
        "docs/changes/item/change.md",
        _change("item").replace("status: proposed", "status: reviewing"),
    )
    result = resolve(root, _settings(root))
    assert "unknown-change-status" in {finding.code for finding in result.errors}


def test_secret_scanning_reuses_discovered_document_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    _write(root, "docs/roadmap.md", _roadmap("tracked"))
    _write(root, "docs/changes/tracked/change.md", _change("tracked"))
    _write(root, "docs/changes/tracked/tasks.md", "# Tasks\n")
    _write(root, "docs/generated/report.md", "API_KEY=generated-fixture\n")
    _write(root, "src/config.py", "API_KEY=source-fixture\n")
    _write(root, ".env", "API_KEY=env-fixture\n")
    _write(root, "vendor/dependency/README.md", "API_KEY=vendor-fixture\n")
    _write(root, "vendor/dependency/.git/HEAD", "ref: refs/heads/main\n")
    _git(root, "init", "-q")
    _git(root, "add", "docs", "src/config.py", ".env")

    scanned_paths: tuple[Path, ...] = ()

    def record_scan(
        paths: Iterable[Path],
        *,
        root: Path | None = None,
        secret_env_names: Iterable[str] = (),
    ) -> list[object]:
        nonlocal scanned_paths
        scanned_paths = tuple(paths)
        assert root == (tmp_path / "repo").resolve()
        assert tuple(secret_env_names) == ()
        return []

    monkeypatch.setattr(resolver_module, "scan", record_scan)
    result = resolver_module.resolve(root, _settings(root))

    assert scanned_paths == result.document_paths
    assert [path.relative_to(root).as_posix() for path in scanned_paths] == [
        "docs/changes/tracked/change.md",
        "docs/changes/tracked/tasks.md",
        "docs/roadmap.md",
    ]


def test_secret_scanning_tracks_untracked_document_discovery(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root, "docs/roadmap.md", _roadmap())
    _write(
        root,
        "docs/changes/provisional/change.md",
        _change("provisional") + "\nAPI_KEY=provisional-fixture\n",
    )
    _git(root, "init", "-q")
    _git(root, "add", "docs/roadmap.md")

    default = resolve(root, _settings(root))
    assert not [finding for finding in default.errors if finding.code == "secret-detected"]

    provisional = resolve(root, _settings(root), include_untracked=True)
    secret_findings = [
        finding for finding in provisional.errors if finding.code == "secret-detected"
    ]
    assert len(secret_findings) == 1
    assert "docs/changes/provisional/change.md" in secret_findings[0].message
    assert "provisional-fixture" not in secret_findings[0].message


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
        suspect = [finding for finding in result.warnings if finding.code == "suspect-link"]
        assert len(suspect) == 1
        finding = suspect[0]
        assert finding.level == "WARN"
        assert finding.subjects == ("source", "target")
        assert finding.message.startswith(
            "source → target: target changed since review (recorded "
        )
        assert "now " in finding.message
        assert "`doc-contract stamp source`" in finding.message
        assert "(add `--include-untracked` while it is provisional)" in finding.message
        assert "suspect-link" not in {finding.code for finding in result.errors}


def test_stamp_clears_suspect_link_after_dependency_archived(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "repo"
    _write(root, ".doc-contract.toml", _config())
    _write(root, "docs/roadmap.md", _roadmap("source"))
    target = _write(
        root,
        "docs/changes/target/change.md",
        "---\nid: target\npersistence: ephemeral\nstatus: landed\ntrack: test\n---\n# Target\n",
    )
    _write(root, "docs/changes/source/change.md", _change("source", fingerprint="0" * 16))
    settings = _settings(root)

    def suspect_warnings() -> int:
        result = resolve(root, settings)
        return len([finding for finding in result.warnings if finding.code == "suspect-link"])

    assert suspect_warnings() == 1

    # Land the dependency: archive it under docs/changes/archive/<date>-<name>/ and change its body.
    original_fingerprint = fingerprint(target.read_text(encoding="utf-8"))
    archived = root / "docs/changes/archive/2026-01-01-target/change.md"
    archived.parent.mkdir(parents=True)
    archived.write_text(
        "---\nid: target\npersistence: ephemeral\nstatus: landed\ntrack: test\n"
        "---\n# Target\n\nChanged after landing.\n",
        encoding="utf-8",
    )
    target.unlink()
    assert fingerprint(archived.read_text(encoding="utf-8")) != original_fingerprint

    # The landed dependency itself has no stampable contract (CLI exits 1).
    assert main(["stamp", "target", "--repo-root", str(root)]) == 1
    assert "has no stampable contract" in capsys.readouterr().err

    # The depender is where the fingerprint lives, so stamping it clears the warning.
    assert stamp_node(root, settings, "source") is True
    assert suspect_warnings() == 0


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
        "- `docs/changes/source/` (proposed)\n"
        "- `docs/changes/active/` (proposed)\n"
        "<!-- BEGIN GENERATED DAG (regenerate: doc-contract update --repo-root .) -->\n"
        "```mermaid\nflowchart TD\n```\n"
        "<!-- END GENERATED DAG -->\n"
    )

    projection = project_landing(
        root,
        _settings(root),
        resolution,
        change_id="source",
        archive_path=archive,
        archive_relative="docs/changes/archive/2026-07-24-source",
        landed_at="2026-07-24",
        roadmap_text=roadmap,
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
    assert "- `docs/changes/archive/2026-07-24-source/` (landed)" in projection.roadmap_text
    assert "docs/changes/source/" not in projection.roadmap_text
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
        "- `docs/changes/source/` (proposed)\n"
        "- `docs/changes/first/` (proposed)\n"
        "- `docs/changes/second/` (proposed)\n"
        "<!-- BEGIN GENERATED DAG (regenerate: doc-contract update --repo-root .) -->\n"
        "```mermaid\nflowchart TD\n```\n"
        "<!-- END GENERATED DAG -->\n"
    )

    projection = project_landing(
        root,
        _settings(root),
        resolution,
        change_id="source",
        archive_path=root / "docs/changes/archive/2026-07-24-source/change.md",
        archive_relative="docs/changes/archive/2026-07-24-source",
        landed_at="2026-07-24",
        roadmap_text=roadmap,
    )

    by_code = {finding.code: finding for finding in projection.resolution.findings}
    assert by_code["unknown-dependency"].subjects == ("first", "missing")
    assert by_code["cycle"].subjects == ("first", "second")

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
    current_roadmap = (root / "docs/roadmap.md").read_text(encoding="utf-8")

    projection = project_landing(
        root,
        settings,
        resolution,
        change_id="source",
        archive_path=archive,
        archive_relative="docs/changes/archive/2026-07-24-source",
        landed_at="2026-07-24",
        roadmap_text=current_roadmap,
    )

    archive.parent.mkdir(parents=True)
    archive.write_text(projection.change_document.content, encoding="utf-8")
    source_path.unlink()
    source_path.parent.rmdir()
    dependent_path.write_text(projection.dependent_documents[0].content, encoding="utf-8")
    (root / "docs/roadmap.md").write_text(
        projection.roadmap_text[: projection.roadmap_text.index("<!-- BEGIN GENERATED DAG")]
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


# ---------------------------------------------------------------- roadmap status span contract
#
# `_roadmap_transition_text` rewrites the roadmap presentation of the change a lifecycle
# transition selected. These tests pin that span contract directly: the presentations it accepts
# are derived from `_STATUS_TOKENS` (the grammar `_roadmap_status_for` already recognizes), the
# whole presentation is replaced by the canonical destination token, and every byte outside the
# span survives.

_DAG_BLOCK = (
    "<!-- BEGIN GENERATED DAG (regenerate: doc-contract update --repo-root .) -->\n"
    "```mermaid\nflowchart TD\n    example[\"example (proposed)\"]\n```\n"
    "<!-- END GENERATED DAG -->\n"
)
_ROADMAP_HEADER = "---\npersistence: living\n---\n# Roadmap\n\n"
_OWN_LINE_PREFIX = "- `docs/changes/example/`"


def _status_node(node_id: str = "example", *, status: str = "proposed") -> Node:
    return Node(
        id=node_id,
        kind="change",
        path=Path(f"docs/changes/{node_id}/change.md"),
        persistence="ephemeral",
        status=status,
        track="test",
        depends_on=[],
        files_owned=[],
        gated_on=None,
    )


def _status_roadmap(line: str, *, dag: str = _DAG_BLOCK, trailer: str = "") -> str:
    return f"{_ROADMAP_HEADER}{line}\n{trailer}{dag}"


def _rewrite(
    text: str,
    *,
    node: Node | None = None,
    source_status: str = "proposed",
    destination_status: str = "accepted",
    change_dirs: set[str] | None = None,
) -> str:
    return resolver_module._roadmap_transition_text(
        text,
        node=node if node is not None else _status_node(),
        source_status=source_status,
        destination_status=destination_status,
        change_dirs={"docs/changes/example/"} if change_dirs is None else change_dirs,
    )


def _own_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith(_OWN_LINE_PREFIX)]


@pytest.mark.parametrize(
    ("presentation", "rationale"),
    [
        ("(proposed)", "— promote the resolver boundary"),
        ("(PROPOSED)", "— promote the resolver boundary"),
        ("(Proposed, not accepted)", "— promote the resolver boundary"),
        ("(proposed, depends on the landed `x`)", "— promote the resolver boundary"),
        ("(proposed foundation)", "— promote the resolver boundary"),
        ("(proposed, depends on x (v1.2))", "— promote the resolver boundary"),
        ("(proposed — depends on x)", "— promote the resolver boundary"),
        ("proposed 2026-08-03", "— promote the resolver boundary"),
        ("(proposed)", "— rationale — with an inner em dash"),
    ],
)
def test_accept_canonicalizes_every_supported_proposed_presentation(
    presentation: str, rationale: str
) -> None:
    line = f"{_OWN_LINE_PREFIX} {presentation} {rationale}"
    rewritten = _rewrite(_status_roadmap(line))
    assert _own_lines(rewritten) == [f"{_OWN_LINE_PREFIX} (accepted) {rationale}"]


def test_accept_canonicalizes_a_marker_that_follows_the_rationale_dash() -> None:
    line = f"{_OWN_LINE_PREFIX} — promote the resolver boundary (proposed)"
    rewritten = _rewrite(_status_roadmap(line))
    assert _own_lines(rewritten) == [
        f"{_OWN_LINE_PREFIX} — promote the resolver boundary (accepted)"
    ]


@pytest.mark.parametrize(
    "presentation",
    [
        "(accepted)",
        "(ACCEPTED)",
        "(Accepted, not started)",
        "(accepted, depends on the landed `x`)",
        "(accepted foundation)",
        "(accepted, depends on x (v1.2))",
    ],
)
def test_begin_canonicalizes_every_supported_accepted_presentation(
    presentation: str,
) -> None:
    line = f"{_OWN_LINE_PREFIX} {presentation} — start the resolver boundary"
    rewritten = _rewrite(
        _status_roadmap(line),
        node=_status_node(status="accepted"),
        source_status="accepted",
        destination_status="in-progress",
    )
    assert _own_lines(rewritten) == [
        f"{_OWN_LINE_PREFIX} (in-progress) — start the resolver boundary"
    ]


@pytest.mark.parametrize(
    ("line", "presentations"),
    [
        (f"{_OWN_LINE_PREFIX} — promote the resolver boundary", 0),
        (f"{_OWN_LINE_PREFIX} (proposed — promote the resolver boundary", 0),
        (f"{_OWN_LINE_PREFIX} (proposed) — was (proposed) before", 2),
        (f"{_OWN_LINE_PREFIX} (proposed) proposed 2026-08-03", 2),
        (f"{_OWN_LINE_PREFIX} (proposed 2026-08-03) — two overlapping presentations", 2),
        (f"{_OWN_LINE_PREFIX} (proposed, ZYZZYVA-annotation — promote", 0),
    ],
)
def test_accept_rejects_a_located_line_it_cannot_rewrite_unambiguously(
    line: str, presentations: int
) -> None:
    with pytest.raises(ValueError) as captured:
        _rewrite(_status_roadmap(line))
    message = str(captured.value)
    assert message == (
        f"roadmap-invalid: unrewritable roadmap status for example ({presentations} status presentations)"
    )
    # Value-free: the detail is re-emitted verbatim as a reconciliation finding, so it carries
    # neither the line, the presentation, nor any annotation prose planted in the fixture.
    assert "ZYZZYVA" not in message
    assert "proposed" not in message
    assert _OWN_LINE_PREFIX not in message


@pytest.mark.parametrize(
    ("line", "presentations"),
    [
        (f"{_OWN_LINE_PREFIX} — start the resolver boundary", 0),
        (f"{_OWN_LINE_PREFIX} accepted 2026-08-03 — start the resolver boundary", 0),
        (f"{_OWN_LINE_PREFIX} (accepted) — was (accepted) before", 2),
    ],
)
def test_begin_rejects_a_located_line_it_cannot_rewrite_unambiguously(
    line: str, presentations: int
) -> None:
    with pytest.raises(ValueError) as captured:
        _rewrite(
            _status_roadmap(line),
            node=_status_node(status="accepted"),
            source_status="accepted",
            destination_status="in-progress",
        )
    assert str(captured.value) == (
        f"roadmap-invalid: unrewritable roadmap status for example ({presentations} status presentations)"
    )


def test_rejection_detail_is_distinct_for_an_ambiguous_multi_folder_line() -> None:
    shared = f"{_OWN_LINE_PREFIX} and `docs/changes/other/` (proposed) — promote"
    with pytest.raises(ValueError) as captured:
        _rewrite(
            _status_roadmap(shared),
            change_dirs={"docs/changes/example/", "docs/changes/other/"},
        )
    assert str(captured.value) == (
        "roadmap-invalid: cross-referenced roadmap entry for example "
        "(1 candidate cites another change folder)"
    )

    missing = "- `docs/changes/elsewhere/` (proposed) — promote"
    with pytest.raises(ValueError) as captured:
        _rewrite(_status_roadmap(missing))
    assert str(captured.value) == "roadmap-invalid: no roadmap entry for example (0 candidates)"


def test_a_line_naming_another_folder_never_donates_its_status_span() -> None:
    cross_ref = "- `docs/changes/other/` and `docs/changes/example/` (accepted) — cross ref"
    own = f"{_OWN_LINE_PREFIX} (proposed) — promote the resolver boundary"
    text = f"{_ROADMAP_HEADER}{cross_ref}\n{own}\n{_DAG_BLOCK}"
    # The cross-reference line plus the own entry are now two candidates, so the rewriter
    # refuses instead of silently donating the `(accepted)` presentation across folders.
    with pytest.raises(ValueError) as captured:
        _rewrite(text, change_dirs={"docs/changes/example/", "docs/changes/other/"})
    assert str(captured.value) == (
        "roadmap-invalid: ambiguous roadmap entry for example (2 candidates)"
    )


def test_rewrite_preserves_every_byte_outside_the_status_span() -> None:
    other = "- `docs/changes/other/` (proposed) — unrelated line stays byte-identical"
    line = f"{_OWN_LINE_PREFIX} (Proposed, not accepted)   — rationale with  spacing   "
    text = _status_roadmap(line, trailer=f"{other}\n\n")
    rewritten = _rewrite(text, change_dirs={"docs/changes/example/", "docs/changes/other/"})

    before, after = text.splitlines(keepends=True), rewritten.splitlines(keepends=True)
    assert len(before) == len(after)
    changed = [index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]
    assert changed == [5]
    assert after[5] == f"{_OWN_LINE_PREFIX} (accepted)   — rationale with  spacing   \n"
    # Exact prefix/suffix equality around the replaced span.
    assert after[5].startswith(f"{_OWN_LINE_PREFIX} ")
    assert after[5].endswith("   — rationale with  spacing   \n")
    assert other in rewritten
    assert rewritten[rewritten.index("<!-- BEGIN GENERATED DAG") :] == _DAG_BLOCK


def test_rewrite_never_selects_a_line_inside_the_generated_dag_region() -> None:
    dag = (
        "<!-- BEGIN GENERATED DAG (regenerate: doc-contract update --repo-root .) -->\n"
        "```mermaid\nflowchart TD\n"
        '    example["docs/changes/example/ (proposed)"]\n'
        "```\n<!-- END GENERATED DAG -->\n"
    )
    line = f"{_OWN_LINE_PREFIX} (proposed) — promote the resolver boundary"
    text = _status_roadmap(line, dag=dag)
    rewritten = _rewrite(text)
    assert rewritten[rewritten.index("<!-- BEGIN GENERATED DAG") :] == dag
    assert _own_lines(rewritten) == [
        f"{_OWN_LINE_PREFIX} (accepted) — promote the resolver boundary"
    ]

    dag_only = f"{_ROADMAP_HEADER}\n{dag}"
    with pytest.raises(ValueError) as captured:
        _rewrite(dag_only)
    assert str(captured.value) == "roadmap-invalid: no roadmap entry for example (0 candidates)"


def test_rewrite_preserves_line_terminators_blank_lines_and_a_final_unterminated_line() -> None:
    dag = _DAG_BLOCK.replace("\n", "\r\n")
    text = (
        "---\r\npersistence: living\r\n---\r\n# Roadmap\r\n\r\n"
        f"{_OWN_LINE_PREFIX} (proposed) — promote\r\n"
        "\r\n"
        f"{dag}"
        "\r\n"
        "- trailing note without a terminator"
    )
    rewritten = _rewrite(text)
    assert rewritten.count("\r\n") == text.count("\r\n")
    assert "\n" not in rewritten.replace("\r\n", "")
    assert not rewritten.endswith(("\n", "\r"))
    assert rewritten.endswith("- trailing note without a terminator")
    assert f"{_OWN_LINE_PREFIX} (accepted) — promote\r\n" in rewritten
    assert rewritten.replace("(accepted)", "(proposed)", 1) == text


def test_rewrite_computes_offsets_against_the_original_line_bytes() -> None:
    # `str.lower()` is not length-preserving ("İ" lowercases to two code points), so an offset
    # found in a lowercased copy would land on the wrong byte here.
    line = f"{_OWN_LINE_PREFIX} İstanbulß (PROPOSED) — résumé"
    rewritten = _rewrite(_status_roadmap(line))
    assert _own_lines(rewritten) == [f"{_OWN_LINE_PREFIX} İstanbulß (accepted) — résumé"]


def test_roadmap_status_recognition_is_unchanged_for_every_annotated_form() -> None:
    node = _status_node()
    change_dirs = {"docs/changes/example/"}
    expected = {
        "(proposed)": "proposed",
        "(PROPOSED)": "proposed",
        "(Proposed, not accepted)": "proposed",
        "(proposed, depends on the landed `x`)": "proposed",
        "(proposed foundation)": "proposed",
        "proposed 2026-08-03": "proposed",
        "(accepted)": "accepted",
        "(Accepted, not started)": "accepted",
        "(accepted foundation)": "accepted",
        "(in-progress)": "in-progress",
        "(blocked)": "blocked",
        "— no status marker here": None,
    }
    for presentation, status in expected.items():
        roadmap = f"{_ROADMAP_HEADER}{_OWN_LINE_PREFIX} {presentation} — rationale\n"
        assert resolver_module._roadmap_status_for(node, roadmap, change_dirs) == status


def test_the_status_span_grammar_is_derived_from_status_tokens_alone() -> None:
    for status in ("proposed", "accepted", "in-progress", "blocked"):
        assert resolver_module._status_source_tokens(status) == tuple(
            token for token, mapped in resolver_module._STATUS_TOKENS if mapped == status
        )
    assert resolver_module._status_source_tokens("proposed")
    assert resolver_module._status_source_tokens("accepted")

    source = Path(resolver_module.__file__).read_text(encoding="utf-8")
    module = ast.parse(source)
    status_words = ("proposed", "accepted", "in-progress", "blocked")
    alternations = [
        constant.value
        for constant in ast.walk(module)
        if isinstance(constant, ast.Constant)
        and isinstance(constant.value, str)
        and "(?" in constant.value
        and sum(word in constant.value for word in status_words) > 1
    ]
    assert alternations == []
    assert r"\((?:proposed|accepted|in-progress|blocked)\)" not in source

    rewriter = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "_roadmap_transition_text"
    )
    assert not [
        call
        for call in ast.walk(rewriter)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "sub"
    ]


@pytest.mark.parametrize("token", resolver_module._status_source_tokens("proposed"))
def test_every_recognized_proposed_token_is_rewritable_by_accept(token: str) -> None:
    completion = ")" if token.startswith("(") else "26-08-03"
    line = f"{_OWN_LINE_PREFIX} {token}{completion} — promote the resolver boundary"
    spans = resolver_module._status_spans(f"{line}\n", (token,))
    assert len(spans) == 1
    assert _own_lines(_rewrite(_status_roadmap(line))) == [
        f"{_OWN_LINE_PREFIX} (accepted) — promote the resolver boundary"
    ]


# --------------------------------------------------------------------------- Proposal projection tests (F-007)


def test_project_proposal_validates_constraints(tmp_path: Path) -> None:
    """REQ-024: project_proposal validates persistence and status constraints."""
    root = tmp_path / "repo"
    _write(root, "docs/roadmap.md", _roadmap())
    settings = _settings(root)

    # Valid proposal content
    valid_content = """---
id: test-proposal
persistence: ephemeral
status: proposed
track: test
---
# Test Proposal

Status: Proposed (not accepted) · Proposed 2026-01-01
"""

    # Test valid projection
    projection = project_proposal(
        root,
        settings,
        proposal_id="test-proposal",
        proposal_path="docs/changes/test-proposal/change.md",
        proposal_content=valid_content,
        roadmap_line="- `docs/changes/test-proposal/` (proposed) — test",
    )
    assert projection.change_document.path == root / "docs/changes/test-proposal/change.md"
    assert projection.resolution.nodes["test-proposal"].status == "proposed"
    assert projection.resolution.nodes["test-proposal"].persistence == "ephemeral"


def test_project_proposal_rejects_wrong_persistence(tmp_path: Path) -> None:
    """REQ-024: project_proposal rejects non-ephemeral persistence."""
    root = tmp_path / "repo"
    _write(root, "docs/roadmap.md", _roadmap())
    settings = _settings(root)

    content = """---
id: test-proposal
persistence: living
status: proposed
---
# Test
"""

    with pytest.raises(ValueError) as exc:
        project_proposal(
            root,
            settings,
            proposal_id="test-proposal",
            proposal_path="docs/changes/test-proposal/change.md",
            proposal_content=content,
            roadmap_line="- `docs/changes/test-proposal/` (proposed) — test",
        )
    assert "persistence must be 'ephemeral'" in str(exc.value)


def test_project_proposal_rejects_wrong_status(tmp_path: Path) -> None:
    """REQ-024: project_proposal rejects non-proposed status."""
    root = tmp_path / "repo"
    _write(root, "docs/roadmap.md", _roadmap())
    settings = _settings(root)

    content = """---
id: test-proposal
persistence: ephemeral
status: accepted
---
# Test
"""

    with pytest.raises(ValueError) as exc:
        project_proposal(
            root,
            settings,
            proposal_id="test-proposal",
            proposal_path="docs/changes/test-proposal/change.md",
            proposal_content=content,
            roadmap_line="- `docs/changes/test-proposal/` (proposed) — test",
        )
    assert "status must be 'proposed'" in str(exc.value)


def test_project_proposal_rejects_id_mismatch(tmp_path: Path) -> None:
    """REQ-024: project_proposal rejects ID mismatch."""
    root = tmp_path / "repo"
    _write(root, "docs/roadmap.md", _roadmap())
    settings = _settings(root)

    content = """---
id: different-id
persistence: ephemeral
status: proposed
---
# Test
"""

    with pytest.raises(ValueError) as exc:
        project_proposal(
            root,
            settings,
            proposal_id="test-proposal",
            proposal_path="docs/changes/test-proposal/change.md",
            proposal_content=content,
            roadmap_line="- `docs/changes/test-proposal/` (proposed) — test",
        )
    assert "does not match" in str(exc.value)


def test_project_proposal_rejects_path_mismatch(tmp_path: Path) -> None:
    """REQ-024: project_proposal rejects path mismatch."""
    root = tmp_path / "repo"
    _write(root, "docs/roadmap.md", _roadmap())
    settings = _settings(root)

    content = """---
id: test-proposal
persistence: ephemeral
status: proposed
---
# Test
"""

    with pytest.raises(ValueError) as exc:
        project_proposal(
            root,
            settings,
            proposal_id="test-proposal",
            proposal_path="docs/changes/wrong-path/change.md",
            proposal_content=content,
            roadmap_line="- `docs/changes/test-proposal/` (proposed) — test",
        )
    assert "does not match expected" in str(exc.value)


def test_project_proposal_parity_with_final_resolution(tmp_path: Path) -> None:
    """REQ-054: projection's findings and Mermaid block equal final on-disk resolution."""
    import subprocess

    root = tmp_path / "repo"
    roadmap_header = "---\npersistence: living\n---\n# Roadmap\n\n## Remediation\n\n"
    generated = (
        "<!-- BEGIN GENERATED DAG (regenerate: doc-contract update --repo-root .) -->\n"
        "```mermaid\nflowchart TD\n```\n"
        "<!-- END GENERATED DAG -->\n"
    )
    _write(root, "docs/roadmap.md", roadmap_header + generated)

    # Initialize git repo
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init", "-q"], cwd=root, check=True, capture_output=True)

    settings = _settings(root)

    proposal_content = """---
id: test-proposal
persistence: ephemeral
status: proposed
track: test
---
# Test Proposal

Status: Proposed (not accepted) · Proposed 2026-01-01
"""

    roadmap_line = "- `docs/changes/test-proposal/` (proposed) — test proposal"

    # Project the proposal
    projection = project_proposal(
        root,
        settings,
        proposal_id="test-proposal",
        proposal_path="docs/changes/test-proposal/change.md",
        proposal_content=proposal_content,
        roadmap_line=roadmap_line,
    )

    # Write the proposal to disk
    proposal_path = root / "docs/changes/test-proposal/change.md"
    proposal_path.parent.mkdir(parents=True, exist_ok=True)
    proposal_path.write_text(proposal_content, encoding="utf-8")

    # Update the roadmap with the line and DAG
    roadmap_new = roadmap_header + roadmap_line + "\n" + projection.roadmap_block + "\n"
    _write(root, "docs/roadmap.md", roadmap_new)

    # Resolve with include_untracked=True
    final = resolve(root, settings, include_untracked=True)

    # Compare findings (excluding untracked-node warnings which differ)
    projected_findings = [f for f in projection.resolution.findings if f.code != "untracked-node-included"]
    final_findings = [f for f in final.findings if f.code != "untracked-node-included"]
    assert projected_findings == final_findings

    # Compare Mermaid blocks
    assert projection.roadmap_block == render_block(final)


# ------------------------------------------------ roadmap-line-dangling guard (REQ-014)
#
# A roadmap prose line that references an absent active change folder with no lineage
# record is the manual-deletion hole supersede closes: ERROR, over the configured roadmap
# text with the generated DAG excluded, and silent for every legitimate shape.


def _dangling_repo(root: Path, *, entry: str) -> Path:
    _write(root, "docs/roadmap.md", _roadmap() + entry)
    _git(root, "init", "-q")
    _git(root, "add", "docs/roadmap.md")
    return root


_DAG = (
    "<!-- BEGIN GENERATED DAG (regenerate: doc-contract update --repo-root .) -->\n"
    "```mermaid\nflowchart TD\n    gone[\"gone (proposed)\"]\n```\n"
    "<!-- END GENERATED DAG -->\n"
)


def test_dangling_roadmap_line_without_lineage_is_an_error(tmp_path: Path) -> None:
    root = _dangling_repo(tmp_path / "repo", entry="- `docs/changes/gone/` (proposed)\n")
    result = resolve(root, _settings(root))
    finding = next(f for f in result.errors if f.code == "roadmap-line-dangling")
    assert finding.subjects == ("gone",)
    assert "docs/changes/gone/" in finding.message


def test_dangling_roadmap_line_with_frozen_record_is_clean(tmp_path: Path) -> None:
    root = _dangling_repo(tmp_path / "repo", entry="- `docs/changes/gone/` (proposed)\n")
    record = (
        "---\nid: gone\npersistence: frozen\nstatus: superseded\n"
        "superseded_at: 2026-01-01\nself_hash: PENDING\n---\n# gone\n"
    )
    record = record.replace("self_hash: PENDING", f"self_hash: {fingerprint(record)}")
    _write(root, "docs/archive/gone.md", record)
    result = resolve(root, _settings(root), include_untracked=True)
    assert not [f for f in result.errors if f.code == "roadmap-line-dangling"]
    assert result.nodes["gone"].kind == "archive"
    assert result.nodes["gone"].status is None


def test_dangling_roadmap_line_with_landed_archive_folder_is_clean(tmp_path: Path) -> None:
    root = _dangling_repo(tmp_path / "repo", entry="- `docs/changes/gone/` (proposed)\n")
    _write(
        root,
        "docs/changes/archive/2026-01-01-gone/change.md",
        "---\nid: gone\npersistence: ephemeral\nstatus: landed\ntrack: test\n---\n# gone\n",
    )
    result = resolve(root, _settings(root))
    assert not [f for f in result.errors if f.code == "roadmap-line-dangling"]


def test_dangling_guard_stays_silent_for_legitimate_shapes(tmp_path: Path) -> None:
    # Live folder, archive-folder reference, statusless cross-reference line, and a
    # reference that only exists inside the generated DAG block.
    root = tmp_path / "repo"
    _write(root, "docs/roadmap.md", _roadmap("live"))
    _write(root, "docs/changes/live/change.md", _change("live"))
    _write(
        root,
        "docs/roadmap.md",
        _roadmap("live")
        + "- `docs/changes/archive/2026-01-01-gone/` (landed) — archive reference\n"
        + "- see `docs/changes/absent/` for the earlier proposal\n"
        + _DAG,
    )
    _write(
        root,
        "docs/changes/archive/2026-01-01-gone/change.md",
        "---\nid: gone\npersistence: ephemeral\nstatus: landed\ntrack: test\n---\n# gone\n",
    )
    _git(root, "init", "-q")
    _git(root, "add", "docs")
    result = resolve(root, _settings(root))
    assert not [f for f in result.errors if f.code == "roadmap-line-dangling"]


def test_dangling_guard_uses_the_projected_roadmap_text(tmp_path: Path) -> None:
    root = _dangling_repo(tmp_path / "repo", entry="- `docs/changes/gone/` (proposed)\n")
    settings = _settings(root)
    result = resolve(root, settings)
    assert "roadmap-line-dangling" in {f.code for f in result.errors}
    projected = validate(
        root,
        result.nodes,
        [],
        settings,
        roadmap_override=(
            "---\npersistence: living\n---\n# Roadmap\n\n"
            "- `docs/archive/gone.md` (superseded)\n"
        ),
    )
    assert not [f for f in projected if f.code == "roadmap-line-dangling"]


# -------------------------------- supersede record + projection (REQ-003/007/008/015)


def _supersede_roadmap(*entries: str) -> str:
    return _roadmap(*entries) + "\n" + _DAG


def _supersede_resolution(root: Path) -> Resolution:
    return resolve(root, _settings(root), include_untracked=True)


def test_project_supersede_builds_the_frozen_record_and_retargets_the_entry(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    reason = "superseded by the successor design — recorded verbatim"
    _write(root, "docs/roadmap.md", _supersede_roadmap("gone"))
    _write(root, "docs/changes/gone/change.md", _change("gone"))
    _git(root, "init", "-q")
    _git(root, "add", "docs")
    settings = _settings(root)
    result = _supersede_resolution(root)
    record_path = root / "docs/archive/gone.md"

    projection = project_supersede(
        root,
        settings,
        result,
        change_id="gone",
        record_path=record_path,
        record_relative="docs/archive/gone.md",
        superseded_at="2026-08-03",
        reason=reason,
        planned_roadmap_text=(root / "docs/roadmap.md").read_text(encoding="utf-8"),
    )

    assert "gone" not in projection.resolution.nodes
    record = projection.record_document.content
    values = parse_front_matter(record)
    assert values is not None
    assert values["id"] == "gone"
    assert values["persistence"] == "frozen"
    assert values["status"] == "superseded"
    assert values["superseded_at"] == "2026-08-03"
    assert values["self_hash"] == fingerprint(record)
    assert reason in record.split("---", 2)[2]
    assert "Superseded 2026-08-03" in record
    assert reason not in record.split("---")[0] + record.split("---")[1]
    assert not projection.resolution.errors
    assert "- `docs/archive/gone.md` (superseded)" in projection.roadmap_text
    assert "docs/changes/gone" not in projection.roadmap_text
    assert "gone" not in projection.roadmap_block


def test_project_supersede_leaves_dependent_edges_unrewritten(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root, "docs/roadmap.md", _supersede_roadmap("gone", "dependent"))
    _write(root, "docs/changes/gone/change.md", _change("gone"))
    _write(
        root,
        "docs/changes/dependent/change.md",
        _change("dependent").replace("track: test\n", "track: test\ndepends_on:\n  - gone\n"),
    )
    _git(root, "init", "-q")
    _git(root, "add", "docs")
    settings = _settings(root)
    result = _supersede_resolution(root)

    projection = project_supersede(
        root,
        settings,
        result,
        change_id="gone",
        record_path=root / "docs/archive/gone.md",
        record_relative="docs/archive/gone.md",
        superseded_at="2026-08-03",
        reason="reason",
        planned_roadmap_text=(root / "docs/roadmap.md").read_text(encoding="utf-8"),
    )

    assert "unknown-dependency" in {f.code for f in projection.resolution.errors}


def test_project_supersede_fails_closed_without_a_roadmap_entry(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root, "docs/roadmap.md", _supersede_roadmap())
    _write(root, "docs/changes/gone/change.md", _change("gone"))
    _git(root, "init", "-q")
    _git(root, "add", "docs")
    settings = _settings(root)
    result = _supersede_resolution(root)

    with pytest.raises(ValueError, match="roadmap-invalid: no roadmap entry for gone \\(0 candidates\\)"):
        project_supersede(
            root,
            settings,
            result,
            change_id="gone",
            record_path=root / "docs/archive/gone.md",
            record_relative="docs/archive/gone.md",
            superseded_at="2026-08-03",
            reason="reason",
            planned_roadmap_text=(root / "docs/roadmap.md").read_text(encoding="utf-8"),
        )


def test_change_status_set_stays_closed(tmp_path: Path) -> None:
    assert resolver_module.CHANGE_STATUSES == frozenset(
        {"proposed", "accepted", "in-progress", "blocked", "landed"}
    )


# ---------------------------------------------------------------- shared roadmap-entry locator
#
# accept/begin (`_roadmap_transition_text`), supersede (`_roadmap_supersede_text`), and land
# (`_roadmap_landing_text`) share one entry locator. These tests pin that the three policies
# differ only in what they substitute, never in what they accept or refuse, and that each
# refusal is a distinct, counted, value-free `roadmap-invalid` detail.


def _supersede_rewrite(
    text: str,
    *,
    node_id: str = "example",
    source_status: str = "proposed",
    needle: str = "docs/changes/example/",
    replacement: str = "docs/archive/example.md",
    change_dirs: set[str] | None = None,
) -> str:
    return resolver_module._roadmap_supersede_text(
        text,
        needle=needle,
        replacement=replacement,
        source_status=source_status,
        change_dirs={"docs/changes/example/"} if change_dirs is None else change_dirs,
        node_id=node_id,
    )


def _landing_rewrite(
    text: str,
    *,
    node_id: str = "example",
    source_status: str = "proposed",
    needle: str = "docs/changes/example/",
    replacement: str = "docs/changes/archive/2026-01-01-example/",
    change_dirs: set[str] | None = None,
) -> str:
    return resolver_module._roadmap_landing_text(
        text,
        needle=needle,
        replacement=replacement,
        source_status=source_status,
        change_dirs={"docs/changes/example/"} if change_dirs is None else change_dirs,
        node_id=node_id,
    )


def _assert_all_rewriters_refuse(
    text: str, detail: str, change_dirs: set[str] | None = None
) -> None:
    with pytest.raises(ValueError) as captured:
        _rewrite(text, change_dirs=change_dirs)
    assert str(captured.value) == detail
    with pytest.raises(ValueError) as captured:
        _supersede_rewrite(text, change_dirs=change_dirs)
    assert str(captured.value) == detail
    with pytest.raises(ValueError) as captured:
        _landing_rewrite(text, change_dirs=change_dirs)
    assert str(captured.value) == detail


@pytest.mark.parametrize(
    ("presentation", "expected"),
    [
        ("(proposed)", "(accepted)"),
        ("(PROPOSED)", "(accepted)"),
        ("(Proposed, not accepted)", "(accepted)"),
    ],
)
def test_case_varied_citation_counts_as_a_candidate_for_every_caller(
    presentation: str, expected: str
) -> None:
    line = f"- `docs/changes/EXAMPLE/` {presentation} — promote"
    text = _status_roadmap(line)
    assert f"- `docs/changes/EXAMPLE/` {expected} — promote\n" in _rewrite(text)
    assert "- `docs/archive/example.md` (superseded) — promote" in _supersede_rewrite(text)
    assert (
        "- `docs/changes/archive/2026-01-01-example/` (landed) — promote"
        in _landing_rewrite(text)
    )


def test_all_rewriters_share_the_four_counted_refusals() -> None:
    _assert_all_rewriters_refuse(
        _status_roadmap("- `docs/changes/elsewhere/` (proposed) — elsewhere"),
        "roadmap-invalid: no roadmap entry for example (0 candidates)",
    )

    duplicated = (
        _ROADMAP_HEADER
        + f"{_OWN_LINE_PREFIX} (proposed) — first\n"
        + f"{_OWN_LINE_PREFIX} (proposed) — second\n"
        + _DAG_BLOCK
    )
    _assert_all_rewriters_refuse(
        duplicated,
        "roadmap-invalid: ambiguous roadmap entry for example (2 candidates)",
    )

    cross_ref = f"{_OWN_LINE_PREFIX} and `docs/changes/other/` (proposed) — cross ref"
    _assert_all_rewriters_refuse(
        _status_roadmap(cross_ref),
        "roadmap-invalid: cross-referenced roadmap entry for example "
        "(1 candidate cites another change folder)",
        change_dirs={"docs/changes/example/", "docs/changes/other/"},
    )

    statusless = _status_roadmap(f"{_OWN_LINE_PREFIX} — no status")
    _assert_all_rewriters_refuse(
        statusless,
        "roadmap-invalid: unrewritable roadmap status for example (0 status presentations)",
    )


def test_cross_folder_ambiguity_is_judged_over_the_whole_entry_block() -> None:
    text = (
        _ROADMAP_HEADER
        + f"{_OWN_LINE_PREFIX} (proposed) — rationale\n"
        + "  cites `docs/changes/other/` in its continuation\n"
        + _DAG_BLOCK
    )
    detail = (
        "roadmap-invalid: cross-referenced roadmap entry for example "
        "(1 candidate cites another change folder)"
    )
    with pytest.raises(ValueError) as captured:
        _rewrite(text, change_dirs={"docs/changes/example/", "docs/changes/other/"})
    assert str(captured.value) == detail


def test_accept_and_begin_refuse_a_duplicated_or_cross_referenced_entry() -> None:
    duplicated = (
        _ROADMAP_HEADER
        + f"{_OWN_LINE_PREFIX} (proposed) — first\n"
        + f"{_OWN_LINE_PREFIX} (proposed) — second\n"
        + _DAG_BLOCK
    )
    with pytest.raises(ValueError) as captured:
        _rewrite(duplicated)
    assert str(captured.value) == (
        "roadmap-invalid: ambiguous roadmap entry for example (2 candidates)"
    )

    cross_ref = f"{_OWN_LINE_PREFIX} and `docs/changes/other/` (proposed) — cross ref"
    with pytest.raises(ValueError) as captured:
        _rewrite(
            _status_roadmap(cross_ref),
            change_dirs={"docs/changes/example/", "docs/changes/other/"},
        )
    assert str(captured.value) == (
        "roadmap-invalid: cross-referenced roadmap entry for example "
        "(1 candidate cites another change folder)"
    )


def test_supersede_accepts_an_entry_whose_continuation_cites_the_folder() -> None:
    text = (
        _ROADMAP_HEADER
        + f"{_OWN_LINE_PREFIX} (proposed) — retire the never-accepted\n"
        + "  proposal (see docs/changes/example/ for context)\n"
        + _DAG_BLOCK
    )
    rewritten = _supersede_rewrite(text)
    assert (
        "- `docs/archive/example.md` (superseded) — retire the never-accepted\n"
        "  proposal (see docs/archive/example.md for context)\n"
    ) in rewritten
    assert "docs/changes/example/" not in rewritten


def test_landing_retarget_canonicalizes_case_varied_and_annotated_presentations() -> None:
    for presentation in ("(PROPOSED)", "(proposed, depends on x)", "proposed 2026-08-03"):
        line = f"{_OWN_LINE_PREFIX} {presentation} — rationale"
        rewritten = _landing_rewrite(_status_roadmap(line))
        assert (
            "- `docs/changes/archive/2026-01-01-example/` (landed) — rationale\n"
        ) in rewritten


def test_supersede_retarget_canonicalizes_case_varied_and_annotated_presentations() -> None:
    for presentation in ("(PROPOSED)", "(proposed, depends on x)", "proposed 2026-08-03"):
        line = f"{_OWN_LINE_PREFIX} {presentation} — rationale"
        rewritten = _supersede_rewrite(_status_roadmap(line))
        assert "- `docs/archive/example.md` (superseded) — rationale\n" in rewritten


def test_landing_refuses_a_post_generated_region_only_entry() -> None:
    text = (
        _ROADMAP_HEADER
        + "\n"
        + _DAG_BLOCK
        + f"{_OWN_LINE_PREFIX} (proposed) — only after the generated block\n"
    )
    with pytest.raises(ValueError) as captured:
        _landing_rewrite(text)
    assert str(captured.value) == (
        "roadmap-invalid: roadmap entry for example is after the generated DAG region "
        "(1 candidate after the generated region)"
    )


@pytest.mark.parametrize(
    ("rewriter", "input_line", "expected_line"),
    [
        (
            lambda text: _rewrite(text),
            f"{_OWN_LINE_PREFIX} (proposed)",
            f"{_OWN_LINE_PREFIX} (accepted) — only after the generated block\n",
        ),
        (
            lambda text: _rewrite(
                text,
                node=_status_node(status="accepted"),
                source_status="accepted",
                destination_status="in-progress",
            ),
            f"{_OWN_LINE_PREFIX} (accepted)",
            f"{_OWN_LINE_PREFIX} (in-progress) — only after the generated block\n",
        ),
        (
            lambda text: _supersede_rewrite(text),
            f"{_OWN_LINE_PREFIX} (proposed)",
            "- `docs/archive/example.md` (superseded) — only after the generated block\n",
        ),
    ],
)
def test_accept_begin_and_supersede_still_rewrite_a_post_generated_region_only_entry(
    rewriter, input_line: str, expected_line: str
) -> None:
    text = (
        _ROADMAP_HEADER
        + "\n"
        + _DAG_BLOCK
        + f"{input_line} — only after the generated block\n"
    )
    rewritten = rewriter(text)
    assert "<!-- BEGIN GENERATED DAG" in rewritten
    assert expected_line in rewritten


def test_landing_retarget_preserves_rationale_continuation_and_terminator() -> None:
    dag = _DAG_BLOCK.replace("\n", "\r\n")
    text = (
        "---\r\npersistence: living\r\n---\r\n# Roadmap\r\n\r\n"
        f"{_OWN_LINE_PREFIX} (proposed) — rationale\r\n"
        "  wrapped continuation\r\n"
        "\r\n"
        f"{dag}"
    )
    rewritten = _landing_rewrite(text)
    assert rewritten.count("\r\n") == text.count("\r\n")
    assert "  wrapped continuation\r\n" in rewritten
    assert (
        "- `docs/changes/archive/2026-01-01-example/` (landed) — rationale\r\n"
    ) in rewritten
    assert rewritten[rewritten.index("<!-- BEGIN GENERATED DAG") :] == dag


def test_multi_node_change_folder_warns_and_keeps_the_graph_unchanged(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(
        root,
        "docs/roadmap.md",
        _roadmap("multi")
        + "- `docs/changes/multi/fix-b.md` (proposed) — sibling\n",
    )
    _write(root, "docs/changes/multi/change.md", _change("multi"))
    _write(
        root,
        "docs/changes/multi/fix-b.md",
        "---\nid: fix-b\npersistence: ephemeral\nstatus: proposed\ntrack: test\n---\n# fix-b\n",
    )
    result = resolve(root, _settings(root))
    warnings = [f for f in result.warnings if f.code == "multi-node-change-folder"]
    assert len(warnings) == 1
    assert warnings[0].subjects == ("fix-b", "multi")
    assert "docs/changes/multi/" in warnings[0].message
    assert "2 change nodes" in warnings[0].message
    assert "multi-node-change-folder" not in {f.code for f in result.errors}
    assert set(result.nodes) == {"roadmap", "multi", "fix-b"}
