"""Command-line interface for explicit, cwd-independent doc-contract checks."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, cast

from . import __version__
from .config import ConfigError, Settings, load_settings, resolve_repo_root
from .landing import LandingError, LandingPlan, execute_landing, execute_supersede
from .lifecycle import (
    LifecycleError,
    LifecyclePlan,
    TransitionAction,
    execute_transition,
)
from .reconciliation import Phase, ReconciliationReport, _subjects_suffix, reconcile_mechanical
from .reflection import (
    ReflectionError,
    ReflectionPlan,
    execute_reflection,
    plan_reflection,
    render_report_text,
)
from .resolver import Finding, Resolution, resolve, stamp_node, update_roadmap
from .sync import sync_package
from .transaction import TransactionError
from .verification import VerificationPolicy, verify

COMMANDS = frozenset(
    {"check", "update", "stamp", "sync", "accept", "begin", "reconcile", "land", "reflect", "supersede"}
)


@dataclass(frozen=True, slots=True)
class Context:
    root: Path
    settings: Settings


def _common_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo-root", type=Path, help="target repository root")
    common.add_argument("--config", type=Path, help="explicit .doc-contract.toml path")
    return common


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="doc-contract")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    common = _common_parser()

    check = subparsers.add_parser("check", parents=[common], help="resolve and validate")
    check.add_argument(
        "--offline", action="store_true", help="skip the configured capability subprocess"
    )
    check.add_argument("--include-untracked", action="store_true")
    update = subparsers.add_parser("update", parents=[common], help="regenerate the roadmap DAG")
    update.add_argument("--include-untracked", action="store_true")
    stamp = subparsers.add_parser("stamp", parents=[common], help="refresh a node's hashes")
    stamp.add_argument("node_id")
    subparsers.add_parser("sync", parents=[common], help="vendor this pinned package")
    reconcile = subparsers.add_parser(
        "reconcile", help="report deterministic reconciliation readiness"
    )
    reconcile_kinds = reconcile.add_subparsers(dest="reconcile_kind", required=True)
    mechanical = reconcile_kinds.add_parser(
        "mechanical", parents=[common], help="produce a read-only mechanical report"
    )
    mechanical.add_argument(
        "change_ref", help="change ID or repository-relative change folder"
    )
    mechanical.add_argument("--phase", choices=("entry", "exit"), required=True)
    mechanical.add_argument("--format", choices=("text", "json"), default="text")
    mechanical.add_argument("--include-untracked", action="store_true")
    land = subparsers.add_parser("land", parents=[common], help="transactionally archive a change")
    land.add_argument("change_ref", help="change ID or repository-relative change folder")
    land.add_argument("--dry-run", action="store_true", help="print the plan without mutations")
    land.add_argument("--diff", action="store_true", help="append the complete content patch")
    land.add_argument("--include-untracked", action="store_true")
    supersede = subparsers.add_parser(
        "supersede", parents=[common], help="retire a never-accepted proposed change"
    )
    supersede.add_argument("change_ref", help="change ID or repository-relative change folder")
    supersede.add_argument(
        "--reason",
        required=True,
        help="supersession rationale recorded in the frozen lineage record",
    )
    supersede.add_argument("--dry-run", action="store_true", help="print the plan without mutations")
    supersede.add_argument("--include-untracked", action="store_true")
    for name, help_text in (("accept", "record explicit acceptance"), ("begin", "start work on an accepted change")):
        transition = subparsers.add_parser(name, parents=[common], help=help_text)
        transition.add_argument("change_ref", help="change ID or repository-relative change folder")
        transition.add_argument("--dry-run", action="store_true", help="print the plan without mutations")
        transition.add_argument("--include-untracked", action="store_true")
    reflect = subparsers.add_parser("reflect", parents=[common], help="reflect on project evidence")
    reflect.add_argument("--source", action="append", help="select a specific source adapter")
    reflect.add_argument("--since", help="inclusive date boundary for evidence (YYYY-MM-DD)")
    reflect.add_argument("--format", choices=("text", "json"), default="text")
    reflect.add_argument("--allow-external-analysis", action="store_true")
    reflect.add_argument("--write-proposal", help="write a proposal with the given change ID")
    reflect.add_argument("--include-untracked", action="store_true")
    return parser


def _context(args: argparse.Namespace) -> Context:
    config_path = args.config.expanduser().resolve() if args.config is not None else None
    root = resolve_repo_root(args.repo_root, config_path)
    settings = load_settings(root, config_path)
    return Context(root=root, settings=settings)


def _print_findings(findings: Sequence[Finding]) -> None:
    for finding in findings:
        print(f"{finding.level}: [{finding.code}] {finding.message}")


def _print_discovery_preview(result: Resolution) -> None:
    included = [record for record in result.discovery if record.included]
    if not included:
        return
    print("untracked discovery preview (no mutation yet):")
    for record in included:
        print(f"  + {record.node_id}: {record.path}")


def _check(context: Context, *, offline: bool, include_untracked: bool) -> int:
    result = resolve(context.root, context.settings, include_untracked=include_untracked)
    _print_discovery_preview(result)
    outcome = verify(
        result,
        VerificationPolicy(
            repo_root=context.settings.repo_root,
            capability_mode=context.settings.capability_mode,
            capability_command=context.settings.capability_command,
            live_requested=not offline,
        ),
        baseline_warnings=result.warnings,
    )
    _print_findings(outcome.errors)
    report = outcome.warning_report
    for finding in report.baseline:
        print(f"WARN BASELINE: [{finding.code}] {finding.message}")
    print(
        f"{outcome.offline_status}; {outcome.live_status}; {len(outcome.errors)} error(s), "
        f"{len(report.baseline)} baseline warning(s), 0 new warning(s); "
        f"{len(result.nodes)} nodes"
    )
    return 1 if outcome.errors else 0


def _update(context: Context, *, include_untracked: bool) -> int:
    result = resolve(context.root, context.settings, include_untracked=include_untracked)
    _print_discovery_preview(result)
    for finding in result.warnings:
        print(f"WARN BASELINE: [{finding.code}] {finding.message}")
    if result.errors:
        _print_findings(result.errors)
        print("roadmap not updated because validation failed")
        return 1
    changed = update_roadmap(
        context.root, context.settings, include_untracked=include_untracked
    )
    print("roadmap updated" if changed else "roadmap already current")
    return 0


def _stamp(context: Context, node_id: str) -> int:
    try:
        changed = stamp_node(context.root, context.settings, node_id)
    except ValueError as exc:
        print(f"ERROR: [stamp-failed] {exc}", file=sys.stderr)
        return 1
    print(f"{node_id} stamped" if changed else f"{node_id} already current")
    return 0


def _sync(context: Context) -> int:
    changed = sync_package(context.root)
    print("vendored package updated" if changed else "vendored package already current")
    return 0


def _reconcile(
    context: Context,
    change_ref: str,
    *,
    phase: str,
    output_format: str,
    include_untracked: bool,
) -> int:
    report: ReconciliationReport = reconcile_mechanical(
        context.root,
        context.settings,
        change_ref,
        phase=cast(Phase, phase),
        include_untracked=include_untracked,
    )
    if output_format == "json":
        print(json.dumps(report.as_dict(), sort_keys=True, separators=(",", ":")))
    else:
        print(report.render_text(), end="")
    return 0 if report.ready else 1


def _print_plan(plan: LandingPlan, *, include_diff: bool) -> None:
    write_count = sum(mutation.kind == "write" for mutation in plan.mutations)
    move_count = sum(mutation.kind == "move" for mutation in plan.mutations)
    print(f"land plan: {plan.change_id}")
    print(f"source: {plan.source}")
    print(f"archive: {plan.archive}")
    print(f"tracking: {plan.tracking}")
    print(f"provisional nodes: {len(plan.provisional_nodes)}")
    if plan.provisional_nodes:
        for node_id, path in plan.provisional_nodes:
            print(f"  + {node_id}: {path}")
    print(
        f"mutations: {len(plan.mutations)} total; {write_count} write(s), "
        f"{move_count} move(s)"
    )
    for mutation in plan.mutations:
        if mutation.kind == "write":
            print(f"  write {mutation.path}")
        else:
            print(f"  move {mutation.path} -> {mutation.destination}")
    print(f"preflight warnings: {len(plan.baseline_warnings)}")
    if not include_diff:
        print("hint: add --diff for the complete patch")
    elif plan.diff is None:
        print("WARN: [complete-diff-unavailable] complete diff unavailable for legacy journal")
    else:
        sys.stdout.write(plan.diff)


def _print_transaction_failure(exc: TransactionError) -> None:
    """Shared land/supersede transaction-failure printer. Prints the stable code
    (exc.code for a LandingError, otherwise the exception type name), the exception text
    with one leading "code: " prefix stripped for display so the code never appears twice
    on one line, then each exc.findings entry's code, message, and subjects. Prints no
    document content or hashes; LifecycleError handling and success output are untouched."""
    landing = isinstance(exc, LandingError)
    code = exc.code if landing else type(exc).__name__
    message = str(exc)
    if landing:
        prefix = f"{exc.code}: "
        if message.startswith(prefix):
            message = message[len(prefix) :]
    print(f"ERROR: [{code}] {message}", file=sys.stderr)
    if landing:
        for finding in exc.findings:
            print(
                f"  {finding.level}: [{finding.code}] {finding.message}"
                f"{_subjects_suffix(finding.subjects)}",
                file=sys.stderr,
            )


def _land(
    context: Context,
    change_ref: str,
    *,
    dry_run: bool,
    include_diff: bool,
    include_untracked: bool,
) -> int:
    try:
        outcome = execute_landing(
            context.root,
            context.settings,
            change_ref,
            dry_run=dry_run,
            include_untracked=include_untracked,
            on_plan=lambda plan: _print_plan(plan, include_diff=include_diff),
        )
    except LifecycleError as exc:
        diagnostic = exc.diagnostic
        print(f"ERROR: [{diagnostic.code}] {diagnostic.message}", file=sys.stderr)
        if diagnostic.next_command is not None:
            print(f"NEXT: {diagnostic.next_command}", file=sys.stderr)
        return 1
    except TransactionError as exc:
        _print_transaction_failure(exc)
        return 1
    if outcome.already_landed:
        diagnostic = outcome.diagnostic
        if diagnostic is None:
            raise AssertionError("completed landing is missing its diagnostic")
        print(f"INFO: [{diagnostic.code}] {diagnostic.message}")
        return 0
    if dry_run:
        for finding in outcome.plan.baseline_warnings if outcome.plan is not None else ():
            print(f"WARN BASELINE: [{finding.code}] {finding.message}")
        print("dry-run; no mutations")
        return 0
    _print_findings(
        [finding for finding in outcome.final_findings if finding.level == "ERROR"]
    )
    for finding in outcome.warning_report.baseline:
        print(f"WARN BASELINE: [{finding.code}] {finding.message}")
    for finding in outcome.warning_report.introduced:
        print(f"WARN NEW: [{finding.code}] {finding.message}")
    print(
        f"warnings: {len(outcome.warning_report.baseline)} baseline, "
        f"{len(outcome.warning_report.introduced)} new, "
        f"{len(outcome.warning_report.resolved)} resolved"
    )
    if any(finding.level == "ERROR" for finding in outcome.final_findings):
        print("landing applied but final validation failed; journal retained", file=sys.stderr)
        return 1
    print(f"landed {outcome.plan.change_id if outcome.plan else change_ref}; {outcome.capability_status}")
    return 0


def _print_supersede_plan(plan: LandingPlan) -> None:
    remove_count = sum(mutation.kind == "remove" for mutation in plan.mutations)
    write_count = sum(mutation.kind == "write" for mutation in plan.mutations)
    create_count = sum(mutation.kind == "create" for mutation in plan.mutations)
    print(f"supersede plan: {plan.change_id}")
    print(f"source: {plan.source}")
    print(f"record: {plan.archive}")
    print(f"tracking: {plan.tracking}")
    print(f"provisional nodes: {len(plan.provisional_nodes)}")
    if plan.provisional_nodes:
        for node_id, path in plan.provisional_nodes:
            print(f"  + {node_id}: {path}")
    print(
        f"mutations: {len(plan.mutations)} total; {remove_count} remove(s), "
        f"{write_count} write(s), {create_count} create(s)"
    )
    for mutation in plan.mutations:
        print(f"  {mutation.kind} {mutation.path}")
    print(f"preflight warnings: {len(plan.baseline_warnings)}")


def _supersede(
    context: Context,
    change_ref: str,
    *,
    reason: str,
    dry_run: bool,
    include_untracked: bool,
) -> int:
    try:
        outcome = execute_supersede(
            context.root,
            context.settings,
            change_ref,
            reason=reason,
            dry_run=dry_run,
            include_untracked=include_untracked,
            on_plan=_print_supersede_plan,
        )
    except LifecycleError as exc:
        diagnostic = exc.diagnostic
        print(f"ERROR: [{diagnostic.code}] {diagnostic.message}", file=sys.stderr)
        if diagnostic.next_command is not None:
            print(f"NEXT: {diagnostic.next_command}", file=sys.stderr)
        return 1
    except TransactionError as exc:
        _print_transaction_failure(exc)
        return 1
    if dry_run:
        for finding in outcome.plan.baseline_warnings if outcome.plan is not None else ():
            print(f"WARN BASELINE: [{finding.code}] {finding.message}")
        print("dry-run; no mutations")
        return 0
    _print_findings(
        [finding for finding in outcome.final_findings if finding.level == "ERROR"]
    )
    for finding in outcome.warning_report.baseline:
        print(f"WARN BASELINE: [{finding.code}] {finding.message}")
    for finding in outcome.warning_report.introduced:
        print(f"WARN NEW: [{finding.code}] {finding.message}")
    print(
        f"warnings: {len(outcome.warning_report.baseline)} baseline, "
        f"{len(outcome.warning_report.introduced)} new, "
        f"{len(outcome.warning_report.resolved)} resolved"
    )
    if any(finding.level == "ERROR" for finding in outcome.final_findings):
        print("supersede applied but final validation failed; journal retained", file=sys.stderr)
        return 1
    print(f"superseded {outcome.plan.change_id if outcome.plan else change_ref}; {outcome.capability_status}")
    return 0


def _print_lifecycle_plan(plan: LifecyclePlan) -> None:
    if plan.provisional_nodes:
        print("untracked discovery preview (no mutation yet):")
        for node_id, path in plan.provisional_nodes:
            print(f"  + {node_id}: {path}")
    print(
        f"{plan.action.value} plan: {plan.change_id}; {plan.source_status} -> "
        f"{plan.destination_status}; {len(plan.mutations)} mutation(s)"
    )
    print("input/output plan hash:", plan.input_tree_hash, "->", plan.output_tree_hash)
    if plan.diff:
        print(plan.diff, end="" if plan.diff.endswith("\n") else "\n")


def _transition(
    context: Context,
    change_ref: str,
    *,
    action: TransitionAction,
    dry_run: bool,
    include_untracked: bool,
) -> int:
    try:
        outcome = execute_transition(
            context.root,
            context.settings,
            change_ref,
            action=action,
            dry_run=dry_run,
            include_untracked=include_untracked,
            on_plan=_print_lifecycle_plan,
        )
    except LifecycleError as exc:
        diagnostic = exc.diagnostic
        print(f"ERROR: [{diagnostic.code}] {diagnostic.message}", file=sys.stderr)
        if diagnostic.next_command is not None:
            print(f"NEXT: {diagnostic.next_command}", file=sys.stderr)
        return 1
    except TransactionError as exc:
        print(f"ERROR: [{type(exc).__name__}] {exc}", file=sys.stderr)
        return 1
    if outcome.already_applied:
        state_word = "accepted" if action is TransitionAction.ACCEPT else "in-progress"
        print(f"{change_ref} already {state_word}; no mutations")
        return 0
    if dry_run:
        print("dry-run; no mutations")
        return 0
    _print_findings([finding for finding in outcome.final_findings if finding.level == "ERROR"])
    if any(finding.level == "ERROR" for finding in outcome.final_findings):
        print("transition applied but final validation failed; journal retained", file=sys.stderr)
        return 1
    state_word = "accepted" if action is TransitionAction.ACCEPT else "in-progress"
    print(f"{outcome.plan.change_id if outcome.plan else change_ref} {state_word}")
    return 0


def _print_reflection_plan(plan: ReflectionPlan) -> None:
    report = plan.report
    print(f"reflection plan: {report.reflection_id}")
    print(f"repository: {report.repository}")
    print(f"status: {report.status}")
    print(f"sources: {', '.join(report.sources)}")
    if report.since:
        print(f"since: {report.since}")
    print(f"evidence: {len(report.evidence)} records")
    print(f"findings: {len(report.findings)}")
    print(f"recommendations: {len(report.recommendations)}")
    print(f"nominations: {len(report.nominations)}")
    if plan.proposal_id is not None:
        print(f"proposal: {plan.proposal_id}")
        print(f"  path: {plan.proposal_path}")


def _reflect(
    context: Context,
    *,
    sources: Sequence[str],
    since: str | None,
    output_format: str,
    allow_external_analysis: bool,
    write_proposal: str | None,
    include_untracked: bool,
) -> int:
    try:
        if write_proposal is not None:
            outcome = execute_reflection(
                context.root,
                context.settings,
                sources=sources,
                since=since,
                allow_external_analysis=allow_external_analysis,
                proposal_id=write_proposal,
                include_untracked=include_untracked,
                write_proposal=True,
                on_plan=_print_reflection_plan if output_format == "text" else None,
            )
        else:
            plan = plan_reflection(
                context.root,
                context.settings,
                sources=sources,
                since=since,
                allow_external_analysis=allow_external_analysis,
                include_untracked=include_untracked,
            )
            if output_format == "text":
                _print_reflection_plan(plan)
            outcome = None
    except ReflectionError as exc:
        print(f"ERROR: [{exc.code}] {exc.detail}", file=sys.stderr)
        # REQ-051: configuration failures exit 2
        if exc.code in ("reflection-not-configured", "source-unknown"):
            return 2
        return 1

    if output_format == "json":
        if outcome is not None and outcome.plan is not None:
            print(json.dumps(outcome.plan.report.as_dict(), sort_keys=True, separators=(",", ":")))
        elif outcome is None:
            # No outcome means we just planned, so use the plan
            print(json.dumps(plan.report.as_dict(), sort_keys=True, separators=(",", ":")))
        else:
            # This shouldn't happen, but handle gracefully
            print(json.dumps({"error": "no plan"}, sort_keys=True))
    else:
        if outcome is not None and outcome.plan is not None:
            print(render_report_text(outcome.plan.report))

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        context = _context(args)
    except ConfigError as exc:
        print(f"ERROR: [{exc.code}] {exc.path}: {exc.detail}", file=sys.stderr)
        return 2
    if args.command == "check":
        return _check(
            context,
            offline=args.offline,
            include_untracked=args.include_untracked,
        )
    if args.command == "update":
        return _update(context, include_untracked=args.include_untracked)
    if args.command == "stamp":
        return _stamp(context, args.node_id)
    if args.command == "sync":
        return _sync(context)
    if args.command == "reconcile":
        if args.reconcile_kind != "mechanical":
            raise AssertionError(args.reconcile_kind)
        return _reconcile(
            context,
            args.change_ref,
            phase=args.phase,
            output_format=args.format,
            include_untracked=args.include_untracked,
        )
    if args.command == "land":
        return _land(
            context,
            args.change_ref,
            dry_run=args.dry_run,
            include_diff=args.diff,
            include_untracked=args.include_untracked,
        )
    if args.command == "supersede":
        return _supersede(
            context,
            args.change_ref,
            reason=args.reason,
            dry_run=args.dry_run,
            include_untracked=args.include_untracked,
        )
    if args.command == "accept":
        return _transition(
            context,
            args.change_ref,
            action=TransitionAction.ACCEPT,
            dry_run=args.dry_run,
            include_untracked=args.include_untracked,
        )
    if args.command == "begin":
        return _transition(
            context,
            args.change_ref,
            action=TransitionAction.BEGIN,
            dry_run=args.dry_run,
            include_untracked=args.include_untracked,
        )
    if args.command == "reflect":
        return _reflect(
            context,
            sources=tuple(args.source) if args.source else (),
            since=args.since,
            output_format=args.format,
            allow_external_analysis=args.allow_external_analysis,
            write_proposal=args.write_proposal,
            include_untracked=args.include_untracked,
        )
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
