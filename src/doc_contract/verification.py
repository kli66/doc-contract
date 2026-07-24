"""Shared offline and live verification composition."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .resolver import Finding, Resolution

CapabilityMode = Literal["skip", "optional", "required"]
DEFAULT_TIMEOUT_SECONDS = 300


@dataclass(frozen=True, slots=True)
class VerificationPolicy:
    repo_root: Path
    capability_mode: CapabilityMode
    capability_command: tuple[str, ...]
    live_requested: bool
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True, slots=True)
class WarningDelta:
    baseline: tuple[Finding, ...]
    introduced: tuple[Finding, ...]
    resolved: tuple[Finding, ...]


@dataclass(frozen=True, slots=True)
class VerificationOutcome:
    offline_status: str
    live_status: str
    findings: tuple[Finding, ...]
    errors: tuple[Finding, ...]
    warning_report: WarningDelta


def warning_delta(
    baseline: Sequence[Finding], current: Sequence[Finding]
) -> WarningDelta:
    def key(finding: Finding) -> tuple[str, str]:
        if finding.code == "untracked-node-included":
            return finding.code, finding.message.split(" ", 1)[0]
        return finding.code, finding.message

    before = {key(finding): finding for finding in baseline if finding.level == "WARN"}
    after = {key(finding): finding for finding in current if finding.level == "WARN"}
    return WarningDelta(
        baseline=tuple(after[item] for item in sorted(before.keys() & after.keys())),
        introduced=tuple(after[item] for item in sorted(after.keys() - before.keys())),
        resolved=tuple(before[item] for item in sorted(before.keys() - after.keys())),
    )


def _run_capability(policy: VerificationPolicy) -> tuple[str, Finding | None]:
    try:
        result = subprocess.run(
            policy.capability_command,
            cwd=policy.repo_root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=policy.timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "live skipped", Finding(
            "ERROR",
            "capability-check-failed",
            f"capability subprocess unavailable ({type(exc).__name__})",
        )
    if result.returncode:
        return "live failed", Finding(
            "ERROR",
            "capability-check-failed",
            f"capability subprocess exited {result.returncode}",
        )
    return "live passed", None


def verify(
    resolution: Resolution,
    policy: VerificationPolicy,
    *,
    baseline_warnings: Sequence[Finding] = (),
) -> VerificationOutcome:
    live_finding: Finding | None = None
    if policy.capability_mode == "skip":
        live_status = "live skipped"
    elif not policy.live_requested:
        live_status = "live skipped"
        if policy.capability_mode == "required":
            live_finding = Finding(
                "ERROR",
                "capability-check-required",
                "required live check was skipped",
            )
    else:
        live_status, live_finding = _run_capability(policy)

    findings = tuple(resolution.findings) + ((live_finding,) if live_finding else ())
    errors = tuple(finding for finding in findings if finding.level == "ERROR")
    return VerificationOutcome(
        offline_status="offline verified" if not resolution.errors else "offline failed",
        live_status=live_status,
        findings=findings,
        errors=errors,
        warning_report=warning_delta(baseline_warnings, findings),
    )
