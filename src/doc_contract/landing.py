"""Transactional change landing with hash-guarded, resumable mutations."""

from __future__ import annotations

import datetime as _datetime
import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import Settings
from .lifecycle import (
    LifecycleDiagnostic,
    LifecycleError,
    LifecycleRequest,
    _resolve_preflight,
    classify_change,
)
from .resolver import (
    DAG_BEGIN_PREFIX,
    DAG_END,
    Finding,
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
    required_str as _required_str,
    save_journal as _save_journal,
    sha as _sha,
    tree_hash as _tree_hash,
    tree_hash_with as _tree_hash_with,
)
from .verification import VerificationOutcome, VerificationPolicy, WarningDelta, verify

JOURNAL_SCHEMA = 2
__all__ = ["ConcurrentModification", "InjectedInterruption", "LandingError"]


class LandingError(TransactionError):
    """A stable landing-planning failure with optional resolver evidence."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        findings: tuple[Finding, ...] = (),
    ) -> None:
        super().__init__(message)
        prefix, separator, _ = message.partition(":")
        self.code = code or (prefix if separator else "landing-failed")
        self.findings = findings


@dataclass(frozen=True, slots=True)
class LandingPlan:
    change_id: str
    source: str
    archive: str
    date: str
    tracking: TrackingMode
    mutations: tuple[Mutation, ...]
    diff: str | None
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
            "diff": self.diff,
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
        diff = raw.get("diff")
        if diff is not None and not isinstance(diff, str):
            raise LandingError("journal-invalid: diff is malformed")
        return cls(
            change_id=_required_str(raw, "change_id"),
            source=_required_str(raw, "source"),
            archive=_required_str(raw, "archive"),
            date=_required_str(raw, "date"),
            tracking=tracking,
            mutations=tuple(Mutation.from_dict(item) for item in mutations),
            diff=diff,
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
    diagnostic: LifecycleDiagnostic | None = None

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


def _plan_landing(
    root: Path,
    settings: Settings,
    ref: str,
    *,
    date: str | None = None,
    include_untracked: bool = False,
) -> LandingPlan:
    root = root.resolve()
    selection = classify_change(
        root,
        settings,
        ref,
        action=LifecycleRequest.LAND,
        include_untracked=include_untracked,
    )
    if selection.diagnostic is not None:
        raise LifecycleError(
            selection.diagnostic,
            change_id=selection.change_id,
            path=selection.path,
            status=selection.status,
        )
    result = _resolve_preflight(
        root,
        settings,
        include_untracked=include_untracked,
    )
    if result.errors:
        raise LandingError(
            "preflight-invalid: repository has resolver errors",
            findings=tuple(result.errors),
        )
    if len(result.topo_order) != len(result.nodes):
        raise LandingError(
            "preflight-invalid: dependency graph contains a cycle",
            findings=tuple(finding for finding in result.findings if finding.code == "cycle"),
        )
    change_id = selection.change_id
    source = root / selection.path
    source_rel = source.relative_to(root).as_posix()
    day = date or _datetime.date.today().isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise LandingError("date-invalid: expected YYYY-MM-DD")
    archive_rel = f"docs/changes/archive/{day}-{source.name}"
    archive = root / archive_rel
    if archive.exists():
        raise LandingError("destination-collision: archive destination already exists")
    tracking = selection.tracking
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
        raise LandingError(
            "preflight-invalid: planned repository state fails validation",
            findings=tuple(projection.resolution.errors),
        )
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


def plan_landing(
    root: Path,
    settings: Settings,
    ref: str,
    *,
    date: str | None = None,
    include_untracked: bool = False,
) -> LandingPlan:
    try:
        return _plan_landing(
            root,
            settings,
            ref,
            date=date,
            include_untracked=include_untracked,
        )
    except LandingError:
        raise
    except LifecycleError:
        raise
    except TransactionError as exc:
        raise LandingError(str(exc)) from None


def _load_journal(path: Path) -> tuple[LandingPlan, list[int]]:
    return load_journal(path, LandingPlan.from_dict)


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
    journal_hint = _journal_for(root, Path(ref).name)
    if journal_hint.is_file() and not dry_run:
        plan, completed = _load_journal(journal_hint)
        journal_path = journal_hint
    else:
        selection = classify_change(
            root,
            settings,
            ref,
            action=LifecycleRequest.LAND,
            include_untracked=include_untracked,
        )
        journal_path = _journal_for(root, selection.change_id)
        if journal_path.is_file() and not dry_run:
            plan, completed = _load_journal(journal_path)
        else:
            if selection.diagnostic is not None:
                return LandingOutcome(
                    None,
                    True,
                    diagnostic=selection.diagnostic,
                )
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
