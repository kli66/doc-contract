"""Transactional landing behavior tests."""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

import pytest

from doc_contract.cli import main
from doc_contract.config import load_settings
from doc_contract.landing import (
    ConcurrentModification,
    InjectedInterruption,
    LandingError,
    LandingPlan,
    execute_landing,
    execute_supersede,
    plan_landing,
    plan_supersede,
)
from doc_contract.lifecycle import LifecycleError
from doc_contract.resolver import (
    Finding,
    fingerprint,
    parse_front_matter,
    resolve,
    stamp_node,
)
from doc_contract.transaction import TransactionError, save_journal


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
        "- `docs/changes/transactional/` (in-progress)\n\n"
        "<!-- BEGIN GENERATED DAG (regenerate: doc-contract update --repo-root .) -->\n"
        "```mermaid\nflowchart TD\n```\n<!-- END GENERATED DAG -->\n",
    )
    _write(
        root,
        "docs/changes/transactional/change.md",
        "---\nid: transactional\npersistence: ephemeral\nstatus: in-progress\ntrack: test\n---\n"
        "# Transactional\n\nStatus: In progress · Started 2026-07-23\n\n## Tasks\n\n"
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


def test_landing_journal_round_trip_retains_diff_and_reads_legacy_shape(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    plan = plan_landing(
        root,
        _settings(root),
        "transactional",
        date="2026-07-23",
        include_untracked=True,
    )

    raw = plan.as_dict()
    assert raw["diff"] == plan.diff
    assert LandingPlan.from_dict(raw).diff == plan.diff

    del raw["diff"]
    assert LandingPlan.from_dict(raw).diff is None


def test_legacy_journal_resume_reports_unavailable_diff(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
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
    journal = next((root / ".git").glob("doc-contract/land-*.json"))
    payload = json.loads(journal.read_text(encoding="utf-8"))
    del payload["diff"]
    journal.write_text(json.dumps(payload), encoding="utf-8")

    assert (
        main(
            [
                "land",
                "transactional",
                "--repo-root",
                str(root),
                "--include-untracked",
                "--diff",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    assert (
        "WARN: [complete-diff-unavailable] complete diff unavailable for legacy journal\n"
        in captured.out
    )
    assert (root / "docs/changes/archive/2026-07-23-transactional/change.md").is_file()


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
    _write(
        root,
        "docs/changes/dependent/change.md",
        "---\nid: dependent\npersistence: ephemeral\nstatus: in-progress\ntrack: test\n"
        "depends_on:\n  - transactional\n---\n"
        "# Dependent\n",
    )
    roadmap = root / "docs/roadmap.md"
    roadmap.write_text(
        roadmap.read_text(encoding="utf-8") + "- `docs/changes/dependent/` (in-progress)\n",
        encoding="utf-8",
    )
    assert _settings(root).edge_fingerprint_policy == "advisory"
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
    with pytest.raises(LandingError, match="partial-tracking") as captured:
        plan_landing(root, _settings(root), "transactional", date="2026-07-23")
    assert captured.value.code == "partial-tracking"
    assert captured.value.findings == ()


def test_plan_landing_wraps_non_landing_transaction_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)

    class PlannerTransactionError(TransactionError):
        pass

    def fail_planner(*_args: object, **_kwargs: object) -> None:
        raise PlannerTransactionError("tracking-state-unavailable: test")

    monkeypatch.setattr("doc_contract.landing._plan_landing", fail_planner)

    with pytest.raises(LandingError) as captured:
        plan_landing(root, _settings(root), "transactional")

    assert str(captured.value) == "tracking-state-unavailable: test"
    assert captured.value.code == "tracking-state-unavailable"


@pytest.mark.parametrize("status", ["proposed", "accepted", "blocked"])
def test_landing_requires_in_progress_status(tmp_path: Path, status: str) -> None:
    root = _repo(tmp_path)
    change = root / "docs/changes/transactional/change.md"
    change.write_text(
        change.read_text(encoding="utf-8").replace("status: in-progress", f"status: {status}"),
        encoding="utf-8",
    )
    roadmap = root / "docs/roadmap.md"
    roadmap.write_text(
        roadmap.read_text(encoding="utf-8").replace("(in-progress)", f"({status})"),
        encoding="utf-8",
    )
    expected = {
        "proposed": "change-proposed-unaccepted",
        "accepted": "change-accepted-not-started",
        "blocked": "change-blocked",
    }[status]
    with pytest.raises(LifecycleError) as captured:
        plan_landing(root, _settings(root), "transactional", date="2026-07-23", include_untracked=True)
    assert captured.value.diagnostic.code == expected


def test_interruption_resumes_at_mutation_boundary(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    with pytest.raises(InjectedInterruption):
        execute_landing(
            root,
            _settings(root),
            "transactional",
            date="2026-07-23",
            include_untracked=True,
            fault_after=3,
        )
    assert (root / "docs/changes/archive/2026-07-23-transactional/change.md").is_file()
    outcome = execute_landing(
        root,
        _settings(root),
        "transactional",
        date="2026-07-23",
        include_untracked=True,
    )
    assert not [finding for finding in outcome.final_findings if finding.level == "ERROR"]
    assert (root / "docs/changes/archive/2026-07-23-transactional/change.md").is_file()


def test_landing_resume_rejects_edit_to_completed_move_boundary(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    with pytest.raises(InjectedInterruption):
        execute_landing(
            root,
            _settings(root),
            "transactional",
            date="2026-07-23",
            include_untracked=True,
            fault_after=3,
        )
    archive = root / "docs/changes/archive/2026-07-23-transactional/change.md"
    archive.write_text(
        archive.read_text(encoding="utf-8") + "\nEdited after journal\n",
        encoding="utf-8",
    )
    with pytest.raises(ConcurrentModification, match="completed boundary"):
        execute_landing(
            root,
            _settings(root),
            "transactional",
            date="2026-07-23",
            include_untracked=True,
        )
    assert list((root / ".git").glob("doc-contract/land-*.json"))


def test_landing_resume_rejects_edit_to_completed_boundary(tmp_path: Path) -> None:
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
    source = root / "docs/changes/transactional/change.md"
    source.write_text(source.read_text(encoding="utf-8") + "\nEdited after journal\n", encoding="utf-8")
    with pytest.raises(ConcurrentModification, match="completed boundary"):
        execute_landing(
            root,
            _settings(root),
            "transactional",
            date="2026-07-23",
            include_untracked=True,
        )
    assert list((root / ".git").glob("doc-contract/land-*.json"))


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


def test_failed_final_validation_matches_check_and_retains_journal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, capability="fail")
    assert main(["check", "--repo-root", str(root), "--include-untracked"]) == 1
    check_output = capsys.readouterr().out
    outcome = execute_landing(
        root,
        _settings(root),
        "transactional",
        date="2026-07-23",
        include_untracked=True,
    )
    failure = next(
        finding
        for finding in outcome.final_findings
        if finding.code == "capability-check-failed"
    )
    assert failure.message in check_output
    assert outcome.capability_status == "live failed"
    assert outcome.verification is not None
    assert list((root / ".git").glob("doc-contract/land-*.json"))


def test_failed_final_offline_validation_retains_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    real_resolve = resolve
    calls = 0

    def fail_final_resolution(*args: object, **kwargs: object):
        nonlocal calls
        calls += 1
        result = real_resolve(*args, **kwargs)
        if calls == 2:
            result.findings.append(
                Finding("ERROR", "final-offline-error", "final offline validation failed")
            )
        return result

    monkeypatch.setattr("doc_contract.lifecycle.resolve", fail_final_resolution)
    monkeypatch.setattr("doc_contract.landing.resolve", fail_final_resolution)
    outcome = execute_landing(
        root,
        _settings(root),
        "transactional",
        date="2026-07-23",
        include_untracked=True,
    )

    assert calls == 2
    assert outcome.verification is not None
    assert outcome.verification.offline_status == "offline failed"
    assert outcome.capability_status == "live skipped"
    assert "final-offline-error" in {finding.code for finding in outcome.final_findings}
    assert list((root / ".git").glob("doc-contract/land-*.json"))


def test_dry_run_and_completed_noop_do_not_execute_live_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, capability="required")
    calls = 0

    def succeed(*_args: object, **_kwargs: object) -> tuple[str, None]:
        nonlocal calls
        calls += 1
        assert not (root / "docs/changes/transactional").exists()
        assert (root / "docs/changes/archive/2026-07-23-transactional").is_dir()
        return "live passed", None

    monkeypatch.setattr("doc_contract.verification._run_capability", succeed)
    dry_run = execute_landing(
        root,
        _settings(root),
        "transactional",
        dry_run=True,
        date="2026-07-23",
        include_untracked=True,
    )
    assert calls == 0
    assert dry_run.capability_status == "not-run"

    landed = execute_landing(
        root,
        _settings(root),
        "transactional",
        date="2026-07-23",
        include_untracked=True,
    )
    assert calls == 1
    assert landed.capability_status == "live passed"
    assert not list((root / ".git").glob("doc-contract/land-*.json"))

    completed = execute_landing(
        root,
        _settings(root),
        "transactional",
        date="2026-07-23",
        include_untracked=True,
    )
    assert completed.already_landed
    assert completed.capability_status == "not-run"
    assert calls == 1


def test_landing_imports_no_private_resolver_symbols() -> None:
    source = Path("src/doc_contract/landing.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    resolver_imports = [
        alias.name
        for node in ast.walk(module)
        if isinstance(node, ast.ImportFrom) and node.module == "resolver"
        for alias in node.names
    ]
    projection_calls = [
        node
        for node in ast.walk(module)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "project_landing"
    ]
    function_names = {
        node.name for node in module.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert resolver_imports
    assert not [name for name in resolver_imports if name.startswith("_")]
    assert len(projection_calls) == 1
    assert "_simulate" not in function_names
    assert "_capability" not in function_names


# --------------------------------------------------------- supersede retirement transaction
#
# A never-accepted proposal is retired by one hash-guarded, resumable, dry-runnable
# transaction: the active folder is removed, the roadmap prose entry is retargeted to the
# frozen lineage record, and the record is created last (staged for tracked plans).

_REASON = "superseded by the successor design review\nacross two review sessions"


def _proposed_fixture(root: Path) -> Path:
    change = root / "docs/changes/transactional/change.md"
    change.write_text(
        change.read_text(encoding="utf-8").replace("status: in-progress", "status: proposed"),
        encoding="utf-8",
    )
    roadmap = root / "docs/roadmap.md"
    roadmap.write_text(
        roadmap.read_text(encoding="utf-8").replace("(in-progress)", "(proposed)"),
        encoding="utf-8",
    )
    return root


def _supersede_repo(tmp_path: Path, *, tracked: bool) -> Path:
    root = _proposed_fixture(_repo(tmp_path))
    if tracked:
        _git(root, "add", "docs/changes/transactional/change.md")
    return root


def _tracked_files(root: Path) -> set[str]:
    output = subprocess.run(
        ["git", "-C", str(root), "ls-files"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return {line for line in output.splitlines() if line}


def test_supersede_dry_run_is_immutable(tmp_path: Path) -> None:
    root = _supersede_repo(tmp_path, tracked=True)
    source = root / "docs/changes/transactional/change.md"
    roadmap = root / "docs/roadmap.md"
    before = (source.read_bytes(), source.stat().st_mtime_ns)
    before_roadmap = (roadmap.read_bytes(), roadmap.stat().st_mtime_ns)

    outcome = execute_supersede(
        root,
        _settings(root),
        "transactional",
        reason=_REASON,
        date="2026-07-23",
        dry_run=True,
    )

    assert outcome.plan is not None
    assert [mutation.kind for mutation in outcome.plan.mutations] == [
        "remove",
        "write",
        "create",
    ]
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before
    assert (roadmap.read_bytes(), roadmap.stat().st_mtime_ns) == before_roadmap
    assert (root / "docs/changes/transactional").is_dir()
    assert not list((root / ".git").glob("doc-contract/supersede-*.json"))


def test_tracked_supersede_applies_record_removal_and_roadmap_retarget(
    tmp_path: Path,
) -> None:
    root = _supersede_repo(tmp_path, tracked=True)
    roadmap = root / "docs/roadmap.md"

    outcome = execute_supersede(
        root,
        _settings(root),
        "transactional",
        reason=_REASON,
        date="2026-07-23",
    )

    assert not [finding for finding in outcome.final_findings if finding.level == "ERROR"]
    assert not outcome.warning_report.introduced
    assert not (root / "docs/changes/transactional").exists()
    record = root / "docs/archive/transactional.md"
    assert record.is_file()
    values = parse_front_matter(record.read_text(encoding="utf-8")) or {}
    assert values["id"] == "transactional"
    assert values["persistence"] == "frozen"
    assert values["status"] == "superseded"
    assert values["superseded_at"] == "2026-07-23"
    assert values["self_hash"] == fingerprint(record.read_text(encoding="utf-8"))
    assert _REASON in record.read_text(encoding="utf-8")
    tracked = _tracked_files(root)
    assert "docs/archive/transactional.md" in tracked
    assert "docs/changes/transactional/change.md" not in tracked
    roadmap_text = roadmap.read_text(encoding="utf-8")
    assert "- `docs/archive/transactional.md` (superseded)" in roadmap_text
    assert "docs/changes/transactional" not in roadmap_text
    assert 'transactional["transactional"]' not in roadmap_text
    assert resolve(root, _settings(root)).nodes["transactional"].kind == "archive"
    assert not list((root / ".git").glob("doc-contract/supersede-*.json"))


def test_superseded_record_stamp_is_idempotent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _supersede_repo(tmp_path, tracked=True)
    execute_supersede(
        root, _settings(root), "transactional", reason=_REASON, date="2026-07-23"
    )
    record = root / "docs/archive/transactional.md"
    before = record.read_bytes()
    assert stamp_node(root, _settings(root), "transactional") is False
    assert record.read_bytes() == before
    assert main(["check", "--repo-root", str(root), "--offline"]) == 0
    assert "untracked-node-excluded" not in capsys.readouterr().out


def test_supersede_interruption_after_removal_fails_closed_then_resumes(
    tmp_path: Path,
) -> None:
    root = _supersede_repo(tmp_path, tracked=True)
    with pytest.raises(InjectedInterruption):
        execute_supersede(
            root,
            _settings(root),
            "transactional",
            reason=_REASON,
            date="2026-07-23",
            fault_after=1,
        )
    assert not (root / "docs/changes/transactional").exists()
    assert not (root / "docs/archive/transactional.md").exists()
    # The mid-state fails closed with a value-free finding, never a traceback.
    midstate = resolve(root, _settings(root))
    assert "roadmap-line-dangling" in {finding.code for finding in midstate.errors}
    outcome = execute_supersede(
        root,
        _settings(root),
        "transactional",
        reason=_REASON,
        date="2026-07-23",
    )
    assert not [finding for finding in outcome.final_findings if finding.level == "ERROR"]
    assert (root / "docs/archive/transactional.md").is_file()
    assert not list((root / ".git").glob("doc-contract/supersede-*.json"))


def test_supersede_interruption_after_roadmap_boundary_is_resolvable(
    tmp_path: Path,
) -> None:
    root = _supersede_repo(tmp_path, tracked=True)
    with pytest.raises(InjectedInterruption):
        execute_supersede(
            root,
            _settings(root),
            "transactional",
            reason=_REASON,
            date="2026-07-23",
            fault_after=2,
        )
    assert not (root / "docs/changes/transactional").exists()
    assert not (root / "docs/archive/transactional.md").exists()
    midstate = resolve(root, _settings(root))
    assert not midstate.errors
    outcome = execute_supersede(
        root,
        _settings(root),
        "transactional",
        reason=_REASON,
        date="2026-07-23",
    )
    assert not [finding for finding in outcome.final_findings if finding.level == "ERROR"]


def test_supersede_resume_rejects_edit_to_completed_remove_boundary(
    tmp_path: Path,
) -> None:
    root = _supersede_repo(tmp_path, tracked=True)
    with pytest.raises(InjectedInterruption):
        execute_supersede(
            root,
            _settings(root),
            "transactional",
            reason=_REASON,
            date="2026-07-23",
            fault_after=1,
        )
    recreated = root / "docs/changes/transactional"
    recreated.mkdir(parents=True)
    (recreated / "change.md").write_text("recreated after removal\n", encoding="utf-8")
    with pytest.raises(ConcurrentModification, match="completed boundary"):
        execute_supersede(
            root,
            _settings(root),
            "transactional",
            reason=_REASON,
            date="2026-07-23",
        )
    assert list((root / ".git").glob("doc-contract/supersede-*.json"))


def test_untracked_supersede_removes_tree_and_leaves_record_untracked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _supersede_repo(tmp_path, tracked=False)
    outcome = execute_supersede(
        root,
        _settings(root),
        "transactional",
        reason=_REASON,
        date="2026-07-23",
        include_untracked=True,
    )
    assert not [finding for finding in outcome.final_findings if finding.level == "ERROR"]
    assert not (root / "docs/changes/transactional").exists()
    record = root / "docs/archive/transactional.md"
    assert record.is_file()
    assert "docs/archive/transactional.md" not in _tracked_files(root)
    # The untracked record keeps the existing --include-untracked rule: excluded with a
    # warning by default, included provisionally with the flag.
    assert main(["check", "--repo-root", str(root), "--offline"]) == 0
    captured = capsys.readouterr()
    assert "untracked-node-excluded" in captured.out
    assert "docs/archive/transactional.md" in captured.out
    assert main(["check", "--repo-root", str(root), "--offline", "--include-untracked"]) == 0


@pytest.mark.parametrize("reason", ["", "   \n\t "])
def test_empty_reason_fails_closed_before_journal_or_mutations(
    tmp_path: Path, reason: str
) -> None:
    root = _supersede_repo(tmp_path, tracked=True)
    source = root / "docs/changes/transactional/change.md"
    before = (source.read_bytes(), source.stat().st_mtime_ns)
    with pytest.raises(LandingError, match="reason-invalid"):
        plan_supersede(
            root, _settings(root), "transactional", reason=reason, date="2026-07-23"
        )
    with pytest.raises(LandingError, match="reason-invalid"):
        execute_supersede(
            root, _settings(root), "transactional", reason=reason, date="2026-07-23"
        )
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before
    assert (root / "docs/changes/transactional").is_dir()
    assert not list((root / ".git").glob("doc-contract/supersede-*.json"))


def test_supersede_remove_rejects_tampered_source_tree(tmp_path: Path) -> None:
    root = _supersede_repo(tmp_path, tracked=True)
    source = root / "docs/changes/transactional/change.md"

    def edit_after_plan(_plan: object) -> None:
        source.write_text("concurrent edit\n", encoding="utf-8")

    with pytest.raises(ConcurrentModification):
        execute_supersede(
            root,
            _settings(root),
            "transactional",
            reason=_REASON,
            date="2026-07-23",
            on_plan=edit_after_plan,
        )
    assert source.read_text(encoding="utf-8") == "concurrent edit\n"


def test_supersede_refuses_while_a_dependent_still_references_the_change(
    tmp_path: Path,
) -> None:
    root = _supersede_repo(tmp_path, tracked=False)
    _write(
        root,
        "docs/changes/dependent/change.md",
        "---\nid: dependent\npersistence: ephemeral\nstatus: proposed\ntrack: test\n"
        "depends_on:\n  - transactional\n---\n# Dependent\n",
    )
    roadmap = root / "docs/roadmap.md"
    roadmap.write_text(
        roadmap.read_text(encoding="utf-8").replace(
            "<!-- BEGIN GENERATED DAG",
            "- `docs/changes/dependent/` (proposed)\n\n<!-- BEGIN GENERATED DAG",
        ),
        encoding="utf-8",
    )
    dependent_before = (root / "docs/changes/dependent/change.md").read_bytes()

    with pytest.raises(LandingError) as captured:
        plan_supersede(
            root,
            _settings(root),
            "transactional",
            reason=_REASON,
            date="2026-07-23",
            include_untracked=True,
        )

    assert captured.value.code == "preflight-invalid"
    assert "unknown-dependency" in {finding.code for finding in captured.value.findings}
    assert (root / "docs/changes/transactional").is_dir()
    assert (root / "docs/changes/dependent/change.md").read_bytes() == dependent_before
    assert not list((root / ".git").glob("doc-contract/supersede-*.json"))


def test_supersede_retargets_wrapped_roadmap_entry_preserving_other_bytes(
    tmp_path: Path,
) -> None:
    root = _supersede_repo(tmp_path, tracked=True)
    roadmap = root / "docs/roadmap.md"
    roadmap.write_text(
        "---\npersistence: living\n---\n# Roadmap\n\n"
        "- `docs/changes/transactional/` (proposed) — retire the never-accepted\n"
        "  proposal after the successor design review\n\n"
        "<!-- BEGIN GENERATED DAG (regenerate: doc-contract update --repo-root .) -->\n"
        "```mermaid\nflowchart TD\n```\n<!-- END GENERATED DAG -->\n",
        encoding="utf-8",
    )
    execute_supersede(
        root, _settings(root), "transactional", reason=_REASON, date="2026-07-23"
    )
    text = roadmap.read_text(encoding="utf-8")
    assert (
        "- `docs/archive/transactional.md` (superseded) — retire the never-accepted\n"
        "  proposal after the successor design review\n"
    ) in text


def test_supersede_with_a_statusless_roadmap_entry_fails_closed(
    tmp_path: Path,
) -> None:
    root = _supersede_repo(tmp_path, tracked=True)
    roadmap = root / "docs/roadmap.md"
    roadmap.write_text(
        "---\npersistence: living\n---\n# Roadmap\n\n"
        "- `docs/changes/transactional/` — retire the never-accepted proposal\n\n"
        "<!-- BEGIN GENERATED DAG (regenerate: doc-contract update --repo-root .) -->\n"
        "```mermaid\nflowchart TD\n```\n<!-- END GENERATED DAG -->\n",
        encoding="utf-8",
    )
    before = roadmap.read_bytes()
    with pytest.raises(LandingError, match="roadmap-invalid"):
        plan_supersede(
            root, _settings(root), "transactional", reason=_REASON, date="2026-07-23"
        )
    assert roadmap.read_bytes() == before
    assert (root / "docs/changes/transactional").is_dir()
    assert not list((root / ".git").glob("doc-contract/supersede-*.json"))


def test_completed_supersede_rerun_reports_change_ref_unknown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _supersede_repo(tmp_path, tracked=True)
    assert (
        main(
            [
                "supersede",
                "transactional",
                "--reason",
                _REASON,
                "--repo-root",
                str(root),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(["supersede", "transactional", "--reason", _REASON, "--repo-root", str(root)])
        == 1
    )
    captured = capsys.readouterr()
    assert captured.err.startswith("ERROR: [change-ref-unknown]")
    assert "Traceback" not in captured.err


def test_supersede_remove_resumes_across_applied_but_not_journaled_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _supersede_repo(tmp_path, tracked=True)

    def crash_before_boundary_journal(path: Path, plan: object, completed: list[int]) -> None:
        # Simulate a crash in the window after `git rm -r` returns but before the removal
        # boundary is journaled: persist the empty journal once, then die before recording
        # the applied removal. The working tree is gone, the journal still says nothing ran.
        if completed:
            raise InjectedInterruption("injected-interruption")
        save_journal(path, plan, completed)

    monkeypatch.setattr("doc_contract.landing._save_journal", crash_before_boundary_journal)
    with pytest.raises(InjectedInterruption):
        execute_supersede(
            root,
            _settings(root),
            "transactional",
            reason=_REASON,
            date="2026-07-23",
        )
    monkeypatch.undo()

    assert not (root / "docs/changes/transactional").exists()
    journal = next((root / ".git").glob("doc-contract/supersede-*.json"))
    assert json.loads(journal.read_text(encoding="utf-8"))["completed"] == []

    # Resuming must treat the absent source as this transaction's own completed removal,
    # not as a concurrent edit, and drive the remaining mutations to completion.
    outcome = execute_supersede(
        root,
        _settings(root),
        "transactional",
        reason=_REASON,
        date="2026-07-23",
    )
    assert not [finding for finding in outcome.final_findings if finding.level == "ERROR"]
    assert (root / "docs/archive/transactional.md").is_file()
    assert not list((root / ".git").glob("doc-contract/supersede-*.json"))


def test_supersede_remove_absent_but_index_tracked_fails_closed(tmp_path: Path) -> None:
    root = _supersede_repo(tmp_path, tracked=True)
    source = root / "docs/changes/transactional"

    def delete_working_tree_but_keep_index(_plan: object) -> None:
        (source / "change.md").unlink()
        source.rmdir()

    with pytest.raises(ConcurrentModification, match="missing source"):
        execute_supersede(
            root,
            _settings(root),
            "transactional",
            reason=_REASON,
            date="2026-07-23",
            on_plan=delete_working_tree_but_keep_index,
        )

    assert not source.exists()
    assert "docs/changes/transactional/change.md" in _tracked_files(root)
    journals = list((root / ".git").glob("doc-contract/supersede-*.json"))
    assert journals and json.loads(journals[0].read_text(encoding="utf-8"))["completed"] == []
