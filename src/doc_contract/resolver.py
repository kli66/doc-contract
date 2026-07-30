"""Resolvable change-DAG — a stdlib resolver + validator for the doc-contract tripwire.

The roadmap DAG used to be prose (a hand-drawn track diagram + scattered "Upstream deps /
Dependents / Files owned" blocks). Nothing could topo-sort it, catch a cycle, spot a
dangling edge, or flag a file-ownership overlap. This module makes the edges a *function of
structured data* — a small YAML front-matter block on each node-bearing doc — so the linkage
qualifies for a tripwire under the kernel's rule ("a doc earns a tripwire only if its content
is a function of code/data"). Plan *wisdom* stays human-judged; only *linkage/consistency*
is enforced here.

Node universe
-------------
* **change** nodes — every `docs/changes/**/*.md` that carries front-matter (so `change.md`,
  `proposal.md`, and the per-item `code-hygiene-fixes/fix-*.md`; companion `tasks.md` /
  `design.md` carry none and are not nodes). Archived folders are nodes too (`status: landed`).
* **adr** nodes — `docs/adr/NNNN-*.md` → id `adr-NNNN`; persistence inferred `frozen` by
  directory (no front-matter churn on append-only decisions).
* **spec** nodes — `docs/spec/*.md` except the two that are root nodes (`capabilities.md`,
  `README.md`); persistence read from a minimal header so every managed doc self-declares its class.
* **root** nodes (`kind="global"`) — every managed doc *outside* changes/adr/spec the repo declares
  in `config.ROOT_NODES`, so none sits loose (the contract/roadmap/glossary, the capability doc, any
  frozen reference the repo wants classified). Persistence is read from each file's own header. The
  `roadmap` member (and, when present, `capabilities`/`agents`) is the association point for the
  global↔node linkage check (see below). All of these are per-repo parameters — this module
  hard-codes none of them; it reads `config`.

Edges are declared **one direction only** (`depends_on`); dependents are *computed*
(Sphinx-Needs' `links_back`), so there is no `blocks:` field to drift.

Validation taxonomy (borrowed from Doorstop)
--------------------------------------------
ERROR (fails the build):
  * `depends_on` an unknown id, or an `adr-NNNN` whose file is missing.
  * a node with no resolvable `persistence` class (the next unclassified static file swept
    in cannot hide).
  * an *active* change node with no `roadmap` line, or a roadmap line whose status token
    contradicts the node's front-matter `status` (the global↔node linkage check — this *is*
    the "every changes/*/ folder has a roadmap line" enforcement a skill cannot provide).
  * absent or invalid active-edge hashes when `edge_fingerprints` is explicitly `required`.
  * invalid or mismatched frozen-document `self_hash` values under every edge policy.
WARN (reported, never fails):
  * a cycle.
  * an invalid advisory edge fingerprint, or a stale valid edge fingerprint under either policy
    (the automated drift signal reconciliation does by hand today).
  * a file-ownership overlap between two *active* change nodes (a real merge hazard).
  * a `requires_status` mismatch (depend on an ADR that must be `accepted`, but isn't).
  * an *orphan* `frozen` reference doc — a `docs/spec/` reference cited by zero live ADRs.
    WARN, **never auto-archived**: "no inbound citation" has two opposite causes (the doc is
    dead → archive, or it is forward-looking reference a decision hasn't cited yet → add the
    citation). The check surfaces; a human classifies.

Fingerprints hash a **canonical form**, never raw bytes — strip the YAML front-matter block
(so back-filling front-matter does not self-invalidate every fingerprint), normalize line
endings to `\n`, strip per-line trailing whitespace, remove boundary blank lines, and emit one
final newline. Prose reflow and Markdown syntax rewrites remain significant. v1 targets are docs
only; a `src/` symbol is never a v1 fingerprint target.
"""

from __future__ import annotations

import copy
import hashlib
import re
import subprocess
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType

from .config import Settings
from .secret_scan import format_finding, scan

# The repo being enforced + the managed-doc node set + the doc-tree layout are the per-project
# parameters — they live in `config.py`, never hard-coded here (that is the invariant/parameter
# split this module's portability rests on). `dag.py` + `doc_tripwire.py` are copied verbatim
# between repos; only `config.py` changes.
PERSISTENCE_CLASSES = frozenset({"frozen", "living", "ephemeral", "deferred"})
CHANGE_STATUSES = frozenset({"proposed", "accepted", "in-progress", "blocked", "landed"})
ACTIVE_STATUSES = frozenset({"proposed", "accepted", "in-progress", "blocked"})

DAG_BEGIN = "<!-- BEGIN GENERATED DAG (regenerate: doc-contract update --repo-root .) -->"
DAG_BEGIN_PREFIX = "<!-- BEGIN GENERATED DAG"
DAG_END = "<!-- END GENERATED DAG -->"

# Roadmap status tokens → canonical node status (only unambiguous markers; absence is not a
# contradiction). Order matters: the most specific marker is matched first.
_STATUS_TOKENS: tuple[tuple[str, str], ...] = (
    ("(blocked", "blocked"),
    ("blocked on", "blocked"),
    ("(in-progress", "in-progress"),
    ("in progress", "in-progress"),
    ("(accepted", "accepted"),
    ("(proposed", "proposed"),
    ("proposed 20", "proposed"),
)


# --------------------------------------------------------------------------- front-matter

_FM_DELIM = re.compile(r"^---\s*$")


def split_front_matter(text: str) -> tuple[str | None, str]:
    """Return (front_matter_block, body). The block excludes the `---` fences; if the file
    does not open with a fence, the front matter is None and body is the whole text."""
    lines = text.splitlines()
    if not lines or not _FM_DELIM.match(lines[0]):
        return None, text
    for i in range(1, len(lines)):
        if _FM_DELIM.match(lines[i]):
            fm = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1 :])
            return fm, body
    return None, text


FMValue = "str | list[str] | dict[str, str]"


def parse_front_matter(text: str) -> dict[str, FMValue] | None:
    """Parse the YAML *subset* this scheme emits — total and stdlib-only (no PyYAML, so the
    resolver stays air-gap-trivial). Three constructs, 2-space indented:

        key: scalar
        key:
          - item            # → list[str]
        key:
          sub: scalar       # → dict[str, str]

    Returns None when there is no front-matter block. Raises ValueError on anything outside
    the grammar, so a malformed header fails loud rather than parsing to garbage.
    """
    fm, _ = split_front_matter(text)
    if fm is None:
        return None
    out: dict[str, FMValue] = {}
    lines = fm.split("\n")
    i = 0
    while i < len(lines):
        raw = lines[i]
        if not raw.strip() or raw.lstrip().startswith("#"):
            i += 1
            continue
        if raw[:1] == " ":
            raise ValueError(f"unexpected indentation at top level: {raw!r}")
        if ":" not in raw:
            raise ValueError(f"expected 'key:' line, got {raw!r}")
        key, _, inline = raw.partition(":")
        key = key.strip()
        inline = inline.strip()
        if inline:
            out[key] = _unquote(inline)
            i += 1
            continue
        # Block follows: collect indented children.
        items: list[str] = []
        mapping: dict[str, str] = {}
        i += 1
        while i < len(lines) and (lines[i][:1] == " " or not lines[i].strip()):
            child = lines[i]
            i += 1
            if not child.strip():
                continue
            body = child.strip()
            if body.startswith("- "):
                items.append(_unquote(body[2:].strip()))
            elif ":" in body:
                sk, _, sv = body.partition(":")
                mapping[sk.strip()] = _unquote(sv.strip())
            else:
                raise ValueError(f"unrecognized block line under {key!r}: {child!r}")
        if items and mapping:
            raise ValueError(f"block under {key!r} mixes list and map forms")
        out[key] = items if items or not mapping else mapping
    return out


def _unquote(s: str) -> str:
    if len(s) >= 2 and s[0] == s[-1] and s[0] in {'"', "'"}:
        return s[1:-1]
    return s


def _as_list(v: FMValue | None) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        return [v]
    raise ValueError(f"expected list, got mapping: {v!r}")


def _as_map(v: FMValue | None) -> dict[str, str]:
    if v is None:
        return {}
    if isinstance(v, dict):
        return v
    raise ValueError(f"expected mapping, got {v!r}")


def _as_str(v: FMValue | None) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    raise ValueError(f"expected scalar, got {v!r}")


# --------------------------------------------------------------------------- canonical hash


def canonical_form(text: str) -> str:
    """The bytes a fingerprint hashes: front-matter stripped, line endings normalized to
    `\\n`, per-line trailing whitespace removed, exactly one final newline."""
    _, body = split_front_matter(text.replace("\r\n", "\n").replace("\r", "\n"))
    stripped = "\n".join(line.rstrip() for line in body.split("\n"))
    return stripped.strip("\n") + "\n"


def fingerprint(text: str) -> str:
    return hashlib.sha256(canonical_form(text).encode("utf-8")).hexdigest()[:16]


class HashState(str, Enum):
    ABSENT = "absent"
    EMPTY = "empty"
    PENDING = "pending"
    INVALID = "invalid"
    VALID = "valid"


def hash_state(value: str | None) -> HashState:
    if value is None:
        return HashState.ABSENT
    if not value.strip():
        return HashState.EMPTY
    if value.strip().upper() == "PENDING":
        return HashState.PENDING
    if not re.fullmatch(r"[0-9a-f]{16}", value.strip()):
        return HashState.INVALID
    return HashState.VALID


# --------------------------------------------------------------------------- model


@dataclass(frozen=True)
class Edge:
    target: str
    fingerprint: str | None = None
    requires_status: str | None = None


@dataclass
class Node:
    id: str
    kind: str  # "change" | "adr" | "spec" | "global" | "archive"
    path: Path
    persistence: str | None
    status: str | None
    track: str | None
    depends_on: list[Edge]
    files_owned: list[str]
    gated_on: str | None
    self_hash: str | None = None  # frozen docs only: hash of own body (immutability tripwire)
    dependents: list[str] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return self.kind == "change" and (self.status or "") in ACTIVE_STATUSES


@dataclass(frozen=True)
class Finding:
    level: str  # "ERROR" | "WARN"
    code: str
    message: str
    subjects: tuple[str, ...] = ()


@dataclass
class Resolution:
    nodes: dict[str, Node]
    findings: list[Finding]
    topo_order: list[str]
    discovery: tuple["DiscoveryRecord", ...] = ()
    document_paths: tuple[Path, ...] = ()

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "ERROR"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "WARN"]


@dataclass(frozen=True)
class DiscoveryRecord:
    node_id: str
    path: str
    included: bool


@dataclass(frozen=True)
class DiscoveryResult:
    nodes: dict[str, Node]
    findings: tuple[Finding, ...]
    records: tuple[DiscoveryRecord, ...]
    document_paths: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class ProjectedDocument:
    path: Path
    content: str


@dataclass(frozen=True, slots=True)
class ProjectedNode:
    id: str
    kind: str
    path: Path
    persistence: str | None
    status: str | None
    track: str | None
    depends_on: tuple[Edge, ...]
    files_owned: tuple[str, ...]
    gated_on: str | None
    self_hash: str | None
    dependents: tuple[str, ...]

    @property
    def active(self) -> bool:
        return self.kind == "change" and (self.status or "") in ACTIVE_STATUSES


@dataclass(frozen=True, slots=True)
class ProjectedResolution:
    nodes: Mapping[str, ProjectedNode]
    findings: tuple[Finding, ...]
    topo_order: tuple[str, ...]
    discovery: tuple["DiscoveryRecord", ...]
    document_paths: tuple[Path, ...]

    @property
    def errors(self) -> tuple[Finding, ...]:
        return tuple(finding for finding in self.findings if finding.level == "ERROR")

    @property
    def warnings(self) -> tuple[Finding, ...]:
        return tuple(finding for finding in self.findings if finding.level == "WARN")


@dataclass(frozen=True, slots=True)
class LandingProjection:
    change_document: ProjectedDocument
    dependent_documents: tuple[ProjectedDocument, ...]
    resolution: ProjectedResolution
    roadmap_block: str

    @property
    def findings(self) -> tuple[Finding, ...]:
        return self.resolution.findings


@dataclass(frozen=True, slots=True)
class TransitionProjection:
    change_document: ProjectedDocument
    dependent_documents: tuple[ProjectedDocument, ...]
    resolution: ProjectedResolution
    roadmap_block: str
    roadmap_text: str
    source_status: str
    destination_status: str
    accepted_at: str | None
    started_at: str | None

    @property
    def findings(self) -> tuple[Finding, ...]:
        return self.resolution.findings


# --------------------------------------------------------------------------- discovery


_DOC_PATHS: dict[str, str] = {
    "adr": "docs/adr",
    "spec": "docs/spec",
    "changes": "docs/changes",
    "archive": "docs/archive",
    "roadmap": "docs/roadmap.md",
}


def _doc_path(root: Path, key: str, settings: Settings | None = None) -> Path:
    """Resolve one doc-tree location (``adr``/``spec``/``changes``/``archive``/``roadmap``)
    under ``root``. The layout is fixed: ``docs/`` at the project root."""
    if key == "roadmap" and settings is not None:
        return root / settings.roadmap
    return root / _DOC_PATHS[key]


def _infer_persistence(root: Path, path: Path, declared: str | None) -> str | None:
    parts = path.resolve().relative_to(root.resolve()).parts
    # `docs/changes/archive/` is change lineage and keeps its declared class;
    # only ADRs and the separate `docs/archive/` tree are directory-frozen.
    if parts[:2] == ("docs", "adr") or parts[:2] == ("docs", "archive"):
        return "frozen"
    return declared


def _tracked_paths(root: Path) -> set[str] | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", "docs"],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return {item for item in result.stdout.decode("utf-8").split("\0") if item}


def discover(
    root: Path,
    settings: Settings,
    *,
    include_untracked: bool = False,
) -> DiscoveryResult:
    nodes: dict[str, Node] = {}
    findings: list[Finding] = []
    records: list[DiscoveryRecord] = []
    document_paths: set[Path] = set()
    tracked_paths = _tracked_paths(root)

    def add(node: Node) -> None:
        if node.id in nodes:
            raise ValueError(f"duplicate node id {node.id!r}: {node.path} vs {nodes[node.id].path}")
        nodes[node.id] = node

    def include_candidate(node_id: str, path: Path) -> bool:
        if tracked_paths is None:
            return True
        relative = path.relative_to(root).as_posix()
        if relative in tracked_paths:
            return True
        records.append(DiscoveryRecord(node_id, relative, include_untracked))
        if include_untracked:
            findings.append(
                Finding(
                    "WARN",
                    "untracked-node-included",
                    f"{node_id} ({relative}) is included provisionally; add it to Git before landing",
                    (node_id,),
                )
            )
            return True
        findings.append(
            Finding(
                "WARN",
                "untracked-node-excluded",
                f"{relative} is untracked and excluded; rerun with --include-untracked to preview it",
                (node_id,),
            )
        )
        return False

    # Root/managed docs first (so a spec/change node can never shadow them); persistence is read
    # from each header, so a missing header trips `missing-persistence` like any other node.
    root_paths: set[Path] = set()
    for nid, rel in settings.root_nodes.items():
        path = root / rel
        if not path.exists():
            continue  # an absent managed doc is simply not a node (deletion is a separate concern)
        root_paths.add(path.resolve())
        document_paths.add(path)
        fm = parse_front_matter(path.read_text(encoding="utf-8")) or {}
        persistence = _as_str(fm.get("persistence"))
        add(
            Node(
                nid,
                "global",
                path,
                persistence,
                None,
                None,
                [],
                [rel],
                None,
                self_hash=_as_str(fm.get("self_hash")),
            )
        )

    # ADRs.
    for adr in sorted(_doc_path(root, "adr").glob("[0-9][0-9][0-9][0-9]-*.md")):
        m = re.match(r"(\d{4})-", adr.name)
        if not m:
            continue
        node_id = f"adr-{m.group(1)}"
        if not include_candidate(node_id, adr):
            continue
        document_paths.add(adr)
        fm = parse_front_matter(adr.read_text(encoding="utf-8")) or {}
        status = (_as_str(fm.get("status")) or "").split()[0] or None
        add(Node(node_id, "adr", adr, "frozen", status, None, [], [], None,
                 self_hash=_as_str(fm.get("self_hash"))))

    # spec/ reference + register (capabilities.md + README.md are root nodes → skip).
    for spec in sorted(_doc_path(root, "spec").glob("*.md")):
        if spec.resolve() in root_paths:
            continue
        if not include_candidate(spec.stem, spec):
            continue
        document_paths.add(spec)
        fm = parse_front_matter(spec.read_text(encoding="utf-8"))
        add(_node_from_change_like(root, spec.stem, "spec", spec, fm or {}))

    # change docs (active + archived) — only those carrying front-matter.
    change_docs = sorted(_doc_path(root, "changes").rglob("*.md"))
    companion_docs: list[Path] = []
    managed_change_folders: set[Path] = set()
    for doc in change_docs:
        text = doc.read_text(encoding="utf-8")
        raw, _ = split_front_matter(text)
        if raw is None:
            companion_docs.append(doc)
            continue
        relative = doc.relative_to(root).as_posix()
        parse_before_filter = (
            tracked_paths is None or relative in tracked_paths or include_untracked
        )
        fm = parse_front_matter(text) if parse_before_filter else None
        provisional_id = (
            _as_str(fm.get("id"))
            if fm is not None
            else doc.parent.name if doc.name in _GENERIC_DOCS else doc.stem
        )
        if not provisional_id:
            raise ValueError(f"change doc has front-matter without an `id`: {doc}")
        if not include_candidate(provisional_id, doc):
            continue
        document_paths.add(doc)
        managed_change_folders.add(doc.parent)
        if fm is None:
            fm = parse_front_matter(text)
            assert fm is not None
        nid = _as_str(fm.get("id"))
        if not nid:
            raise ValueError(f"change doc has front-matter without an `id`: {doc}")
        add(_node_from_change_like(root, nid, "change", doc, fm))

    # Companion Markdown shares the owning change folder's managed boundary but is not a graph
    # node. Reuse the rglob result above so secret scanning does not trigger another traversal.
    for doc in companion_docs:
        if not any(folder == doc.parent or folder in doc.parents for folder in managed_change_folders):
            continue
        relative = doc.relative_to(root).as_posix()
        if tracked_paths is not None and relative not in tracked_paths and not include_untracked:
            continue
        document_paths.add(doc)

    # docs/archive/ lineage — frozen by directory; node-ified so nothing frozen is unguarded.
    for arc in sorted(_doc_path(root, "archive").glob("*.md")):
        if not include_candidate(f"archive-{arc.stem}", arc):
            continue
        document_paths.add(arc)
        fm = parse_front_matter(arc.read_text(encoding="utf-8")) or {}
        nid = _as_str(fm.get("id")) or f"archive-{arc.stem}"
        add(Node(nid, "archive", arc, "frozen", None, None, [], [], None,
                 self_hash=_as_str(fm.get("self_hash"))))

    ordered_paths = tuple(sorted(document_paths, key=lambda path: path.relative_to(root).as_posix()))
    return DiscoveryResult(nodes, tuple(findings), tuple(records), ordered_paths)


def discover_nodes(
    root: Path,
    settings: Settings,
    *,
    include_untracked: bool = False,
) -> dict[str, Node]:
    return discover(root, settings, include_untracked=include_untracked).nodes


def _node_from_change_like(
    root: Path,
    nid: str,
    kind: str,
    path: Path,
    fm: Mapping[str, FMValue],
) -> Node:
    fingerprints = _as_map(fm.get("fingerprints"))
    requires = _as_map(fm.get("requires_status"))
    edges = [
        Edge(t, fingerprints.get(t), requires.get(t)) for t in _as_list(fm.get("depends_on"))
    ]
    persistence = _infer_persistence(root, path, _as_str(fm.get("persistence")))
    return Node(
        id=nid,
        kind=kind,
        path=path,
        persistence=persistence,
        status=_as_str(fm.get("status")),
        track=_as_str(fm.get("track")),
        depends_on=edges,
        files_owned=_as_list(fm.get("files_owned")),
        gated_on=_as_str(fm.get("gated_on")),
        self_hash=_as_str(fm.get("self_hash")),
    )


# --------------------------------------------------------------------------- graph ops


def _compute_dependents(nodes: dict[str, Node]) -> None:
    for n in nodes.values():
        for e in n.depends_on:
            if e.target in nodes:
                nodes[e.target].dependents.append(n.id)


def _topo_sort(nodes: dict[str, Node]) -> tuple[list[str], list[str]]:
    """Kahn's algorithm. Returns (order, cycle_members). Only edges to known nodes count."""
    indeg = {nid: 0 for nid in nodes}
    adj: dict[str, list[str]] = {nid: [] for nid in nodes}
    for n in nodes.values():
        for e in n.depends_on:
            if e.target in nodes:
                adj[e.target].append(n.id)
                indeg[n.id] += 1
    queue = deque(sorted(nid for nid, d in indeg.items() if d == 0))
    order: list[str] = []
    while queue:
        nid = queue.popleft()
        order.append(nid)
        for nxt in sorted(adj[nid]):
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    cycle = sorted(nid for nid in nodes if nid not in order)
    return order, cycle


# --------------------------------------------------------------------------- validation


def _roadmap_text(root: Path, settings: Settings) -> str:
    """The human-maintained roadmap text — the generated DAG block is stripped so the linkage
    checks read the hand-written lines, not the diagram regenerated from the front-matter."""
    p = _doc_path(root, "roadmap", settings)
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8")
    if DAG_BEGIN_PREFIX in text and DAG_END in text:
        text = text[: text.index(DAG_BEGIN_PREFIX)] + text[text.index(DAG_END) + len(DAG_END) :]
    return text


_GENERIC_DOCS = frozenset({"change.md", "proposal.md", "design.md", "tasks.md"})


def locate_change(root: Path, ref: str, nodes: Mapping[str, Node]) -> tuple[str, Path]:
    """Resolve a change ID or repository-relative change folder to its source folder."""
    candidate = Path(ref)
    if candidate.parts and candidate.parts[0] == "docs":
        path = (root / candidate).resolve()
        if not path.is_dir() or root not in path.parents or "changes" not in path.relative_to(root).parts:
            raise ValueError("change-not-found: ref is not an active change folder")
        for doc in sorted(path.glob("*.md")):
            values = parse_front_matter(doc.read_text(encoding="utf-8")) or {}
            change_id = _as_str(values.get("id"))
            node = nodes.get(change_id) if change_id else None
            if change_id and node is not None and node.active:
                return change_id, path
        raise ValueError("change-not-found: folder has no resolvable change id")
    node = nodes.get(ref)
    if node is None or node.kind != "change" or not node.active:
        raise ValueError("change-not-found: ref is not an active change")
    return ref, node.path.parent


def _specific_needle(node: Node) -> str:
    """The string that identifies *this* node in the roadmap: its own basename when the folder
    holds several node-docs (the `fix-*.md` case), else the folder dir-path (when the doc is a
    generic `change.md`/`proposal.md` the folder is the identifier)."""
    if node.path.name in _GENERIC_DOCS:
        return f"docs/changes/{node.path.parent.name}/"
    return node.path.name


def _roadmap_status_for(node: Node, roadmap: str, change_dirs: set[str]) -> str | None:
    """The status token the roadmap asserts for this node, or None if indeterminate. Only a
    line that mentions this node *and no other change folder* counts — a cross-reference line
    that names two folders (e.g. an ad2b line that also cites a code-hygiene file) is ambiguous
    and skipped, so one node's status marker never bleeds onto another."""
    own_dir = f"docs/changes/{node.path.parent.name}/"
    other_dirs = change_dirs - {own_dir}
    specific = _specific_needle(node).lower()
    for line in roadmap.splitlines():
        low = line.lower()
        if specific not in low:
            continue
        if any(od.lower() in low for od in other_dirs):
            continue
        for token, status in _STATUS_TOKENS:
            if token in low:
                return status
    return None


def _has_roadmap_line(node: Node, roadmap: str) -> bool:
    """The folder dir-path (or, for a multi-node folder, the doc basename) appears in the
    roadmap. The bare node id is *not* a fallback — short ids (`fix-b`, `a`) substring-match
    unrelated prose, which would silently satisfy the linkage check it exists to enforce."""
    own_dir = f"docs/changes/{node.path.parent.name}/"
    return own_dir in roadmap or _specific_needle(node) in roadmap


def _adr_citations(root: Path) -> str:
    """Concatenated text of every ADR — the corpus the orphan-check searches for inbound
    citations of a frozen reference doc."""
    chunks: list[str] = []
    for adr in sorted(_doc_path(root, "adr").glob("*.md")):
        chunks.append(adr.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def validate(
    root: Path,
    nodes: dict[str, Node],
    cycle: list[str],
    settings: Settings,
    *,
    roadmap_override: str | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    roadmap = _roadmap_text(root, settings) if roadmap_override is None else roadmap_override
    adr_text = _adr_citations(root)

    # Edges: unknown target / missing ADR / requires_status / review fingerprint provenance.
    for n in sorted(nodes.values(), key=lambda x: x.id):
        for e in n.depends_on:
            target = nodes.get(e.target)
            if target is None:
                findings.append(
                    Finding(
                        "ERROR",
                        "unknown-dependency",
                        f"{n.id} depends_on unknown id {e.target!r}",
                        (n.id, e.target),
                    )
                )
                continue
            if e.target.startswith("adr-") and not target.path.exists():
                findings.append(
                    Finding(
                        "ERROR",
                        "missing-adr",
                        f"{n.id} depends_on {e.target} but {target.path} is missing",
                        (n.id, e.target),
                    )
                )
            if e.requires_status and (target.status or "") != e.requires_status:
                findings.append(
                    Finding(
                        "WARN",
                        "requires-status",
                        f"{n.id} requires {e.target} status={e.requires_status!r} "
                        f"but it is {target.status!r}",
                        (n.id, e.target),
                    )
                )
            state = hash_state(e.fingerprint)
            if n.active and state in {HashState.EMPTY, HashState.PENDING, HashState.INVALID}:
                findings.append(
                    Finding(
                        "ERROR" if settings.edge_fingerprint_policy == "required" else "WARN",
                        f"edge-hash-{state.value}",
                        f"{n.id} → {e.target}: fingerprint is {state.value}; "
                        f"review the target and run `doc-contract stamp {n.id}`",
                        (n.id, e.target),
                    )
                )
            if state == HashState.VALID and n.active and target.path.exists():
                current = fingerprint(target.path.read_text(encoding="utf-8"))
                if current != e.fingerprint:
                    findings.append(
                        Finding(
                            "WARN",
                            "suspect-link",
                            f"{n.id} → {e.target}: target changed since review "
                            f"(recorded {e.fingerprint}, now {current}); re-review and re-stamp",
                            (n.id, e.target),
                        )
                    )
            # Structural dependency edges are always mandatory. Review fingerprints are optional
            # metadata unless the repository explicitly opts into required enforcement.
            if (
                n.active
                and state == HashState.ABSENT
                and settings.edge_fingerprint_policy == "required"
            ):
                findings.append(
                    Finding(
                        "ERROR",
                        "missing-fingerprint",
                        f"{n.id} → {e.target}: active doc-edge has no fingerprint "
                        f"(edge_fingerprints is required — stamp the target's content hash)",
                        (n.id, e.target),
                    )
                )

    # Persistence classification (ERROR — no unclassified managed doc can hide).
    for n in sorted(nodes.values(), key=lambda x: x.id):
        if n.persistence is None:
            findings.append(
                Finding(
                    "ERROR",
                    "missing-persistence",
                    f"{n.id} ({n.path}) declares no `persistence` class",
                    (n.id,),
                )
            )
        elif n.persistence not in PERSISTENCE_CLASSES:
            findings.append(
                Finding(
                    "ERROR",
                    "bad-persistence",
                    f"{n.id} persistence={n.persistence!r} "
                    f"not one of {sorted(PERSISTENCE_CLASSES)}",
                    (n.id,),
                )
            )

    # Change lifecycle is a closed machine-readable set. Missing/unknown values fail closed;
    # archived lineage remains valid through the terminal `landed` state.
    for n in sorted(nodes.values(), key=lambda x: x.id):
        if n.kind == "change" and n.status not in CHANGE_STATUSES:
            findings.append(
                Finding(
                    "ERROR",
                    "unknown-change-status",
                    f"{n.id} has unsupported change status {n.status!r}; "
                    f"expected one of {sorted(CHANGE_STATUSES)}",
                    (n.id,),
                )
            )

    # Frozen-doc immutability (self_hash): a frozen doc records a hash of its own body; a body edit
    # that doesn't re-stamp is tamper → ERROR. A frozen doc with no self_hash → WARN (nudge to stamp
    # on freeze) — not ERROR, so a still-being-drafted frozen-by-directory file isn't hard-blocked.
    for n in sorted(nodes.values(), key=lambda x: x.id):
        if n.persistence != "frozen" or not n.path.exists():
            continue
        state = hash_state(n.self_hash)
        if state == HashState.ABSENT:
            findings.append(
                Finding(
                    "WARN",
                    "unstamped-frozen",
                    f"{n.id} ({n.path.name}) is frozen but records no self_hash",
                    (n.id,),
                )
            )
        elif state in {HashState.EMPTY, HashState.PENDING, HashState.INVALID}:
            findings.append(
                Finding(
                    "ERROR",
                    f"hash-{state.value}",
                    f"{n.id} ({n.path.name}) self_hash is {state.value}; "
                    f"review the frozen document and run `doc-contract stamp {n.id}`",
                    (n.id,),
                )
            )
        elif n.self_hash != fingerprint(n.path.read_text(encoding="utf-8")):
            findings.append(
                Finding(
                    "ERROR",
                    "self-hash-mismatch",
                    f"{n.id} ({n.path.name}): body changed since self_hash was stamped "
                    f"(frozen/append-only) — re-review and re-stamp if the edit was intended",
                    (n.id,),
                )
            )

    # Global↔node linkage (ERROR): every active change node needs a roadmap line + agreeing status.
    change_dirs = {
        f"docs/changes/{n.path.parent.name}/" for n in nodes.values() if n.kind == "change"
    }
    for n in sorted(nodes.values(), key=lambda x: x.id):
        if not n.active:
            continue
        if not _has_roadmap_line(n, roadmap):
            findings.append(
                Finding(
                    "ERROR",
                    "no-roadmap-line",
                    f"active change {n.id} has no line in docs/roadmap.md",
                    (n.id,),
                )
            )

    # Entry preflight: declared ownership and test paths must resolve before a change can land.
    # Proposed changes may name files that do not exist yet; keep that state visible as WARN.
    for n in sorted(nodes.values(), key=lambda x: x.id):
        if not n.active:
            continue
        for relative in sorted(set(n.files_owned)):
            if (root / relative).exists():
                continue
            findings.append(
                Finding(
                    "WARN",
                    "owned-file-missing",
                    f"{n.id} declares missing owned path {relative}; create it or update files_owned",
                    (n.id,),
                )
            )
            continue
        rstatus = _roadmap_status_for(n, roadmap, change_dirs)
        if rstatus is not None and rstatus != n.status:
            findings.append(
                Finding(
                    "ERROR",
                    "roadmap-status-mismatch",
                    f"{n.id}: front-matter status={n.status!r} but roadmap line reads {rstatus!r}",
                    (n.id,),
                )
            )

    # Cycle (WARN).
    if cycle:
        findings.append(
            Finding("WARN", "cycle", f"dependency cycle among: {cycle}", tuple(cycle))
        )

    # File-ownership overlap among IN-PROGRESS change nodes (WARN — real merge hazard). A merge
    # conflict needs two branches editing one file *concurrently*, i.e. two `in-progress` changes;
    # `proposed`/`blocked` changes are plans, and their `files_owned` is a forecast — forecasts
    # overlapping is expected, not a hazard. So the check stays quiet through planning and fires the
    # moment two changes are actually being worked at once (which is when parallel dispatch marks
    # them in-progress). Widen to `n.active` only if you want overlap visible pre-dispatch.
    owners: dict[str, list[str]] = {}
    for n in nodes.values():
        if n.kind != "change" or n.status != "in-progress":
            continue
        for f in n.files_owned:
            owners.setdefault(f, []).append(n.id)
    for path, owning in sorted(owners.items()):
        if len(owning) > 1:
            findings.append(
                Finding(
                    "WARN",
                    "ownership-overlap",
                    f"{path} claimed by concurrent in-progress changes: {sorted(owning)}",
                    tuple(sorted(owning)),
                )
            )

    # Orphan frozen-reference (WARN, never auto-archive).
    for n in sorted(nodes.values(), key=lambda x: x.id):
        if n.kind != "spec" or n.persistence != "frozen":
            continue
        if n.path.name not in adr_text and n.id not in adr_text:
            findings.append(
                Finding(
                    "WARN",
                    "orphan-reference",
                    f"frozen reference {n.path.name} is cited by zero live ADRs — a human "
                    f"decides: archive (dead) or cite it (forward-looking reference)",
                    (n.id,),
                )
            )

    return findings


def resolve(
    root: Path,
    settings: Settings,
    *,
    include_untracked: bool = False,
) -> Resolution:
    root = root.resolve()
    boundary_findings: list[Finding] = []
    if not root.is_dir():
        boundary_findings.append(
            Finding("ERROR", "repo-root-mismatch", f"repository root is unavailable: {root}")
        )
        return Resolution(nodes={}, findings=boundary_findings, topo_order=[])
    roadmap = _doc_path(root, "roadmap", settings)
    if not roadmap.is_file():
        boundary_findings.append(
            Finding("ERROR", "repo-root-mismatch", f"required roadmap is missing: {settings.roadmap}")
        )
    for node_id in sorted(settings.required_root_ids):
        relative = settings.root_nodes[node_id]
        if not (root / relative).is_file():
            boundary_findings.append(
                Finding(
                    "ERROR",
                    "required-root-missing",
                    f"required root node {node_id!r} is missing: {relative}",
                )
            )
    for node_id in sorted(settings.optional_root_ids):
        relative = settings.root_nodes[node_id]
        if not (root / relative).is_file():
            boundary_findings.append(
                Finding(
                    "WARN",
                    "optional-root-missing",
                    f"optional root node {node_id!r} is not present: {relative}",
                )
            )

    discovery = discover(root, settings, include_untracked=include_untracked)
    nodes = discovery.nodes
    if not nodes:
        boundary_findings.append(
            Finding("ERROR", "repo-root-mismatch", "target repository resolved zero nodes")
        )
    _compute_dependents(nodes)
    order, cycle = _topo_sort(nodes)
    findings = boundary_findings + list(discovery.findings) + validate(
        root, nodes, cycle, settings
    )
    findings.extend(
        Finding("ERROR", "secret-detected", format_finding(secret))
        for secret in scan(
            discovery.document_paths,
            root=root,
            secret_env_names=settings.additional_environment_names,
        )
    )
    return Resolution(
        nodes=nodes,
        findings=findings,
        topo_order=order,
        discovery=discovery.records,
        document_paths=discovery.document_paths,
    )


# --------------------------------------------------------------------------- Mermaid


def render_mermaid(res: Resolution) -> str:
    """A deterministic `flowchart TD` of the change-DAG: every change node plus any node that
    is the target of a change edge. `prereq --> dependent`."""

    def safe(nid: str) -> str:
        return re.sub(r"[^0-9A-Za-z_]", "_", nid)

    change_ids = {n.id for n in res.nodes.values() if n.kind == "change"}
    edges: list[tuple[str, str]] = []
    shown: set[str] = set(change_ids)
    for n in res.nodes.values():
        if n.kind != "change":
            continue
        for e in n.depends_on:
            if e.target in res.nodes:
                edges.append((e.target, n.id))
                shown.add(e.target)
    lines = ["flowchart TD"]
    for nid in sorted(shown):
        node = res.nodes[nid]
        suffix = f" ({node.status})" if node.status else ""
        lines.append(f"    {safe(nid)}[\"{nid}{suffix}\"]")
    for src, dst in sorted(set(edges)):
        lines.append(f"    {safe(src)} --> {safe(dst)}")
    return "\n".join(lines)


def render_block(res: Resolution) -> str:
    return f"{DAG_BEGIN}\n```mermaid\n{render_mermaid(res)}\n```\n{DAG_END}"


def _landed_change_text(text: str, landed_at: str, archive_path: str) -> str:
    values = parse_front_matter(text)
    if values is None:
        raise ValueError("change-invalid: missing front matter")
    values["status"] = "landed"
    values["landed_at"] = landed_at
    values["archive_path"] = archive_path
    _, body = split_front_matter(text)
    body = re.sub(
        r"^Status:.*$",
        f"Status: Landed · {landed_at}",
        body,
        count=1,
        flags=re.MULTILINE,
    )
    return _render_front_matter(values, body)


def _refreshed_dependent_text(text: str, change_id: str, target_hash: str) -> str:
    values = parse_front_matter(text)
    if values is None:
        raise ValueError("dependent-invalid: missing front matter")
    fingerprints = _as_map(values.get("fingerprints"))
    if fingerprints.get(change_id) == target_hash:
        return text
    fingerprints[change_id] = target_hash
    values["fingerprints"] = fingerprints
    _, body = split_front_matter(text)
    return _render_front_matter(values, body)


def _transition_change_text(
    text: str,
    *,
    action: str,
    transition_date: str,
) -> tuple[str, str | None, str | None]:
    values = parse_front_matter(text)
    if values is None:
        raise ValueError("change-invalid: missing front matter")
    accepted_at = _as_str(values.get("accepted_at"))
    started_at = _as_str(values.get("started_at"))
    _, body = split_front_matter(text)
    if action == "accept":
        values["status"] = "accepted"
        values["accepted_at"] = transition_date
        accepted_at = transition_date
        body_line = f"Status: Accepted · Accepted {transition_date}"
    elif action == "begin":
        values["status"] = "in-progress"
        values["started_at"] = transition_date
        started_at = transition_date
        body_line = f"Status: In progress · Started {transition_date}"
        if accepted_at is not None:
            body_line = f"Status: In progress · Accepted {accepted_at} · Started {transition_date}"
    else:
        raise ValueError(f"transition-invalid: unsupported action {action!r}")
    body = re.sub(r"^Status:.*$", body_line, body, count=1, flags=re.MULTILINE)
    return _render_front_matter(values, body), accepted_at, started_at


def _without_generated_roadmap(text: str) -> str:
    if DAG_BEGIN_PREFIX in text and DAG_END in text:
        return text[: text.index(DAG_BEGIN_PREFIX)] + text[text.index(DAG_END) + len(DAG_END) :]
    return text


def _roadmap_transition_text(
    text: str,
    *,
    node: Node,
    destination_status: str,
    change_dirs: set[str],
) -> str:
    if DAG_BEGIN_PREFIX not in text or DAG_END not in text:
        raise ValueError("roadmap-invalid: generated DAG markers are missing")
    own_dir = f"docs/changes/{node.path.parent.name}/"
    specific = _specific_needle(node).lower()
    lines = text.splitlines(keepends=True)
    matched = False
    for index, line in enumerate(lines):
        low = line.lower()
        if specific not in low or any(
            other.lower() in low for other in change_dirs - {own_dir}
        ):
            continue
        if DAG_BEGIN_PREFIX in line:
            continue
        lines[index] = re.sub(
            r"\((?:proposed|accepted|in-progress|blocked)\)",
            f"({destination_status})",
            line,
            count=1,
            flags=re.IGNORECASE,
        )
        matched = True
        break
    if not matched:
        raise ValueError(f"roadmap-invalid: no roadmap line for {node.id}")
    return "".join(lines)


def _projected_resolution(result: Resolution) -> ProjectedResolution:
    nodes = {
        node_id: ProjectedNode(
            id=node.id,
            kind=node.kind,
            path=node.path,
            persistence=node.persistence,
            status=node.status,
            track=node.track,
            depends_on=tuple(node.depends_on),
            files_owned=tuple(node.files_owned),
            gated_on=node.gated_on,
            self_hash=node.self_hash,
            dependents=tuple(node.dependents),
        )
        for node_id, node in result.nodes.items()
    }
    return ProjectedResolution(
        nodes=MappingProxyType(nodes),
        findings=tuple(result.findings),
        topo_order=tuple(result.topo_order),
        discovery=tuple(result.discovery),
        document_paths=tuple(result.document_paths),
    )


def project_landing(
    root: Path,
    settings: Settings,
    result: Resolution,
    *,
    change_id: str,
    archive_path: Path,
    archive_relative: str,
    landed_at: str,
    planned_roadmap_text: str,
) -> LandingProjection:
    """Project one complete landed document-graph state without mutating caller-owned input."""
    nodes = copy.deepcopy(result.nodes)
    try:
        change = nodes[change_id]
    except KeyError:
        raise ValueError(f"change-invalid: unknown change id {change_id!r}") from None
    if not change.path.is_file():
        raise ValueError("change-invalid: change document is missing")

    change_text = _landed_change_text(
        change.path.read_text(encoding="utf-8"), landed_at, archive_relative
    )
    target_hash = fingerprint(change_text)
    change.path = archive_path
    change.status = "landed"

    dependent_documents: list[ProjectedDocument] = []
    for node in sorted(nodes.values(), key=lambda item: item.id):
        node.dependents.clear()
        if not node.active or not any(edge.target == change_id for edge in node.depends_on):
            continue
        node.depends_on = [
            Edge(edge.target, target_hash, edge.requires_status)
            if edge.target == change_id
            else edge
            for edge in node.depends_on
        ]
        if node.path.is_file():
            content = _refreshed_dependent_text(
                node.path.read_text(encoding="utf-8"), change_id, target_hash
            )
            dependent_documents.append(ProjectedDocument(node.path, content))

    _compute_dependents(nodes)
    order, cycle = _topo_sort(nodes)
    findings = validate(
        root,
        nodes,
        cycle,
        settings,
        roadmap_override=_without_generated_roadmap(planned_roadmap_text),
    )
    transitioned = Resolution(
        nodes=nodes,
        findings=findings,
        topo_order=order,
        discovery=result.discovery,
        document_paths=result.document_paths,
    )
    return LandingProjection(
        change_document=ProjectedDocument(archive_path, change_text),
        dependent_documents=tuple(dependent_documents),
        resolution=_projected_resolution(transitioned),
        roadmap_block=render_block(transitioned),
    )


def project_transition(
    root: Path,
    settings: Settings,
    result: Resolution,
    *,
    change_id: str,
    action: str,
    transition_date: str,
    planned_roadmap_text: str | None = None,
) -> TransitionProjection:
    """Project an explicit accept/begin transition without mutating the input resolution."""
    nodes = copy.deepcopy(result.nodes)
    try:
        change = nodes[change_id]
    except KeyError:
        raise ValueError(f"change-invalid: unknown change id {change_id!r}") from None
    if change.kind != "change" or not change.path.is_file():
        raise ValueError(f"change-invalid: unknown change id {change_id!r}")
    old_status = change.status
    if old_status is None:
        raise ValueError(f"change-status-invalid: {change_id} has no status")
    destination = {"accept": "accepted", "begin": "in-progress"}.get(action)
    if destination is None:
        raise ValueError(f"transition-invalid: unsupported action {action!r}")
    new_text, accepted_at, started_at = _transition_change_text(
        change.path.read_text(encoding="utf-8"), action=action, transition_date=transition_date
    )
    target_hash = fingerprint(new_text)
    change.status = destination
    dependent_documents: list[ProjectedDocument] = []
    for node in sorted(nodes.values(), key=lambda item: item.id):
        node.dependents.clear()
        if not node.active or not any(edge.target == change_id for edge in node.depends_on):
            continue
        node.depends_on = [
            Edge(edge.target, target_hash, edge.requires_status)
            if edge.target == change_id
            else edge
            for edge in node.depends_on
        ]
        if node.path.is_file():
            dependent_documents.append(
                ProjectedDocument(
                    node.path,
                    _refreshed_dependent_text(
                        node.path.read_text(encoding="utf-8"), change_id, target_hash
                    ),
                )
            )
    _compute_dependents(nodes)
    order, cycle = _topo_sort(nodes)
    roadmap = planned_roadmap_text or (root / settings.roadmap).read_text(encoding="utf-8")
    change_dirs = {
        f"docs/changes/{node.path.parent.name}/" for node in nodes.values() if node.kind == "change"
    }
    roadmap = _roadmap_transition_text(
        roadmap,
        node=change,
        destination_status=destination,
        change_dirs=change_dirs,
    )
    findings = validate(
        root,
        nodes,
        cycle,
        settings,
        roadmap_override=_without_generated_roadmap(roadmap),
    )
    transitioned = Resolution(
        nodes=nodes,
        findings=findings,
        topo_order=order,
        discovery=result.discovery,
        document_paths=result.document_paths,
    )
    return TransitionProjection(
        change_document=ProjectedDocument(change.path, new_text),
        dependent_documents=tuple(dependent_documents),
        resolution=_projected_resolution(transitioned),
        roadmap_block=render_block(transitioned),
        roadmap_text=roadmap,
        source_status=old_status,
        destination_status=destination,
        accepted_at=accepted_at,
        started_at=started_at,
    )


def update_roadmap(
    root: Path,
    settings: Settings,
    *,
    include_untracked: bool = False,
) -> bool:
    """Rewrite (or, on first run, fail with guidance to insert) the generated DAG block in
    docs/roadmap.md. Returns True if the file changed."""
    res = resolve(root, settings, include_untracked=include_untracked)
    block = render_block(res)
    path = _doc_path(root, "roadmap", settings)
    text = path.read_text(encoding="utf-8")
    if DAG_BEGIN_PREFIX in text and DAG_END in text:
        pre = text[: text.index(DAG_BEGIN_PREFIX)]
        post = text[text.index(DAG_END) + len(DAG_END) :]
        new = pre + block + post
    else:
        raise SystemExit(
            f"no generated-DAG markers in {path}; insert this block where the diagram should "
            f"live, then re-run update:\n\n{block}\n"
        )
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def _render_front_matter(values: Mapping[str, FMValue], body: str) -> str:
    lines = ["---"]
    for key, value in values.items():
        if isinstance(value, str):
            lines.append(f"{key}: {value}")
        elif isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {item}" for item in value)
        else:
            lines.append(f"{key}:")
            lines.extend(f"  {item_key}: {item}" for item_key, item in value.items())
    lines.extend(["---", body.lstrip("\n")])
    return "\n".join(lines).rstrip() + "\n"


def stamp_node(root: Path, settings: Settings, node_id: str) -> bool:
    """Refresh one node's dependency fingerprints and, when frozen, its self hash."""
    nodes = discover_nodes(root.resolve(), settings)
    node = nodes.get(node_id)
    if node is None:
        raise ValueError(f"unknown node id {node_id!r}")
    text = node.path.read_text(encoding="utf-8")
    raw, body = split_front_matter(text)
    if raw is None:
        raise ValueError(f"node {node_id!r} has no front matter")
    values = parse_front_matter(text) or {}
    changed = False

    if node.active and node.depends_on:
        fingerprints = _as_map(values.get("fingerprints"))
        refreshed = dict(fingerprints)
        for edge in node.depends_on:
            target = nodes.get(edge.target)
            if target is None or not target.path.is_file():
                continue
            refreshed[edge.target] = fingerprint(target.path.read_text(encoding="utf-8"))
        if refreshed != fingerprints:
            values["fingerprints"] = refreshed
            changed = True

    if node.persistence == "frozen":
        current = fingerprint(text)
        if _as_str(values.get("self_hash")) != current:
            values["self_hash"] = current
            changed = True

    if not node.active and node.persistence != "frozen":
        raise ValueError(f"node {node_id!r} has no stampable contract")
    if changed:
        node.path.write_text(_render_front_matter(values, body), encoding="utf-8")
    return changed
