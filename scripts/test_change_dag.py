"""The change-DAG tripwire — the second enforced-living surface (alongside `capabilities.md`).

ERROR-level findings fail the build; WARN-level are reported but tolerated. The real-corpus
test pins the live `docs/` tree (it must parse with zero ERROR); the crafted-fixture tests pin
each check in isolation, so the strict ERROR/WARN semantics are exercised deterministically
without depending on the prose of the real roadmap.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import config
import dag
from dag import PERSISTENCE_CLASSES, REPO_ROOT, Finding, fingerprint, resolve

# --------------------------------------------------------------------------- real corpus
# These run against the *installing* repo's corpus, driven entirely by `config` — no repo-specific
# names are baked in, so the file copies verbatim between repos. Repo-specific corpus regressions
# (e.g. "doc X must stay cited") live in that repo's own tests/, not here.


def test_real_corpus_has_no_errors() -> None:
    res = resolve(REPO_ROOT)
    assert not res.errors, "live doc-DAG has ERROR-level findings:\n" + "\n".join(
        f"  [{f.code}] {f.message}" for f in res.errors
    )


def test_capability_doc_is_one_node_not_duplicated() -> None:
    """The capability doc (whichever `config.CAPABILITY_DOC` names) is code-coupled via its own
    tripwire; the DAG must record it at most once (single-canonical-owner). Skipped if the repo
    declares no capability doc / it isn't present."""
    cap_path = (REPO_ROOT / config.CAPABILITY_DOC).resolve()
    if not cap_path.exists():
        return
    res = resolve(REPO_ROOT)
    matches = [n for n in res.nodes.values() if n.path.resolve() == cap_path]
    assert len(matches) == 1, f"{config.CAPABILITY_DOC} backs {len(matches)} nodes, expected 1"


# --------------------------------------------------------------------------- fixtures


def _write(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _fm(
    nid: str,
    *,
    status: str = "proposed",
    persistence: str | None = "ephemeral",
    depends: list[str] | None = None,
    files: list[str] | None = None,
    fingerprints: dict[str, str] | None = None,
    body: str = "Body.",
) -> str:
    lines = [f"id: {nid}"]
    if persistence is not None:
        lines.append(f"persistence: {persistence}")
    lines.append(f"status: {status}")
    lines.append("track: t")
    if depends:
        lines.append("depends_on:")
        lines += [f"  - {d}" for d in depends]
    if files:
        lines.append("files_owned:")
        lines += [f"  - {f}" for f in files]
    if fingerprints:
        lines.append("fingerprints:")
        lines += [f"  {k}: {v}" for k, v in fingerprints.items()]
    return "---\n" + "\n".join(lines) + "\n---\n\n# " + nid + "\n\n" + body + "\n"


_ROADMAP_HEAD = "---\npersistence: living\n---\n\n"


def _roadmap(*entries: str) -> str:
    body = "\n".join(f"- `docs/changes/{e}/` {tag}" for e, tag in (x.split("|") for x in entries))
    return _ROADMAP_HEAD + "# roadmap\n\n" + body + "\n"


def _codes(findings: list[Finding], level: str) -> set[str]:
    return {f.code for f in findings if f.level == level}


def test_dangling_dependency_is_error(tmp_path: Path) -> None:
    _write(tmp_path, "docs/changes/a/change.md", _fm("a", depends=["does-not-exist"]))
    _write(tmp_path, "docs/roadmap.md", _roadmap("a|(proposed)"))
    res = resolve(tmp_path)
    assert "unknown-dependency" in _codes(res.errors, "ERROR")


def test_missing_adr_file_is_error(tmp_path: Path) -> None:
    _write(tmp_path, "docs/changes/a/change.md", _fm("a", depends=["adr-9999"]))
    _write(tmp_path, "docs/roadmap.md", _roadmap("a|(proposed)"))
    res = resolve(tmp_path)
    # adr-9999 has no file → it is an unknown id (no ADR node created for a missing file).
    assert "unknown-dependency" in _codes(res.errors, "ERROR")


def test_cycle_is_warn_not_error(tmp_path: Path) -> None:
    # landed (inactive) so the cyclic edges don't also trip missing-fingerprint — cycle
    # detection is status-agnostic, so this still exercises the cycle path cleanly.
    _write(tmp_path, "docs/changes/a/change.md", _fm("a", status="landed", depends=["b"]))
    _write(tmp_path, "docs/changes/b/change.md", _fm("b", status="landed", depends=["a"]))
    _write(tmp_path, "docs/roadmap.md", _roadmap("a|(landed)", "b|(landed)"))
    res = resolve(tmp_path)
    assert not res.errors
    assert "cycle" in _codes(res.warnings, "WARN")


def test_ownership_overlap_is_warn_only_when_concurrent(tmp_path: Path) -> None:
    # Two IN-PROGRESS changes sharing a file = a live merge hazard → WARN.
    _write(tmp_path, "docs/changes/a/change.md", _fm("a", status="in-progress", files=["src/x.py"]))
    _write(tmp_path, "docs/changes/b/change.md", _fm("b", status="in-progress", files=["src/x.py"]))
    _write(tmp_path, "docs/roadmap.md", _roadmap("a|(in-progress)", "b|(in-progress)"))
    res = resolve(tmp_path)
    assert not res.errors
    assert "ownership-overlap" in _codes(res.warnings, "WARN")


def test_ownership_overlap_quiet_while_only_planned(tmp_path: Path) -> None:
    # Same files, but both merely `proposed` (a forecast, not a worktree) → no hazard, no WARN.
    _write(tmp_path, "docs/changes/a/change.md", _fm("a", files=["src/x.py"]))
    _write(tmp_path, "docs/changes/b/change.md", _fm("b", files=["src/x.py"]))
    _write(tmp_path, "docs/roadmap.md", _roadmap("a|(proposed)", "b|(proposed)"))
    res = resolve(tmp_path)
    assert not res.errors
    assert "ownership-overlap" not in _codes(res.warnings, "WARN")


def test_missing_roadmap_line_is_error(tmp_path: Path) -> None:
    _write(tmp_path, "docs/changes/a/change.md", _fm("a"))
    _write(tmp_path, "docs/roadmap.md", _ROADMAP_HEAD + "# roadmap\n\nnothing about it\n")
    res = resolve(tmp_path)
    assert "no-roadmap-line" in _codes(res.errors, "ERROR")


def test_archived_change_keeps_declared_ephemeral_persistence(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "docs/changes/archive/2026-07-23-landed/change.md",
        _fm("landed", status="landed", persistence="ephemeral"),
    )
    _write(tmp_path, "docs/roadmap.md", _ROADMAP_HEAD + "# roadmap\n")
    res = resolve(tmp_path)
    assert res.nodes["landed"].persistence == "ephemeral"
    assert "unstamped-frozen" not in _codes(res.warnings, "WARN")


def test_docs_archive_remains_frozen_and_tamper_guarded(tmp_path: Path) -> None:
    body = "---\n# reference\n\nBODY\n"
    stamp = fingerprint(body)
    reference = _write(
        tmp_path,
        "docs/archive/reference.md",
        f"---\nself_hash: {stamp}\n---\n# reference\n\nBODY\n",
    )
    _write(tmp_path, "docs/roadmap.md", _ROADMAP_HEAD + "# roadmap\n")
    reference.write_text(reference.read_text(encoding="utf-8") + "EDIT\n", encoding="utf-8")
    res = resolve(tmp_path)
    assert "self-hash-mismatch" in _codes(res.errors, "ERROR")


def test_roadmap_status_mismatch_is_error(tmp_path: Path) -> None:
    _write(tmp_path, "docs/changes/a/change.md", _fm("a", status="proposed"))
    _write(tmp_path, "docs/roadmap.md", _roadmap("a|(blocked)"))
    res = resolve(tmp_path)
    assert "roadmap-status-mismatch" in _codes(res.errors, "ERROR")


def test_cross_reference_line_does_not_bleed_status(tmp_path: Path) -> None:
    """A single roadmap line that names two change folders is ambiguous and must not let one
    node's status marker contaminate the other."""
    _write(tmp_path, "docs/changes/a/change.md", _fm("a", status="proposed"))
    _write(tmp_path, "docs/changes/b/change.md", _fm("b", status="proposed"))
    # One line names b with a (blocked) marker *and* references a's folder — ambiguous for a.
    _write(
        tmp_path,
        "docs/roadmap.md",
        _ROADMAP_HEAD + "# roadmap\n\n- `docs/changes/b/` (blocked); see also `docs/changes/a/`\n"
        "- `docs/changes/a/` (proposed)\n",
    )
    res = resolve(tmp_path)
    assert "roadmap-status-mismatch" not in _codes(res.errors, "ERROR")


def test_missing_persistence_is_error(tmp_path: Path) -> None:
    _write(tmp_path, "docs/changes/a/change.md", _fm("a", persistence=None))
    _write(tmp_path, "docs/roadmap.md", _roadmap("a|(proposed)"))
    res = resolve(tmp_path)
    assert "missing-persistence" in _codes(res.errors, "ERROR")


def test_bad_persistence_value_is_error(tmp_path: Path) -> None:
    _write(tmp_path, "docs/changes/a/change.md", _fm("a", persistence="forzen"))
    _write(tmp_path, "docs/roadmap.md", _roadmap("a|(proposed)"))
    res = resolve(tmp_path)
    assert "bad-persistence" in _codes(res.errors, "ERROR")


def test_orphan_frozen_reference_is_warn_not_archived(tmp_path: Path) -> None:
    _write(tmp_path, "docs/adr/0001-x.md", "---\nstatus: accepted\n---\n# x\n\ncites used.md\n")
    _write(tmp_path, "docs/spec/used.md", "---\npersistence: frozen\n---\n# used\n")
    _write(tmp_path, "docs/spec/orphan.md", "---\npersistence: frozen\n---\n# orphan\n")
    _write(tmp_path, "docs/roadmap.md", _ROADMAP_HEAD + "# roadmap\n")
    res = resolve(tmp_path)
    assert not res.errors  # orphan is WARN, never a hard fail (a human classifies it)
    orphans = [f.message for f in res.warnings if f.code == "orphan-reference"]
    assert any("orphan.md" in m for m in orphans)
    assert not any("used.md" in m for m in orphans)


def test_fingerprint_ignores_front_matter_but_catches_body_change(tmp_path: Path) -> None:
    target = _write(tmp_path, "docs/changes/t/change.md", _fm("t", body="ORIGINAL BODY"))
    fp = fingerprint(target.read_text(encoding="utf-8"))
    _write(tmp_path, "docs/changes/s/change.md", _fm("s", depends=["t"], fingerprints={"t": fp}))
    _write(tmp_path, "docs/roadmap.md", _roadmap("t|(proposed)", "s|(proposed)"))

    # Baseline: fingerprint matches → no suspect link.
    res = resolve(tmp_path)
    assert "suspect-link" not in _codes(res.warnings, "WARN")

    # (a) Adding front-matter to the target must NOT trip suspect (canonical form strips it) —
    # this is the back-fill self-invalidation defence.
    target.write_text(
        _fm("t", body="ORIGINAL BODY", files=["src/extra.py"]), encoding="utf-8"
    )
    res = resolve(tmp_path)
    assert "suspect-link" not in _codes(res.warnings, "WARN")

    # (b) Changing the target's body MUST trip suspect.
    target.write_text(_fm("t", body="REWRITTEN BODY"), encoding="utf-8")
    res = resolve(tmp_path)
    assert "suspect-link" in _codes(res.warnings, "WARN")


def test_landed_change_fingerprint_is_not_suspect(tmp_path: Path) -> None:
    """A landed change's edge fingerprint is lineage, not a live drift signal — so a target that
    moved on afterwards must not perpetually flag suspect on the archived change."""
    target = _write(tmp_path, "docs/changes/t/change.md", _fm("t", status="landed", body="V1"))
    fp = fingerprint(target.read_text(encoding="utf-8"))
    _write(
        tmp_path,
        "docs/changes/s/change.md",
        _fm("s", status="landed", depends=["t"], fingerprints={"t": fp}),
    )
    target.write_text(_fm("t", status="landed", body="MOVED ON"), encoding="utf-8")
    res = resolve(tmp_path)
    assert "suspect-link" not in _codes(res.warnings, "WARN")


def test_root_docs_are_classified_nodes() -> None:
    """Every managed doc the repo declares in `config.ROOT_NODES` that exists on disk is folded into
    the node universe as a `global` node and self-declares a valid persistence class — so no managed
    doc sits loose (the repo-wide guarantee). Config-driven, so it holds for any installing repo."""
    res = resolve(REPO_ROOT)
    for nid, rel in config.ROOT_NODES.items():
        if not (REPO_ROOT / rel).exists():
            continue  # an absent managed doc is simply not a node (deletion is a separate concern)
        node = res.nodes.get(nid)
        assert node is not None and node.kind == "global", f"root node {nid} missing"
        assert node.persistence in PERSISTENCE_CLASSES, nid


def test_root_doc_missing_persistence_is_error(tmp_path: Path) -> None:
    """A managed root doc with no `persistence` header trips the same ERROR as any other node —
    an unclassified static file can no longer hide, repo-wide."""
    _write(tmp_path, "AGENTS.md", "# contract with no front-matter\n")
    res = resolve(tmp_path)
    assert "missing-persistence" in _codes(res.errors, "ERROR")


def test_edge_fingerprint_policy_defaults_advisory_and_supports_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The legacy adapter reads the same advisory/required policy seam as the package."""
    adr = _write(tmp_path, "docs/adr/0001-x.md", "---\nstatus: accepted\n---\n# x\n")
    _write(tmp_path, "docs/roadmap.md", _roadmap("a|(proposed)"))
    _write(tmp_path, "docs/changes/a/change.md", _fm("a", depends=["adr-0001"]))
    assert config.EDGE_FINGERPRINT_POLICY == "advisory"
    assert "missing-fingerprint" not in _codes(resolve(tmp_path).findings, "ERROR")
    legacy_settings = dag._settings(tmp_path)
    assert legacy_settings.repo_root == tmp_path.resolve()
    with pytest.raises(TypeError):
        legacy_settings.root_nodes["other"] = "docs/other.md"  # type: ignore[index]

    monkeypatch.setattr(config, "EDGE_FINGERPRINT_POLICY", "required")
    assert "missing-fingerprint" in _codes(resolve(tmp_path).errors, "ERROR")

    monkeypatch.setattr(config, "EDGE_FINGERPRINT_POLICY", "strict")
    with pytest.raises(ValueError, match="edge_fingerprint_policy"):
        resolve(tmp_path)

    monkeypatch.setattr(config, "EDGE_FINGERPRINT_POLICY", "required")

    fp = fingerprint(adr.read_text(encoding="utf-8"))
    _write(
        tmp_path,
        "docs/changes/a/change.md",
        _fm("a", depends=["adr-0001"], fingerprints={"adr-0001": fp}),
    )
    assert "missing-fingerprint" not in _codes(resolve(tmp_path).errors, "ERROR")


def test_frozen_self_hash_immutability(tmp_path: Path) -> None:
    """A frozen doc's self_hash guards its body: missing → WARN (nudge), body edit → ERROR, while a
    front-matter-only change never trips (front-matter is excluded from the hash)."""
    _write(tmp_path, "docs/roadmap.md", _ROADMAP_HEAD + "# roadmap\n")
    ref = _write(tmp_path, "docs/spec/ref.md", "---\npersistence: frozen\n---\n# ref\n\nBODY V1\n")

    # (0) frozen but unstamped → WARN, not ERROR (a still-being-drafted frozen file isn't blocked)
    res = resolve(tmp_path)
    assert "unstamped-frozen" in _codes(res.warnings, "WARN")
    assert "self-hash-mismatch" not in _codes(res.errors, "ERROR")

    h = fingerprint(ref.read_text(encoding="utf-8"))
    # (a) stamped + adding MORE front-matter (body identical) → no mismatch
    ref.write_text(f"---\npersistence: frozen\nself_hash: {h}\nextra: x\n---\n# ref\n\nBODY V1\n")
    assert "self-hash-mismatch" not in _codes(resolve(tmp_path).errors, "ERROR")
    # (b) editing the body → mismatch ERROR
    ref.write_text(f"---\npersistence: frozen\nself_hash: {h}\n---\n# ref\n\nBODY EDITED\n")
    assert "self-hash-mismatch" in _codes(resolve(tmp_path).errors, "ERROR")
