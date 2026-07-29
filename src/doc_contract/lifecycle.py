"""Explicit, deterministic acceptance and work-start lifecycle transitions."""

from __future__ import annotations

import datetime as _datetime
import difflib
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .config import Settings
from .resolver import (
    Finding,
    Resolution,
    locate_change,
    parse_front_matter,
    project_transition,
    resolve,
)
from .transaction import (
    ConcurrentModification,
    InjectedInterruption,
    Mutation,
    TrackingMode,
    TransactionError,
    execute_mutations,
    file_hash,
    git_metadata_path,
    load_journal,
    save_journal,
    sha,
    tracking_mode,
)

LIFECYCLE_JOURNAL_SCHEMA = 1


class TransitionAction(str, Enum):
    ACCEPT = "accept"
    BEGIN = "begin"


LifecycleError = TransactionError


@dataclass(frozen=True, slots=True)
class LifecyclePlan:
    action: TransitionAction
    change_id: str
    source: str
    date: str
    source_status: str
    destination_status: str
    accepted_at: str | None
    started_at: str | None
    tracking: TrackingMode
    mutations: tuple[Mutation, ...]
    diff: str
    input_tree_hash: str
    output_tree_hash: str
    journal_path: str
    provisional_nodes: tuple[tuple[str, str], ...]
    current_findings: tuple[Finding, ...]
    projected_findings: tuple[Finding, ...]
    baseline_warnings: tuple[Finding, ...] = ()
    already_applied: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": LIFECYCLE_JOURNAL_SCHEMA,
            "action": self.action.value,
            "change_id": self.change_id,
            "source": self.source,
            "date": self.date,
            "source_status": self.source_status,
            "destination_status": self.destination_status,
            "accepted_at": self.accepted_at,
            "started_at": self.started_at,
            "tracking": self.tracking,
            "input_tree_hash": self.input_tree_hash,
            "output_tree_hash": self.output_tree_hash,
            "journal_path": self.journal_path,
            "provisional_nodes": [list(item) for item in self.provisional_nodes],
            "current_findings": [_finding_dict(item) for item in self.current_findings],
            "projected_findings": [_finding_dict(item) for item in self.projected_findings],
            "baseline_warnings": [_finding_dict(item) for item in self.baseline_warnings],
            "mutations": [item.as_dict() for item in self.mutations],
            "already_applied": self.already_applied,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> LifecyclePlan:
        if raw.get("schema") != LIFECYCLE_JOURNAL_SCHEMA:
            raise LifecycleError("journal-invalid: unsupported lifecycle schema")
        action = raw.get("action")
        if not isinstance(action, str):
            raise LifecycleError("journal-invalid: missing action")
        try:
            parsed_action = TransitionAction(action)
        except ValueError:
            raise LifecycleError("journal-invalid: invalid lifecycle action") from None
        tracking = raw.get("tracking")
        if tracking not in {"tracked", "untracked"}:
            raise LifecycleError("journal-invalid: invalid tracking mode")
        mutations = raw.get("mutations")
        if not isinstance(mutations, list) or not all(isinstance(item, dict) for item in mutations):
            raise LifecycleError("journal-invalid: mutations must be a list")
        provisional = raw.get("provisional_nodes", [])
        if not isinstance(provisional, list) or not all(
            isinstance(item, list)
            and len(item) == 2
            and all(isinstance(value, str) for value in item)
            for item in provisional
        ):
            raise LifecycleError("journal-invalid: provisional_nodes is malformed")
        return cls(
            action=parsed_action,
            change_id=_required_str(raw, "change_id"),
            source=_required_str(raw, "source"),
            date=_required_str(raw, "date"),
            source_status=_required_str(raw, "source_status"),
            destination_status=_required_str(raw, "destination_status"),
            accepted_at=_optional_str(raw.get("accepted_at")),
            started_at=_optional_str(raw.get("started_at")),
            tracking=tracking,
            mutations=tuple(Mutation.from_dict(item) for item in mutations),
            diff="",
            input_tree_hash=_required_str(raw, "input_tree_hash"),
            output_tree_hash=_required_str(raw, "output_tree_hash"),
            journal_path=_required_str(raw, "journal_path"),
            provisional_nodes=tuple((item[0], item[1]) for item in provisional),
            current_findings=tuple(_finding_from(item) for item in _finding_list(raw, "current_findings")),
            projected_findings=tuple(_finding_from(item) for item in _finding_list(raw, "projected_findings")),
            baseline_warnings=tuple(_finding_from(item) for item in _finding_list(raw, "baseline_warnings")),
            already_applied=raw.get("already_applied") is True,
        )


@dataclass(frozen=True, slots=True)
class LifecycleOutcome:
    plan: LifecyclePlan | None
    already_applied: bool
    final_findings: tuple[Finding, ...] = ()

    @property
    def already_transitioned(self) -> bool:
        return self.already_applied


def _required_str(raw: Mapping[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise LifecycleError(f"journal-invalid: missing {key}")
    return value


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _finding_dict(finding: Finding) -> dict[str, str]:
    return {"level": finding.level, "code": finding.code, "message": finding.message}


def _finding_list(raw: Mapping[str, object], key: str) -> list[dict[str, object]]:
    values = raw.get(key, [])
    if not isinstance(values, list) or not all(isinstance(item, dict) for item in values):
        raise LifecycleError(f"journal-invalid: {key} is malformed")
    return values


def _finding_from(raw: Mapping[str, object]) -> Finding:
    level = raw.get("level")
    if level not in {"ERROR", "WARN"}:
        raise LifecycleError("journal-invalid: finding level is malformed")
    return Finding(level, _required_str(raw, "code"), _required_str(raw, "message"))


def _normalize_action(action: TransitionAction | str) -> TransitionAction:
    try:
        return action if isinstance(action, TransitionAction) else TransitionAction(action)
    except ValueError:
        raise LifecycleError("transition-invalid: unknown lifecycle action") from None


def _validate_date(date: str | None) -> str:
    day = date or _datetime.date.today().isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise LifecycleError("date-invalid: expected YYYY-MM-DD")
    return day


def _status_error(action: TransitionAction, change_id: str, status: str) -> LifecycleError:
    if status == "blocked":
        return LifecycleError(f"blocked-change: {action.value} refuses blocked change {change_id}")
    expected = "proposed" if action is TransitionAction.ACCEPT else "accepted"
    return LifecycleError(
        f"lifecycle-ineligible: {action.value} requires {expected}; {change_id} is {status}"
    )


def _locate_for_lifecycle(root: Path, ref: str, result: Resolution) -> tuple[str, Path]:
    node = result.nodes.get(ref)
    if node is not None and node.kind == "change":
        return ref, node.path.parent
    try:
        return locate_change(root, ref, result.nodes)
    except ValueError as exc:
        raise LifecycleError(str(exc)) from None


def _metadata_path(root: Path, action: TransitionAction, change_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", change_id)
    return git_metadata_path(
        root,
        f"doc-contract/lifecycle-{action.value}-{safe}.json",
        operation="lifecycle transition",
    )


def _plan_hash(mutations: Sequence[Mutation], *, after: bool) -> str:
    pieces = []
    for mutation in mutations:
        digest = mutation.after_hash if after else mutation.before_hash
        pieces.append(f"{mutation.path}\0{digest}\n")
    return sha("".join(pieces).encode("utf-8"))


def _roadmap_with_block(text: str, block: str) -> str:
    begin = text.find("<!-- BEGIN GENERATED DAG")
    end = text.find("<!-- END GENERATED DAG -->")
    if begin < 0 or end < begin:
        raise LifecycleError("roadmap-invalid: generated DAG markers are missing")
    return text[:begin] + block + text[end + len("<!-- END GENERATED DAG -->") :]


def _diff_for(path: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=path,
            tofile=path,
        )
    )


def _make_noop_plan(
    root: Path,
    settings: Settings,
    result: Resolution,
    *,
    change_id: str,
    source: Path,
    action: TransitionAction,
    date: str,
) -> LifecyclePlan:
    status = result.nodes[change_id].status or ""
    tracking = tracking_mode(root, source)
    journal = _metadata_path(root, action, change_id)
    return LifecyclePlan(
        action=action,
        change_id=change_id,
        source=source.relative_to(root).as_posix(),
        date=date,
        source_status=status,
        destination_status=status,
        accepted_at=_optional_str(parse_front_matter((source / "change.md").read_text(encoding="utf-8")).get("accepted_at")),
        started_at=_optional_str(parse_front_matter((source / "change.md").read_text(encoding="utf-8")).get("started_at")),
        tracking=tracking,
        mutations=(),
        diff="",
        input_tree_hash=sha(b""),
        output_tree_hash=sha(b""),
        journal_path=journal.as_posix(),
        provisional_nodes=tuple((record.node_id, record.path) for record in result.discovery if record.included),
        current_findings=tuple(result.findings),
        projected_findings=tuple(result.findings),
        baseline_warnings=tuple(result.warnings),
        already_applied=True,
    )


def plan_transition(
    root: Path,
    settings: Settings,
    change_ref: str,
    *,
    action: TransitionAction | str,
    include_untracked: bool = False,
    date: str | None = None,
) -> LifecyclePlan:
    root = root.resolve()
    action = _normalize_action(action)
    day = _validate_date(date)
    result = resolve(root, settings, include_untracked=include_untracked)
    if result.errors:
        raise LifecycleError("preflight-invalid: repository has resolver errors")
    requested = Path(change_ref).name
    if not include_untracked and any(
        not record.included
        and (record.node_id == requested or requested in Path(record.path).parts)
        for record in result.discovery
    ):
        raise LifecycleError(
            "untracked-change-excluded: rerun with --include-untracked to preview it"
        )
    change_id, source = _locate_for_lifecycle(root, change_ref, result)
    node = result.nodes[change_id]
    status = node.status or ""
    destination = "accepted" if action is TransitionAction.ACCEPT else "in-progress"
    if status == destination:
        return _make_noop_plan(
            root, settings, result, change_id=change_id, source=source, action=action, date=day
        )
    expected = "proposed" if action is TransitionAction.ACCEPT else "accepted"
    if status != expected:
        raise _status_error(action, change_id, status)
    if not (source / "change.md").is_file():
        raise LifecycleError("change-invalid: change.md is missing")
    current_text = (source / "change.md").read_text(encoding="utf-8")
    roadmap_path = root / settings.roadmap
    current_roadmap = roadmap_path.read_text(encoding="utf-8")
    try:
        projection = project_transition(
            root,
            settings,
            result,
            change_id=change_id,
            action=action.value,
            transition_date=day,
            planned_roadmap_text=current_roadmap,
        )
    except ValueError as exc:
        raise LifecycleError(str(exc)) from None
    roadmap_new = _roadmap_with_block(projection.roadmap_text, projection.roadmap_block)
    mutations: list[Mutation] = []
    diff_parts: list[str] = []
    change_rel = f"{source.relative_to(root).as_posix()}/change.md"
    mutations.append(Mutation("write", change_rel, None, file_hash(source / "change.md"), sha(projection.change_document.content.encode()), projection.change_document.content))
    diff_parts.append(_diff_for(change_rel, current_text, projection.change_document.content))
    for document in projection.dependent_documents:
        old = document.path.read_text(encoding="utf-8")
        if old == document.content:
            continue
        relative = document.path.relative_to(root).as_posix()
        mutations.append(Mutation("write", relative, None, file_hash(document.path), sha(document.content.encode()), document.content))
        diff_parts.append(_diff_for(relative, old, document.content))
    mutations.append(Mutation("write", settings.roadmap, None, file_hash(roadmap_path), sha(roadmap_new.encode()), roadmap_new))
    diff_parts.append(_diff_for(settings.roadmap, current_roadmap, roadmap_new))
    if projection.resolution.errors:
        raise LifecycleError("preflight-invalid: projected repository state fails validation")
    journal = _metadata_path(root, action, change_id)
    return LifecyclePlan(
        action=action,
        change_id=change_id,
        source=source.relative_to(root).as_posix(),
        date=day,
        source_status=status,
        destination_status=destination,
        accepted_at=projection.accepted_at,
        started_at=projection.started_at,
        tracking=tracking_mode(root, source),
        mutations=tuple(mutations),
        diff="".join(diff_parts),
        input_tree_hash=_plan_hash(mutations, after=False),
        output_tree_hash=_plan_hash(mutations, after=True),
        journal_path=journal.as_posix(),
        provisional_nodes=tuple((record.node_id, record.path) for record in result.discovery if record.included),
        current_findings=tuple(result.findings),
        projected_findings=tuple(projection.findings),
        baseline_warnings=tuple(result.warnings),
    )


def _change_id_for_ref(root: Path, ref: str, result: Resolution) -> str | None:
    if ref in result.nodes and result.nodes[ref].kind == "change":
        return ref
    candidate = (root / ref).resolve()
    if not candidate.is_dir():
        return None
    for doc in sorted(candidate.glob("*.md")):
        values = parse_front_matter(doc.read_text(encoding="utf-8")) or {}
        value = values.get("id")
        if isinstance(value, str) and value in result.nodes:
            return value
    return None


def execute_transition(
    root: Path,
    settings: Settings,
    change_ref: str,
    *,
    action: TransitionAction | str,
    include_untracked: bool = False,
    date: str | None = None,
    dry_run: bool = False,
    on_plan: Callable[[LifecyclePlan], None] | None = None,
    fault_after: int | None = None,
) -> LifecycleOutcome:
    root = root.resolve()
    action = _normalize_action(action)
    result = resolve(root, settings, include_untracked=include_untracked)
    change_id = _change_id_for_ref(root, change_ref, result)
    journal_path = _metadata_path(root, action, change_id or Path(change_ref).name)
    if journal_path.is_file():
        plan, completed = load_journal(journal_path, LifecyclePlan.from_dict)
    else:
        if result.errors:
            raise LifecycleError("preflight-invalid: repository has resolver errors")
        plan = plan_transition(
            root,
            settings,
            change_ref,
            action=action,
            include_untracked=include_untracked,
            date=date,
        )
        completed = []
    if on_plan is not None:
        on_plan(plan)
    if plan.already_applied:
        return LifecycleOutcome(plan, True, tuple(result.findings))
    if dry_run:
        return LifecycleOutcome(plan, False, plan.projected_findings)
    try:
        execute_mutations(
            root,
            plan,
            journal_path,
            completed,
            fault_after=fault_after,
            save=save_journal,
        )
    except InjectedInterruption:
        raise
    except TransactionError:
        raise
    final = resolve(root, settings, include_untracked=include_untracked)
    if final.errors:
        return LifecycleOutcome(plan, False, tuple(final.findings))
    journal_path.unlink(missing_ok=True)
    return LifecycleOutcome(plan, False, tuple(final.findings))


__all__ = [
    "ConcurrentModification",
    "InjectedInterruption",
    "LifecycleError",
    "LifecycleOutcome",
    "LifecyclePlan",
    "TransitionAction",
    "execute_transition",
    "plan_transition",
]
