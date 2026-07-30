"""Read-only mechanical reconciliation reports."""

from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

import doc_contract.reconciliation as reconciliation_runtime
from doc_contract.landing import plan_landing
from doc_contract.lifecycle import TransitionAction, plan_transition
from doc_contract.reconciliation import reconcile_mechanical
from doc_contract.resolver import Finding, parse_front_matter
from test_landing import _repo, _settings, _write


def _replace_status(root: Path, status: str) -> None:
    change = root / "docs/changes/transactional/change.md"
    text = change.read_text(encoding="utf-8")
    text = re.sub(r"^status: \S+$", f"status: {status}", text, count=1, flags=re.MULTILINE)
    change.write_text(text, encoding="utf-8")
    roadmap = root / "docs/roadmap.md"
    roadmap.write_text(
        re.sub(
            r"\((?:proposed|accepted|in-progress|blocked|landed)\)",
            f"({status})",
            roadmap.read_text(encoding="utf-8"),
            count=1,
        ),
        encoding="utf-8",
    )


def _snapshot(root: Path) -> tuple[dict[str, tuple[bytes, int]], bytes, tuple[str, ...]]:
    files = {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }
    index = subprocess.run(
        ["git", "-C", str(root), "show", ":docs/roadmap.md"],
        check=True,
        capture_output=True,
    ).stdout
    journals = tuple(
        path.relative_to(root / ".git").as_posix()
        for path in sorted((root / ".git").rglob("doc-contract/*.json"))
    )
    return files, index, journals


def test_entry_report_matches_begin_plan_and_is_byte_stable(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _replace_status(root, "accepted")
    before = _snapshot(root)

    report = reconcile_mechanical(
        root,
        _settings(root),
        "transactional",
        phase="entry",
        include_untracked=True,
    )
    plan = plan_transition(
        root,
        _settings(root),
        "transactional",
        action=TransitionAction.BEGIN,
        include_untracked=True,
    )

    assert report.ready
    assert report.change_id == plan.change_id
    assert report.change_status == plan.source_status
    assert report.manifest.tracking == plan.tracking
    assert report.manifest.source_status == plan.source_status
    assert report.manifest.destination_status == plan.destination_status
    assert report.as_dict()["manifest"] == {
        "tracking": plan.tracking,
        "archive_target": None,
        "source_status": plan.source_status,
        "destination_status": plan.destination_status,
        "provisional_nodes": [
            {"id": node_id, "path": path} for node_id, path in plan.provisional_nodes
        ],
        "mutations": [item.as_dict() for item in report.manifest.mutations],
    }
    assert f"transition: {plan.source_status} -> {plan.destination_status}" in report.render_text()
    assert [item.path for item in report.manifest.mutations] == [
        item.path for item in plan.mutations
    ]
    first = json.dumps(report.as_dict(), sort_keys=True)
    second = json.dumps(
        reconcile_mechanical(
            root,
            _settings(root),
            "transactional",
            phase="entry",
            include_untracked=True,
        ).as_dict(),
        sort_keys=True,
    )
    assert first == second
    assert _snapshot(root) == before


def test_exit_report_matches_landing_plan_without_diff_or_content(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    private_body = "PRIVATE-BODY-MARKER"
    change = root / "docs/changes/transactional/change.md"
    change.write_text(change.read_text(encoding="utf-8") + private_body, encoding="utf-8")
    before = _snapshot(root)

    report = reconcile_mechanical(
        root,
        _settings(root),
        "transactional",
        phase="exit",
        include_untracked=True,
    )
    plan = plan_landing(
        root,
        _settings(root),
        "transactional",
        include_untracked=True,
    )
    rendered = json.dumps(report.as_dict(), sort_keys=True)

    assert report.ready
    assert report.manifest.tracking == plan.tracking
    assert report.manifest.archive_target == plan.archive
    assert [item.path for item in report.manifest.mutations] == [
        item.path for item in plan.mutations
    ]
    assert private_body not in rendered
    assert "@@" not in rendered
    assert _snapshot(root) == before


@pytest.mark.parametrize(
    ("phase", "status", "next_verb"),
    [
        ("entry", "proposed", "accept"),
        ("entry", "in-progress", None),
        ("exit", "accepted", "begin"),
        ("exit", "landed", None),
    ],
)
def test_ineligible_states_are_actionable_without_planning(
    phase: str,
    status: str,
    next_verb: str | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(tmp_path)
    _replace_status(root, status)
    monkeypatch.setattr(
        reconciliation_runtime,
        "plan_transition",
        lambda *_args, **_kwargs: pytest.fail("entry planner called"),
    )
    monkeypatch.setattr(
        reconciliation_runtime,
        "plan_landing",
        lambda *_args, **_kwargs: pytest.fail("exit planner called"),
    )

    report = reconcile_mechanical(
        root,
        _settings(root),
        "transactional",
        phase=phase,  # type: ignore[arg-type]
        include_untracked=True,
    )

    assert not report.ready
    if next_verb is None:
        assert report.next_command is None
    else:
        assert report.next_command is not None
        assert report.next_command.startswith(f"doc-contract {next_verb} ")


@pytest.mark.parametrize("with_gate", [False, True])
def test_blocked_report_exposes_only_gate_presence(
    with_gate: bool, tmp_path: Path
) -> None:
    root = _repo(tmp_path)
    _replace_status(root, "blocked")
    change = root / "docs/changes/transactional/change.md"
    private_gate = "PRIVATE-GATE-MARKER"
    text = change.read_text(encoding="utf-8")
    if with_gate:
        text = text.replace("track: test\n", f"track: test\ngated_on: {private_gate}\n")
    text += f"\nBody prose {private_gate}\n"
    change.write_text(text, encoding="utf-8")

    report = reconcile_mechanical(
        root,
        _settings(root),
        "transactional",
        phase="entry",
        include_untracked=True,
    )
    rendered = json.dumps(report.as_dict(), sort_keys=True) + report.render_text()

    assert report.gate_present is with_gate
    assert report.next_command is None
    assert private_gate not in rendered


def test_planners_are_each_called_exactly_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _repo(tmp_path)
    real_landing = reconciliation_runtime.plan_landing
    landing_calls = 0

    def counted_landing(*args: object, **kwargs: object):
        nonlocal landing_calls
        landing_calls += 1
        return real_landing(*args, **kwargs)

    monkeypatch.setattr(reconciliation_runtime, "plan_landing", counted_landing)
    reconcile_mechanical(
        root,
        _settings(root),
        "transactional",
        phase="exit",
        include_untracked=True,
    )
    assert landing_calls == 1

    _replace_status(root, "accepted")
    real_transition = reconciliation_runtime.plan_transition
    transition_calls = 0

    def counted_transition(*args: object, **kwargs: object):
        nonlocal transition_calls
        transition_calls += 1
        return real_transition(*args, **kwargs)

    monkeypatch.setattr(reconciliation_runtime, "plan_transition", counted_transition)
    reconcile_mechanical(
        root,
        _settings(root),
        "transactional",
        phase="entry",
        include_untracked=True,
    )
    assert transition_calls == 1


def test_missing_owned_path_warns_at_entry_and_blocks_exit(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    change = root / "docs/changes/transactional/change.md"
    text = change.read_text(encoding="utf-8").replace(
        "track: test\n", "track: test\nfiles_owned:\n  - src/future.py\n"
    )
    change.write_text(text, encoding="utf-8")
    _replace_status(root, "accepted")

    entry = reconcile_mechanical(
        root,
        _settings(root),
        "transactional",
        phase="entry",
        include_untracked=True,
    )
    _replace_status(root, "in-progress")
    exit_report = reconcile_mechanical(
        root,
        _settings(root),
        "transactional",
        phase="exit",
        include_untracked=True,
    )

    assert entry.ready
    assert any(
        finding.code == "owned-file-missing" and finding.level == "WARN"
        for finding in entry.findings
    )
    assert not exit_report.ready
    assert any(
        finding.code == "owned-file-missing" and finding.level == "ERROR"
        for finding in exit_report.findings
    )


def test_exit_missing_owned_path_blocks_alongside_landing_failure(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    change = root / "docs/changes/transactional/change.md"
    change.write_text(
        change.read_text(encoding="utf-8").replace(
            "track: test\n", "track: test\nfiles_owned:\n  - src/missing.py\n"
        ),
        encoding="utf-8",
    )
    _write(
        root,
        f"docs/changes/archive/{dt.date.today():%Y-%m-%d}-transactional/change.md",
        "occupied\n",
    )

    report = reconcile_mechanical(
        root,
        _settings(root),
        "transactional",
        phase="exit",
        include_untracked=True,
    )

    assert not report.ready
    findings = {finding.code: finding for finding in report.findings}
    assert findings["owned-file-missing"].level == "ERROR"
    assert findings["destination-collision"].level == "ERROR"


def test_excluded_untracked_change_retains_identity_and_rerun_instruction(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    report = reconcile_mechanical(
        root, _settings(root), "transactional", phase="exit", include_untracked=False
    )
    payload = report.as_dict()
    text = report.render_text()

    assert report.change_id == "transactional"
    assert report.change_path == "docs/changes/transactional"
    assert payload["change"] == {
        "id": "transactional",
        "path": "docs/changes/transactional",
        "status": None,
    }
    assert "transactional (docs/changes/transactional)" in text
    assert "[change-untracked-excluded]" in text
    assert report.next_command == (
        "doc-contract reconcile mechanical transactional --phase exit --include-untracked"
    )


def test_dependency_failure_blocks_reconciliation(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    change = root / "docs/changes/transactional/change.md"
    change.write_text(
        change.read_text(encoding="utf-8").replace(
            "track: test\n", "track: test\ndepends_on:\n  - missing\n"
        ),
        encoding="utf-8",
    )

    report = reconcile_mechanical(
        root,
        _settings(root),
        "transactional",
        phase="exit",
        include_untracked=True,
    )

    assert not report.ready
    assert "unknown-dependency" in {finding.code for finding in report.findings}


@pytest.mark.parametrize(
    ("policy", "expected_level", "ready"),
    [("advisory", "WARN", True), ("required", "ERROR", False)],
)
def test_fingerprint_policy_is_preserved_in_reconciliation(
    policy: str, expected_level: str, ready: bool, tmp_path: Path
) -> None:
    root = _repo(tmp_path)
    _write(
        root,
        "docs/changes/target/change.md",
        "---\nid: target\npersistence: ephemeral\nstatus: landed\ntrack: test\n---\n# Target\n",
    )
    change = root / "docs/changes/transactional/change.md"
    change.write_text(
        change.read_text(encoding="utf-8").replace(
            "track: test\n",
            "track: test\ndepends_on:\n  - target\nfingerprints:\n  target: PENDING\n",
        ),
        encoding="utf-8",
    )
    settings = replace(_settings(root), edge_fingerprint_policy=policy)

    report = reconcile_mechanical(
        root, settings, "transactional", phase="exit", include_untracked=True
    )

    assert report.ready is ready
    finding = next(
        item for item in report.findings if item.code == "edge-hash-pending"
    )
    assert finding.level == expected_level


def test_roadmap_mismatch_blocks_reconciliation(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    roadmap = root / "docs/roadmap.md"
    roadmap.write_text(
        roadmap.read_text(encoding="utf-8").replace("(in-progress)", "(accepted)"),
        encoding="utf-8",
    )

    report = reconcile_mechanical(
        root,
        _settings(root),
        "transactional",
        phase="exit",
        include_untracked=True,
    )

    assert not report.ready
    assert "roadmap-status-mismatch" in {finding.code for finding in report.findings}


@pytest.mark.parametrize("phase", ["entry", "exit"])
def test_projected_ownership_overlap_blocks_mechanical_readiness(
    phase: str, tmp_path: Path
) -> None:
    root = _repo(tmp_path)
    _write(root, "src/shared.py", "shared = True\n")
    change = root / "docs/changes/transactional/change.md"
    change.write_text(
        change.read_text(encoding="utf-8").replace(
            "track: test\n", "track: test\nfiles_owned:\n  - src/shared.py\n"
        ),
        encoding="utf-8",
    )
    _write(
        root,
        "docs/changes/competing/change.md",
        "---\nid: competing\npersistence: ephemeral\nstatus: in-progress\ntrack: test\n"
        "files_owned:\n  - src/shared.py\n---\n# Competing\n",
    )
    roadmap = root / "docs/roadmap.md"
    roadmap.write_text(
        roadmap.read_text(encoding="utf-8")
        + "- `docs/changes/competing/` (in-progress)\n",
        encoding="utf-8",
    )
    if phase == "entry":
        _replace_status(root, "accepted")

    report = reconcile_mechanical(
        root,
        _settings(root),
        "transactional",
        phase=phase,  # type: ignore[arg-type]
        include_untracked=True,
    )

    assert not report.ready
    finding = next(item for item in report.findings if item.code == "ownership-overlap")
    assert finding.level == "ERROR"
    assert finding.scope == "change"


def test_repository_global_blocker_is_not_compacted_or_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    real_resolve = reconciliation_runtime.resolve

    def resolve_with_global(*args: object, **kwargs: object):
        result = real_resolve(*args, **kwargs)
        result.findings.append(
            Finding("ERROR", "repository-global", "repository-wide blocker")
        )
        return result

    monkeypatch.setattr(reconciliation_runtime, "resolve", resolve_with_global)
    report = reconcile_mechanical(
        root,
        _settings(root),
        "transactional",
        phase="exit",
        include_untracked=True,
    )

    assert not report.ready
    finding = next(item for item in report.findings if item.code == "repository-global")
    assert finding.scope == "repository"


def test_archive_collision_and_partial_tracking_are_typed_blockers(tmp_path: Path) -> None:
    collision_root = _repo(tmp_path / "collision")
    day = dt.date.today().isoformat()
    _write(
        collision_root,
        f"docs/changes/archive/{day}-transactional/change.md",
        "occupied\n",
    )
    collision = reconcile_mechanical(
        collision_root,
        _settings(collision_root),
        "transactional",
        phase="exit",
        include_untracked=True,
    )
    assert not collision.ready
    assert "destination-collision" in {finding.code for finding in collision.findings}

    partial_root = _repo(tmp_path / "partial")
    _write(partial_root, "docs/changes/transactional/notes.md", "notes\n")
    subprocess.run(
        [
            "git",
            "-C",
            str(partial_root),
            "add",
            "docs/changes/transactional/change.md",
        ],
        check=True,
    )
    partial = reconcile_mechanical(
        partial_root,
        _settings(partial_root),
        "transactional",
        phase="exit",
        include_untracked=True,
    )
    assert not partial.ready
    assert "partial-tracking" in {finding.code for finding in partial.findings}


def test_unrelated_warning_is_compacted_in_text_but_retained_in_json(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(
        root,
        "docs/changes/unrelated/change.md",
        "---\nid: unrelated\npersistence: ephemeral\nstatus: proposed\ntrack: test\n"
        "files_owned:\n  - src/unrelated.py\n---\n# Unrelated\n",
    )
    roadmap = root / "docs/roadmap.md"
    roadmap.write_text(
        roadmap.read_text(encoding="utf-8")
        + "\n- `docs/changes/unrelated/` (proposed)\n",
        encoding="utf-8",
    )

    report = reconcile_mechanical(
        root,
        _settings(root),
        "transactional",
        phase="exit",
        include_untracked=True,
    )
    text = report.render_text()
    payload = json.dumps(report.as_dict(), sort_keys=True)

    assert "repository warnings: " in text
    assert "src/unrelated.py" not in text
    assert "src/unrelated.py" in payload


def test_report_never_runs_configured_capability(tmp_path: Path) -> None:
    root = _repo(tmp_path, capability="required")
    marker = root / "capability-ran"
    config = root / ".doc-contract.toml"
    command = f"open({str(marker)!r}, 'w').write('ran')"
    config.write_text(
        re.sub(
            r"command = .*",
            f'command = ["python", "-c", {json.dumps(command)}]',
            config.read_text(encoding="utf-8"),
        ),
        encoding="utf-8",
    )

    report = reconcile_mechanical(
        root,
        _settings(root),
        "transactional",
        phase="exit",
        include_untracked=True,
    )

    assert report.ready
    assert not marker.exists()
    rendered = json.dumps(report.as_dict(), sort_keys=True)
    assert str(marker) not in rendered
    assert "python" not in rendered


def test_blocked_metadata_is_detected_without_body_scraping(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _replace_status(root, "blocked")
    change = root / "docs/changes/transactional/change.md"
    values = parse_front_matter(change.read_text(encoding="utf-8"))
    assert values is not None and "gated_on" not in values
    report = reconcile_mechanical(
        root,
        _settings(root),
        "transactional",
        phase="exit",
        include_untracked=True,
    )
    assert report.gate_present is False
