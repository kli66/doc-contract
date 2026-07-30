"""Explicit acceptance and work-start lifecycle transitions."""

from __future__ import annotations

from pathlib import Path

import pytest

from doc_contract.cli import main
from doc_contract.lifecycle import (
    ConcurrentModification,
    InjectedInterruption,
    LifecycleError,
    LifecycleRequest,
    TransitionAction,
    classify_change,
    execute_transition,
    plan_transition,
)
from doc_contract.resolver import parse_front_matter, resolve
from test_landing import _repo, _settings


def _proposed(root: Path) -> None:
    source = root / "docs/changes/transactional/change.md"
    source.write_text(source.read_text(encoding="utf-8").replace("status: in-progress", "status: proposed"), encoding="utf-8")
    roadmap = root / "docs/roadmap.md"
    roadmap.write_text(roadmap.read_text(encoding="utf-8").replace("(in-progress)", "(proposed)"), encoding="utf-8")


def _status(root: Path, status: str, *, gate: str | None = None) -> None:
    source = root / "docs/changes/transactional/change.md"
    text = source.read_text(encoding="utf-8").replace(
        "status: in-progress", f"status: {status}"
    )
    if gate is not None:
        text = text.replace("track: test\n", f"track: test\ngated_on: {gate}\n")
    source.write_text(text, encoding="utf-8")
    roadmap = root / "docs/roadmap.md"
    roadmap.write_text(
        roadmap.read_text(encoding="utf-8").replace(
            "(in-progress)", f"({status})"
        ),
        encoding="utf-8",
    )


def _archive(root: Path) -> Path:
    source = root / "docs/changes/transactional"
    archive = root / "docs/changes/archive/2026-07-30-transactional"
    archive.parent.mkdir(parents=True, exist_ok=True)
    text = (source / "change.md").read_text(encoding="utf-8")
    text = text.replace("status: in-progress", "status: landed")
    text = text.replace(
        "track: test\n",
        "track: test\narchive_path: docs/changes/archive/2026-07-30-transactional\n",
    )
    (source / "change.md").write_text(text, encoding="utf-8")
    source.rename(archive)
    return archive


def test_lifecycle_classifier_stable_taxonomy_and_safe_messages(tmp_path: Path) -> None:
    cases: list[
        tuple[str, LifecycleRequest, bool, str, str, str | None]
    ] = []

    proposed = _repo(tmp_path / "proposed")
    _status(proposed, "proposed")
    cases.append(
        (
            str(proposed),
            LifecycleRequest.LAND,
            True,
            "change-proposed-unaccepted",
            "change transactional has status=proposed and is not accepted",
            "doc-contract accept transactional --dry-run",
        )
    )
    accepted = _repo(tmp_path / "accepted")
    _status(accepted, "accepted")
    cases.append(
        (
            str(accepted),
            LifecycleRequest.LAND,
            True,
            "change-accepted-not-started",
            "change transactional has status=accepted and has not started",
            "doc-contract begin transactional --dry-run",
        )
    )
    blocked = _repo(tmp_path / "blocked")
    _status(blocked, "blocked", gate="private-gate-text")
    cases.append(
        (
            str(blocked),
            LifecycleRequest.LAND,
            True,
            "change-blocked",
            "change transactional has status=blocked; gate_present=true",
            None,
        )
    )
    untracked = _repo(tmp_path / "untracked")
    cases.append(
        (
            str(untracked),
            LifecycleRequest.LAND,
            False,
            "change-untracked-excluded",
            "change transactional is untracked and excluded",
            "doc-contract land transactional --dry-run --include-untracked",
        )
    )
    missing = _repo(tmp_path / "missing")
    (missing / "docs/changes/transactional/change.md").write_text(
        "raw-private-body\n", encoding="utf-8"
    )
    cases.append(
        (
            str(missing),
            LifecycleRequest.LAND,
            True,
            "change-front-matter-missing",
            "change folder docs/changes/transactional has no node-bearing Markdown front matter",
            None,
        )
    )
    invalid = _repo(tmp_path / "invalid")
    (invalid / "docs/changes/transactional/change.md").write_text(
        "---\nid: transactional\nraw-private-parser-line\n---\nprivate body\n",
        encoding="utf-8",
    )
    cases.append(
        (
            str(invalid),
            LifecycleRequest.LAND,
            True,
            "change-front-matter-invalid",
            "change folder docs/changes/transactional has invalid or ambiguous front matter",
            None,
        )
    )
    wrong = _repo(tmp_path / "wrong")
    cases.append(
        (
            str(wrong),
            LifecycleRequest.LAND,
            True,
            "change-ref-wrong-folder",
            "change reference is not an exact active or archive change folder",
            None,
        )
    )
    unknown = _repo(tmp_path / "unknown")
    cases.append(
        (
            str(unknown),
            LifecycleRequest.LAND,
            True,
            "change-ref-unknown",
            "change reference is unknown",
            None,
        )
    )

    for root_text, request, include_untracked, code, message, hint in cases:
        root = Path(root_text)
        reference = (
            "docs/spec/private-raw-reference"
            if code == "change-ref-wrong-folder"
            else "unknown-private-reference"
            if code == "change-ref-unknown"
            else "transactional"
        )
        with pytest.raises(LifecycleError) as captured:
            classify_change(
                root,
                _settings(root),
                reference,
                action=request,
                include_untracked=include_untracked,
            )
        assert captured.value.diagnostic.code == code
        assert captured.value.diagnostic.message == message
        assert captured.value.diagnostic.next_command == hint
        rendered = f"{message}\n{hint or ''}"
        assert "private" not in rendered
        assert "parser" not in rendered

    landed = _repo(tmp_path / "landed")
    archive = _archive(landed)
    selection = classify_change(
        landed,
        _settings(landed),
        "transactional",
        action=LifecycleRequest.LAND,
        include_untracked=True,
    )
    assert selection.path == archive.relative_to(landed).as_posix()
    assert selection.diagnostic is not None
    assert selection.diagnostic.code == "change-already-landed"
    assert selection.diagnostic.message == "change transactional has status=landed"
    assert selection.diagnostic.next_command is None
    by_path = classify_change(
        landed,
        _settings(landed),
        archive.relative_to(landed).as_posix(),
        action=LifecycleRequest.LAND,
        include_untracked=True,
    )
    assert by_path == selection


def test_id_and_repository_relative_path_classify_equivalently(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _status(root, "accepted")
    by_id = classify_change(
        root,
        _settings(root),
        "transactional",
        action=LifecycleRequest.BEGIN,
        include_untracked=True,
    )
    by_path = classify_change(
        root,
        _settings(root),
        "docs/changes/transactional",
        action=LifecycleRequest.BEGIN,
        include_untracked=True,
    )
    assert by_path == by_id


def test_lifecycle_classification_precedence(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    change = root / "docs/changes/transactional/change.md"
    change.write_text(
        "---\nid: transactional\nmalformed-private-line\n---\nprivate body\n",
        encoding="utf-8",
    )

    with pytest.raises(LifecycleError) as wrong:
        classify_change(
            root,
            _settings(root),
            "docs/changes/transactional/nested",
            action=LifecycleRequest.LAND,
            include_untracked=False,
        )
    assert wrong.value.diagnostic.code == "change-ref-wrong-folder"
    with pytest.raises(LifecycleError) as traversal:
        classify_change(
            root,
            _settings(root),
            "../private-raw-reference",
            action=LifecycleRequest.LAND,
            include_untracked=False,
        )
    assert traversal.value.diagnostic.code == "change-ref-wrong-folder"

    with pytest.raises(LifecycleError) as excluded:
        classify_change(
            root,
            _settings(root),
            "transactional",
            action=LifecycleRequest.LAND,
            include_untracked=False,
        )
    assert excluded.value.diagnostic.code == "change-untracked-excluded"

    with pytest.raises(LifecycleError) as invalid:
        classify_change(
            root,
            _settings(root),
            "transactional",
            action=LifecycleRequest.LAND,
            include_untracked=True,
        )
    assert invalid.value.diagnostic.code == "change-front-matter-invalid"

    _status_root = _repo(tmp_path / "status")
    archive = _archive(_status_root)
    active = _status_root / "docs/changes/transactional"
    active.mkdir(parents=True)
    (active / "change.md").write_text(
        "---\nid: transactional\npersistence: ephemeral\nstatus: proposed\ntrack: test\n---\n",
        encoding="utf-8",
    )
    with pytest.raises(LifecycleError) as proposed:
        classify_change(
            _status_root,
            _settings(_status_root),
            "transactional",
            action=LifecycleRequest.LAND,
            include_untracked=True,
        )
    assert proposed.value.diagnostic.code == "change-proposed-unaccepted"
    active.rename(_status_root / "active-stashed")

    landed = classify_change(
        _status_root,
        _settings(_status_root),
        "transactional",
        action=LifecycleRequest.LAND,
        include_untracked=True,
    )
    assert landed.diagnostic is not None
    assert landed.diagnostic.code == "change-already-landed"
    archive.rename(_status_root / "archive-stashed")

    with pytest.raises(LifecycleError) as unknown:
        classify_change(
            _status_root,
            _settings(_status_root),
            "transactional",
            action=LifecycleRequest.LAND,
            include_untracked=True,
        )
    assert unknown.value.diagnostic.code == "change-ref-unknown"


def test_accept_projects_and_applies_status_roadmap_and_dates(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _proposed(root)
    source = root / "docs/changes/transactional/change.md"
    roadmap = root / "docs/roadmap.md"
    before_source = source.read_bytes()
    before_roadmap = roadmap.read_bytes()
    plan = plan_transition(root, _settings(root), "transactional", action=TransitionAction.ACCEPT, include_untracked=True, date="2026-07-29")
    assert plan.source_status == "proposed"
    assert plan.destination_status == "accepted"
    assert plan.diff
    dry_run = execute_transition(root, _settings(root), "transactional", action="accept", include_untracked=True, date="2026-07-29", dry_run=True)
    assert dry_run.plan is not None
    assert source.read_bytes() == before_source
    assert roadmap.read_bytes() == before_roadmap
    assert not list((root / ".git").glob("doc-contract/lifecycle-*.json"))
    outcome = execute_transition(root, _settings(root), "transactional", action="accept", include_untracked=True, date="2026-07-29")
    values = parse_front_matter(source.read_text(encoding="utf-8")) or {}
    assert values["status"] == "accepted"
    assert values["accepted_at"] == "2026-07-29"
    assert "Status: Accepted · Accepted 2026-07-29" in source.read_text(encoding="utf-8")
    assert "docs/changes/transactional/` (accepted)" in roadmap.read_text(encoding="utf-8")
    assert not [finding for finding in outcome.final_findings if finding.level == "ERROR"]
    assert not list((root / ".git").glob("doc-contract/lifecycle-*.json"))


def test_begin_requires_accepted_and_is_idempotent(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _proposed(root)
    with pytest.raises(LifecycleError) as captured:
        plan_transition(root, _settings(root), "transactional", action="begin", include_untracked=True)
    assert captured.value.diagnostic.code == "change-proposed-unaccepted"
    assert main(["accept", "transactional", "--repo-root", str(root), "--include-untracked"]) == 0
    outcome = execute_transition(root, _settings(root), "transactional", action=TransitionAction.BEGIN, include_untracked=True, date="2026-07-29")
    assert outcome.plan is not None
    assert outcome.plan.destination_status == "in-progress"
    values = parse_front_matter((root / "docs/changes/transactional/change.md").read_text(encoding="utf-8")) or {}
    assert values["status"] == "in-progress"
    assert values["started_at"] == "2026-07-29"
    again = execute_transition(root, _settings(root), "transactional", action="begin", include_untracked=True, date="2026-07-30")
    assert again.already_applied
    assert values["started_at"] == "2026-07-29"


def test_blocked_changes_are_not_reclassified(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    source = root / "docs/changes/transactional/change.md"
    source.write_text(source.read_text(encoding="utf-8").replace("status: in-progress", "status: blocked"), encoding="utf-8")
    roadmap = root / "docs/roadmap.md"
    roadmap.write_text(roadmap.read_text(encoding="utf-8").replace("(in-progress)", "(blocked)"), encoding="utf-8")
    before = source.read_bytes()
    with pytest.raises(LifecycleError) as captured:
        execute_transition(root, _settings(root), "transactional", action="accept", include_untracked=True)
    assert captured.value.diagnostic.code == "change-blocked"
    assert source.read_bytes() == before
    assert resolve(root, _settings(root), include_untracked=True).nodes["transactional"].status == "blocked"


def test_interrupted_accept_resumes_from_lifecycle_journal(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _proposed(root)
    with pytest.raises(InjectedInterruption):
        execute_transition(
            root,
            _settings(root),
            "transactional",
            action="accept",
            include_untracked=True,
            date="2026-07-29",
            fault_after=1,
        )
    journal = list((root / ".git").glob("doc-contract/lifecycle-accept-*.json"))
    assert journal
    outcome = execute_transition(
        root,
        _settings(root),
        "transactional",
        action="accept",
        include_untracked=True,
        date="2026-07-29",
    )
    assert not [finding for finding in outcome.final_findings if finding.level == "ERROR"]
    assert not journal[0].exists()


def test_lifecycle_resume_rejects_edit_to_completed_boundary(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _proposed(root)
    with pytest.raises(InjectedInterruption):
        execute_transition(
            root,
            _settings(root),
            "transactional",
            action="accept",
            include_untracked=True,
            date="2026-07-29",
            fault_after=1,
        )
    source = root / "docs/changes/transactional/change.md"
    source.write_text(source.read_text(encoding="utf-8") + "\nEdited after journal\n", encoding="utf-8")
    with pytest.raises(ConcurrentModification, match="completed boundary"):
        execute_transition(
            root,
            _settings(root),
            "transactional",
            action="accept",
            include_untracked=True,
            date="2026-07-29",
        )
    assert list((root / ".git").glob("doc-contract/lifecycle-accept-*.json"))
