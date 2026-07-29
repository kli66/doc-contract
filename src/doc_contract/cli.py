"""Command-line interface for explicit, cwd-independent doc-contract checks."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from . import __version__
from .config import ConfigError, Settings, load_settings, resolve_repo_root
from .landing import LandingError, LandingPlan, execute_landing
from .lifecycle import (
    LifecycleError,
    LifecyclePlan,
    TransitionAction,
    execute_transition,
)
from .resolver import Finding, Resolution, resolve, stamp_node, update_roadmap
from .sync import sync_package
from .verification import VerificationPolicy, verify

COMMANDS = frozenset({"check", "update", "stamp", "sync", "accept", "begin", "land"})


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
    land = subparsers.add_parser("land", parents=[common], help="transactionally archive a change")
    land.add_argument("change_ref", help="change ID or repository-relative change folder")
    land.add_argument("--dry-run", action="store_true", help="print the plan without mutations")
    land.add_argument("--include-untracked", action="store_true")
    for name, help_text in (("accept", "record explicit acceptance"), ("begin", "start work on an accepted change")):
        transition = subparsers.add_parser(name, parents=[common], help=help_text)
        transition.add_argument("change_ref", help="change ID or repository-relative change folder")
        transition.add_argument("--dry-run", action="store_true", help="print the plan without mutations")
        transition.add_argument("--include-untracked", action="store_true")
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


def _print_plan(plan: LandingPlan) -> None:
    if plan.provisional_nodes:
        print("untracked discovery preview (no mutation yet):")
        for node_id, path in plan.provisional_nodes:
            print(f"  + {node_id}: {path}")
    print(
        f"land plan: {plan.change_id}; {plan.source} -> {plan.archive}; "
        f"tracking={plan.tracking}; {len(plan.mutations)} mutation(s)"
    )
    print("input/output tree:", plan.input_tree_hash, "->", plan.output_tree_hash)
    print(plan.diff, end="" if plan.diff.endswith("\n") else "\n")


def _land(
    context: Context,
    change_ref: str,
    *,
    dry_run: bool,
    include_untracked: bool,
) -> int:
    try:
        outcome = execute_landing(
            context.root,
            context.settings,
            change_ref,
            dry_run=dry_run,
            include_untracked=include_untracked,
            on_plan=_print_plan,
        )
    except LandingError as exc:
        print(f"ERROR: [{type(exc).__name__}] {exc}", file=sys.stderr)
        return 1
    if outcome.already_landed:
        print(f"{change_ref} already landed; no mutations")
        return 0
    if dry_run:
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
    if args.command == "land":
        return _land(
            context,
            args.change_ref,
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
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
