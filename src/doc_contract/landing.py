"""Transactional change landing with hash-guarded, resumable mutations."""

from __future__ import annotations

import datetime as _datetime
import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import Settings
from .resolver import (
    DAG_BEGIN_PREFIX,
    DAG_END,
    Finding,
    parse_front_matter,
    locate_change,
    project_landing,
    resolve,
)
from .transaction import (
    ConcurrentModification,
    InjectedInterruption,
    Mutation,
    TrackingMode,
    TransactionError,
    execute_mutations,
    file_hash as _file_hash,
    git_metadata_path,
    load_journal,
    optional_str as _optional_str,
    required_str as _required_str,
    save_journal as _save_journal,
    sha as _sha,
    tracking_mode as _tracking_mode,
    tree_hash as _tree_hash,
    tree_hash_with as _tree_hash_with,
)
from .verification import VerificationOutcome, VerificationPolicy, WarningDelta, verify

JOURNAL_SCHEMA = 2
LandingError = TransactionError


@dataclass(frozen=True, slots=True)
class LandingPlan:
    change_id: str
    source: str
    archive: str
    date: str
    tracking: TrackingMode
    mutations: tuple[Mutation, ...]
    diff: str
    input_tree_hash: str
    output_tree_hash: str
    journal_path: str
    provisional_nodes: tuple[tuple[str, str], ...] = ()
    baseline_warnings: tuple[Finding, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": JOURNAL_SCHEMA,
            "change_id": self.change_id,
            "source": self.source,
            "archive": self.archive,
            "date": self.date,
            "tracking": self.tracking,
            "input_tree_hash": self.input_tree_hash,
            "output_tree_hash": self.output_tree_hash,
            "journal_path": self.journal_path,
            "provisional_nodes": [list(item) for item in self.provisional_nodes],
            "baseline_warnings": [
                {"level": finding.level, "code": finding.code, "message": finding.message}
                for finding in self.baseline_warnings
            ],
            "mutations": [mutation.as_dict() for mutation in self.mutations],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "LandingPlan":
        if raw.get("schema") != JOURNAL_SCHEMA:
            raise LandingError("journal-invalid: unsupported schema")
        tracking = raw.get("tracking")
        if tracking not in {"tracked", "untracked"}:
            raise LandingError("journal-invalid: invalid tracking mode")
        mutations = raw.get("mutations")
        if not isinstance(mutations, list):
            raise LandingError("journal-invalid: mutations must be a list")
        if not all(isinstance(item, dict) for item in mutations):
            raise LandingError("journal-invalid: mutation entries must be objects")
        provisional = raw.get("provisional_nodes", [])
        if not isinstance(provisional, list) or not all(
            isinstance(item, list)
            and len(item) == 2
            and all(isinstance(value, str) for value in item)
            for item in provisional
        ):
            raise LandingError("journal-invalid: provisional_nodes is malformed")
        warning_items = raw.get("baseline_warnings", [])
        if not isinstance(warning_items, list) or not all(
            isinstance(item, dict)
            and item.get("level") == "WARN"
            and isinstance(item.get("code"), str)
            and isinstance(item.get("message"), str)
            for item in warning_items
        ):
            raise LandingError("journal-invalid: baseline_warnings is malformed")
        return cls(
            change_id=_required_str(raw, "change_id"),
            source=_required_str(raw, "source"),
            archive=_required_str(raw, "archive"),
            date=_required_str(raw, "date"),
            tracking=tracking,
            mutations=tuple(Mutation.from_dict(item) for item in mutations),
            diff="",
            input_tree_hash=_required_str(raw, "input_tree_hash"),
            output_tree_hash=_required_str(raw, "output_tree_hash"),
            journal_path=_required_str(raw, "journal_path"),
            provisional_nodes=tuple((item[0], item[1]) for item in provisional),
            baseline_warnings=tuple(
                Finding("WARN", item["code"], item["message"])
                for item in warning_items
            ),
        )


@dataclass(frozen=True, slots=True)
class LandingOutcome:
    plan: LandingPlan | None
    already_landed: bool
    verification: VerificationOutcome | None = None

    @property
    def final_findings(self) -> tuple[Finding, ...]:
        return self.verification.findings if self.verification is not None else ()

    @property
    def capability_status(self) -> str:
        return self.verification.live_status if self.verification is not None else "not-run"

    @property
    def warning_report(self) -> WarningDelta:
        if self.verification is None:
            return WarningDelta((), (), ())
        return self.verification.warning_report


def _git_path(root: Path, change_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", change_id)
    return git_metadata_path(
        root, f"doc-contract/land-{safe}.json", operation="landing"
    )


def _roadmap_prose_output(text: str, source: str, archive: str) -> str:
    def replace_lines(segment: str) -> str:
        lines: list[str] = []
        for line in segment.splitlines(keepends=True):
            newline = "\n" if line.endswith("\n") else ""
            content = line[:-1] if newline else line
            if source in content:
                content = content.replace(source, archive)
                content = re.sub(r"\((?:proposed|in-progress|blocked)\)", "(landed)", content)
            lines.append(content + newline)
        return "".join(lines)

    if DAG_BEGIN_PREFIX in text and DAG_END in text:
        marker = text.index(DAG_BEGIN_PREFIX)
        prefix = replace_lines(text[:marker])
        return prefix + text[marker:]
    raise LandingError("roadmap-invalid: generated DAG markers are missing")


def _roadmap_output(text: str, block: str) -> str:
    return text[: text.index(DAG_BEGIN_PREFIX)] + block + text[text.index(DAG_END) + len(DAG_END) :]


def _diff_for(path: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=path,
            tofile=path,
        )
    )


def plan_landing(
    root: Path,
    settings: Settings,
    ref: str,
    *,
    date: str | None = None,
    include_untracked: bool = False,
) -> LandingPlan:
    root = root.resolve()
    result = resolve(root, settings, include_untracked=include_untracked)
    if result.errors:
        raise LandingError("preflight-invalid: repository has resolver errors")
    if len(result.topo_order) != len(result.nodes):
        raise LandingError("preflight-invalid: dependency graph contains a cycle")
    requested = Path(ref).name
    if not include_untracked and any(
        not record.included
        and (record.node_id == requested or requested in Path(record.path).parts)
        for record in result.discovery
    ):
        raise LandingError(
            "untracked-change-excluded: rerun with --include-untracked to preview it"
        )
    try:
        change_id, source = locate_change(root, ref, result.nodes)
    except ValueError as exc:
        raise LandingError(str(exc)) from None
    status = result.nodes[change_id].status
    if status != "in-progress":
        if status == "blocked":
            raise LandingError(f"blocked-change: land refuses blocked change {change_id}")
        raise LandingError(
            f"lifecycle-ineligible: land requires in-progress; {change_id} is {status}"
        )
    source_rel = source.relative_to(root).as_posix()
    day = date or _datetime.date.today().isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise LandingError("date-invalid: expected YYYY-MM-DD")
    archive_rel = f"docs/changes/archive/{day}-{source.name}"
    archive = root / archive_rel
    if archive.exists():
        raise LandingError("destination-collision: archive destination already exists")
    tracking = _tracking_mode(root, source)
    change_file = source / "change.md"
    if not change_file.is_file():
        raise LandingError("change-invalid: change.md is missing")
    old_change = change_file.read_text(encoding="utf-8")
    current_roadmap = (root / settings.roadmap).read_text(encoding="utf-8")
    planned_roadmap = _roadmap_prose_output(current_roadmap, source_rel, archive_rel)
    try:
        projection = project_landing(
            root,
            settings,
            result,
            change_id=change_id,
            archive_path=archive / "change.md",
            archive_relative=archive_rel,
            landed_at=day,
            planned_roadmap_text=planned_roadmap,
        )
    except ValueError as exc:
        raise LandingError(str(exc)) from None
    new_change = projection.change_document.content
    change_hash_before = _file_hash(change_file)
    change_hash_after = _sha(new_change.encode("utf-8"))
    mutations: list[Mutation] = [
        Mutation("write", f"{source_rel}/change.md", None, change_hash_before, change_hash_after, new_change)
    ]
    diff_parts = [_diff_for(f"{source_rel}/change.md", old_change, new_change)]
    for document in projection.dependent_documents:
        old = document.path.read_text(encoding="utf-8")
        new = document.content
        if new == old:
            continue
        relative = document.path.relative_to(root).as_posix()
        mutations.append(Mutation("write", relative, None, _file_hash(document.path), _sha(new.encode()), new))
        diff_parts.append(_diff_for(relative, old, new))

    roadmap_new = _roadmap_output(planned_roadmap, projection.roadmap_block)
    roadmap_path = root / settings.roadmap
    mutations.append(
        Mutation(
            "write",
            settings.roadmap,
            None,
            _file_hash(roadmap_path),
            _sha(roadmap_new.encode()),
            roadmap_new,
        )
    )
    diff_parts.append(_diff_for(settings.roadmap, current_roadmap, roadmap_new))
    if projection.resolution.errors:
        raise LandingError("preflight-invalid: planned repository state fails validation")
    before_tree = _tree_hash(source)
    after_tree = _tree_hash_with(source, {"change.md": new_change.encode("utf-8")})
    mutations.append(Mutation("move", source_rel, archive_rel, after_tree, after_tree))
    diff_parts.append(f"rename {source_rel}/ -> {archive_rel}/ ({tracking})\n")
    journal_path = _git_path(root, change_id)
    return LandingPlan(
        change_id=change_id,
        source=source_rel,
        archive=archive_rel,
        date=day,
        tracking=tracking,
        mutations=tuple(mutations),
        diff="".join(diff_parts),
        input_tree_hash=before_tree,
        output_tree_hash=after_tree,
        journal_path=journal_path.as_posix(),
        provisional_nodes=tuple(
            (record.node_id, record.path) for record in result.discovery if record.included
        ),
        baseline_warnings=tuple(result.warnings),
    )


def _load_journal(path: Path) -> tuple[LandingPlan, list[int]]:
    return load_journal(path, LandingPlan.from_dict)


def _find_completed(root: Path, change_id: str) -> bool:
    archive_root = root / "docs/changes/archive"
    if not archive_root.is_dir():
        return False
    for folder in sorted(archive_root.iterdir()):
        change = folder / "change.md"
        if not change.is_file():
            continue
        try:
            values = parse_front_matter(change.read_text(encoding="utf-8")) or {}
        except (OSError, ValueError):
            continue
        recorded_id = values.get("id")
        matches_id = isinstance(recorded_id, str) and recorded_id == change_id
        matches_folder = folder.name.endswith(f"-{change_id}")
        raw_archive = values.get("archive_path")
        recorded_archive = raw_archive if isinstance(raw_archive, str) else None
        actual_archive = folder.relative_to(root).as_posix()
        metadata_matches = recorded_archive is None or recorded_archive == actual_archive
        status = values.get("status")
        if (
            (matches_id or matches_folder)
            and metadata_matches
            and isinstance(status, str)
            and status == "landed"
        ):
            return True
    return False


def _journal_for(root: Path, change_id: str) -> Path:
    return _git_path(root, change_id)


def execute_landing(
    root: Path,
    settings: Settings,
    ref: str,
    *,
    dry_run: bool = False,
    include_untracked: bool = False,
    date: str | None = None,
    fault_after: int | None = None,
    on_plan: Callable[[LandingPlan], None] | None = None,
) -> LandingOutcome:
    root = root.resolve()
    result = resolve(root, settings, include_untracked=include_untracked)
    active_id: str | None = None
    if Path(ref).parts and Path(ref).parts[0] == "docs":
        active_id = Path(ref).name
    elif ref in result.nodes:
        active_id = ref
    journal_path = _journal_for(root, active_id or Path(ref).name)
    if journal_path.is_file() and not dry_run:
        plan, completed = _load_journal(journal_path)
    else:
        if active_id and _find_completed(root, active_id):
            return LandingOutcome(None, True)
        plan = plan_landing(
            root,
            settings,
            ref,
            date=date,
            include_untracked=include_untracked,
        )
        completed = []
    if on_plan is not None:
        on_plan(plan)
    if dry_run:
        return LandingOutcome(plan, False)
    execute_mutations(
        root,
        plan,
        journal_path,
        completed,
        fault_after=fault_after,
        save=_save_journal,
    )
    final = resolve(root, settings, include_untracked=include_untracked)
    verification = verify(
        final,
        VerificationPolicy(
            repo_root=settings.repo_root,
            capability_mode=settings.capability_mode,
            capability_command=settings.capability_command,
            live_requested=True,
        ),
        baseline_warnings=plan.baseline_warnings,
    )
    if verification.errors:
        return LandingOutcome(plan, False, verification)
    journal_path.unlink(missing_ok=True)
    return LandingOutcome(plan, False, verification)
