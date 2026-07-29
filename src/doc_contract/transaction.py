"""Hash-guarded, journaled, resumable repository mutations."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, TypeVar

TrackingMode = Literal["tracked", "untracked"]


class TransactionError(RuntimeError):
    """A deterministic, value-free transaction failure."""


class ConcurrentModification(TransactionError):
    pass


class InjectedInterruption(TransactionError):
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
    def from_dict(cls, raw: Mapping[str, object]) -> Mutation:
        kind = raw.get("kind")
        if kind not in {"write", "move"}:
            raise TransactionError("journal-invalid: unknown mutation kind")
        return cls(
            kind=kind,
            path=required_str(raw, "path"),
            destination=optional_str(raw.get("destination")),
            before_hash=required_str(raw, "before_hash"),
            after_hash=required_str(raw, "after_hash"),
            content=optional_str(raw.get("content")),
        )


class TransactionPlan(Protocol):
    tracking: TrackingMode
    mutations: Sequence[Mutation]

    def as_dict(self) -> dict[str, object]: ...


PlanT = TypeVar("PlanT", bound=TransactionPlan)


def required_str(raw: Mapping[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise TransactionError(f"journal-invalid: missing {key}")
    return value


def optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_hash(path: Path) -> str:
    try:
        return sha(path.read_bytes())
    except OSError as exc:
        raise TransactionError(f"input-unavailable: {type(exc).__name__}") from None


def tree_files(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    files: list[Path] = []
    for item in sorted(path.rglob("*")):
        if item.is_symlink() or not item.is_file():
            raise TransactionError("source-tree-invalid: only regular files are supported")
        files.append(item)
    return files


def tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for item in tree_files(path):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash(item).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def tree_hash_with(path: Path, overrides: Mapping[str, bytes]) -> str:
    digest = hashlib.sha256()
    names = {item.relative_to(path).as_posix() for item in tree_files(path)} | set(overrides)
    for name in sorted(names):
        data = overrides.get(name)
        if data is None:
            data = (path / name).read_bytes()
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha(data).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def git_metadata_path(root: Path, relative: str, *, operation: str) -> Path:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--git-path", relative],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        raise TransactionError(f"repo-not-git: {operation} requires a Git worktree") from None
    path = Path(result.stdout.strip())
    return path if path.is_absolute() else root / path


def tracking_mode(root: Path, source: Path) -> TrackingMode:
    relative = source.relative_to(root).as_posix()
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--full-name", "-z", "--", relative],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        raise TransactionError("tracking-state-unavailable: cannot inspect Git index") from None
    tracked = {item for item in result.stdout.decode("utf-8").split("\0") if item}
    files = {item.relative_to(root).as_posix() for item in tree_files(source)}
    if tracked and tracked != files:
        raise TransactionError("partial-tracking: change folder is neither fully tracked nor untracked")
    return "tracked" if tracked else "untracked"


def journal_payload(plan: TransactionPlan, completed: Sequence[int]) -> dict[str, object]:
    payload = plan.as_dict()
    payload["completed"] = list(completed)
    return payload


def save_journal(path: Path, plan: TransactionPlan, completed: Sequence[int]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(journal_payload(plan, completed), indent=2, sort_keys=True) + "\n").encode()
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
    except OSError as exc:
        raise TransactionError(f"journal-unavailable: {type(exc).__name__}") from None


def load_journal(path: Path, parser: Callable[[dict[str, object]], PlanT]) -> tuple[PlanT, list[int]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise TransactionError("journal-invalid: root must be an object")
        plan = parser(raw)
        completed = raw.get("completed", [])
        if not isinstance(completed, list) or not all(isinstance(item, int) for item in completed):
            raise TransactionError("journal-invalid: completed boundaries are malformed")
        return plan, completed
    except (OSError, json.JSONDecodeError) as exc:
        raise TransactionError(f"journal-invalid: {type(exc).__name__}") from None


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def apply_mutation(root: Path, plan: TransactionPlan, mutation: Mutation) -> None:
    path = root / mutation.path
    if mutation.kind == "write":
        current = file_hash(path)
        if current == mutation.after_hash:
            return
        if current != mutation.before_hash or mutation.content is None:
            raise ConcurrentModification(f"concurrent-modification: {mutation.path}")
        atomic_write(path, mutation.content)
        return

    destination = root / (mutation.destination or "")
    source_present = path.exists()
    destination_present = destination.exists()
    if not source_present and destination_present and tree_hash(destination) == mutation.after_hash:
        return
    if source_present and destination_present:
        raise TransactionError("destination-collision: source and archive both exist")
    if not source_present:
        raise ConcurrentModification(f"concurrent-modification: missing source {mutation.path}")
    if tree_hash(path) != mutation.before_hash:
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
            raise TransactionError("git-move-failed: tracked change could not be archived") from None
    else:
        os.replace(path, destination)


def _completed_path(
    mutation: Mutation, mutations: Sequence[Mutation], completed: Sequence[int], index: int
) -> str:
    path = mutation.path
    for later_index in completed:
        if later_index <= index:
            continue
        later = mutations[later_index]
        is_within_move = path == later.path or path.startswith(f"{later.path}/")
        if later.kind != "move" or not is_within_move:
            continue
        suffix = path.removeprefix(later.path).lstrip("/")
        path = "/".join(part for part in (later.destination or "", suffix) if part)
    return path


def _completed_mutation_matches(
    root: Path, mutations: Sequence[Mutation], completed: Sequence[int], index: int
) -> bool:
    """Confirm a journaled boundary still has the exact planned output state."""
    try:
        mutation = mutations[index]
        path = root / _completed_path(mutation, mutations, completed, index)
        if mutation.kind == "write":
            return path.is_file() and file_hash(path) == mutation.after_hash
        destination = root / (mutation.destination or "")
        return (
            not path.exists()
            and destination.is_dir()
            and tree_hash(destination) == mutation.after_hash
        )
    except (OSError, TransactionError):
        return False


def execute_mutations(
    root: Path,
    plan: TransactionPlan,
    journal_path: Path,
    completed: list[int],
    *,
    fault_after: int | None = None,
    save: Callable[[Path, TransactionPlan, Sequence[int]], None] = save_journal,
) -> None:
    if not journal_path.is_file():
        save(journal_path, plan, completed)
    mutation_count = len(plan.mutations)
    for index in completed:
        if index < 0 or index >= mutation_count:
            raise TransactionError("journal-invalid: completed boundary is out of range")
    for index, mutation in enumerate(plan.mutations):
        if index in completed:
            if not _completed_mutation_matches(root, plan.mutations, completed, index):
                raise ConcurrentModification(
                    f"concurrent-modification: completed boundary {mutation.path}"
                )
            continue
        apply_mutation(root, plan, mutation)
        completed.append(index)
        completed.sort()
        save(journal_path, plan, completed)
        if fault_after is not None and len(completed) >= fault_after:
            raise InjectedInterruption("injected-interruption")
