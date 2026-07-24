"""CLI and packaging boundary tests."""

from __future__ import annotations

import json
import os
import subprocess
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
    optional_roots: tuple[str, ...] = (),
    edge_fingerprints: str | None = None,
    capability_mode: str = "skip",
    capability_command: tuple[str, ...] = (),
) -> str:
    lines = [
        "schema_version = 1",
        'repo_name = "fixture"',
        'roadmap = "docs/roadmap.md"',
        "optional_roots = ["
        + ", ".join(json.dumps(item) for item in optional_roots)
        + "]",
    ]
    if edge_fingerprints is not None:
        lines.append(f'edge_fingerprints = "{edge_fingerprints}"')
    lines.extend(["", "[root_nodes]"])
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
    optional_roots: tuple[str, ...] = (),
) -> Path:
    _write(
        root,
        ".doc-contract.toml",
        _config(roots=roots, optional_roots=optional_roots),
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
    )
    assert main(["check", "--repo-root", str(repo), "--offline"]) == 1
    assert "required-root-missing" in capsys.readouterr().out


def test_explicit_optional_root_is_reported_without_failing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(
        tmp_path / "repo",
        roots={"roadmap": "docs/roadmap.md", "contract": "AGENTS.md"},
        optional_roots=("contract",),
    )
    assert main(["check", "--repo-root", str(repo), "--offline"]) == 0
    assert "optional-root-missing" in capsys.readouterr().out


def test_edge_fingerprints_default_to_advisory_and_allow_required_opt_in(
    tmp_path: Path,
) -> None:
    default_repo = _repo(tmp_path / "default")
    required_repo = tmp_path / "required"
    _write(
        required_repo,
        ".doc-contract.toml",
        _config(edge_fingerprints="required"),
    )
    _write(
        required_repo,
        "docs/roadmap.md",
        "---\npersistence: living\n---\n# Roadmap\n",
    )

    assert load_settings(default_repo).edge_fingerprint_policy == "advisory"
    assert load_settings(required_repo).edge_fingerprint_policy == "required"


@pytest.mark.parametrize(
    "config",
    [
        "schema_version = 1\nrepo_name = 'x'\nrequired_roots = []\n[root_nodes]\n",
        "schema_version = 1\nrepo_name = 'x'\noptional_roots = ['roadmap']\n"
        "[root_nodes]\nroadmap = 'docs/roadmap.md'\n",
        "schema_version = 1\nrepo_name = 'x'\n[root_nodes]\n"
        "one = 'docs/roadmap.md'\ntwo = 'docs/roadmap.md'\n",
        "schema_version = 1\nrepo_name = 'x'\nedge_fingerprints = 'strict'\n"
        "[root_nodes]\n",
        "schema_version = 1\nrepo_name = 'x'\nedge_fingerprints = []\n[root_nodes]\n",
    ],
)
def test_ambiguous_root_policy_is_rejected(
    config: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "repo"
    _write(root, ".doc-contract.toml", config)
    assert main(["check", "--repo-root", str(root)]) == 2
    assert "config-invalid" in capsys.readouterr().err


def test_invalid_settings_never_reach_cli_or_echo_command_arguments(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "repo"
    private_argument = "private-command-argument"
    _write(
        root,
        ".doc-contract.toml",
        _config(capability_command=(private_argument, "")),
    )

    assert main(["check", "--repo-root", str(root)]) == 2
    error = capsys.readouterr().err
    assert "config-invalid" in error
    assert private_argument not in error


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


def test_update_previews_untracked_nodes_before_mutation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path / "repo")
    roadmap = repo / "docs/roadmap.md"
    roadmap.write_text(
        roadmap.read_text(encoding="utf-8")
        + "\n- `docs/changes/provisional/` (proposed)\n\n"
        "<!-- BEGIN GENERATED DAG (regenerate: doc-contract update --repo-root .) -->\n"
        "```mermaid\nflowchart TD\n```\n<!-- END GENERATED DAG -->\n",
        encoding="utf-8",
    )
    _write(
        repo,
        "docs/changes/provisional/change.md",
        "---\nid: provisional\npersistence: ephemeral\nstatus: proposed\ntrack: test\n"
        "---\n# Provisional\n",
    )
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "add", ".doc-contract.toml", "docs/roadmap.md"],
        check=True,
    )

    assert main(["update", "--repo-root", str(repo)]) == 0
    assert "untracked-node-excluded" in capsys.readouterr().out
    assert "provisional (proposed)" not in roadmap.read_text(encoding="utf-8")

    assert main(["update", "--repo-root", str(repo), "--include-untracked"]) == 0
    output = capsys.readouterr().out
    assert output.index("untracked discovery preview") < output.index("roadmap updated")
    assert "provisional (proposed)" in roadmap.read_text(encoding="utf-8")


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
    assert load_settings(repo).edge_fingerprint_policy == "advisory"
    assert not resolve(repo, load_settings(repo)).errors
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


def test_packaged_sync_produces_offline_vendored_check_from_unrelated_cwd(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "fresh-repo"
    _write(
        repo,
        ".doc-contract.toml",
        _config(roots={"contract": "AGENTS.md", "roadmap": "docs/roadmap.md"}),
    )
    _write(repo, "AGENTS.md", "---\npersistence: living\n---\n# Operating contract\n")
    _write(repo, "docs/roadmap.md", "---\npersistence: living\n---\n# Roadmap\n")
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)

    elsewhere = tmp_path / "unrelated-cwd"
    elsewhere.mkdir()
    clean_environment = os.environ.copy()
    clean_environment.pop("PYTHONPATH", None)
    synced = subprocess.run(
        [
            sys.executable,
            "-m",
            "doc_contract.cli",
            "sync",
            "--repo-root",
            str(repo),
        ],
        cwd=elsewhere,
        env=clean_environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert synced.returncode == 0, synced.stderr
    assert "vendored package updated" in synced.stdout

    launcher = repo / ".doc-contract/doc_contract_cli.py"
    checked = subprocess.run(
        [
            sys.executable,
            str(launcher),
            "check",
            "--repo-root",
            str(repo),
            "--offline",
        ],
        cwd=elsewhere,
        env=clean_environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert checked.returncode == 0, checked.stderr
    assert "offline verified; live skipped" in checked.stdout
    assert "2 nodes" in checked.stdout
    assert launcher.is_file()
    assert not (repo / ".claude").exists()


def test_capability_surface_is_explicit() -> None:
    assert COMMANDS == {"check", "update", "stamp", "sync", "land"}
