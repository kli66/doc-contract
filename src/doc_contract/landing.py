"""Transactional change landing with hash-guarded, resumable mutations."""

from __future__ import annotations

import copy
import datetime as _datetime
import difflib
import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Literal

from .config import Settings
from .resolver import (
    DAG_BEGIN_PREFIX,
    DAG_END,
    Finding,
    Resolution,
    _as_map,
    _as_str,
    _compute_dependents,
    _render_front_matter,
    _topo_sort,
    fingerprint,
    parse_front_matter,
    render_block,
    resolve,
    split_front_matter,
    validate,
)

TrackingMode = Literal["tracked", "untracked"]
JOURNAL_SCHEMA = 1


class LandingError(RuntimeError):
    """A deterministic, value-free landing failure."""


class ConcurrentModification(LandingError):
    pass


class InjectedInterruption(LandingError):
    pass


@dataclass(frozen=True, slots=True)
class Mutation:
    kind: Literal["write", "move"]
    path: str
    destination: str | None
    before_hash: str
    after_hash: str
    content: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "path": self.path,
            "destination": self.destination,
            "before_hash": self.before_hash,
            "after_hash": self.after_hash,
            "content": self.content,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "Mutation":
        kind = raw.get("kind")
        if kind not in {"write", "move"}:
            raise LandingError("journal-invalid: unknown mutation kind")
        return cls(
            kind=kind,
            path=_required_str(raw, "path"),
            destination=_optional_str(raw.get("destination")),
            before_hash=_required_str(raw, "before_hash"),
            after_hash=_required_str(raw, "after_hash"),
            content=_optional_str(raw.get("content")),
        )


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
        )


@dataclass(frozen=True, slots=True)
class LandingOutcome:
    plan: LandingPlan | None
    already_landed: bool
    final_findings: tuple[Finding, ...] = ()
    capability_status: str = "not-run"


def _required_str(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise LandingError(f"journal-invalid: missing {key}")
    return value


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_hash(path: Path) -> str:
    try:
        return _sha(path.read_bytes())
    except OSError as exc:
        raise LandingError(f"input-unavailable: {type(exc).__name__}") from None


def _tree_files(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    files: list[Path] = []
    for item in sorted(path.rglob("*")):
        if item.is_symlink() or not item.is_file():
            raise LandingError("source-tree-invalid: only regular files are supported")
        files.append(item)
    return files


def _tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for item in _tree_files(path):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(_file_hash(item).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _tree_hash_with(path: Path, overrides: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    names = {item.relative_to(path).as_posix() for item in _tree_files(path)} | set(overrides)
    for name in sorted(names):
        data = overrides.get(name)
        if data is None:
            data = (path / name).read_bytes()
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha(data).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _git_path(root: Path, change_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", change_id)
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--git-path", f"doc-contract/land-{safe}.json"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        raise LandingError("repo-not-git: landing requires a Git worktree") from None
    path = Path(result.stdout.strip())
    return path if path.is_absolute() else root / path


def _tracking_mode(root: Path, source: Path) -> TrackingMode:
    relative = source.relative_to(root).as_posix()
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--full-name", "-z", "--", relative],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        raise LandingError("tracking-state-unavailable: cannot inspect Git index") from None
    tracked = {item for item in result.stdout.decode("utf-8").split("\0") if item}
    files = {item.relative_to(root).as_posix() for item in _tree_files(source)}
    if tracked and tracked != files:
        raise LandingError("partial-tracking: change folder is neither fully tracked nor untracked")
    if tracked:
        return "tracked"
    return "untracked"


def _locate_source(root: Path, ref: str, nodes: dict[str, object]) -> tuple[str, Path]:
    candidate = Path(ref)
    if candidate.parts and candidate.parts[0] == "docs":
        path = (root / candidate).resolve()
        if not path.is_dir() or root not in path.parents or "changes" not in path.relative_to(root).parts:
            raise LandingError("change-not-found: ref is not an active change folder")
        docs = sorted(path.glob("*.md"))
        for doc in docs:
            fm = parse_front_matter(doc.read_text(encoding="utf-8")) or {}
            change_id = _as_str(fm.get("id"))
            node = nodes.get(change_id) if change_id else None
            if change_id and node is not None and getattr(node, "active", False):
                return change_id, path
        raise LandingError("change-not-found: folder has no resolvable change id")
    node = nodes.get(ref)
    if node is None or getattr(node, "kind", None) != "change" or not getattr(node, "active", False):
        raise LandingError("change-not-found: ref is not an active change")
    return ref, getattr(node, "path").parent


def _land_change_text(text: str, date: str, archive: str) -> str:
    values = parse_front_matter(text)
    if values is None:
        raise LandingError("change-invalid: missing front matter")
    values["status"] = "landed"
    values["landed_at"] = date
    values["archive_path"] = archive
    _, body = split_front_matter(text)
    body = re.sub(r"^Status:.*$", f"Status: Landed · {date}", body, count=1, flags=re.MULTILINE)
    return _render_front_matter(values, body)


def _dependent_text(text: str, change_id: str, target_hash: str) -> str:
    values = parse_front_matter(text)
    if values is None:
        raise LandingError("dependent-invalid: missing front matter")
    fingerprints = _as_map(values.get("fingerprints"))
    if fingerprints.get(change_id) == target_hash:
        return text
    fingerprints[change_id] = target_hash
    values["fingerprints"] = fingerprints
    _, body = split_front_matter(text)
    return _render_front_matter(values, body)


def _strip_generated(text: str) -> str:
    if DAG_BEGIN_PREFIX in text and DAG_END in text:
        return text[: text.index(DAG_BEGIN_PREFIX)] + text[text.index(DAG_END) + len(DAG_END) :]
    return text


def _roadmap_output(text: str, source: str, archive: str, block: str) -> str:
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
        suffix = text[text.index(DAG_END) + len(DAG_END) :]
        return prefix + block + suffix
    raise LandingError("roadmap-invalid: generated DAG markers are missing")


def _diff_for(path: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=path,
            tofile=path,
        )
    )


def _simulate(
    root: Path,
    settings: Settings,
    result: Resolution,
    change_id: str,
    archive_path: Path,
    change_output: str,
    roadmap_output: str,
) -> Resolution:
    nodes = copy.deepcopy(result.nodes)
    for current in nodes.values():
        current.dependents.clear()
    node = nodes[change_id]
    node.path = archive_path
    node.status = "landed"
    target_hash = fingerprint(change_output)
    for dependent in nodes.values():
        if dependent.active:
            dependent.depends_on = [
                replace(edge, fingerprint=target_hash) if edge.target == change_id else edge
                for edge in dependent.depends_on
            ]
    _compute_dependents(nodes)
    order, cycle = _topo_sort(nodes)
    findings = validate(
        root,
        nodes,
        cycle,
        settings,
        roadmap_override=_strip_generated(roadmap_output),
    )
    return Resolution(nodes=nodes, findings=findings, topo_order=order)


def plan_landing(
    root: Path,
    settings: Settings,
    ref: str,
    *,
    date: str | None = None,
) -> LandingPlan:
    root = root.resolve()
    result = resolve(root, settings)
    if result.errors:
        raise LandingError("preflight-invalid: repository has resolver errors")
    if len(result.topo_order) != len(result.nodes):
        raise LandingError("preflight-invalid: dependency graph contains a cycle")
    change_id, source = _locate_source(root, ref, result.nodes)
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
    new_change = _land_change_text(old_change, day, archive_rel)
    change_hash_before = _file_hash(change_file)
    change_hash_after = _sha(new_change.encode("utf-8"))
    mutations: list[Mutation] = [
        Mutation("write", f"{source_rel}/change.md", None, change_hash_before, change_hash_after, new_change)
    ]
    diff_parts = [_diff_for(f"{source_rel}/change.md", old_change, new_change)]
    target_hash = fingerprint(new_change)
    for dependent in sorted(result.nodes.values(), key=lambda item: item.id):
        if not dependent.active or not dependent.path.is_file():
            continue
        if not any(edge.target == change_id for edge in dependent.depends_on):
            continue
        old = dependent.path.read_text(encoding="utf-8")
        new = _dependent_text(old, change_id, target_hash)
        if new == old:
            continue
        relative = dependent.path.relative_to(root).as_posix()
        mutations.append(Mutation("write", relative, None, _file_hash(dependent.path), _sha(new.encode()), new))
        diff_parts.append(_diff_for(relative, old, new))

    current_roadmap = (root / settings.roadmap).read_text(encoding="utf-8")
    simulated = copy.deepcopy(result)
    simulated.nodes[change_id].status = "landed"
    simulated.nodes[change_id].path = archive
    for current in simulated.nodes.values():
        current.dependents.clear()
    for dependent in simulated.nodes.values():
        if dependent.active:
            dependent.depends_on = [
                replace(edge, fingerprint=target_hash) if edge.target == change_id else edge
                for edge in dependent.depends_on
            ]
    _compute_dependents(simulated.nodes)
    simulated.topo_order, _ = _topo_sort(simulated.nodes)
    roadmap_new = _roadmap_output(current_roadmap, source_rel, archive_rel, render_block(simulated))
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
    final = _simulate(root, settings, result, change_id, archive, new_change, roadmap_new)
    if final.errors:
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
    )


def _journal_payload(plan: LandingPlan, completed: list[int]) -> dict[str, object]:
    payload = plan.as_dict()
    payload["completed"] = completed
    return payload


def _save_journal(path: Path, plan: LandingPlan, completed: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(_journal_payload(plan, completed), indent=2, sort_keys=True) + "\n").encode()
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _load_journal(path: Path) -> tuple[LandingPlan, list[int]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        plan = LandingPlan.from_dict(raw)
        completed = raw.get("completed", [])
        if not isinstance(completed, list) or not all(isinstance(item, int) for item in completed):
            raise LandingError("journal-invalid: completed boundaries are malformed")
        return plan, completed
    except (OSError, json.JSONDecodeError) as exc:
        raise LandingError(f"journal-invalid: {type(exc).__name__}") from None


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _apply_mutation(root: Path, plan: LandingPlan, mutation: Mutation) -> None:
    path = root / mutation.path
    if mutation.kind == "write":
        current = _file_hash(path)
        if current == mutation.after_hash:
            return
        if current != mutation.before_hash or mutation.content is None:
            raise ConcurrentModification(f"concurrent-modification: {mutation.path}")
        _atomic_write(path, mutation.content)
        return
    destination = root / (mutation.destination or "")
    source_present = path.exists()
    destination_present = destination.exists()
    if not source_present and destination_present and _tree_hash(destination) == mutation.after_hash:
        return
    if source_present and destination_present:
        raise LandingError("destination-collision: source and archive both exist")
    if not source_present:
        raise ConcurrentModification(f"concurrent-modification: missing source {mutation.path}")
    if _tree_hash(path) != mutation.before_hash:
        raise ConcurrentModification(f"concurrent-modification: source tree {mutation.path}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if plan.tracking == "tracked":
        try:
            subprocess.run(
                ["git", "-C", str(root), "mv", "--", mutation.path, mutation.destination or ""],
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError):
            raise LandingError("git-move-failed: tracked change could not be archived") from None
    else:
        os.replace(path, destination)


def _capability(settings: Settings) -> tuple[str, Finding | None]:
    if settings.capability_mode == "skip":
        return "live skipped", None
    try:
        result = subprocess.run(
            settings.capability_command,
            cwd=settings.repo_root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "live skipped", Finding("ERROR", "capability-check-failed", type(exc).__name__)
    if result.returncode:
        return "live failed", Finding("ERROR", "capability-check-failed", f"exit {result.returncode}")
    return "live passed", None


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
        matches_id = _as_str(values.get("id")) == change_id
        matches_folder = folder.name.endswith(f"-{change_id}")
        recorded_archive = _as_str(values.get("archive_path"))
        actual_archive = folder.relative_to(root).as_posix()
        metadata_matches = recorded_archive is None or recorded_archive == actual_archive
        if (
            (matches_id or matches_folder)
            and metadata_matches
            and _as_str(values.get("status")) == "landed"
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
    date: str | None = None,
    fault_after: int | None = None,
    on_plan: Callable[[LandingPlan], None] | None = None,
) -> LandingOutcome:
    root = root.resolve()
    result = resolve(root, settings)
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
        plan = plan_landing(root, settings, ref, date=date)
        completed = []
    if on_plan is not None:
        on_plan(plan)
    if dry_run:
        return LandingOutcome(plan, False)
    for index, mutation in enumerate(plan.mutations):
        if index in completed:
            continue
        _apply_mutation(root, plan, mutation)
        completed.append(index)
        completed.sort()
        _save_journal(journal_path, plan, completed)
        if fault_after is not None and len(completed) >= fault_after:
            raise InjectedInterruption("injected-interruption")
    final = resolve(root, settings)
    capability_status, capability_finding = _capability(settings)
    findings = list(final.findings)
    if capability_finding is not None:
        findings.append(capability_finding)
    if any(finding.level == "ERROR" for finding in findings):
        return LandingOutcome(plan, False, tuple(findings), capability_status)
    journal_path.unlink(missing_ok=True)
    return LandingOutcome(plan, False, tuple(findings), capability_status)
