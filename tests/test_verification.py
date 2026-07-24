"""Shared offline and live verification behavior."""

from __future__ import annotations

import subprocess
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pytest

from doc_contract.resolver import Finding, Resolution
from doc_contract.verification import (
    DEFAULT_TIMEOUT_SECONDS,
    VerificationPolicy,
    verify,
    warning_delta,
)


def _resolution(*findings: Finding) -> Resolution:
    return Resolution(nodes={}, findings=list(findings), topo_order=[])


def _policy(root: Path, mode: str, live_requested: bool) -> VerificationPolicy:
    return VerificationPolicy(
        repo_root=root,
        capability_mode=mode,
        capability_command=("private-command", "private-argument"),
        live_requested=live_requested,
    )


@pytest.mark.parametrize(
    ("mode", "live_requested", "live_status", "error_code", "run_count"),
    [
        ("skip", False, "live skipped", None, 0),
        ("skip", True, "live skipped", None, 0),
        ("optional", False, "live skipped", None, 0),
        ("optional", True, "live passed", None, 1),
        ("required", False, "live skipped", "capability-check-required", 0),
        ("required", True, "live passed", None, 1),
    ],
)
def test_capability_mode_live_request_matrix(
    mode: str,
    live_requested: bool,
    live_status: str,
    error_code: str | None,
    run_count: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    def succeed(*_args: object, **_kwargs: object) -> SimpleNamespace:
        calls.append(object())
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("doc_contract.verification.subprocess.run", succeed)
    outcome = verify(_resolution(), _policy(tmp_path, mode, live_requested))

    assert outcome.offline_status == "offline verified"
    assert outcome.live_status == live_status
    assert [finding.code for finding in outcome.errors] == (
        [error_code] if error_code is not None else []
    )
    assert len(calls) == run_count


@pytest.mark.parametrize(
    ("failure", "live_status", "message"),
    [
        (SimpleNamespace(returncode=7), "live failed", "capability subprocess exited 7"),
        (
            FileNotFoundError("private exception text"),
            "live skipped",
            "capability subprocess unavailable (FileNotFoundError)",
        ),
        (
            subprocess.TimeoutExpired(
                ("private-command", "private-argument"),
                DEFAULT_TIMEOUT_SECONDS,
                output=b"private stdout",
                stderr=b"private stderr",
            ),
            "live skipped",
            "capability subprocess unavailable (TimeoutExpired)",
        ),
    ],
)
def test_live_failures_are_value_free(
    failure: object,
    live_status: str,
    message: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> object:
        if isinstance(failure, BaseException):
            raise failure
        return failure

    monkeypatch.setattr("doc_contract.verification.subprocess.run", fail)
    outcome = verify(_resolution(), _policy(tmp_path, "required", True))

    assert outcome.live_status == live_status
    assert outcome.errors == (
        Finding("ERROR", "capability-check-failed", message),
    )
    rendered = repr(outcome)
    for private in (
        "private-command",
        "private-argument",
        "private exception text",
        "private stdout",
        "private stderr",
    ):
        assert private not in rendered


def test_subprocess_adapter_disconnects_all_streams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def inspect(command: tuple[str, ...], **kwargs: object) -> SimpleNamespace:
        captured["command"] = command
        captured.update(kwargs)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("doc_contract.verification.subprocess.run", inspect)
    policy = _policy(tmp_path, "optional", True)
    verify(_resolution(), policy)

    assert captured == {
        "command": policy.capability_command,
        "cwd": tmp_path,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "timeout": DEFAULT_TIMEOUT_SECONDS,
        "check": False,
    }


def test_verification_composes_findings_without_mutating_inputs(tmp_path: Path) -> None:
    baseline = Finding("WARN", "baseline", "existing warning")
    introduced = Finding("WARN", "introduced", "new warning")
    offline_error = Finding("ERROR", "offline-error", "offline failed")
    resolution = _resolution(baseline, introduced, offline_error)
    original_findings = list(resolution.findings)
    baseline_warnings = (baseline,)

    outcome = verify(
        resolution,
        _policy(tmp_path, "skip", False),
        baseline_warnings=baseline_warnings,
    )

    assert outcome.offline_status == "offline failed"
    assert outcome.findings == (baseline, introduced, offline_error)
    assert outcome.errors == (offline_error,)
    assert outcome.warning_report.baseline == (baseline,)
    assert outcome.warning_report.introduced == (introduced,)
    assert not outcome.warning_report.resolved
    assert resolution.findings == original_findings
    assert baseline_warnings == (baseline,)
    with pytest.raises(FrozenInstanceError):
        outcome.live_status = "changed"


def test_warning_delta_tracks_same_untracked_node_across_archive_path() -> None:
    before = [
        Finding(
            "WARN",
            "untracked-node-included",
            "example (docs/changes/example/change.md) is included provisionally",
        )
    ]
    after = [
        Finding(
            "WARN",
            "untracked-node-included",
            "example (docs/changes/archive/2026-07-23-example/change.md) is included provisionally",
        )
    ]

    report = warning_delta(before, after)

    assert report.baseline == tuple(after)
    assert not report.introduced
    assert not report.resolved
