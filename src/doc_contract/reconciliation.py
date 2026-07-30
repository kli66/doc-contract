"""Read-only mechanical evidence for semantic change reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

from .config import Settings
from .landing import LandingError, LandingPlan, plan_landing
from .lifecycle import (
    LifecycleError,
    LifecyclePlan,
    LifecycleRequest,
    TransitionAction,
    classify_change,
    plan_transition,
)
from .resolver import (
    Finding,
    Node,
    resolve,
)
from .transaction import Mutation, TransactionError

Phase = Literal["entry", "exit"]
Scope = Literal["change", "related", "repository"]
REPORT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ScopedFinding:
    level: str
    code: str
    message: str
    subjects: tuple[str, ...]
    scope: Scope

    def as_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "subjects": list(self.subjects),
            "scope": self.scope,
        }


@dataclass(frozen=True, slots=True)
class ManifestMutation:
    kind: str
    path: str
    destination: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "path": self.path,
            "destination": self.destination,
        }


@dataclass(frozen=True, slots=True)
class ReconciliationManifest:
    tracking: str | None = None
    archive_target: str | None = None
    source_status: str | None = None
    destination_status: str | None = None
    provisional_nodes: tuple[tuple[str, str], ...] = ()
    mutations: tuple[ManifestMutation, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "tracking": self.tracking,
            "archive_target": self.archive_target,
            "source_status": self.source_status,
            "destination_status": self.destination_status,
            "provisional_nodes": [
                {"id": node_id, "path": path} for node_id, path in self.provisional_nodes
            ],
            "mutations": [mutation.as_dict() for mutation in self.mutations],
        }


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    phase: Phase
    ready: bool
    change_id: str | None
    change_path: str | None
    change_status: str | None
    next_command: str | None
    findings: tuple[ScopedFinding, ...]
    manifest: ReconciliationManifest
    gate_present: bool | None = None

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "kind": "mechanical",
            "phase": self.phase,
            "ready": self.ready,
            "change": {
                "id": self.change_id,
                "path": self.change_path,
                "status": self.change_status,
            },
            "next_command": self.next_command,
            "findings": [finding.as_dict() for finding in self.findings],
            "manifest": self.manifest.as_dict(),
        }
        if self.gate_present is not None:
            result["gate_present"] = self.gate_present
        return result

    def render_text(self) -> str:
        identity = self.change_id or "unresolved"
        path = self.change_path or "unresolved"
        status = self.change_status or "unknown"
        lines = [
            f"mechanical reconciliation: {identity} ({path}); phase={self.phase}; status={status}",
            "READY: mechanically ready" if self.ready else "BLOCKED: not mechanically ready",
        ]
        if self.gate_present is not None:
            lines.append(f"gate_present: {'true' if self.gate_present else 'false'}")
        repository_warnings = 0
        for finding in self.findings:
            if finding.level == "WARN" and finding.scope == "repository":
                repository_warnings += 1
                continue
            if finding.level == "WARN" or finding.level == "ERROR":
                lines.append(
                    f"{finding.level} {finding.scope}: [{finding.code}] {finding.message}"
                )
        if repository_warnings:
            lines.append(f"repository warnings: {repository_warnings} unrelated warning(s)")
        manifest = self.manifest
        if manifest.tracking is not None:
            lines.append(f"tracking: {manifest.tracking}")
        if (
            manifest.source_status is not None and manifest.destination_status is not None
        ):
            lines.append(f"transition: {manifest.source_status} -> {manifest.destination_status}")
        if manifest.archive_target is not None:
            lines.append(f"archive target: {manifest.archive_target}")
        for mutation in manifest.mutations:
            destination = f" -> {mutation.destination}" if mutation.destination else ""
            lines.append(f"plan path: {mutation.kind} {mutation.path}{destination}")
        lines.append(f"next command: {self.next_command or 'none'}")
        return "\n".join(lines) + "\n"


@dataclass(frozen=True, slots=True)
class _Selection:
    change_id: str | None
    path: str | None
    node: Node | None


def _synthetic(
    level: str,
    code: str,
    message: str,
    change_id: str | None,
) -> Finding:
    return Finding(level, code, message, (change_id,) if change_id else ())


def _manifest_mutations(mutations: Sequence[Mutation]) -> tuple[ManifestMutation, ...]:
    return tuple(
        ManifestMutation(item.kind, item.path, item.destination) for item in mutations
    )


def _entry_manifest(plan: LifecyclePlan) -> ReconciliationManifest:
    return ReconciliationManifest(
        tracking=plan.tracking,
        source_status=plan.source_status,
        destination_status=plan.destination_status,
        provisional_nodes=plan.provisional_nodes,
        mutations=_manifest_mutations(plan.mutations),
    )


def _exit_manifest(plan: LandingPlan) -> ReconciliationManifest:
    return ReconciliationManifest(
        tracking=plan.tracking,
        archive_target=plan.archive,
        provisional_nodes=plan.provisional_nodes,
        mutations=_manifest_mutations(plan.mutations),
    )


def _deduplicate(findings: Sequence[Finding]) -> tuple[Finding, ...]:
    seen: set[tuple[str, str, str, tuple[str, ...]]] = set()
    ordered: list[Finding] = []
    for finding in findings:
        key = (finding.level, finding.code, finding.message, finding.subjects)
        if key not in seen:
            seen.add(key)
            ordered.append(finding)
    return tuple(ordered)


def _related_ids(selection: _Selection, findings: Sequence[Finding]) -> set[str]:
    if selection.node is None or selection.change_id is None:
        return set()
    related = {edge.target for edge in selection.node.depends_on}
    related.update(selection.node.dependents)
    for finding in findings:
        if finding.code == "ownership-overlap" and selection.change_id in finding.subjects:
            related.update(finding.subjects)
    related.discard(selection.change_id)
    return related


def _scope_findings(
    selection: _Selection, findings: Sequence[Finding]
) -> tuple[ScopedFinding, ...]:
    related = _related_ids(selection, findings)
    scoped: list[ScopedFinding] = []
    for finding in _deduplicate(findings):
        if selection.change_id is not None and selection.change_id in finding.subjects:
            scope: Scope = "change"
        elif related.intersection(finding.subjects):
            scope = "related"
        else:
            scope = "repository"
        scoped.append(
            ScopedFinding(
                finding.level,
                finding.code,
                finding.message,
                finding.subjects,
                scope,
            )
        )
    return tuple(scoped)


def _normalize_phase_policy(
    selection: _Selection, phase: Phase, findings: Sequence[Finding]
) -> tuple[Finding, ...]:
    """Apply readiness-only severity policy without changing resolver findings."""
    normalized: list[Finding] = []
    for finding in findings:
        selected = selection.change_id is not None and selection.change_id in finding.subjects
        promote_missing_path = (
            phase == "exit" and selected and finding.code == "owned-file-missing"
        )
        promote_overlap = selected and finding.code == "ownership-overlap"
        if finding.level == "WARN" and (promote_missing_path or promote_overlap):
            normalized.append(
                Finding("ERROR", finding.code, finding.message, finding.subjects)
            )
        else:
            normalized.append(finding)
    return tuple(normalized)


def reconcile_mechanical(
    root: Path,
    settings: Settings,
    change_ref: str,
    *,
    phase: Phase,
    include_untracked: bool = False,
) -> ReconciliationReport:
    """Produce a content-free readiness report without executing any mutation or capability."""
    root = root.resolve()
    request = (
        LifecycleRequest.RECONCILE_ENTRY
        if phase == "entry"
        else LifecycleRequest.RECONCILE_EXIT
    )
    try:
        classified = classify_change(
            root,
            settings,
            change_ref,
            action=request,
            include_untracked=include_untracked,
        )
    except LifecycleError as exc:
        selection = _Selection(exc.change_id, exc.path, None)
        finding = _synthetic(
            "ERROR",
            exc.diagnostic.code,
            exc.diagnostic.message,
            exc.change_id,
        )
        return ReconciliationReport(
            phase=phase,
            ready=False,
            change_id=exc.change_id,
            change_path=exc.path,
            change_status=exc.status,
            next_command=exc.diagnostic.next_command,
            findings=_scope_findings(selection, (finding,)),
            manifest=ReconciliationManifest(),
            gate_present=exc.gate_present,
        )
    except TransactionError as exc:
        code, separator, _ = str(exc).partition(":")
        finding = _synthetic(
            "ERROR",
            code if separator else "lifecycle-failed",
            str(exc),
            None,
        )
        return ReconciliationReport(
            phase=phase,
            ready=False,
            change_id=None,
            change_path=None,
            change_status=None,
            next_command=None,
            findings=_scope_findings(_Selection(None, None, None), (finding,)),
            manifest=ReconciliationManifest(),
        )
    try:
        resolution = resolve(root, settings, include_untracked=include_untracked)
    except (OSError, ValueError):
        selection = _Selection(classified.change_id, classified.path, None)
        finding = _synthetic(
            "ERROR",
            "preflight-invalid",
            "repository preflight failed",
            classified.change_id,
        )
        return ReconciliationReport(
            phase=phase,
            ready=False,
            change_id=classified.change_id,
            change_path=classified.path,
            change_status=classified.status,
            next_command=None,
            findings=_scope_findings(selection, (finding,)),
            manifest=ReconciliationManifest(),
        )
    selection = _Selection(
        classified.change_id,
        classified.path,
        resolution.nodes.get(classified.change_id),
    )
    findings: list[Finding] = list(resolution.findings)
    manifest = ReconciliationManifest(
        provisional_nodes=tuple(
            (record.node_id, record.path) for record in resolution.discovery if record.included
        )
    )
    next_command: str | None = None
    status = classified.status
    phase_eligible = status == ("accepted" if phase == "entry" else "in-progress")
    eligible = phase_eligible and not resolution.errors

    if not phase_eligible:
        findings.append(
            _synthetic(
                "ERROR",
                "lifecycle-ineligible",
                f"{phase} reconciliation is already past status={status}",
                selection.change_id,
            )
        )

    if eligible and phase == "entry":
        try:
            plan = plan_transition(
                root,
                settings,
                change_ref,
                action=TransitionAction.BEGIN,
                include_untracked=include_untracked,
            )
        except LifecycleError as exc:
            findings.append(
                _synthetic(
                    "ERROR",
                    exc.diagnostic.code,
                    exc.diagnostic.message,
                    selection.change_id,
                )
            )
        else:
            findings.extend(plan.current_findings)
            findings.extend(plan.projected_findings)
            manifest = _entry_manifest(plan)
            if plan.source_status == "accepted":
                next_command = f"doc-contract begin {plan.source}"
    elif eligible:
        try:
            plan = plan_landing(
                root,
                settings,
                change_ref,
                include_untracked=include_untracked,
            )
        except LifecycleError as exc:
            findings.append(
                _synthetic(
                    "ERROR",
                    exc.diagnostic.code,
                    exc.diagnostic.message,
                    selection.change_id,
                )
            )
        except LandingError as exc:
            findings.extend(exc.findings)
            findings.append(
                _synthetic("ERROR", exc.code, str(exc), selection.change_id)
            )
        else:
            findings.extend(plan.baseline_warnings)
            manifest = _exit_manifest(plan)
            next_command = f"doc-contract land {plan.source}"

    scoped = _scope_findings(
        selection, _normalize_phase_policy(selection, phase, findings)
    )
    ready = eligible and not any(finding.level == "ERROR" for finding in scoped)
    if not ready and eligible:
        next_command = None
    return ReconciliationReport(
        phase=phase,
        ready=ready,
        change_id=selection.change_id,
        change_path=selection.path,
        change_status=status,
        next_command=next_command,
        findings=scoped,
        manifest=manifest,
        gate_present=None,
    )
