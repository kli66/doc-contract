"""CLI and packaging boundary tests."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import doc_contract.cli as cli_runtime
import doc_contract.sync as sync_runtime
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


def test_check_resolves_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path / "repo")
    real_resolve = cli_runtime.resolve
    calls = 0

    def counted_resolve(*args: object, **kwargs: object):
        nonlocal calls
        calls += 1
        return real_resolve(*args, **kwargs)

    monkeypatch.setattr(cli_runtime, "resolve", counted_resolve)

    assert main(["check", "--repo-root", str(repo), "--offline"]) == 0
    assert calls == 1


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


def test_required_capability_fails_when_offline_without_executing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    marker = repo / "capability-ran"
    _write(
        repo,
        ".doc-contract.toml",
        _config(
            capability_mode="required",
            capability_command=(
                sys.executable,
                "-c",
                f"from pathlib import Path; Path({str(marker)!r}).touch()",
            ),
        ),
    )
    _write(repo, "docs/roadmap.md", "---\npersistence: living\n---\n# Roadmap\n")

    assert main(["check", "--repo-root", str(repo), "--offline"]) == 1
    output = capsys.readouterr().out
    assert "capability-check-required" in output
    assert "offline verified; live skipped" in output
    assert not marker.exists()


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
    stale = _write(
        repo,
        ".doc-contract/vendor/doc_contract/removed_module.py",
        "raise RuntimeError('stale')\n",
    )
    outside_package = _write(repo, ".doc-contract/vendor/retained.txt", "not package-owned\n")
    outside_tree = _write(repo, "retained.txt", "not generated\n")
    external_directory = tmp_path / "external"
    external_directory.mkdir()
    external_file = _write(external_directory, "untouched.py", "outside = True\n")
    stale_symlink = repo / ".doc-contract/vendor/doc_contract/removed_directory"
    stale_symlink.symlink_to(external_directory, target_is_directory=True)

    assert main(["sync", "--repo-root", str(repo)]) == 0
    manifest = json.loads((repo / ".doc-contract-manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"]
    package_source = Path(sync_runtime.__file__).resolve().parent
    expected_package_files = {
        path.relative_to(package_source).as_posix()
        for path in package_source.rglob("*.py")
        if path.is_file()
    }
    expected_package_files.add("_version.py")
    vendor = repo / ".doc-contract/vendor/doc_contract"
    vendored_package_files = {
        path.relative_to(vendor).as_posix() for path in vendor.rglob("*") if path.is_file()
    }
    manifest_package_files = {
        path.removeprefix("doc_contract/")
        for path in manifest["files"]
        if path.startswith("doc_contract/")
    }
    assert vendored_package_files == manifest_package_files == expected_package_files
    for relative, digest in manifest["files"].items():
        target = repo / relative
        if relative.startswith("doc_contract/"):
            target = repo / ".doc-contract/vendor" / relative
        assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
    assert not stale.exists()
    assert not stale_symlink.exists()
    assert outside_package.read_text(encoding="utf-8") == "not package-owned\n"
    assert outside_tree.read_text(encoding="utf-8") == "not generated\n"
    assert external_file.read_text(encoding="utf-8") == "outside = True\n"

    generated_files = [
        *[path for path in vendor.rglob("*") if path.is_file()],
        repo / ".doc-contract/doc_contract_cli.py",
        repo / ".doc-contract-manifest.json",
    ]
    mtimes = {path: path.stat().st_mtime_ns for path in generated_files}
    capsys.readouterr()

    assert main(["sync", "--repo-root", str(repo)]) == 0
    assert "already current" in capsys.readouterr().out
    assert {path: path.stat().st_mtime_ns for path in generated_files} == mtimes


def test_sync_discovers_new_modules_and_rewrites_only_changed_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "running-package"
    _write(source, "__init__.py", "package = True\n")
    _write(source, "cli.py", "def main():\n    return 0\n")
    automatic = _write(source, "nested/automatic.py", "VALUE = 1\n")
    _write(source, "nested/__init__.py", "nested = True\n")
    monkeypatch.setattr(sync_runtime, "_package_source", lambda: source)

    repo = tmp_path / "repo"
    repo.mkdir()
    assert sync_runtime.sync_package(repo)
    manifest_path = repo / ".doc-contract-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "doc_contract/nested/automatic.py" in manifest["files"]
    assert "doc_contract/_version.py" in manifest["files"]

    generated_files = [
        *[
            path
            for path in (repo / ".doc-contract/vendor/doc_contract").rglob("*")
            if path.is_file()
        ],
        repo / ".doc-contract/doc_contract_cli.py",
        manifest_path,
    ]
    initial_bytes = {path: path.read_bytes() for path in generated_files}
    initial_mtimes = {path: path.stat().st_mtime_ns for path in generated_files}
    assert not sync_runtime.sync_package(repo)
    assert {path: path.stat().st_mtime_ns for path in generated_files} == initial_mtimes

    automatic.write_text("VALUE = 2\n", encoding="utf-8")
    assert sync_runtime.sync_package(repo)
    changed = {path for path in generated_files if path.read_bytes() != initial_bytes[path]}
    assert changed == {
        repo / ".doc-contract/vendor/doc_contract/nested/automatic.py",
        manifest_path,
    }
    unchanged = set(generated_files) - changed
    assert {path: path.stat().st_mtime_ns for path in unchanged} == {
        path: initial_mtimes[path] for path in unchanged
    }


def test_sync_missing_required_entry_fails_before_manifest_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "incomplete-package"
    _write(source, "__init__.py", "package = True\n")
    monkeypatch.setattr(sync_runtime, "_package_source", lambda: source)
    repo = tmp_path / "repo"
    previous_manifest = _write(repo, ".doc-contract-manifest.json", "previous manifest\n")

    with pytest.raises(
        RuntimeError,
        match=r"^runtime image missing required entry module: cli\.py$",
    ):
        sync_runtime.sync_package(repo)

    assert previous_manifest.read_text(encoding="utf-8") == "previous manifest\n"
    assert not (repo / ".doc-contract").exists()


def test_sync_fails_closed_when_stale_package_content_cannot_be_pruned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    assert sync_runtime.sync_package(repo)
    manifest = repo / ".doc-contract-manifest.json"
    manifest_bytes = manifest.read_bytes()
    stale_file = _write(
        repo,
        ".doc-contract/vendor/doc_contract/unreadable/stale.py",
        "stale = True\n",
    )

    def inaccessible_walk(
        _top: Path,
        *,
        topdown: bool,
        onerror: object,
        followlinks: bool,
    ) -> tuple[tuple[str, list[str], list[str]], ...]:
        assert topdown is False
        assert followlinks is False
        assert callable(onerror)
        onerror(PermissionError("cannot inspect generated package"))
        return ()

    monkeypatch.setattr(sync_runtime.os, "walk", inaccessible_walk)
    with pytest.raises(PermissionError, match="cannot inspect generated package"):
        sync_runtime.sync_package(repo)

    assert manifest.read_bytes() == manifest_bytes
    assert stale_file.is_file()


def test_sync_rejects_symlink_in_generated_package_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "running-package"
    _write(source, "__init__.py", "package = True\n")
    _write(source, "cli.py", "def main():\n    return 0\n")
    _write(source, "nested/automatic.py", "VALUE = 1\n")
    monkeypatch.setattr(sync_runtime, "_package_source", lambda: source)

    repo = tmp_path / "repo"
    vendor = repo / ".doc-contract/vendor/doc_contract"
    vendor.mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    external_marker = _write(external, "retained.py", "outside = True\n")
    (vendor / "nested").symlink_to(external, target_is_directory=True)
    manifest = _write(repo, ".doc-contract-manifest.json", "previous manifest\n")

    with pytest.raises(
        RuntimeError,
        match=r"^vendored runtime directory contains a symbolic link$",
    ):
        sync_runtime.sync_package(repo)

    assert manifest.read_text(encoding="utf-8") == "previous manifest\n"
    assert external_marker.read_text(encoding="utf-8") == "outside = True\n"
    assert not (external / "automatic.py").exists()


def test_packaged_sync_produces_vendored_verification_from_unrelated_cwd(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "fresh-repo"
    _write(
        repo,
        ".doc-contract.toml",
        _config(
            roots={"contract": "AGENTS.md", "roadmap": "docs/roadmap.md"},
            capability_mode="optional",
            capability_command=(sys.executable, "-c", "raise SystemExit(0)"),
        ),
    )
    _write(repo, "AGENTS.md", "---\npersistence: living\n---\n# Operating contract\n")
    _write(repo, "docs/roadmap.md", "---\npersistence: living\n---\n# Roadmap\n")
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)

    elsewhere = tmp_path / "unrelated-cwd"
    elsewhere.mkdir()
    clean_environment = os.environ.copy()
    clean_environment.pop("PYTHONPATH", None)
    installed_version = subprocess.run(
        [sys.executable, "-m", "doc_contract.cli", "--version"],
        cwd=elsewhere,
        env=clean_environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert installed_version.returncode == 0, installed_version.stderr
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
    vendored_version = subprocess.run(
        [sys.executable, str(launcher), "--version"],
        cwd=elsewhere,
        env=clean_environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert vendored_version.returncode == 0, vendored_version.stderr
    manifest = json.loads((repo / ".doc-contract-manifest.json").read_text(encoding="utf-8"))
    assert installed_version.stdout.strip() == manifest["version"]
    assert vendored_version.stdout.strip() == manifest["version"]
    assert "doc_contract/verification.py" in manifest["files"]
    assert (repo / ".doc-contract/vendor/doc_contract/verification.py").is_file()

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

    live_checked = subprocess.run(
        [
            sys.executable,
            str(launcher),
            "check",
            "--repo-root",
            str(repo),
        ],
        cwd=elsewhere,
        env=clean_environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert live_checked.returncode == 0, live_checked.stderr
    assert "offline verified; live passed" in live_checked.stdout
    assert launcher.is_file()
    assert not (repo / ".claude").exists()


def test_capability_surface_is_explicit() -> None:
    assert COMMANDS == {"check", "update", "stamp", "sync", "land"}
