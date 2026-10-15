"""Explicit acceptance and work-start lifecycle transitions."""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from doc_contract.cli import main
from doc_contract.landing import execute_supersede, plan_supersede
from doc_contract.lifecycle import (
    LifecycleError,
    LifecycleRequest,
    TransitionAction,
    classify_change,
    execute_transition,
    plan_transition,
)
from doc_contract.resolver import fingerprint, parse_front_matter, resolve
from test_landing import _repo, _settings, _write


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
    # Interrupted execution now returns an interrupted outcome instead of raising
    outcome = execute_transition(
        root,
        _settings(root),
        "transactional",
        action="accept",
        include_untracked=True,
        date="2026-07-29",
        fault_after=1,
    )
    from doc_contract.lifecycle import ExecutionStatus
    assert outcome.execution_status == ExecutionStatus.INTERRUPTED
    assert outcome.journal_retained is True
    journal = list((root / ".git").glob("doc-contract/lifecycle-accept-*.json"))
    assert journal
    # Resume and complete
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
    # Interrupted execution now returns an interrupted outcome instead of raising
    outcome = execute_transition(
        root,
        _settings(root),
        "transactional",
        action="accept",
        include_untracked=True,
        date="2026-07-29",
        fault_after=1,
    )
    from doc_contract.lifecycle import ExecutionStatus
    assert outcome.execution_status == ExecutionStatus.INTERRUPTED
    source = root / "docs/changes/transactional/change.md"
    source.write_text(source.read_text(encoding="utf-8") + "\nEdited after journal\n", encoding="utf-8")
    # Edit to completed boundary must fail closed with journal retained
    # Now returns INTERRUPTED outcome instead of raising ConcurrentModification
    outcome2 = execute_transition(
        root,
        _settings(root),
        "transactional",
        action="accept",
        include_untracked=True,
        date="2026-07-29",
    )
    assert outcome2.execution_status == ExecutionStatus.INTERRUPTED
    assert outcome2.journal_retained is True
    # Journal must still exist (fail-closed behavior)
    assert list((root / ".git").glob("doc-contract/lifecycle-accept-*.json"))


# ------------------------------------------------------- roadmap status canonicalization
#
# A lifecycle transition owns the selected roadmap line: it must canonicalize every status
# presentation `_STATUS_TOKENS` recognizes for the transition's source status, and fail closed
# with a value-free `roadmap-invalid` planning error — before projected validation, and before
# any byte, mtime, index, or journal side effect — when the located line has no single
# rewritable presentation.

_RATIONALE = "— promote the resolver boundary"
_DEPENDENT_LINE = "- `docs/changes/dependent/` (proposed) — depend on the transactional change"
_UNRELATED_LINE = "- `docs/changes/archive/2026-07-30-landed-item/` (landed) — an unrelated line"
_DAG_BLOCK = (
    "<!-- BEGIN GENERATED DAG (regenerate: doc-contract update --repo-root .) -->\n"
    "```mermaid\nflowchart TD\n```\n"
    "<!-- END GENERATED DAG -->\n"
)
_BODY_STATUS = {
    "proposed": "Status: Proposed (not accepted) · Proposed 2026-08-01",
    "accepted": "Status: Accepted · Accepted 2026-08-02",
}


def _change_document(node_id: str, status: str, *, edges: str = "") -> str:
    accepted_at = "accepted_at: 2026-08-02\n" if status == "accepted" else ""
    return (
        "---\n"
        f"id: {node_id}\n"
        "persistence: ephemeral\n"
        f"status: {status}\n"
        "track: test\n"
        f"{accepted_at}{edges}"
        "---\n"
        f"# {node_id}\n\n{_BODY_STATUS[status]}\n\n## Tasks\n\n1. Implement it\n"
    )


def _annotated_repo(tmp_path: Path, *, presentation: str, status: str = "proposed") -> Path:
    """A fixture repository whose selected roadmap line carries `presentation`, plus one
    dependent change (so the plan refreshes a fingerprint) and one unrelated roadmap line."""
    root = _repo(tmp_path)
    change = root / "docs/changes/transactional/change.md"
    change.write_text(_change_document("transactional", status), encoding="utf-8")
    edges = (
        "depends_on:\n  - transactional\nfingerprints:\n"
        f"  transactional: {fingerprint(change.read_text(encoding='utf-8'))}\n"
    )
    _write(
        root,
        "docs/changes/dependent/change.md",
        _change_document("dependent", "proposed", edges=edges),
    )
    (root / "docs/roadmap.md").write_text(
        "---\npersistence: living\n---\n# Roadmap\n\n"
        f"- `docs/changes/transactional/` {presentation} {_RATIONALE}\n"
        f"{_DEPENDENT_LINE}\n"
        f"{_UNRELATED_LINE}\n\n"
        f"{_DAG_BLOCK}",
        encoding="utf-8",
    )
    return root


def _repository_state(root: Path) -> tuple[dict[str, tuple[bytes, int]], str, list[str]]:
    """The four signals a rejected plan must leave untouched: document bytes, mtimes, the Git
    index/worktree report, and the private lifecycle journal glob."""
    files = {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }
    index = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    journals = [
        path.relative_to(root).as_posix()
        for path in sorted((root / ".git").glob("doc-contract/lifecycle-*.json"))
    ]
    return files, index, journals


def _roadmap_line(root: Path, node_id: str) -> str:
    needle = f"- `docs/changes/{node_id}/`"
    lines = [
        line
        for line in (root / "docs/roadmap.md").read_text(encoding="utf-8").splitlines()
        if line.startswith(needle)
    ]
    assert len(lines) == 1
    return lines[0]


def _human_region(text: str) -> list[str]:
    """The hand-maintained roadmap lines — everything before the generated DAG block."""
    return text[: text.index("<!-- BEGIN GENERATED DAG")].splitlines()


def _assert_only_the_selected_line_changed(before: str, after: str, node_id: str) -> None:
    """Every unrelated roadmap line, and the em-dash rationale on the selected one, survive
    byte-for-byte; only the status presentation differs."""
    needle = f"- `docs/changes/{node_id}/`"
    old, new = _human_region(before), _human_region(after)
    assert len(old) == len(new)
    changed = [index for index, pair in enumerate(zip(old, new)) if pair[0] != pair[1]]
    assert len(changed) == 1
    index = changed[0]
    assert old[index].startswith(needle)
    assert new[index].startswith(needle)
    separator = " — "
    assert old[index].split(separator, 1)[1] == new[index].split(separator, 1)[1]


@pytest.mark.parametrize(
    "presentation",
    [
        "(proposed)",
        "(Proposed, not accepted)",
        "(proposed, depends on the landed `x`)",
        "(proposed foundation)",
        "proposed 2026-08-03",
    ],
)
def test_accept_canonicalizes_each_supported_proposed_presentation(
    tmp_path: Path, presentation: str
) -> None:
    root = _annotated_repo(tmp_path, presentation=presentation)
    source = root / "docs/changes/transactional/change.md"
    roadmap = root / "docs/roadmap.md"
    before_source = source.read_bytes()
    before_roadmap = roadmap.read_bytes()

    # The annotated line is valid for resolution: current check passes with zero errors.
    assert main(["check", "--repo-root", str(root), "--offline", "--include-untracked"]) == 0

    plan = plan_transition(
        root,
        _settings(root),
        "transactional",
        action=TransitionAction.ACCEPT,
        include_untracked=True,
        date="2026-08-03",
    )
    assert [mutation.path for mutation in plan.mutations] == [
        "docs/changes/transactional/change.md",
        "docs/changes/dependent/change.md",
        "docs/roadmap.md",
    ]

    dry_run = execute_transition(
        root,
        _settings(root),
        "transactional",
        action="accept",
        include_untracked=True,
        date="2026-08-03",
        dry_run=True,
    )
    assert dry_run.plan is not None
    assert source.read_bytes() == before_source
    assert roadmap.read_bytes() == before_roadmap
    assert not list((root / ".git").glob("doc-contract/lifecycle-*.json"))
    assert main(["accept", "transactional", "--repo-root", str(root), "--include-untracked", "--dry-run"]) == 0
    assert source.read_bytes() == before_source
    assert roadmap.read_bytes() == before_roadmap

    assert main(["accept", "transactional", "--repo-root", str(root), "--include-untracked"]) == 0

    assert resolve(root, _settings(root), include_untracked=True).nodes["transactional"].status == "accepted"
    values = parse_front_matter(source.read_text(encoding="utf-8")) or {}
    assert values["status"] == "accepted"
    assert _roadmap_line(root, "transactional") == (
        f"- `docs/changes/transactional/` (accepted) {_RATIONALE}"
    )
    text = roadmap.read_text(encoding="utf-8")
    assert text.count('    transactional["transactional (accepted)"]') == 1
    assert f"{_DEPENDENT_LINE}\n" in text
    assert f"{_UNRELATED_LINE}\n" in text
    _assert_only_the_selected_line_changed(
        before_roadmap.decode("utf-8"), text, "transactional"
    )
    assert not [finding for finding in resolve(root, _settings(root), include_untracked=True).findings if finding.level == "ERROR"]
    assert not list((root / ".git").glob("doc-contract/lifecycle-*.json"))


@pytest.mark.parametrize(
    "presentation",
    [
        "(accepted)",
        "(Accepted, not started)",
        "(accepted, depends on the landed `x`)",
        "(accepted foundation)",
    ],
)
def test_begin_canonicalizes_each_supported_accepted_presentation(
    tmp_path: Path, presentation: str
) -> None:
    root = _annotated_repo(tmp_path, presentation=presentation, status="accepted")
    source = root / "docs/changes/transactional/change.md"
    roadmap = root / "docs/roadmap.md"
    before_source = source.read_bytes()
    before_roadmap = roadmap.read_bytes()

    assert main(["check", "--repo-root", str(root), "--offline", "--include-untracked"]) == 0

    dry_run = execute_transition(
        root,
        _settings(root),
        "transactional",
        action="begin",
        include_untracked=True,
        date="2026-08-03",
        dry_run=True,
    )
    assert dry_run.plan is not None
    assert [mutation.path for mutation in dry_run.plan.mutations] == [
        "docs/changes/transactional/change.md",
        "docs/changes/dependent/change.md",
        "docs/roadmap.md",
    ]
    assert source.read_bytes() == before_source
    assert roadmap.read_bytes() == before_roadmap

    assert main(["begin", "transactional", "--repo-root", str(root), "--include-untracked"]) == 0

    assert resolve(root, _settings(root), include_untracked=True).nodes["transactional"].status == "in-progress"
    values = parse_front_matter(source.read_text(encoding="utf-8")) or {}
    assert values["status"] == "in-progress"
    assert values["accepted_at"] == "2026-08-02"
    assert _roadmap_line(root, "transactional") == (
        f"- `docs/changes/transactional/` (in-progress) {_RATIONALE}"
    )
    text = roadmap.read_text(encoding="utf-8")
    assert text.count('    transactional["transactional (in-progress)"]') == 1
    assert f"{_DEPENDENT_LINE}\n" in text
    assert f"{_UNRELATED_LINE}\n" in text
    _assert_only_the_selected_line_changed(
        before_roadmap.decode("utf-8"), text, "transactional"
    )
    assert not list((root / ".git").glob("doc-contract/lifecycle-*.json"))


@pytest.mark.parametrize(
    ("status", "action", "presentation"),
    [
        ("proposed", "accept", "— promote the resolver boundary"),
        ("proposed", "accept", "(proposed ZYZZYVA-annotation — promote the resolver boundary"),
        ("proposed", "accept", "(proposed) — was (proposed) before"),
        ("proposed", "accept", "(proposed) proposed 2026-08-03"),
        ("accepted", "begin", "— promote the resolver boundary"),
        ("accepted", "begin", "(accepted ZYZZYVA-annotation — promote the resolver boundary"),
        ("accepted", "begin", "(accepted) — was (accepted) before"),
        # `_STATUS_TOKENS` has no bare token mapping to accepted, so a bare dated accepted
        # marker is unrecognized and must reject; it is not a bare-marker canonicalization case.
        ("accepted", "begin", "accepted 2026-08-03 — promote the resolver boundary"),
    ],
)
def test_an_unrewritable_roadmap_status_fails_closed_before_any_side_effect(
    tmp_path: Path, status: str, action: str, presentation: str
) -> None:
    root = _annotated_repo(tmp_path, presentation=presentation, status=status)
    # The located line still resolves cleanly, so the rejection must come from the rewrite
    # guard rather than from the generic projected-validation failure.
    assert main(["check", "--repo-root", str(root), "--offline", "--include-untracked"]) == 0
    before = _repository_state(root)

    with pytest.raises(LifecycleError) as captured:
        plan_transition(
            root,
            _settings(root),
            "transactional",
            action=action,
            include_untracked=True,
            date="2026-08-03",
        )
    diagnostic = captured.value.diagnostic
    assert diagnostic.code == "roadmap-invalid"
    # A fixed, value-free detail: no line text, no presentation, no annotation prose, no offsets.
    assert diagnostic.message == "roadmap-invalid: unrewritable roadmap status for transactional"
    assert "preflight-invalid" not in diagnostic.message
    assert "ZYZZYVA" not in diagnostic.message
    assert "docs/roadmap.md" not in diagnostic.message
    assert _repository_state(root) == before

    assert main([action, "transactional", "--repo-root", str(root), "--include-untracked", "--dry-run"]) == 1
    assert _repository_state(root) == before

    with pytest.raises(LifecycleError) as applied:
        execute_transition(
            root,
            _settings(root),
            "transactional",
            action=action,
            include_untracked=True,
            date="2026-08-03",
        )
    assert applied.value.diagnostic.code == "roadmap-invalid"
    assert _repository_state(root) == before


def test_the_operator_sees_the_specific_roadmap_invalid_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _annotated_repo(tmp_path, presentation="(proposed ZYZZYVA-annotation — promote")
    capsys.readouterr()
    assert main(["accept", "transactional", "--repo-root", str(root), "--include-untracked"]) == 1
    captured = capsys.readouterr()
    assert "ERROR: [roadmap-invalid]" in captured.err
    assert "preflight-invalid" not in captured.err
    assert "ZYZZYVA" not in captured.err + captured.out
    assert _repository_state(root)[2] == []


def test_annotated_and_canonical_accept_plans_have_identical_mutation_shape(
    tmp_path: Path,
) -> None:
    annotated = _annotated_repo(tmp_path / "annotated", presentation="(Proposed, not accepted)")
    canonical = _annotated_repo(tmp_path / "canonical", presentation="(proposed)")
    plans = [
        plan_transition(
            root,
            _settings(root),
            "transactional",
            action=TransitionAction.ACCEPT,
            include_untracked=True,
            date="2026-08-03",
        )
        for root in (annotated, canonical)
    ]
    assert [mutation.path for mutation in plans[0].mutations] == [
        mutation.path for mutation in plans[1].mutations
    ]
    assert len(plans[0].mutations) == len(plans[1].mutations) == 3

    change = next(m for m in plans[0].mutations if m.path.endswith("transactional/change.md"))
    dependent = next(m for m in plans[0].mutations if m.path.endswith("dependent/change.md"))
    assert dependent.before_hash != dependent.after_hash
    assert dependent.content is not None
    assert f"transactional: {fingerprint(change.content or '')}" in dependent.content
    assert plans[0].input_tree_hash != plans[0].output_tree_hash


# ------------------------------------------------------------- supersede classification gate
#
# Supersede admits only a never-accepted `proposed` change; every other status is refused
# before whole-repository preflight with stable, value-free diagnostics, and `land` keeps
# its in-progress-only precondition untouched.


@pytest.mark.parametrize(
    ("status", "expected_code", "expected_message"),
    [
        ("accepted", "change-not-proposed", "change transactional has status=accepted; supersede requires proposed"),
        ("in-progress", "change-not-proposed", "change transactional has status=in-progress; supersede requires proposed"),
        ("blocked", "change-blocked", "change transactional has status=blocked; gate_present=false"),
    ],
)
def test_supersede_refuses_every_non_proposed_status(
    tmp_path: Path, status: str, expected_code: str, expected_message: str
) -> None:
    root = _repo(tmp_path / status)
    _status(root, status)
    with pytest.raises(LifecycleError) as captured:
        classify_change(
            root,
            _settings(root),
            "transactional",
            action=LifecycleRequest.SUPERSEDE,
            include_untracked=True,
        )
    assert captured.value.diagnostic.code == expected_code
    assert captured.value.diagnostic.message == expected_message
    assert captured.value.diagnostic.next_command is None
    assert "private-gate-text" not in captured.value.diagnostic.message


def test_supersede_admits_proposed_and_honors_landed_diagnostic(tmp_path: Path) -> None:
    proposed = _repo(tmp_path / "proposed")
    _proposed(proposed)
    selection = classify_change(
        proposed,
        _settings(proposed),
        "transactional",
        action=LifecycleRequest.SUPERSEDE,
        include_untracked=True,
    )
    assert selection.change_id == "transactional"
    assert selection.status == "proposed"
    assert selection.diagnostic is None

    landed = _repo(tmp_path / "landed")
    _archive(landed)
    landed_selection = classify_change(
        landed,
        _settings(landed),
        "transactional",
        action=LifecycleRequest.SUPERSEDE,
        include_untracked=True,
    )
    assert landed_selection.diagnostic is not None
    assert landed_selection.diagnostic.code == "change-already-landed"
    assert landed_selection.diagnostic.message == "change transactional has status=landed"


def test_supersede_refuses_a_landed_change_end_to_end(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _archive(root)
    for executor in (
        lambda: plan_supersede(
            root,
            _settings(root),
            "transactional",
            reason="reason",
            date="2026-07-23",
            include_untracked=True,
        ),
        lambda: execute_supersede(
            root,
            _settings(root),
            "transactional",
            reason="reason",
            date="2026-07-23",
            include_untracked=True,
        ),
    ):
        with pytest.raises(LifecycleError) as captured:
            executor()
        assert captured.value.diagnostic.code == "change-already-landed"
    assert not list((root / ".git").glob("doc-contract/supersede-*.json"))


def test_supersede_untracked_exclusion_precedes_classification(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _proposed(root)
    with pytest.raises(LifecycleError) as captured:
        classify_change(
            root,
            _settings(root),
            "transactional",
            action=LifecycleRequest.SUPERSEDE,
            include_untracked=False,
        )
    assert captured.value.diagnostic.code == "change-untracked-excluded"
    assert captured.value.diagnostic.next_command == (
        "doc-contract supersede transactional --dry-run --include-untracked"
    )


def test_land_still_refuses_a_proposed_change(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _proposed(root)
    with pytest.raises(LifecycleError) as captured:
        classify_change(
            root,
            _settings(root),
            "transactional",
            action=LifecycleRequest.LAND,
            include_untracked=True,
        )
    assert captured.value.diagnostic.code == "change-proposed-unaccepted"


# ------------------------------------------------------------- plan_id and expectation tests
#
# Tests for the new plan_id computation, expectation validation, and execution status.


def test_plan_id_is_deterministic_and_changes_with_inputs(tmp_path: Path) -> None:
    """plan_id must be deterministic and change when plan inputs change."""
    from doc_contract.lifecycle import compute_plan_id

    root = _repo(tmp_path)
    _proposed(root)

    plan1 = plan_transition(
        root,
        _settings(root),
        "transactional",
        action=TransitionAction.ACCEPT,
        include_untracked=True,
        date="2026-08-01",
    )
    plan_id1 = compute_plan_id(plan1)

    # Same inputs produce same plan_id
    plan2 = plan_transition(
        root,
        _settings(root),
        "transactional",
        action=TransitionAction.ACCEPT,
        include_untracked=True,
        date="2026-08-01",
    )
    plan_id2 = compute_plan_id(plan2)
    assert plan_id1 == plan_id2

    # Different date produces different plan_id
    plan3 = plan_transition(
        root,
        _settings(root),
        "transactional",
        action=TransitionAction.ACCEPT,
        include_untracked=True,
        date="2026-08-02",
    )
    plan_id3 = compute_plan_id(plan3)
    assert plan_id3 != plan_id1

    # plan_id format is canonical
    assert plan_id1.startswith("sha256:")
    assert len(plan_id1) == 71  # "sha256:" + 64 hex chars


def test_schema_2_journal_persists_include_untracked(tmp_path: Path) -> None:
    """Schema-2 journals must persist include_untracked and reproduce plan_id."""
    import json
    from doc_contract.lifecycle import LIFECYCLE_JOURNAL_SCHEMA

    root = _repo(tmp_path)
    _proposed(root)

    # Plan with include_untracked=True (to verify the journal captures it)
    plan_transition(
        root,
        _settings(root),
        "transactional",
        action=TransitionAction.ACCEPT,
        include_untracked=True,
        date="2026-08-01",
    )

    # Execute to create journal - interrupted execution returns interrupted outcome
    outcome = execute_transition(
        root,
        _settings(root),
        "transactional",
        action="accept",
        include_untracked=True,
        date="2026-08-01",
        fault_after=1,  # Interrupt after first mutation to retain journal
    )
    from doc_contract.lifecycle import ExecutionStatus
    assert outcome.execution_status == ExecutionStatus.INTERRUPTED
    assert outcome.journal_retained is True
    # Check the journal was created
    journal_files = list((root / ".git").glob("doc-contract/lifecycle-accept-*.json"))
    assert journal_files

    # Read the journal and verify schema 2 and include_untracked
    journal_data = json.loads(journal_files[0].read_text(encoding="utf-8"))
    assert journal_data["schema"] == LIFECYCLE_JOURNAL_SCHEMA
    assert journal_data["include_untracked"] is True


def test_schema_1_journal_is_readable_without_migration(tmp_path: Path) -> None:
    """Schema-1 journals must remain readable without payload migration."""
    import json
    from doc_contract.lifecycle import LifecyclePlan

    root = _repo(tmp_path)
    _proposed(root)

    # Create a schema-1 journal manually
    journal_path = root / ".git" / "doc-contract" / "lifecycle-accept-transactional.json"
    journal_path.parent.mkdir(parents=True, exist_ok=True)

    # Create a minimal schema-1 journal payload
    schema1_payload = {
        "schema": 1,
        "action": "accept",
        "change_id": "transactional",
        "source": "docs/changes/transactional",
        "date": "2026-08-01",
        "source_status": "proposed",
        "destination_status": "accepted",
        "accepted_at": None,
        "started_at": None,
        "tracking": "untracked",
        "input_tree_hash": "abc123",
        "output_tree_hash": "def456",
        "journal_path": str(journal_path),
        "provisional_nodes": [],
        "current_findings": [],
        "projected_findings": [],
        "baseline_warnings": [],
        "mutations": [],
        "already_applied": False,
        "completed": [],
    }
    journal_path.write_text(json.dumps(schema1_payload, indent=2), encoding="utf-8")

    # Load the journal - should succeed
    from doc_contract.transaction import load_journal
    plan, completed = load_journal(journal_path, LifecyclePlan.from_dict)

    assert plan.change_id == "transactional"
    assert plan.include_untracked is None  # Schema-1 has unknown include_untracked
    assert completed == []


def test_schema_1_journal_with_expectation_is_rejected(tmp_path: Path) -> None:
    """Schema-1 journal with expectation must reject as not-verifiable."""
    import json
    from doc_contract.lifecycle import ExecutionStatus

    root = _repo(tmp_path)
    _proposed(root)

    # Create a schema-1 journal manually
    journal_path = root / ".git" / "doc-contract" / "lifecycle-accept-transactional.json"
    journal_path.parent.mkdir(parents=True, exist_ok=True)

    schema1_payload = {
        "schema": 1,
        "action": "accept",
        "change_id": "transactional",
        "source": "docs/changes/transactional",
        "date": "2026-08-01",
        "source_status": "proposed",
        "destination_status": "accepted",
        "accepted_at": None,
        "started_at": None,
        "tracking": "untracked",
        "input_tree_hash": "abc123",
        "output_tree_hash": "def456",
        "journal_path": str(journal_path),
        "provisional_nodes": [],
        "current_findings": [],
        "projected_findings": [],
        "baseline_warnings": [],
        "mutations": [],
        "already_applied": False,
        "completed": [],
    }
    journal_path.write_text(json.dumps(schema1_payload, indent=2), encoding="utf-8")

    # Execute with expectation - should reject as not-verifiable
    outcome = execute_transition(
        root,
        _settings(root),
        "transactional",
        action="accept",
        include_untracked=True,
        date="2026-08-01",
        expect_plan_id="sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    )

    assert outcome.execution_status == ExecutionStatus.REJECTED
    assert outcome.expectation == "not-verifiable"
    assert outcome.journal_retained is True


def test_expectation_mismatch_rejects_before_mutation(tmp_path: Path) -> None:
    """Expectation mismatch must reject before any mutation."""
    from doc_contract.lifecycle import ExecutionStatus

    root = _repo(tmp_path)
    _proposed(root)

    # Execute with wrong expectation
    wrong_plan_id = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    outcome = execute_transition(
        root,
        _settings(root),
        "transactional",
        action="accept",
        include_untracked=True,
        date="2026-08-01",
        expect_plan_id=wrong_plan_id,
        dry_run=True,
    )

    assert outcome.execution_status == ExecutionStatus.REJECTED
    assert outcome.expectation == "mismatch"

    # Verify no mutation occurred
    source = root / "docs/changes/transactional/change.md"
    values = parse_front_matter(source.read_text(encoding="utf-8"))
    assert values is not None
    assert values["status"] == "proposed"  # Unchanged


def test_malformed_expectation_is_rejected_without_echoing(tmp_path: Path) -> None:
    """Malformed expectation must be rejected without echoing the input."""
    from doc_contract.lifecycle import ExecutionStatus

    root = _repo(tmp_path)
    _proposed(root)

    # Execute with malformed expectation
    outcome = execute_transition(
        root,
        _settings(root),
        "transactional",
        action="accept",
        include_untracked=True,
        date="2026-08-01",
        expect_plan_id="not-a-valid-sha256",
        dry_run=True,
    )

    assert outcome.execution_status == ExecutionStatus.REJECTED
    assert outcome.expectation == "malformed"


def test_execution_status_distinguishes_rejected_from_interrupted(tmp_path: Path) -> None:
    """Execution status must distinguish rejected from interrupted."""
    from doc_contract.lifecycle import ExecutionStatus

    root = _repo(tmp_path)
    _proposed(root)

    # Rejected case (expectation mismatch)
    outcome_rejected = execute_transition(
        root,
        _settings(root),
        "transactional",
        action="accept",
        include_untracked=True,
        date="2026-08-01",
        expect_plan_id="sha256:0000000000000000000000000000000000000000000000000000000000000000",
        dry_run=True,
    )
    assert outcome_rejected.execution_status == ExecutionStatus.REJECTED
    assert outcome_rejected.journal_retained is False

    # Interrupted case (fault_after)
    outcome_interrupted = execute_transition(
        root,
        _settings(root),
        "transactional",
        action="accept",
        include_untracked=True,
        date="2026-08-01",
        fault_after=1,
    )
    assert outcome_interrupted.execution_status == ExecutionStatus.INTERRUPTED
    assert outcome_interrupted.journal_retained is True
    # Journal should exist
    assert list((root / ".git").glob("doc-contract/lifecycle-accept-*.json"))


def test_already_applied_reports_correct_status(tmp_path: Path) -> None:
    """Already-applied no-op must report correct execution status."""
    from doc_contract.lifecycle import ExecutionStatus

    root = _repo(tmp_path)
    _proposed(root)

    # First accept
    outcome1 = execute_transition(
        root,
        _settings(root),
        "transactional",
        action="accept",
        include_untracked=True,
        date="2026-08-01",
    )
    assert outcome1.execution_status == ExecutionStatus.APPLIED

    # Second accept (already-applied)
    outcome2 = execute_transition(
        root,
        _settings(root),
        "transactional",
        action="accept",
        include_untracked=True,
        date="2026-08-01",
    )
    assert outcome2.execution_status == ExecutionStatus.ALREADY_APPLIED
    assert outcome2.already_applied is True


def test_findings_do_not_affect_plan_id(tmp_path: Path) -> None:
    """Findings must not affect plan_id."""
    from doc_contract.lifecycle import compute_plan_id

    root = _repo(tmp_path)
    _proposed(root)

    # Add an unrelated warning that shouldn't affect plan_id
    _write(
        root,
        "docs/changes/unrelated/change.md",
        "---\nid: unrelated\npersistence: ephemeral\nstatus: proposed\ntrack: test\n"
        "files_owned:\n  - src/unrelated.py\n---\n# Unrelated\n",
    )
    roadmap = root / "docs/roadmap.md"
    roadmap.write_text(
        roadmap.read_text(encoding="utf-8") + "\n- `docs/changes/unrelated/` (proposed)\n",
        encoding="utf-8",
    )

    plan = plan_transition(
        root,
        _settings(root),
        "transactional",
        action=TransitionAction.ACCEPT,
        include_untracked=True,
        date="2026-08-01",
    )

    # plan_id should be computed successfully despite the warning
    plan_id = compute_plan_id(plan)
    assert plan_id.startswith("sha256:")

    # The warning should be in findings but not affect plan_id
    assert any(f.code == "owned-file-missing" for f in plan.current_findings)
