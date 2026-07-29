"""Explicit acceptance and work-start lifecycle transitions."""

from __future__ import annotations

from pathlib import Path

import pytest

from doc_contract.cli import main
from doc_contract.lifecycle import (
    ConcurrentModification,
    InjectedInterruption,
    LifecycleError,
    TransitionAction,
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
    with pytest.raises(LifecycleError, match="requires accepted"):
        plan_transition(root, _settings(root), "transactional", action="begin", include_untracked=True)
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
    with pytest.raises(LifecycleError, match="blocked change"):
        execute_transition(root, _settings(root), "transactional", action="accept", include_untracked=True)
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
