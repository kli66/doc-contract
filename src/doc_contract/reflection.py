"""Project-scoped evidence reflection for doc-contract.

This module implements the reflection application layer: evidence collection through
configured source adapters, optional semantic analysis through an external analyzer,
deterministic report generation, and transactional proposal creation.

The runtime remains stdlib-only. Source adapters and analyzers are external subprocesses
that are never imported into the resolver.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Any, Literal

from .config import (
    Analyzer,
    ReflectionSettings,
    Settings,
    SourceAdapter,
)
from .resolver import (
    Finding,
    project_proposal,
)
from .secret_scan import SecretFinding, scan_text
from .transaction import (
    Mutation,
    TransactionError,
    TransactionPlan,
    execute_mutations,
    file_hash,
    git_metadata_path,
    sha,
)

SCHEMA_VERSION = 1
REPORT_VERSION = 1

# Status tokens for roadmap remediation lines (REQ-054)
_STATUS_TOKENS: tuple[tuple[str, str], ...] = (
    ("(blocked", "blocked"),
    ("blocked on", "blocked"),
    ("(in-progress", "in-progress"),
    ("in progress", "in-progress"),
    ("(accepted", "accepted"),
    ("(proposed", "proposed"),
    ("proposed 20", "proposed"),
)


class ReflectionError(RuntimeError):
    """A deterministic, value-free reflection failure."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


# --------------------------------------------------------------------------- Evidence model


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """A normalized evidence record from a source adapter."""

    adapter: str
    record_id: str
    repository: str
    subject_path: str | None
    observed_at: str
    kind: str
    digest: str
    byte_length: int
    summary: str | None
    redacted: bool
    omitted: bool
    metadata: tuple[tuple[str, str], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "adapter": self.adapter,
            "record_id": self.record_id,
            "repository": self.repository,
            "observed_at": self.observed_at,
            "kind": self.kind,
            "digest": self.digest,
            "byte_length": self.byte_length,
            "redacted": self.redacted,
            "omitted": self.omitted,
        }
        if self.subject_path is not None:
            result["subject_path"] = self.subject_path
        if self.summary is not None:
            result["summary"] = self.summary
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        return result


@dataclass(frozen=True, slots=True)
class FindingRecord:
    """A typed finding from the analyzer."""

    kind: str
    evidence_ids: tuple[str, ...]
    frequency: int | None = None
    confidence: float | None = None
    summary: str | None = None
    target: str | None = None
    proposed_improvement: str | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "kind": self.kind,
            "evidence_ids": list(self.evidence_ids),
        }
        if self.frequency is not None:
            result["frequency"] = self.frequency
        if self.confidence is not None:
            result["confidence"] = self.confidence
        if self.summary is not None:
            result["summary"] = self.summary
        if self.target is not None:
            result["target"] = self.target
        if self.proposed_improvement is not None:
            result["proposed_improvement"] = self.proposed_improvement
        return result


@dataclass(frozen=True, slots=True)
class Recommendation:
    """A typed recommendation from the analyzer."""

    kind: str
    evidence_ids: tuple[str, ...]
    target: str
    proposed_improvement: str
    rationale: str | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "kind": self.kind,
            "evidence_ids": list(self.evidence_ids),
            "target": self.target,
            "proposed_improvement": self.proposed_improvement,
        }
        if self.rationale is not None:
            result["rationale"] = self.rationale
        return result


@dataclass(frozen=True, slots=True)
class Nomination:
    """A cross-project or global promotion nomination."""

    kind: str
    evidence_ids: tuple[str, ...]
    summary: str
    scope: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "evidence_ids": list(self.evidence_ids),
            "summary": self.summary,
            "scope": self.scope,
        }


@dataclass(frozen=True, slots=True)
class CandidateRequirement:
    """A candidate requirement for the proposed change."""

    text: str
    evidence_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True, slots=True)
class CandidateTask:
    """A candidate task for the proposed change."""

    text: str
    evidence_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True, slots=True)
class Remediation:
    """A substantial remediation candidate for proposal creation."""

    why: str
    requirements: tuple[CandidateRequirement, ...]
    tasks: tuple[CandidateTask, ...]
    files_owned: tuple[str, ...]
    exclusions: tuple[str, ...]
    verification: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "why": self.why,
            "requirements": [r.as_dict() for r in self.requirements],
            "tasks": [t.as_dict() for t in self.tasks],
            "files_owned": list(self.files_owned),
            "exclusions": list(self.exclusions),
            "verification": self.verification,
        }


# --------------------------------------------------------------------------- Report model


@dataclass(frozen=True, slots=True)
class ReflectionReport:
    """A versioned reflection report."""

    version: int
    repository: str
    reflection_id: str
    sources: tuple[str, ...]
    since: str | None
    evidence: tuple[EvidenceRecord, ...]
    findings: tuple[FindingRecord, ...]
    recommendations: tuple[Recommendation, ...]
    nominations: tuple[Nomination, ...]
    remediation: Remediation | None
    coverage: tuple[str, ...]
    omissions: tuple[str, ...]
    redacted_count: int
    omitted_count: int
    status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "repository": self.repository,
            "reflection_id": self.reflection_id,
            "sources": list(self.sources),
            "since": self.since,
            "evidence": [e.as_dict() for e in self.evidence],
            "findings": [f.as_dict() for f in self.findings],
            "recommendations": [r.as_dict() for r in self.recommendations],
            "nominations": [n.as_dict() for n in self.nominations],
            "remediation": self.remediation.as_dict() if self.remediation else None,
            "coverage": list(self.coverage),
            "omissions": list(self.omissions),
            "redacted_count": self.redacted_count,
            "omitted_count": self.omitted_count,
            "status": self.status,
        }


# --------------------------------------------------------------------------- Plan and outcome


@dataclass(frozen=True, slots=True)
class ReflectionPlan:
    """An immutable reflection plan."""

    report: ReflectionReport
    evidence_digest: str
    reflection_digest: str
    adapter_statuses: tuple[tuple[str, str], ...]
    proposal_id: str | None
    proposal_path: str | None
    proposal_content: str | None
    roadmap_line: str | None
    mutations: tuple[Mutation, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "report": self.report.as_dict(),
            "evidence_digest": self.evidence_digest,
            "reflection_digest": self.reflection_digest,
            "adapter_statuses": dict(self.adapter_statuses),
            "proposal_id": self.proposal_id,
            "proposal_path": self.proposal_path,
            "mutations": [m.as_dict() for m in self.mutations],
        }


@dataclass(frozen=True, slots=True)
class ReflectionOutcome:
    """The result of executing a reflection plan."""

    plan: ReflectionPlan | None
    already_written: bool
    final_findings: tuple[Finding, ...]


# --------------------------------------------------------------------------- Adapter execution


def _run_source_adapter(
    adapter: SourceAdapter,
    root: Path,
    settings: ReflectionSettings,
    since: str | None,
) -> tuple[list[EvidenceRecord], str, int]:
    """Run a source adapter and return normalized records.

    Returns (records, status, record_count).
    """
    request: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "repository_root": str(root),
        "repository_name": root.name,
        "max_records": settings.max_records_per_source,
        "max_bytes": settings.source_stdout_cap,
    }
    if since is not None:
        request["since"] = since

    try:
        result = subprocess.run(
            list(adapter.argv),
            cwd=root,
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=settings.source_timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        raise ReflectionError(
            "source-timeout",
            f"source adapter {adapter.name} timed out",
        ) from None
    except OSError:
        raise ReflectionError(
            "source-unavailable",
            f"source adapter {adapter.name} unavailable",
        ) from None

    if result.returncode != 0:
        raise ReflectionError(
            "source-failed",
            f"source adapter {adapter.name} exited with nonzero status",
        )

    stdout_bytes = len(result.stdout.encode("utf-8"))
    if stdout_bytes > settings.source_stdout_cap:
        raise ReflectionError(
            "source-output-oversized",
            f"source adapter {adapter.name} output exceeded cap",
        )

    records: list[EvidenceRecord] = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            raise ReflectionError(
                "source-output-malformed",
                f"source adapter {adapter.name} produced malformed JSONL",
            ) from None

        if not isinstance(raw, dict):
            raise ReflectionError(
                "source-output-malformed",
                f"source adapter {adapter.name} produced non-object record",
            ) from None

        record = _parse_evidence_record(raw, adapter.name, root.name, settings)
        records.append(record)

    if len(records) > settings.max_records_per_source:
        raise ReflectionError(
            "source-records-over-limit",
            f"source adapter {adapter.name} produced too many records",
        )

    return records, "success", len(records)


def _parse_evidence_record(
    raw: dict[str, Any],
    adapter_name: str,
    repository_name: str,
    settings: ReflectionSettings,
) -> EvidenceRecord:
    """Parse and validate a single evidence record."""
    # Check schema version
    schema = raw.get("schema_version")
    if schema != SCHEMA_VERSION:
        raise ReflectionError(
            "evidence-schema-mismatch",
            "evidence record has unsupported schema version",
        )

    # Required fields
    record_id = raw.get("record_id")
    if not isinstance(record_id, str) or not record_id.strip():
        raise ReflectionError(
            "evidence-field-missing",
            "evidence record missing record_id",
        )

    observed_at = raw.get("observed_at")
    if not isinstance(observed_at, str) or not observed_at.strip():
        raise ReflectionError(
            "evidence-field-missing",
            f"evidence record {record_id} missing observed_at",
        )

    # Validate observed_at as ISO-8601 date or timestamp
    # Accept YYYY-MM-DD, YYYY-MM-DDThh:mm:ss, optional fractional seconds, and optional Z or ±hh:mm offset
    # Normalize trailing Z to +00:00 and use datetime.fromisoformat
    observed_at_normalized = observed_at.rstrip("Z") + "+00:00" if observed_at.endswith("Z") else observed_at
    try:
        datetime.fromisoformat(observed_at_normalized)
    except ValueError:
        raise ReflectionError(
            "evidence-field-invalid",
            f"evidence record {record_id} has invalid observed_at",
        ) from None

    kind = raw.get("kind")
    if not isinstance(kind, str) or not kind.strip():
        raise ReflectionError(
            "evidence-field-missing",
            f"evidence record {record_id} missing kind",
        )

    digest = raw.get("digest")
    if not isinstance(digest, str) or not digest.strip():
        raise ReflectionError(
            "evidence-field-missing",
            f"evidence record {record_id} missing digest",
        )

    # Validate digest as exactly 64 hexadecimal characters (SHA-256)
    # Normalize to lowercase
    if not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
        raise ReflectionError(
            "evidence-field-invalid",
            f"evidence record {record_id} has invalid digest",
        ) from None
    digest = digest.lower()

    byte_length = raw.get("byte_length")
    if not isinstance(byte_length, int) or byte_length < 0:
        raise ReflectionError(
            "evidence-field-missing",
            f"evidence record {record_id} missing or invalid byte_length",
        )

    # Repository validation
    repo = raw.get("repository")
    if repo != repository_name:
        raise ReflectionError(
            "evidence-repository-mismatch",
            f"evidence record {record_id} repository mismatch",
        )

    # Optional fields
    subject_path = raw.get("subject_path")
    if subject_path is not None:
        if not isinstance(subject_path, str):
            raise ReflectionError(
                "evidence-field-invalid",
                f"evidence record {record_id} has invalid subject_path",
            )
        # Validate path stays inside repo
        path = Path(subject_path)
        if path.is_absolute() or ".." in path.parts:
            raise ReflectionError(
                "evidence-path-escaping",
                f"evidence record {record_id} has escaping subject_path",
            )

    summary = raw.get("summary")
    redacted = raw.get("redacted", False)
    omitted = raw.get("omitted", False)

    if summary is not None:
        if not isinstance(summary, str):
            raise ReflectionError(
                "evidence-field-invalid",
                f"evidence record {record_id} has invalid summary",
            )
        # Cap summary length by UTF-8 byte length
        summary_bytes = len(summary.encode("utf-8"))
        if summary_bytes > settings.summary_cap:
            # Truncate to fit within the byte cap, preserving valid UTF-8
            summary = summary.encode("utf-8")[: settings.summary_cap].decode("utf-8", errors="ignore")
            redacted = True

    # Metadata
    metadata_raw = raw.get("metadata", {})
    metadata: tuple[tuple[str, str], ...] = ()
    if isinstance(metadata_raw, dict):
        metadata = tuple(
            (str(k), str(v)) for k, v in metadata_raw.items()
            if isinstance(k, str) and isinstance(v, str)
        )

    # Reject unknown fields that could affect scope
    known_fields = {
        "schema_version", "record_id", "repository", "subject_path",
        "observed_at", "kind", "digest", "byte_length", "summary",
        "redacted", "omitted", "metadata",
    }
    unknown = set(raw.keys()) - known_fields
    if unknown:
        raise ReflectionError(
            "evidence-unknown-field",
            f"evidence record {record_id} has unknown field",
        )

    return EvidenceRecord(
        adapter=adapter_name,
        record_id=record_id,
        repository=repository_name,
        subject_path=subject_path,
        observed_at=observed_at,
        kind=kind,
        digest=digest,
        byte_length=byte_length,
        summary=summary,
        redacted=bool(redacted),
        omitted=bool(omitted),
        metadata=metadata,
    )


# --------------------------------------------------------------------------- Analyzer execution


def _run_analyzer(
    analyzer: Analyzer,
    root: Path,
    settings: ReflectionSettings,
    evidence: Sequence[EvidenceRecord],
    allow_external: bool,
) -> dict[str, Any]:
    """Run the analyzer and return the typed result."""
    if analyzer.trust == "external" and not allow_external:
        raise ReflectionError(
            "analyzer-external-not-allowed",
            "external analyzer requires --allow-external-analysis",
        )

    # Build canonical analyzer input
    request: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "evidence": [e.as_dict() for e in evidence],
        "targets": {
            "instructions": list(settings.instruction_targets),
            "skills": list(settings.skill_targets),
            "specs": list(settings.spec_targets),
            "config": list(settings.config_targets),
        },
    }

    try:
        result = subprocess.run(
            list(analyzer.argv),
            cwd=root,
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=settings.analyzer_timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        raise ReflectionError(
            "analyzer-timeout",
            "analyzer timed out",
        ) from None
    except OSError:
        raise ReflectionError(
            "analyzer-unavailable",
            "analyzer unavailable",
        ) from None

    if result.returncode != 0:
        raise ReflectionError(
            "analyzer-failed",
            f"analyzer exited with status {result.returncode}",
        )

    stdout_bytes = len(result.stdout.encode("utf-8"))
    if stdout_bytes > settings.analyzer_stdout_cap:
        raise ReflectionError(
            "analyzer-output-oversized",
            "analyzer output exceeded cap",
        )

    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise ReflectionError(
            "analyzer-output-malformed",
            "analyzer produced malformed JSON",
        ) from None

    if not isinstance(raw, dict):
        raise ReflectionError(
            "analyzer-output-malformed",
            "analyzer produced non-object result",
        )

    return raw


def _parse_analyzer_result(
    raw: dict[str, Any],
    evidence_ids: set[str],
    settings: ReflectionSettings,
) -> tuple[
    tuple[FindingRecord, ...],
    tuple[Recommendation, ...],
    tuple[Nomination, ...],
    Remediation | None,
]:
    """Parse and validate analyzer result."""
    # Validate evidence citations
    def validate_evidence_ids(ids: Sequence[Any]) -> tuple[str, ...]:
        if not isinstance(ids, Sequence):
            raise ReflectionError(
                "analyzer-output-invalid",
                "analyzer result has invalid evidence_ids",
            )
        result: list[str] = []
        for eid in ids:
            if not isinstance(eid, str):
                raise ReflectionError(
                    "analyzer-output-invalid",
                    "analyzer result has non-string evidence_id",
                )
            if eid not in evidence_ids:
                raise ReflectionError(
                    "analyzer-unknown-evidence",
                    "analyzer cites unknown evidence id",
                )
            result.append(eid)
        return tuple(result)

    # Parse findings
    findings: list[FindingRecord] = []
    for i, f in enumerate(raw.get("findings", [])):
        if not isinstance(f, dict):
            raise ReflectionError(
                "analyzer-output-invalid",
                f"analyzer finding {i} is not an object",
            )
        kind = f.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            raise ReflectionError(
                "analyzer-output-invalid",
                f"analyzer finding {i} missing kind",
            )
        evidence_ids_f = validate_evidence_ids(f.get("evidence_ids", []))
        findings.append(FindingRecord(
            kind=kind,
            evidence_ids=evidence_ids_f,
            frequency=f.get("frequency") if isinstance(f.get("frequency"), int) else None,
            confidence=f.get("confidence") if isinstance(f.get("confidence"), (int, float)) else None,
            summary=f.get("summary") if isinstance(f.get("summary"), str) else None,
            target=f.get("target") if isinstance(f.get("target"), str) else None,
            proposed_improvement=f.get("proposed_improvement") if isinstance(f.get("proposed_improvement"), str) else None,
        ))

    if len(findings) > settings.max_findings:
        raise ReflectionError(
            "analyzer-findings-over-limit",
            "analyzer produced too many findings",
        )

    # Parse recommendations
    recommendations: list[Recommendation] = []
    for i, r in enumerate(raw.get("recommendations", [])):
        if not isinstance(r, dict):
            raise ReflectionError(
                "analyzer-output-invalid",
                f"analyzer recommendation {i} is not an object",
            )
        kind = r.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            raise ReflectionError(
                "analyzer-output-invalid",
                f"analyzer recommendation {i} missing kind",
            )
        target = r.get("target")
        if not isinstance(target, str) or not target.strip():
            raise ReflectionError(
                "analyzer-output-invalid",
                f"analyzer recommendation {i} missing target",
            )
        proposed = r.get("proposed_improvement")
        if not isinstance(proposed, str) or not proposed.strip():
            raise ReflectionError(
                "analyzer-output-invalid",
                f"analyzer recommendation {i} missing proposed_improvement",
            )
        evidence_ids_r = validate_evidence_ids(r.get("evidence_ids", []))
        recommendations.append(Recommendation(
            kind=kind,
            evidence_ids=evidence_ids_r,
            target=target,
            proposed_improvement=proposed,
            rationale=r.get("rationale") if isinstance(r.get("rationale"), str) else None,
        ))

    if len(recommendations) > settings.max_recommendations:
        raise ReflectionError(
            "analyzer-recommendations-over-limit",
            "analyzer produced too many recommendations",
        )

    # Parse nominations
    nominations: list[Nomination] = []
    for i, n in enumerate(raw.get("nominations", [])):
        if not isinstance(n, dict):
            raise ReflectionError(
                "analyzer-output-invalid",
                f"analyzer nomination {i} is not an object",
            )
        kind = n.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            raise ReflectionError(
                "analyzer-output-invalid",
                f"analyzer nomination {i} missing kind",
            )
        summary = n.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise ReflectionError(
                "analyzer-output-invalid",
                f"analyzer nomination {i} missing summary",
            )
        scope = n.get("scope", "global")
        evidence_ids_n = validate_evidence_ids(n.get("evidence_ids", []))
        nominations.append(Nomination(
            kind=kind,
            evidence_ids=evidence_ids_n,
            summary=summary,
            scope=scope,
        ))

    if len(nominations) > settings.max_nominations:
        raise ReflectionError(
            "analyzer-nominations-over-limit",
            "analyzer produced too many nominations",
        )

    # Parse remediation
    remediation: Remediation | None = None
    raw_remediation = raw.get("remediation")
    if raw_remediation is not None:
        if not isinstance(raw_remediation, dict):
            raise ReflectionError(
                "analyzer-output-invalid",
                "analyzer remediation is not an object",
            )
        why = raw_remediation.get("why")
        if not isinstance(why, str) or not why.strip():
            raise ReflectionError(
                "analyzer-output-invalid",
                "analyzer remediation missing why",
            )

        # Parse requirements
        requirements: list[CandidateRequirement] = []
        for j, req in enumerate(raw_remediation.get("requirements", [])):
            if not isinstance(req, dict):
                raise ReflectionError(
                    "analyzer-output-invalid",
                    f"analyzer remediation requirement {j} is not an object",
                )
            text = req.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ReflectionError(
                    "analyzer-output-invalid",
                    f"analyzer remediation requirement {j} missing text",
                )
            evidence_ids_req = validate_evidence_ids(req.get("evidence_ids", []))
            requirements.append(CandidateRequirement(text=text, evidence_ids=evidence_ids_req))

        if len(requirements) > settings.max_candidate_requirements:
            raise ReflectionError(
                "analyzer-requirements-over-limit",
                "analyzer produced too many requirements",
            )

        # Parse tasks
        tasks: list[CandidateTask] = []
        for j, task in enumerate(raw_remediation.get("tasks", [])):
            if not isinstance(task, dict):
                raise ReflectionError(
                    "analyzer-output-invalid",
                    f"analyzer remediation task {j} is not an object",
                )
            text = task.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ReflectionError(
                    "analyzer-output-invalid",
                    f"analyzer remediation task {j} missing text",
                )
            evidence_ids_task = validate_evidence_ids(task.get("evidence_ids", []))
            tasks.append(CandidateTask(text=text, evidence_ids=evidence_ids_task))

        if len(tasks) > settings.max_candidate_tasks:
            raise ReflectionError(
                "analyzer-tasks-over-limit",
                "analyzer produced too many tasks",
            )

        # Parse files_owned
        files_owned: list[str] = []
        for f in raw_remediation.get("files_owned", []):
            if not isinstance(f, str) or not f.strip():
                raise ReflectionError(
                    "analyzer-output-invalid",
                    "analyzer remediation has invalid files_owned entry",
                )
            # Validate path stays inside repo
            path = Path(f)
            if path.is_absolute() or ".." in path.parts:
                raise ReflectionError(
                    "analyzer-path-escaping",
                    "analyzer remediation has escaping files_owned path",
                )
            files_owned.append(f)

        # Parse exclusions
        exclusions: list[str] = []
        for e in raw_remediation.get("exclusions", []):
            if isinstance(e, str):
                exclusions.append(e)

        # Parse verification
        verification = raw_remediation.get("verification")
        if not isinstance(verification, str) or not verification.strip():
            raise ReflectionError(
                "analyzer-output-invalid",
                "analyzer remediation missing verification",
            )

        remediation = Remediation(
            why=why,
            requirements=tuple(requirements),
            tasks=tuple(tasks),
            files_owned=tuple(files_owned),
            exclusions=tuple(exclusions),
            verification=verification,
        )

    # Reject unknown fields that could affect scope
    known_fields = {
        "findings", "recommendations", "nominations", "remediation",
    }
    unknown = set(raw.keys()) - known_fields
    if unknown:
        raise ReflectionError(
            "analyzer-unknown-field",
            "analyzer result has unknown field",
        )

    return tuple(findings), tuple(recommendations), tuple(nominations), remediation


# --------------------------------------------------------------------------- Report generation


def _compute_reflection_id(
    evidence: Sequence[EvidenceRecord],
    since: str | None,
    analyzer_identity: str | None,
    analyzer_result: dict[str, Any] | None,
) -> str:
    """Compute a content-addressed reflection ID."""
    digest = hashlib.sha256()
    for record in sorted(evidence, key=lambda r: (r.adapter, r.record_id)):
        digest.update(record.adapter.encode("utf-8"))
        digest.update(b"\0")
        digest.update(record.record_id.encode("utf-8"))
        digest.update(b"\0")
        digest.update(record.digest.encode("utf-8"))
        digest.update(b"\n")
    if since is not None:
        digest.update(since.encode("utf-8"))
        digest.update(b"\n")
    if analyzer_identity is not None:
        digest.update(analyzer_identity.encode("utf-8"))
        digest.update(b"\n")
    if analyzer_result is not None:
        digest.update(json.dumps(analyzer_result, sort_keys=True).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()[:16]


def _compute_evidence_digest(evidence: Sequence[EvidenceRecord]) -> str:
    """Compute a digest over the evidence manifest."""
    digest = hashlib.sha256()
    for record in sorted(evidence, key=lambda r: (r.adapter, r.record_id)):
        digest.update(record.adapter.encode("utf-8"))
        digest.update(b"\0")
        digest.update(record.record_id.encode("utf-8"))
        digest.update(b"\0")
        digest.update(record.digest.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()[:16]


# --------------------------------------------------------------------------- Proposal rendering


_PROPOSAL_TEMPLATE = Template("""---
id: ${proposal_id}
persistence: ephemeral
status: proposed
track: ${track}
depends_on:
${dependencies}
files_owned:
${files_owned}
---

# ${title}

Status: Proposed (not accepted) · Proposed ${date}

**Upstream dependencies:** ${upstream}

**Dependents:** No current in-repository change or roadmap item depends on this change.

**Files owned:** ${files_owned_summary}

## Why

${why}

## Requirements

${requirements}

## Design and interfaces

${design}

## Failure modes

${failure_modes}

## Privacy, provenance, and authority

${privacy}

## Preserved behavior and non-goals

${preserved}

## What changes

${what_changes}

## Tasks

${tasks}

## Verify

${verify}
""")


def _render_proposal(
    proposal_id: str,
    remediation: Remediation,
    plan_date: str,
    track: str,
    dependencies: Sequence[str],
) -> str:
    """Render a proposed change.md from remediation."""
    deps_lines = "\n".join(f"  - {d}" for d in dependencies) if dependencies else "  - none"
    files_lines = "\n".join(f"  - {f}" for f in remediation.files_owned)

    # Requirements section
    req_lines: list[str] = []
    for i, req in enumerate(remediation.requirements, 1):
        citations = ", ".join(req.evidence_ids)
        req_lines.append(f"{i}. {req.text} (evidence: {citations})")
    requirements_text = "\n".join(req_lines) if req_lines else "None."

    # Tasks section
    task_lines: list[str] = []
    for i, task in enumerate(remediation.tasks, 1):
        citations = ", ".join(task.evidence_ids)
        task_lines.append(f"{i}. {task.text} (evidence: {citations})")
    tasks_text = "\n".join(task_lines) if task_lines else "None."

    return _PROPOSAL_TEMPLATE.substitute(
        proposal_id=proposal_id,
        track=track,
        dependencies=deps_lines,
        files_owned=files_lines,
        title=remediation.why.split("\n")[0][:50],
        date=plan_date,
        upstream="none" if not dependencies else ", ".join(dependencies),
        files_owned_summary=", ".join(remediation.files_owned[:3]) + ("..." if len(remediation.files_owned) > 3 else ""),
        why=remediation.why,
        requirements=requirements_text,
        design="Design details to be filled during implementation.",
        failure_modes="Failure modes to be documented during implementation.",
        privacy="Privacy considerations to be documented during implementation.",
        preserved="Preserved behavior to be documented during implementation.",
        what_changes="**Δ ADDED** — Implementation to be added.\n\n**Δ MODIFIED** — None.\n\n**Δ REMOVED** — None.",
        tasks=tasks_text,
        verify="- **Focused tests:** To be added during implementation.\n- **Canonical:** `uv run --group test pytest -q -p no:cacheprovider`, `uv run --group lint ruff check --no-cache .`, and `doc-contract check --repo-root . --offline --include-untracked` pass.",
    )


def _render_roadmap_line(proposal_id: str, rationale: str) -> str:
    """Render a roadmap remediation line using the canonical (proposed) token (REQ-054)."""
    return f"- `docs/changes/{proposal_id}/` (proposed) — {rationale}"


# --------------------------------------------------------------------------- Secret scanning


def _scan_proposal(content: str, path: str) -> list[SecretFinding]:
    """Scan rendered proposal content for secrets."""
    return scan_text(content, path=path)


# --------------------------------------------------------------------------- Transaction plan


@dataclass
class _ProposalPlan(TransactionPlan):
    tracking: Literal["tracked", "untracked"]
    mutations: Sequence[Mutation]

    def as_dict(self) -> dict[str, object]:
        return {
            "tracking": self.tracking,
            "mutations": [m.as_dict() for m in self.mutations],
        }


# --------------------------------------------------------------------------- Public API


def plan_reflection(
    root: Path,
    settings: Settings,
    *,
    sources: Sequence[str] = (),
    since: str | None = None,
    allow_external_analysis: bool = False,
    proposal_id: str | None = None,
    include_untracked: bool = False,
    date: str | None = None,
) -> ReflectionPlan:
    """Plan a reflection run without mutating the repository.

    Args:
        root: Repository root path.
        settings: Repository settings.
        sources: Optional subset of source names to run.
        since: Optional inclusive date boundary for evidence.
        allow_external_analysis: Whether to allow external analyzers.
        proposal_id: Optional change ID for proposal creation.
        include_untracked: Whether to include untracked files in resolution.
        date: Optional date for the plan (defaults to today).

    Returns:
        An immutable ReflectionPlan.

    Raises:
        ReflectionError: If reflection is not configured or a validation fails.
    """
    # Check reflection configuration
    if settings.reflection is None:
        raise ReflectionError(
            "reflection-not-configured",
            "reflection is not configured; add [reflection] table to .doc-contract.toml",
        )

    reflection = settings.reflection

    # Validate source selection
    available_sources = {s.name for s in reflection.sources}
    if sources:
        unknown = set(sources) - available_sources
        if unknown:
            raise ReflectionError(
                "source-unknown",
                "unknown source name(s)",
            )
        selected_sources = [s for s in reflection.sources if s.name in sources]
    else:
        selected_sources = list(reflection.sources)

    # Run source adapters in sorted order
    all_evidence: list[EvidenceRecord] = []
    adapter_statuses: list[tuple[str, str]] = []
    seen_ids: set[tuple[str, str]] = set()

    for adapter in sorted(selected_sources, key=lambda a: a.name):
        records, status, count = _run_source_adapter(adapter, root, reflection, since)
        for record in records:
            key = (record.adapter, record.record_id)
            if key in seen_ids:
                raise ReflectionError(
                    "evidence-duplicate-id",
                    f"duplicate evidence record id {record.record_id}",
                )
            seen_ids.add(key)
        all_evidence.extend(records)
        adapter_statuses.append((adapter.name, status))

    # Check total records limit
    if len(all_evidence) > reflection.max_total_records:
        raise ReflectionError(
            "evidence-over-limit",
            "total evidence records exceeded limit",
        )

    # Zero evidence case (REQ-050)
    if not all_evidence:
        report = ReflectionReport(
            version=REPORT_VERSION,
            repository=root.name,
            reflection_id=_compute_reflection_id([], since, None, None),
            sources=tuple(s.name for s in selected_sources),
            since=since,
            evidence=(),
            findings=(),
            recommendations=(),
            nominations=(),
            remediation=None,
            coverage=tuple(s.name for s in selected_sources),
            omissions=(),
            redacted_count=0,
            omitted_count=0,
            status="insufficient-evidence",
        )
        return ReflectionPlan(
            report=report,
            evidence_digest="",
            reflection_digest=_compute_reflection_id([], since, None, None),
            adapter_statuses=tuple(adapter_statuses),
            proposal_id=None,
            proposal_path=None,
            proposal_content=None,
            roadmap_line=None,
            mutations=(),
        )

    # Run analyzer if configured
    findings: tuple[FindingRecord, ...] = ()
    recommendations: tuple[Recommendation, ...] = ()
    nominations: tuple[Nomination, ...] = ()
    remediation: Remediation | None = None
    analyzer_identity: str | None = None
    analyzer_result: dict[str, Any] | None = None

    if reflection.analyzer is not None:
        analyzer_identity = " ".join(reflection.analyzer.argv)
        analyzer_result = _run_analyzer(
            reflection.analyzer, root, reflection, all_evidence, allow_external_analysis
        )
        evidence_ids = {f"{r.adapter}:{r.record_id}" for r in all_evidence}
        findings, recommendations, nominations, remediation = _parse_analyzer_result(
            analyzer_result, evidence_ids, reflection
        )

    # Compute reflection ID
    reflection_id = _compute_reflection_id(
        all_evidence, since, analyzer_identity, analyzer_result
    )
    evidence_digest = _compute_evidence_digest(all_evidence)

    # Compute coverage and omissions
    coverage = tuple(s.name for s in selected_sources)
    omissions: tuple[str, ...] = ()
    redacted_count = sum(1 for r in all_evidence if r.redacted)
    omitted_count = sum(1 for r in all_evidence if r.omitted)

    # Determine status
    status = "complete"
    if not findings and not recommendations:
        status = "no-findings"

    # Build report
    report = ReflectionReport(
        version=REPORT_VERSION,
        repository=root.name,
        reflection_id=reflection_id,
        sources=tuple(s.name for s in selected_sources),
        since=since,
        evidence=tuple(all_evidence),
        findings=findings,
        recommendations=recommendations,
        nominations=nominations,
        remediation=remediation,
        coverage=coverage,
        omissions=omissions,
        redacted_count=redacted_count,
        omitted_count=omitted_count,
        status=status,
    )

    # Build proposal if requested and remediation exists
    proposal_path: str | None = None
    proposal_content: str | None = None
    roadmap_line: str | None = None
    mutations: tuple[Mutation, ...] = ()

    if proposal_id is not None:
        if remediation is None:
            raise ReflectionError(
                "proposal-no-remediation",
                "cannot create proposal without substantial remediation",
            )

        # Validate proposal ID
        if not proposal_id.strip() or "/" in proposal_id or proposal_id.startswith("."):
            raise ReflectionError(
                "proposal-id-invalid",
                "proposal id must be a non-empty string without slashes or leading dots",
            )

        proposal_path = f"docs/changes/{proposal_id}/change.md"

        # Check for existing proposal
        if (root / proposal_path).exists():
            raise ReflectionError(
                "proposal-exists",
                f"proposal {proposal_id} already exists",
            )

        # Render proposal
        plan_date = date or datetime.now().strftime("%Y-%m-%d")
        proposal_content = _render_proposal(
            proposal_id, remediation, plan_date, "architecture", []
        )

        # Scan for secrets
        secret_findings = _scan_proposal(proposal_content, proposal_path)
        if secret_findings:
            raise ReflectionError(
                "proposal-secret-detected",
                "proposal contains potential secret(s)",
            )

        # Render roadmap line
        roadmap_line = _render_roadmap_line(proposal_id, remediation.why.split("\n")[0][:80])

        # Build mutations - use "create" kind for new files
        mutations = (
            Mutation(
                kind="create",
                path=proposal_path,
                destination=None,
                before_hash="",
                after_hash=sha(proposal_content.encode("utf-8")),
                content=proposal_content,
            ),
        )

    return ReflectionPlan(
        report=report,
        evidence_digest=evidence_digest,
        reflection_digest=reflection_id,
        adapter_statuses=tuple(adapter_statuses),
        proposal_id=proposal_id,
        proposal_path=proposal_path,
        proposal_content=proposal_content,
        roadmap_line=roadmap_line,
        mutations=mutations,
    )


def execute_reflection(
    root: Path,
    settings: Settings,
    *,
    write_proposal: bool = False,
    on_plan: Callable[[ReflectionPlan], None] | None = None,
    **plan_options: Any,
) -> ReflectionOutcome:
    """Execute a reflection run, optionally writing a proposal.

    Args:
        root: Repository root path.
        settings: Repository settings.
        write_proposal: Whether to write the proposal to disk.
        on_plan: Optional callback to receive the plan before execution.
        **plan_options: Options passed to plan_reflection.

    Returns:
        An immutable ReflectionOutcome.

    Raises:
        ReflectionError: If planning or execution fails.
    """
    from .resolver import resolve as resolver_resolve

    plan = plan_reflection(root, settings, **plan_options)

    if on_plan is not None:
        on_plan(plan)

    # Check if we need to write a proposal
    # REQ-050: zero evidence with --write-proposal requested
    if write_proposal and plan.report.status == "insufficient-evidence":
        raise ReflectionError(
            "proposal-no-remediation",
            "cannot create proposal without substantial remediation",
        )

    if not write_proposal or plan.proposal_id is None or plan.proposal_path is None:
        return ReflectionOutcome(
            plan=plan,
            already_written=False,
            final_findings=(),
        )

    # Create journal path using git_metadata_path for linked worktree support
    journal_path = git_metadata_path(
        root, f"doc-contract/reflection-{plan.proposal_id}.json", operation="reflection"
    )

    # Build roadmap mutation if we have a roadmap line
    mutations = list(plan.mutations)
    if plan.roadmap_line is not None:
        roadmap_path = settings.roadmap
        roadmap_full_path = root / roadmap_path
        if roadmap_full_path.exists():
            roadmap_content = roadmap_full_path.read_text(encoding="utf-8")
            # Insert the remediation line under ## Remediation section
            new_roadmap = _insert_remediation_line(roadmap_content, plan.roadmap_line)
            # Regenerate the DAG block
            from .resolver import _without_generated_roadmap
            # We need to project the proposal to get the new DAG
            projection = project_proposal(
                root,
                settings,
                proposal_id=plan.proposal_id,
                proposal_path=plan.proposal_path,
                proposal_content=plan.proposal_content or "",
                roadmap_line=plan.roadmap_line,
                roadmap_text=roadmap_content,
            )
            # Replace the DAG block in the roadmap
            roadmap_without_dag = _without_generated_roadmap(new_roadmap)
            new_roadmap_with_dag = roadmap_without_dag + projection.roadmap_block + "\n"
            mutations.append(
                Mutation(
                    kind="write",
                    path=roadmap_path,
                    destination=None,
                    before_hash=file_hash(roadmap_full_path),
                    after_hash=sha(new_roadmap_with_dag.encode("utf-8")),
                    content=new_roadmap_with_dag,
                )
            )

    # Build transaction plan
    tx_plan = _ProposalPlan(
        tracking="untracked",
        mutations=mutations,
    )

    # Execute mutations
    try:
        execute_mutations(
            root,
            tx_plan,
            journal_path,
            completed=[],
        )
    except TransactionError as exc:
        # On failure, retain the journal and report the error
        raise ReflectionError(
            "proposal-transaction-failed",
            str(exc),
        ) from None

    # Run final resolution with include_untracked=True
    final_findings: tuple[Finding, ...] = ()
    try:
        final_resolution = resolver_resolve(root, settings, include_untracked=True)
        final_findings = tuple(final_resolution.findings)
    except Exception:
        # On final-resolution failure, retain the journal and fail
        # The written proposal stays proposed; do not stage anything
        raise ReflectionError(
            "proposal-final-resolution-failed",
            "final resolution failed after proposal write",
        ) from None

    # Clean up journal on success
    if journal_path.exists():
        journal_path.unlink()

    return ReflectionOutcome(
        plan=plan,
        already_written=False,
        final_findings=final_findings,
    )


def _insert_remediation_line(roadmap_text: str, line: str) -> str:
    """Insert a remediation line under the ## Remediation section.

    If the section exists, insert after it. If not, raise an error.
    """
    lines = roadmap_text.splitlines(keepends=True)
    remediation_index = None
    for i, current_line in enumerate(lines):
        if current_line.strip() == "## Remediation":
            remediation_index = i
            break

    if remediation_index is None:
        raise ValueError("roadmap-invalid: missing ## Remediation section")

    # Find the next section or end
    insert_index = remediation_index + 1
    for i in range(insert_index, len(lines)):
        if lines[i].strip().startswith("##"):
            insert_index = i
            break
    else:
        insert_index = len(lines)

    # Insert the line
    lines.insert(insert_index, line + "\n")
    return "".join(lines)


def render_report_text(report: ReflectionReport) -> str:
    """Render a reflection report as human-readable text."""
    lines: list[str] = [
        f"Reflection Report v{report.version}",
        f"Repository: {report.repository}",
        f"Reflection ID: {report.reflection_id}",
        f"Status: {report.status}",
        "",
        f"Sources: {', '.join(report.sources)}",
    ]
    if report.since:
        lines.append(f"Since: {report.since}")
    lines.append(f"Evidence records: {len(report.evidence)}")
    lines.append(f"Findings: {len(report.findings)}")
    lines.append(f"Recommendations: {len(report.recommendations)}")
    lines.append(f"Nominations: {len(report.nominations)}")
    lines.append(f"Redacted: {report.redacted_count}, Omitted: {report.omitted_count}")
    lines.append("")

    if report.findings:
        lines.append("## Findings")
        for f in report.findings:
            lines.append(f"- [{f.kind}] {f.summary or '(no summary)'}")
            if f.target:
                lines.append(f"  Target: {f.target}")
            lines.append(f"  Evidence: {', '.join(f.evidence_ids)}")
        lines.append("")

    if report.recommendations:
        lines.append("## Recommendations")
        for r in report.recommendations:
            lines.append(f"- [{r.kind}] {r.target}")
            lines.append(f"  Proposed: {r.proposed_improvement}")
            lines.append(f"  Evidence: {', '.join(r.evidence_ids)}")
        lines.append("")

    if report.nominations:
        lines.append("## Nominations")
        for n in report.nominations:
            lines.append(f"- [{n.scope}] {n.kind}: {n.summary}")
        lines.append("")

    if report.remediation:
        lines.append("## Remediation")
        lines.append(f"Why: {report.remediation.why}")
        lines.append(f"Requirements: {len(report.remediation.requirements)}")
        lines.append(f"Tasks: {len(report.remediation.tasks)}")
        lines.append(f"Files owned: {len(report.remediation.files_owned)}")

    return "\n".join(lines)