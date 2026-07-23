"""Transactional landing behavior tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from doc_contract.config import load_settings
from doc_contract.landing import (
    ConcurrentModification,
    InjectedInterruption,
    LandingError,
    execute_landing,
    plan_landing,
)
from doc_contract.resolver import fingerprint


def _write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _repo(tmp_path: Path, *, capability: str | None = None) -> Path:
    root = tmp_path / "repo"
    _write(
        root,
        ".doc-contract.toml",
        "schema_version = 1\nrepo_name = 'fixture'\nroadmap = 'docs/roadmap.md'\n"
        "optional_roots = []\n\n[root_nodes]\nroadmap = 'docs/roadmap.md'\n\n"
        "[capability]\nmode = 'skip'\n"
        if capability is None
        else "schema_version = 1\nrepo_name = 'fixture'\nroadmap = 'docs/roadmap.md'\n"
        "optional_roots = []\n\n[root_nodes]\nroadmap = 'docs/roadmap.md'\n\n"
        "[capability]\nmode = 'required'\ncommand = ['python', '-c', 'raise SystemExit(1)']\n",
    )
    _write(
        root,
        "docs/roadmap.md",
        "---\npersistence: living\n---\n# Roadmap\n\n"
        "- `docs/changes/transactional/` (proposed)\n\n"
        "<!-- BEGIN GENERATED DAG (regenerate: doc-contract update --repo-root .) -->\n"
        "```mermaid\nflowchart TD\n```\n<!-- END GENERATED DAG -->\n",
    )
    _write(
        root,
        "docs/changes/transactional/change.md",
        "---\nid: transactional\npersistence: ephemeral\nstatus: proposed\ntrack: test\n---\n"
        "# Transactional\n\nStatus: Proposed (not accepted) · Proposed 2026-07-23\n\n## Tasks\n\n"
        "1. Implement it\n",
    )
    _git(root, "init", "-q")
    _git(root, "add", ".doc-contract.toml", "docs/roadmap.md")
    return root


def _settings(root: Path):
    return load_settings(root)


def test_dry_run_is_immutable_and_printable(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    source = root / "docs/changes/transactional"
    roadmap = root / "docs/roadmap.md"
    before_source = (source / "change.md").read_bytes()
    before_roadmap = roadmap.read_bytes()

    outcome = execute_landing(
        root,
        _settings(root),
        "transactional",
        dry_run=True,
        date="2026-07-23",
        include_untracked=True,
    )

    assert outcome.plan is not None
    assert outcome.plan.diff
    assert (source / "change.md").read_bytes() == before_source
    assert roadmap.read_bytes() == before_roadmap
    assert source.is_dir()
    assert not list((root / ".git").glob("doc-contract/land-*.json"))


def test_journal_failure_happens_before_first_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    source = root / "docs/changes/transactional/change.md"
    roadmap = root / "docs/roadmap.md"
    before_source = source.read_bytes()
    before_roadmap = roadmap.read_bytes()

    def fail_journal(*_args, **_kwargs) -> None:
        raise LandingError("journal-unavailable: test")

    monkeypatch.setattr("doc_contract.landing._save_journal", fail_journal)
    with pytest.raises(LandingError, match="journal-unavailable"):
        execute_landing(
            root,
            _settings(root),
            "transactional",
            date="2026-07-23",
            include_untracked=True,
        )

    assert source.read_bytes() == before_source
    assert roadmap.read_bytes() == before_roadmap


def test_untracked_landing_recovers_and_second_run_is_noop(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    outcome = execute_landing(
        root,
        _settings(root),
        "transactional",
        date="2026-07-23",
        include_untracked=True,
    )
    archive = root / "docs/changes/archive/2026-07-23-transactional"

    assert not [finding for finding in outcome.final_findings if finding.level == "ERROR"]
    assert not outcome.warning_report.introduced
    assert archive.is_dir()
    assert not (root / "docs/changes/transactional").exists()
    assert not list((root / ".git").glob("doc-contract/land-*.json"))
    before = (archive / "change.md").stat().st_mtime_ns
    second = execute_landing(
        root,
        _settings(root),
        "transactional",
        date="2026-07-23",
        include_untracked=True,
    )
    assert second.already_landed
    assert (archive / "change.md").stat().st_mtime_ns == before


def test_active_dependents_receive_the_landed_target_fingerprint(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    target = root / "docs/changes/transactional/change.md"
    target_hash = fingerprint(target.read_text(encoding="utf-8"))
    _write(
        root,
        "docs/changes/dependent/change.md",
        "---\nid: dependent\npersistence: ephemeral\nstatus: in-progress\ntrack: test\n"
        f"depends_on:\n  - transactional\nfingerprints:\n  transactional: {target_hash}\n---\n"
        "# Dependent\n",
    )
    roadmap = root / "docs/roadmap.md"
    roadmap.write_text(
        roadmap.read_text(encoding="utf-8") + "- `docs/changes/dependent/` (in-progress)\n",
        encoding="utf-8",
    )
    outcome = execute_landing(
        root,
        _settings(root),
        "transactional",
        date="2026-07-23",
        include_untracked=True,
    )
    assert not [finding for finding in outcome.final_findings if finding.level == "ERROR"]
    dependent = root / "docs/changes/dependent/change.md"
    assert fingerprint((root / "docs/changes/archive/2026-07-23-transactional/change.md").read_text(encoding="utf-8")) in dependent.read_text(encoding="utf-8")


def test_fully_tracked_landing_uses_git_move(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _git(root, "add", "docs/changes/transactional/change.md")
    execute_landing(root, _settings(root), "transactional", date="2026-07-23")
    tracked = subprocess.run(
        ["git", "-C", str(root), "ls-files"], check=True, capture_output=True, text=True
    ).stdout
    assert "docs/changes/archive/2026-07-23-transactional/change.md" in tracked
    assert "docs/changes/transactional/change.md" not in tracked


def test_partial_tracking_is_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "docs/changes/transactional/notes.md", "notes\n")
    _git(root, "add", "docs/changes/transactional/change.md")
    with pytest.raises(LandingError, match="partial-tracking"):
        plan_landing(root, _settings(root), "transactional", date="2026-07-23")


def test_interruption_resumes_at_mutation_boundary(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    with pytest.raises(InjectedInterruption):
        execute_landing(
            root,
            _settings(root),
            "transactional",
            date="2026-07-23",
            include_untracked=True,
            fault_after=1,
        )
    assert (root / "docs/changes/transactional/change.md").is_file()
    outcome = execute_landing(
        root,
        _settings(root),
        "transactional",
        date="2026-07-23",
        include_untracked=True,
    )
    assert not [finding for finding in outcome.final_findings if finding.level == "ERROR"]
    assert (root / "docs/changes/archive/2026-07-23-transactional/change.md").is_file()


def test_concurrent_change_fails_without_overwrite(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    source = root / "docs/changes/transactional/change.md"

    def edit_after_plan(_plan) -> None:
        source.write_text("concurrent edit\n", encoding="utf-8")

    with pytest.raises(ConcurrentModification):
        execute_landing(
            root,
            _settings(root),
            "transactional",
            date="2026-07-23",
            include_untracked=True,
            on_plan=edit_after_plan,
        )
    assert source.read_text(encoding="utf-8") == "concurrent edit\n"


def test_destination_collision_is_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "docs/changes/archive/2026-07-23-transactional/change.md", "occupied\n")
    with pytest.raises(LandingError, match="destination-collision"):
        plan_landing(
            root,
            _settings(root),
            "transactional",
            date="2026-07-23",
            include_untracked=True,
        )


def test_failed_final_validation_retains_journal(tmp_path: Path) -> None:
    root = _repo(tmp_path, capability="fail")
    outcome = execute_landing(
        root,
        _settings(root),
        "transactional",
        date="2026-07-23",
        include_untracked=True,
    )
    assert any(finding.code == "capability-check-failed" for finding in outcome.final_findings)
    assert list((root / ".git").glob("doc-contract/land-*.json"))
