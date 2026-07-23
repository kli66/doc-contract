"""CLI and packaging boundary tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from doc_contract.cli import COMMANDS, main
from doc_contract.config import load_settings
from doc_contract.resolver import fingerprint, resolve


def _write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _config(
    *,
    roots: dict[str, str] | None = None,
    required_roots: tuple[str, ...] = (),
    capability_mode: str = "skip",
    capability_command: tuple[str, ...] = (),
) -> str:
    lines = [
        "schema_version = 1",
        'repo_name = "fixture"',
        'roadmap = "docs/roadmap.md"',
        "required_roots = ["
        + ", ".join(json.dumps(item) for item in required_roots)
        + "]",
        "",
        "[root_nodes]",
    ]
    for node_id, path in (roots if roots is not None else {"roadmap": "docs/roadmap.md"}).items():
        lines.append(f'{node_id} = "{path}"')
    lines.extend(["", "[capability]", f'mode = "{capability_mode}"'])
    if capability_command:
        command = ", ".join(json.dumps(part) for part in capability_command)
        lines.append(f"command = [{command}]")
    return "\n".join(lines) + "\n"


def _repo(
    root: Path,
    *,
    roots: dict[str, str] | None = None,
    required_roots: tuple[str, ...] = (),
) -> Path:
    _write(
        root,
        ".doc-contract.toml",
        _config(roots=roots, required_roots=required_roots),
    )
    _write(root, "docs/roadmap.md", "---\npersistence: living\n---\n# Roadmap\n")
    return root


def test_check_uses_explicit_root_after_leaving_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path / "repo")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert main(["check", "--repo-root", str(repo), "--offline"]) == 0
    output = capsys.readouterr().out
    assert "offline verified; live skipped" in output
    assert "1 nodes" in output


@pytest.mark.parametrize("kind", ["absent", "missing-roadmap", "zero-nodes"])
def test_root_boundary_failures_are_nonzero(
    kind: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / kind
    if kind == "absent":
        pass
    elif kind == "missing-roadmap":
        _write(root, ".doc-contract.toml", _config())
    else:
        _write(root, ".doc-contract.toml", _config(roots={}))
        _write(root, "docs/roadmap.md", "# unmanaged roadmap\n")

    assert main(["check", "--repo-root", str(root), "--offline"]) != 0
    output = capsys.readouterr()
    rendered = output.out + output.err
    assert "repo-root-mismatch" in rendered


def test_missing_required_root_is_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(
        tmp_path / "repo",
        roots={"roadmap": "docs/roadmap.md", "contract": "AGENTS.md"},
        required_roots=("contract",),
    )
    assert main(["check", "--repo-root", str(repo), "--offline"]) == 1
    assert "required-root-missing" in capsys.readouterr().out


@pytest.mark.parametrize(
    "content, code",
    [
        (None, "repo-root-mismatch"),
        ("not = [valid", "config-invalid"),
        ('schema_version = 99\nrepo_name = "x"\n[root_nodes]\n', "config-invalid"),
    ],
)
def test_missing_and_malformed_config_fail_without_traceback(
    content: str | None,
    code: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    if content is not None:
        _write(root, ".doc-contract.toml", content)
    assert main(["check", "--repo-root", str(root)]) == 2
    error = capsys.readouterr().err
    assert code in error
    assert "Traceback" not in error


def test_optional_capability_can_be_skipped_or_passed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _write(
        repo,
        ".doc-contract.toml",
        _config(
            capability_mode="optional",
            capability_command=(sys.executable, "-c", "raise SystemExit(0)"),
        ),
    )
    _write(repo, "docs/roadmap.md", "---\npersistence: living\n---\n# Roadmap\n")

    assert main(["check", "--repo-root", str(repo), "--offline"]) == 0
    assert "live skipped" in capsys.readouterr().out
    assert main(["check", "--repo-root", str(repo)]) == 0
    assert "live passed" in capsys.readouterr().out


def test_capability_output_is_not_forwarded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    marker = "subprocess-output-must-stay-private"
    _write(
        repo,
        ".doc-contract.toml",
        _config(
            capability_mode="optional",
            capability_command=(sys.executable, "-c", f"print({marker!r})"),
        ),
    )
    _write(repo, "docs/roadmap.md", "---\npersistence: living\n---\n# Roadmap\n")
    assert main(["check", "--repo-root", str(repo)]) == 0
    assert marker not in capsys.readouterr().out


def test_update_rewrites_existing_marker_deterministically(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path / "repo")
    roadmap = repo / "docs/roadmap.md"
    roadmap.write_text(
        roadmap.read_text(encoding="utf-8")
        + "\n<!-- BEGIN GENERATED DAG (old command) -->\nold\n"
        "<!-- END GENERATED DAG -->\n",
        encoding="utf-8",
    )
    assert main(["update", "--repo-root", str(repo)]) == 0
    assert "doc-contract update --repo-root ." in roadmap.read_text(encoding="utf-8")
    capsys.readouterr()
    assert main(["update", "--repo-root", str(repo)]) == 0
    assert "already current" in capsys.readouterr().out


def test_stamp_refreshes_active_dependency_fingerprint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path / "repo")
    target = _write(
        repo,
        "docs/changes/target/change.md",
        "---\nid: target\npersistence: ephemeral\nstatus: landed\ntrack: t\n---\n# Target\n",
    )
    source = _write(
        repo,
        "docs/changes/source/change.md",
        "---\nid: source\npersistence: ephemeral\nstatus: in-progress\ntrack: t\n"
        "depends_on:\n  - target\n---\n# Source\n",
    )
    _write(
        repo,
        "docs/roadmap.md",
        "---\npersistence: living\n---\n# Roadmap\n\n"
        "- `docs/changes/source/` (in-progress)\n",
    )
    assert main(["stamp", "source", "--repo-root", str(repo)]) == 0
    assert fingerprint(target.read_text(encoding="utf-8")) in source.read_text(encoding="utf-8")
    assert not resolve(repo, load_settings(repo)).errors
    assert "source stamped" in capsys.readouterr().out


def test_sync_writes_pinned_manifest_and_is_idempotent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path / "repo")
    assert main(["sync", "--repo-root", str(repo)]) == 0
    manifest = json.loads((repo / ".doc-contract-manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"]
    assert "doc_contract/cli.py" in manifest["files"]
    assert "doc_contract/landing.py" in manifest["files"]
    assert (repo / ".doc-contract/vendor/doc_contract/resolver.py").is_file()
    assert (repo / ".doc-contract/doc_contract_cli.py").is_file()
    capsys.readouterr()

    assert main(["sync", "--repo-root", str(repo)]) == 0
    assert "already current" in capsys.readouterr().out


def test_capability_surface_is_explicit() -> None:
    assert COMMANDS == {"check", "update", "stamp", "sync", "land"}
