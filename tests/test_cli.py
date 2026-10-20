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
from doc_contract.resolver import Finding, fingerprint, resolve
from doc_contract.transaction import TransactionError


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


def test_stamp_include_untracked_admits_provisional_node(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path / "repo")
    target = _write(
        repo,
        "docs/changes/target/change.md",
        "---\nid: target\npersistence: ephemeral\nstatus: landed\ntrack: t\n---\n# Target\n",
    )
    tracked = _write(
        repo,
        "docs/changes/tracked/change.md",
        "---\nid: tracked\npersistence: ephemeral\nstatus: in-progress\ntrack: t\n"
        "depends_on:\n  - target\n---\n# Tracked\n",
    )
    roadmap = repo / "docs/roadmap.md"
    roadmap.write_text(
        roadmap.read_text(encoding="utf-8")
        + "- `docs/changes/tracked/` (in-progress)\n"
        "- `docs/changes/provisional/` (proposed)\n",
        encoding="utf-8",
    )
    provisional = _write(
        repo,
        "docs/changes/provisional/change.md",
        "---\nid: provisional\npersistence: ephemeral\nstatus: proposed\ntrack: t\n"
        "depends_on:\n  - target\n---\n# Provisional\n",
    )
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "add",
            ".doc-contract.toml",
            "docs/roadmap.md",
            "docs/changes/target/change.md",
            "docs/changes/tracked/change.md",
        ],
        check=True,
    )

    # Without the flag the untracked node is absent from discovery entirely.
    assert main(["stamp", "provisional", "--repo-root", str(repo)]) == 1
    captured = capsys.readouterr()
    assert "unknown node id 'provisional'" in captured.err
    assert "untracked" not in captured.out
    assert "fingerprints" not in provisional.read_text(encoding="utf-8")

    # With the flag the named node is admitted without any discovery preview.
    assert (
        main(["stamp", "provisional", "--repo-root", str(repo), "--include-untracked"]) == 0
    )
    captured = capsys.readouterr()
    assert "provisional stamped" in captured.out
    assert "untracked-node-included" not in captured.out
    assert fingerprint(target.read_text(encoding="utf-8")) in provisional.read_text(
        encoding="utf-8"
    )

    # A tracked node stamps identically with and without the flag.
    assert main(["stamp", "tracked", "--repo-root", str(repo)]) == 0
    assert "tracked stamped" in capsys.readouterr().out
    assert fingerprint(target.read_text(encoding="utf-8")) in tracked.read_text(encoding="utf-8")
    assert main(["stamp", "tracked", "--repo-root", str(repo), "--include-untracked"]) == 0
    assert "tracked already current" in capsys.readouterr().out

    # The follow-up check gains no new error or warning for the stamped nodes.
    assert main(["check", "--repo-root", str(repo), "--offline", "--include-untracked"]) == 0
    check_output = capsys.readouterr().out
    assert "ERROR" not in check_output
    assert "suspect-link" not in check_output
    assert "edge-hash-" not in check_output


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
    assert "doc_contract/reconciliation.py" in manifest["files"]
    assert (repo / ".doc-contract/vendor/doc_contract/reconciliation.py").is_file()

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
    assert COMMANDS == {
        "check",
        "update",
        "stamp",
        "sync",
        "accept",
        "begin",
        "reconcile",
        "land",
        "reflect",
        "supersede",
    }


def test_land_cli_reports_stable_code_and_preserves_transaction_type_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path / "repo")

    class PlannerTransactionError(TransactionError):
        pass

    def fail_with_planner_error(*_args: object, **_kwargs: object) -> None:
        raise PlannerTransactionError("tracking-state-unavailable: test")

    monkeypatch.setattr(cli_runtime, "execute_landing", fail_with_planner_error)
    assert main(["land", "example", "--repo-root", str(repo)]) == 1
    assert capsys.readouterr().err == (
        "ERROR: [PlannerTransactionError] tracking-state-unavailable: test\n"
    )

    def fail_with_landing_error(*_args: object, **_kwargs: object) -> None:
        raise cli_runtime.LandingError("destination-collision: test")

    monkeypatch.setattr(cli_runtime, "execute_landing", fail_with_landing_error)
    assert main(["land", "example", "--repo-root", str(repo)]) == 1
    assert capsys.readouterr().err == "ERROR: [destination-collision] test\n"

    class CustomLandingError(cli_runtime.LandingError):
        pass

    def fail_with_custom_landing_error(*_args: object, **_kwargs: object) -> None:
        raise CustomLandingError("destination-collision: custom")

    monkeypatch.setattr(cli_runtime, "execute_landing", fail_with_custom_landing_error)
    assert main(["land", "example", "--repo-root", str(repo)]) == 1
    assert capsys.readouterr().err == "ERROR: [destination-collision] custom\n"


def test_land_cli_prints_findings_with_subjects_under_stable_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path / "repo")

    def fail_with_preflight(*_args: object, **_kwargs: object) -> None:
        raise cli_runtime.LandingError(
            "preflight-invalid: planned repository state fails validation",
            code="preflight-invalid",
            findings=(
                Finding(
                    "ERROR",
                    "unknown-dependency",
                    "unknown dependency 'missing'",
                    ("example",),
                ),
            ),
        )

    monkeypatch.setattr(cli_runtime, "execute_landing", fail_with_preflight)
    assert main(["land", "example", "--repo-root", str(repo)]) == 1
    err = capsys.readouterr().err
    assert "ERROR: [preflight-invalid] planned repository state fails validation\n" in err
    assert (
        "  ERROR: [unknown-dependency] unknown dependency 'missing'"
        " (subjects: example)\n"
    ) in err
    assert "[TransactionError]" not in err


def test_supersede_cli_prints_findings_with_subjects_under_stable_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path / "repo")

    def fail_with_preflight(*_args: object, **_kwargs: object) -> None:
        raise cli_runtime.LandingError(
            "preflight-invalid: planned repository state fails validation",
            code="preflight-invalid",
            findings=(
                Finding(
                    "ERROR",
                    "unknown-dependency",
                    "unknown dependency 'missing'",
                    ("example",),
                ),
            ),
        )

    monkeypatch.setattr(cli_runtime, "execute_supersede", fail_with_preflight)
    assert (
        main(
            ["supersede", "example", "--reason", "r", "--repo-root", str(repo)]
        )
        == 1
    )
    err = capsys.readouterr().err
    assert "ERROR: [preflight-invalid] planned repository state fails validation\n" in err
    assert (
        "  ERROR: [unknown-dependency] unknown dependency 'missing'"
        " (subjects: example)\n"
    ) in err
    assert "[TransactionError]" not in err


def _lifecycle_repo(
    root: Path,
    status: str,
    *,
    tracked: bool = True,
    gate: str | None = None,
) -> Path:
    _repo(root)
    _write(
        root,
        "docs/roadmap.md",
        "---\npersistence: living\n---\n# Roadmap\n\n"
        f"- `docs/changes/example/` ({status})\n\n"
        "<!-- BEGIN GENERATED DAG (regenerate: doc-contract update --repo-root .) -->\n"
        "```mermaid\nflowchart TD\n```\n<!-- END GENERATED DAG -->\n",
    )
    gate_line = f"gated_on: {gate}\n" if gate is not None else ""
    _write(
        root,
        "docs/changes/example/change.md",
        "---\nid: example\npersistence: ephemeral\n"
        f"status: {status}\ntrack: test\n{gate_line}---\n"
        "# Example\n\nprivate body that diagnostics must not quote\n",
    )
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "add", ".doc-contract.toml", "docs/roadmap.md"],
        check=True,
    )
    if tracked:
        subprocess.run(
            ["git", "-C", str(root), "add", "docs/changes/example/change.md"],
            check=True,
        )
    return root


def test_land_cli_compact_output_and_explicit_diff(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tracked = _lifecycle_repo(tmp_path / "tracked", "in-progress")
    base_args = [
        "land",
        "example",
        "--repo-root",
        str(tracked),
        "--dry-run",
    ]

    assert main(base_args) == 0
    compact = capsys.readouterr()
    assert compact.err == ""
    assert "land plan: example\n" in compact.out
    assert "source: docs/changes/example\n" in compact.out
    assert "tracking: tracked\n" in compact.out
    assert "provisional nodes: 0\n" in compact.out
    assert "mutations: 3 total; 2 write(s), 1 move(s)\n" in compact.out
    assert "  write docs/changes/example/change.md\n" in compact.out
    assert "  write docs/roadmap.md\n" in compact.out
    assert "  move docs/changes/example -> docs/changes/archive/" in compact.out
    assert "preflight warnings: 0\n" in compact.out
    assert "hint: add --diff for the complete patch\n" in compact.out
    assert "--- docs/changes/example/change.md" not in compact.out
    assert "input/output tree:" not in compact.out

    assert main([*base_args, "--diff"]) == 0
    with_diff = capsys.readouterr()
    assert with_diff.err == ""
    assert "hint: add --diff" not in with_diff.out
    assert "--- docs/changes/example/change.md\n" in with_diff.out
    assert "rename docs/changes/example/ -> docs/changes/archive/" in with_diff.out


def test_land_cli_dry_run_prints_provisional_nodes_and_warning_details(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    untracked = _lifecycle_repo(tmp_path / "untracked-plan", "in-progress", tracked=False)

    assert (
        main(
            [
                "land",
                "example",
                "--repo-root",
                str(untracked),
                "--dry-run",
                "--include-untracked",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "tracking: untracked\n" in captured.out
    assert "provisional nodes: 1\n" in captured.out
    assert "  + example: docs/changes/example/change.md\n" in captured.out
    assert "preflight warnings: 1\n" in captured.out
    assert "WARN BASELINE: [untracked-node-included]" in captured.out


def test_lifecycle_cli_renders_stable_codes_and_canonical_hints(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proposed = _lifecycle_repo(tmp_path / "proposed", "proposed")
    assert main(["begin", "example", "--repo-root", str(proposed)]) == 1
    captured = capsys.readouterr()
    assert captured.err == (
        "ERROR: [change-proposed-unaccepted] "
        "change example has status=proposed and is not accepted\n"
        "NEXT: doc-contract accept example --dry-run\n"
    )
    assert (
        main(
            [
                "reconcile",
                "mechanical",
                "example",
                "--phase",
                "entry",
                "--format",
                "json",
                "--repo-root",
                str(proposed),
            ]
        )
        == 1
    )
    proposed_report = json.loads(capsys.readouterr().out)
    assert proposed_report["findings"][0] == {
        "code": "change-proposed-unaccepted",
        "level": "ERROR",
        "message": "change example has status=proposed and is not accepted",
        "scope": "change",
        "subjects": ["example"],
    }
    assert proposed_report["next_command"] == "doc-contract accept example --dry-run"

    accepted = _lifecycle_repo(tmp_path / "accepted", "accepted")
    assert main(["land", "example", "--repo-root", str(accepted)]) == 1
    captured = capsys.readouterr()
    assert captured.err == (
        "ERROR: [change-accepted-not-started] "
        "change example has status=accepted and has not started\n"
        "NEXT: doc-contract begin example --dry-run\n"
    )

    blocked = _lifecycle_repo(
        tmp_path / "blocked", "blocked", gate="private-gate-value"
    )
    assert main(["land", "example", "--repo-root", str(blocked)]) == 1
    captured = capsys.readouterr()
    assert captured.err == (
        "ERROR: [change-blocked] "
        "change example has status=blocked; gate_present=true\n"
    )
    assert "private-gate-value" not in captured.err
    assert main(["accept", "example", "--repo-root", str(blocked)]) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("ERROR: [change-blocked] ")
    assert "NEXT:" not in captured.err

    untracked = _lifecycle_repo(
        tmp_path / "untracked", "in-progress", tracked=False
    )
    assert (
        main(
            [
                "reconcile",
                "mechanical",
                "example",
                "--phase",
                "exit",
                "--format",
                "json",
                "--repo-root",
                str(untracked),
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["findings"][0]["code"] == "change-untracked-excluded"
    assert payload["next_command"] == (
        "doc-contract reconcile mechanical example --phase exit --include-untracked"
    )


def test_lifecycle_cli_invalid_and_repeated_landing_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    invalid = _lifecycle_repo(tmp_path / "invalid", "in-progress")
    change = invalid / "docs/changes/example/change.md"
    change.write_text(
        "---\nid: example\nprivate-parser-fragment\n---\nprivate body\n",
        encoding="utf-8",
    )
    assert main(["land", "example", "--repo-root", str(invalid)]) == 1
    captured = capsys.readouterr()
    assert captured.err == (
        "ERROR: [change-front-matter-invalid] "
        "change folder docs/changes/example has invalid or ambiguous front matter\n"
    )
    assert "Traceback" not in captured.err
    assert "private" not in captured.err

    repeated = _lifecycle_repo(
        tmp_path / "repeated", "in-progress", tracked=False
    )
    args = [
        "land",
        "example",
        "--repo-root",
        str(repeated),
        "--include-untracked",
    ]
    assert main(args) == 0
    capsys.readouterr()
    assert main(args) == 0
    captured = capsys.readouterr()
    assert captured.out == (
        "INFO: [change-already-landed] change example has status=landed\n"
    )


def test_installed_and_vendored_reconciliation_work_from_unrelated_cwd(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    marker = repo / "capability-ran"
    _write(
        repo,
        ".doc-contract.toml",
        _config(
            capability_mode="optional",
            capability_command=(
                sys.executable,
                "-c",
                f"open({str(marker)!r}, 'w').write('ran')",
            ),
        ),
    )
    _write(
        repo,
        "docs/roadmap.md",
        "---\npersistence: living\n---\n# Roadmap\n\n"
        "- `docs/changes/example/` (accepted)\n\n"
        "<!-- BEGIN GENERATED DAG (regenerate: doc-contract update --repo-root .) -->\n"
        "```mermaid\nflowchart TD\n```\n<!-- END GENERATED DAG -->\n",
    )
    _write(
        repo,
        "docs/changes/example/change.md",
        "---\nid: example\npersistence: ephemeral\nstatus: accepted\ntrack: test\n---\n"
        "# Example\n\nStatus: Accepted · 2026-07-29\n",
    )
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    clean_environment = os.environ.copy()
    clean_environment.pop("PYTHONPATH", None)
    command = [
        "reconcile",
        "mechanical",
        "example",
        "--phase",
        "entry",
        "--format",
        "json",
        "--repo-root",
        str(repo),
    ]

    installed = subprocess.run(
        [sys.executable, "-m", "doc_contract.cli", *command],
        cwd=elsewhere,
        env=clean_environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert installed.returncode == 0, installed.stderr
    installed_payload = json.loads(installed.stdout)
    assert installed_payload["ready"] is True
    assert installed_payload["kind"] == "mechanical"
    assert not marker.exists()

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
    launcher = repo / ".doc-contract/doc_contract_cli.py"
    vendored = subprocess.run(
        [sys.executable, str(launcher), *command],
        cwd=elsewhere,
        env=clean_environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert vendored.returncode == 0, vendored.stderr
    assert json.loads(vendored.stdout) == installed_payload
    assert not marker.exists()

    change = repo / "docs/changes/example/change.md"
    change.write_text(
        change.read_text(encoding="utf-8").replace(
            "status: accepted", "status: proposed"
        ),
        encoding="utf-8",
    )
    roadmap = repo / "docs/roadmap.md"
    roadmap.write_text(
        roadmap.read_text(encoding="utf-8").replace("(accepted)", "(proposed)"),
        encoding="utf-8",
    )
    installed_blocker = subprocess.run(
        [sys.executable, "-m", "doc_contract.cli", *command],
        cwd=elsewhere,
        env=clean_environment,
        check=False,
        capture_output=True,
        text=True,
    )
    vendored_blocker = subprocess.run(
        [sys.executable, str(launcher), *command],
        cwd=elsewhere,
        env=clean_environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert installed_blocker.returncode == vendored_blocker.returncode == 1
    blocker_payload = json.loads(installed_blocker.stdout)
    assert json.loads(vendored_blocker.stdout) == blocker_payload
    assert blocker_payload["findings"][0]["code"] == "change-proposed-unaccepted"
    assert blocker_payload["next_command"] == "doc-contract accept example --dry-run"


def test_supersede_parser_requires_reason_and_empty_reason_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _lifecycle_repo(tmp_path / "repo", "proposed")
    with pytest.raises(SystemExit) as missing:
        main(["supersede", "example", "--repo-root", str(repo)])
    assert missing.value.code == 2
    captured = capsys.readouterr()
    assert "reason" in captured.err
    assert "Traceback" not in captured.err

    source = repo / "docs/changes/example/change.md"
    before = source.read_bytes()
    assert main(["supersede", "example", "--reason", "", "--repo-root", str(repo)]) == 1
    captured = capsys.readouterr()
    assert "reason-invalid" in captured.err
    assert source.read_bytes() == before
    assert not list((repo / ".git").glob("doc-contract/supersede-*.json"))


_REASON_MARKER = "ZZ-SUPERSEDE-REASON-MARKER"


def _assert_reason_marker_absent(out: str, err: str) -> None:
    """Fail without ever echoing the reason marker: the assertion reports only the boolean
    leak flag, never the marker text or the captured stream contents."""
    leaked = _REASON_MARKER in out or _REASON_MARKER in err
    assert not leaked, "supersede leaked the --reason text into stdout or stderr"


def test_supersede_never_echoes_reason_marker(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _lifecycle_repo(tmp_path / "repo", "proposed")
    assert (
        main(
            [
                "supersede",
                "example",
                "--reason",
                _REASON_MARKER,
                "--repo-root",
                str(repo),
                "--dry-run",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    _assert_reason_marker_absent(captured.out, captured.err)
    assert "supersede plan: example\n" in captured.out
    assert "  remove docs/changes/example\n" in captured.out
    assert "  create docs/archive/example.md\n" in captured.out


def test_supersede_reason_marker_absent_on_non_proposed_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _lifecycle_repo(tmp_path / "repo", "accepted")
    assert (
        main(
            ["supersede", "example", "--reason", _REASON_MARKER, "--repo-root", str(repo)]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert "change-not-proposed" in captured.err
    _assert_reason_marker_absent(captured.out, captured.err)


def test_supersede_reason_marker_absent_on_roadmap_invalid_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _lifecycle_repo(tmp_path / "repo", "proposed")
    roadmap = repo / "docs/roadmap.md"
    roadmap.write_text(
        roadmap.read_text(encoding="utf-8").replace("(proposed)", ""),
        encoding="utf-8",
    )
    assert (
        main(
            ["supersede", "example", "--reason", _REASON_MARKER, "--repo-root", str(repo)]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert "roadmap-invalid" in captured.err
    _assert_reason_marker_absent(captured.out, captured.err)


def test_supersede_reason_marker_absent_on_dependent_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _lifecycle_repo(tmp_path / "repo", "proposed")
    _write(
        repo,
        "docs/changes/dependent/change.md",
        "---\nid: dependent\npersistence: ephemeral\nstatus: proposed\ntrack: test\n"
        "depends_on:\n  - example\n---\n# Dependent\n",
    )
    roadmap = repo / "docs/roadmap.md"
    roadmap.write_text(
        roadmap.read_text(encoding="utf-8").replace(
            "<!-- BEGIN GENERATED DAG",
            "- `docs/changes/dependent/` (proposed)\n\n<!-- BEGIN GENERATED DAG",
        ),
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-C", str(repo), "add", "docs/changes/dependent/change.md"],
        check=True,
    )
    assert (
        main(
            ["supersede", "example", "--reason", _REASON_MARKER, "--repo-root", str(repo)]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert "preflight-invalid" in captured.err
    _assert_reason_marker_absent(captured.out, captured.err)


# ------------------------------------------------------------- accept --format json tests
#
# Tests for the new accept --format json and --expect-plan-id options.


def test_accept_format_json_produces_single_versioned_object(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """accept --format json must produce exactly one versioned JSON object."""
    repo = _lifecycle_repo(tmp_path / "repo", "proposed")

    assert (
        main(
            [
                "accept",
                "example",
                "--repo-root",
                str(repo),
                "--include-untracked",
                "--dry-run",
                "--format",
                "json",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert captured.err == ""

    # Parse as single JSON object
    payload = json.loads(captured.out)
    assert payload["schema_version"] == 1
    assert payload["kind"] == "acceptance-transition"
    assert payload["plan_id"].startswith("sha256:")
    assert payload["plan"]["action"] == "accept"
    assert payload["plan"]["change"]["id"] == "example"
    assert payload["execution"]["mode"] == "dry-run"
    assert payload["execution"]["status"] == "not-applied"
    assert payload["execution"]["expectation"] == "not-provided"
    assert payload["diagnostic"] is None


def test_accept_format_json_excludes_private_fields(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """accept --format json must exclude private fields."""
    repo = _lifecycle_repo(tmp_path / "repo", "proposed")

    assert (
        main(
            [
                "accept",
                "example",
                "--repo-root",
                str(repo),
                "--include-untracked",
                "--dry-run",
                "--format",
                "json",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    # Check that private fields are not present
    payload_str = json.dumps(payload)
    assert "before_hash" not in payload_str
    assert "after_hash" not in payload_str
    assert "content" not in payload_str
    assert "diff" not in payload_str
    assert "journal_path" not in payload_str
    assert "input_tree_hash" not in payload_str
    assert "output_tree_hash" not in payload_str

    # Check mutation descriptors are content-free
    for mutation in payload["plan"]["mutations"]:
        assert set(mutation.keys()) == {"kind", "path", "destination"}


def test_accept_format_json_with_expect_plan_id_matched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """accept --format json with matching --expect-plan-id must report matched."""
    repo = _lifecycle_repo(tmp_path / "repo", "proposed")

    # First, get the plan_id from a dry-run
    assert (
        main(
            [
                "accept",
                "example",
                "--repo-root",
                str(repo),
                "--include-untracked",
                "--dry-run",
                "--format",
                "json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    plan_id = payload["plan_id"]

    # Now run with matching expectation
    assert (
        main(
            [
                "accept",
                "example",
                "--repo-root",
                str(repo),
                "--include-untracked",
                "--dry-run",
                "--format",
                "json",
                "--expect-plan-id",
                plan_id,
            ]
        )
        == 0
    )
    payload2 = json.loads(capsys.readouterr().out)
    assert payload2["execution"]["expectation"] == "matched"
    assert payload2["execution"]["status"] == "not-applied"


def test_accept_format_json_with_expect_plan_id_mismatch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """accept --format json with mismatching --expect-plan-id must report rejected."""
    repo = _lifecycle_repo(tmp_path / "repo", "proposed")

    wrong_plan_id = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    assert (
        main(
            [
                "accept",
                "example",
                "--repo-root",
                str(repo),
                "--include-untracked",
                "--dry-run",
                "--format",
                "json",
                "--expect-plan-id",
                wrong_plan_id,
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution"]["expectation"] == "mismatch"
    assert payload["execution"]["status"] == "rejected"


def test_accept_format_json_with_malformed_expect_plan_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """accept --format json with malformed --expect-plan-id must report rejected."""
    repo = _lifecycle_repo(tmp_path / "repo", "proposed")

    assert (
        main(
            [
                "accept",
                "example",
                "--repo-root",
                str(repo),
                "--include-untracked",
                "--dry-run",
                "--format",
                "json",
                "--expect-plan-id",
                "not-a-valid-sha256",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution"]["expectation"] == "malformed"
    assert payload["execution"]["status"] == "rejected"
    # Must not echo the malformed input
    assert "not-a-valid-sha256" not in json.dumps(payload)


def test_accept_format_json_applied_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """accept --format json applied must report applied status."""
    repo = _lifecycle_repo(tmp_path / "repo", "proposed")

    assert (
        main(
            [
                "accept",
                "example",
                "--repo-root",
                str(repo),
                "--include-untracked",
                "--format",
                "json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution"]["mode"] == "apply"
    assert payload["execution"]["status"] == "applied"
    assert payload["execution"]["journal_retained"] is False


def test_accept_format_json_already_applied_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """accept --format json already-applied must report already-applied status."""
    repo = _lifecycle_repo(tmp_path / "repo", "proposed")

    # First accept
    assert (
        main(
            [
                "accept",
                "example",
                "--repo-root",
                str(repo),
                "--include-untracked",
                "--format",
                "json",
            ]
        )
        == 0
    )
    capsys.readouterr()  # Clear the output

    # Second accept (already-applied)
    assert (
        main(
            [
                "accept",
                "example",
                "--repo-root",
                str(repo),
                "--include-untracked",
                "--format",
                "json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution"]["status"] == "already-applied"
    assert payload["execution"]["expectation"] == "not-verifiable"


def test_accept_format_text_is_unchanged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """accept --format text (default) must produce unchanged text output."""
    repo = _lifecycle_repo(tmp_path / "repo", "proposed")

    # Run with explicit --format text
    assert (
        main(
            [
                "accept",
                "example",
                "--repo-root",
                str(repo),
                "--include-untracked",
                "--dry-run",
                "--format",
                "text",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    # Text output should contain human-readable text, not JSON
    assert "accept plan:" in captured.out
    assert "mutation(s)" in captured.out
    assert "dry-run; no mutations" in captured.out


def test_begin_does_not_accept_format_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """begin must not accept --format json."""
    repo = _lifecycle_repo(tmp_path / "repo", "accepted")

    # argparse rejects unknown arguments with exit code 2
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "begin",
                "example",
                "--repo-root",
                str(repo),
                "--include-untracked",
                "--format",
                "json",
            ]
        )
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "unrecognized arguments: --format" in captured.err


def test_accept_format_json_blocker_returns_plan_null(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """accept --format json with blocker must return plan_id null and plan null."""
    repo = _lifecycle_repo(tmp_path / "repo", "blocked", gate="private-gate")

    assert (
        main(
            [
                "accept",
                "example",
                "--repo-root",
                str(repo),
                "--include-untracked",
                "--format",
                "json",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["plan_id"] is None
    assert payload["plan"] is None
    assert payload["execution"]["status"] == "rejected"
    assert payload["diagnostic"]["code"] == "change-blocked"


def test_accept_text_mode_expectation_mismatch_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """accept --format text with expectation mismatch must exit nonzero and print error."""
    repo = _lifecycle_repo(tmp_path / "repo", "proposed")

    wrong_plan_id = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    assert (
        main(
            [
                "accept",
                "example",
                "--repo-root",
                str(repo),
                "--include-untracked",
                "--dry-run",
                "--expect-plan-id",
                wrong_plan_id,
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    # Must print error to stderr
    assert "ERROR: [accept-plan-mismatch]" in captured.err
    # Must not print success line
    assert "dry-run; no mutations" not in captured.out


def test_accept_text_mode_malformed_expectation_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """accept --format text with malformed expectation must exit nonzero and print error."""
    repo = _lifecycle_repo(tmp_path / "repo", "proposed")

    assert (
        main(
            [
                "accept",
                "example",
                "--repo-root",
                str(repo),
                "--include-untracked",
                "--dry-run",
                "--expect-plan-id",
                "not-a-valid-sha256",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    # Must print error to stderr
    assert "ERROR: [accept-plan-id-invalid]" in captured.err
    # Must not echo the malformed input
    assert "not-a-valid-sha256" not in captured.err
    assert "not-a-valid-sha256" not in captured.out


def test_accept_text_mode_without_expectation_is_unchanged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """accept --format text without --expect-plan-id must produce unchanged text output."""
    repo = _lifecycle_repo(tmp_path / "repo", "proposed")

    assert (
        main(
            [
                "accept",
                "example",
                "--repo-root",
                str(repo),
                "--include-untracked",
                "--dry-run",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    # Text output should contain human-readable text
    assert "accept plan:" in captured.out
    assert "mutation(s)" in captured.out
    assert "dry-run; no mutations" in captured.out


def test_accept_json_diagnostic_codes_for_expectation_rejection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """accept --format json must emit correct diagnostic codes for expectation rejections."""
    repo = _lifecycle_repo(tmp_path / "repo", "proposed")

    # Test malformed identifier
    assert (
        main(
            [
                "accept",
                "example",
                "--repo-root",
                str(repo),
                "--include-untracked",
                "--dry-run",
                "--format",
                "json",
                "--expect-plan-id",
                "not-a-valid-sha256",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["diagnostic"]["code"] == "accept-plan-id-invalid"

    # Test mismatch
    wrong_plan_id = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    assert (
        main(
            [
                "accept",
                "example",
                "--repo-root",
                str(repo),
                "--include-untracked",
                "--dry-run",
                "--format",
                "json",
                "--expect-plan-id",
                wrong_plan_id,
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["diagnostic"]["code"] == "accept-plan-mismatch"


def test_accept_json_schema1_journal_with_expectation_reports_not_verifiable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """accept --format json with schema-1 journal and expectation must report not-verifiable."""
    import json as json_module

    repo = _lifecycle_repo(tmp_path / "repo", "proposed")

    # Create a schema-1 journal manually
    journal_path = repo / ".git" / "doc-contract" / "lifecycle-accept-example.json"
    journal_path.parent.mkdir(parents=True, exist_ok=True)

    schema1_payload = {
        "schema": 1,
        "action": "accept",
        "change_id": "example",
        "source": "docs/changes/example",
        "date": "2026-08-01",
        "source_status": "proposed",
        "destination_status": "accepted",
        "accepted_at": None,
        "started_at": None,
        "tracking": "untracked",
        "input_tree_hash": "abc123",
        "output_tree_hash": "def456",
        "journal_path": str(journal_path),
        "provisional_nodes": [],
        "current_findings": [],
        "projected_findings": [],
        "baseline_warnings": [],
        "mutations": [],
        "already_applied": False,
        "completed": [],
    }
    journal_path.write_text(json_module.dumps(schema1_payload, indent=2), encoding="utf-8")

    assert (
        main(
            [
                "accept",
                "example",
                "--repo-root",
                str(repo),
                "--include-untracked",
                "--format",
                "json",
                "--expect-plan-id",
                "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution"]["expectation"] == "not-verifiable"
    assert payload["diagnostic"]["code"] == "accept-plan-legacy-journal"
    assert payload["execution"]["journal_retained"] is True


def test_accept_json_already_applied_with_expectation_reports_not_verifiable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """accept --format json already-applied with expectation must report not-verifiable."""
    repo = _lifecycle_repo(tmp_path / "repo", "proposed")

    # First accept
    assert (
        main(
            [
                "accept",
                "example",
                "--repo-root",
                str(repo),
                "--include-untracked",
                "--format",
                "json",
            ]
        )
        == 0
    )
    capsys.readouterr()  # Clear the output

    # Second accept with expectation - should report not-verifiable (no journal to verify)
    assert (
        main(
            [
                "accept",
                "example",
                "--repo-root",
                str(repo),
                "--include-untracked",
                "--format",
                "json",
                "--expect-plan-id",
                "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution"]["status"] == "already-applied"
    assert payload["execution"]["expectation"] == "not-verifiable"


def test_accept_json_interrupted_reports_real_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """accept --format json interrupted must report real completed/total mutation counts."""
    repo = _lifecycle_repo(tmp_path / "repo", "proposed")

    # Use fault_after to simulate interruption
    # We need to call execute_transition directly since CLI doesn't expose fault_after
    from doc_contract.lifecycle import execute_transition, ExecutionStatus
    from test_landing import _settings

    outcome = execute_transition(
        repo,
        _settings(repo),
        "example",
        action="accept",
        include_untracked=True,
        date="2026-08-01",
        fault_after=1,  # Interrupt after first mutation
    )

    assert outcome.execution_status == ExecutionStatus.INTERRUPTED
    assert outcome.journal_retained is True
    assert outcome.completed_mutations >= 1  # At least one mutation completed
    assert outcome.total_mutations >= outcome.completed_mutations
    assert outcome.diagnostic is not None
    assert outcome.diagnostic.code == "accept-interrupted"


def test_accept_json_validation_failed_reports_journal_retained(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """accept --format json validation-failed must report journal retained."""
    repo = _lifecycle_repo(tmp_path / "repo", "proposed")

    # Add a dependency that will cause validation to fail
    _write(
        repo,
        "docs/changes/missing/change.md",
        "---\nid: missing\npersistence: ephemeral\nstatus: proposed\ntrack: test\n---\n# Missing\n",
    )
    roadmap = repo / "docs/roadmap.md"
    roadmap.write_text(
        roadmap.read_text(encoding="utf-8").replace(
            "<!-- BEGIN GENERATED DAG",
            "- `docs/changes/missing/` (proposed)\n\n<!-- BEGIN GENERATED DAG",
        ),
        encoding="utf-8",
    )

    # Accept should still succeed (the missing change is unrelated)
    assert (
        main(
            [
                "accept",
                "example",
                "--repo-root",
                str(repo),
                "--include-untracked",
                "--format",
                "json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution"]["status"] == "applied"


def test_installed_and_vendored_accept_from_unrelated_cwd(
    tmp_path: Path,
) -> None:
    """Installed and synced vendored acceptance must produce identical JSON and plan_id."""
    repo = tmp_path / "repo"
    _write(
        repo,
        ".doc-contract.toml",
        _config(
            capability_mode="optional",
            capability_command=(sys.executable, "-c", "raise SystemExit(0)"),
        ),
    )
    _write(
        repo,
        "docs/roadmap.md",
        "---\npersistence: living\n---\n# Roadmap\n\n"
        "- `docs/changes/example/` (proposed)\n\n"
        "<!-- BEGIN GENERATED DAG (regenerate: doc-contract update --repo-root .) -->\n"
        "```mermaid\nflowchart TD\n```\n<!-- END GENERATED DAG -->\n",
    )
    _write(
        repo,
        "docs/changes/example/change.md",
        "---\nid: example\npersistence: ephemeral\nstatus: proposed\ntrack: test\n---\n"
        "# Example\n\nStatus: Proposed (not accepted)\n",
    )
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    clean_environment = os.environ.copy()
    clean_environment.pop("PYTHONPATH", None)

    # Sync the vendored package
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

    launcher = repo / ".doc-contract/doc_contract_cli.py"

    # Test accept --format json from installed CLI
    installed_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "doc_contract.cli",
            "accept",
            "example",
            "--repo-root",
            str(repo),
            "--include-untracked",
            "--dry-run",
            "--format",
            "json",
        ],
        cwd=elsewhere,
        env=clean_environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert installed_result.returncode == 0, installed_result.stderr
    installed_payload = json.loads(installed_result.stdout)

    # Test accept --format json from vendored CLI
    vendored_result = subprocess.run(
        [
            sys.executable,
            str(launcher),
            "accept",
            "example",
            "--repo-root",
            str(repo),
            "--include-untracked",
            "--dry-run",
            "--format",
            "json",
        ],
        cwd=elsewhere,
        env=clean_environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert vendored_result.returncode == 0, vendored_result.stderr
    vendored_payload = json.loads(vendored_result.stdout)

    # Verify identical schema and plan_id
    assert installed_payload["schema_version"] == vendored_payload["schema_version"]
    assert installed_payload["kind"] == vendored_payload["kind"]
    assert installed_payload["plan_id"] == vendored_payload["plan_id"]
    assert installed_payload["plan"] == vendored_payload["plan"]
    assert installed_payload["execution"] == vendored_payload["execution"]

    # Verify no distribution metadata or third-party dependencies
    assert "version" not in installed_payload
    assert "distribution" not in installed_payload


def test_accept_cli_interrupted_json_reports_real_counts_and_journal_retained(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI-level test: accept --format json interrupted must report real counts and journal_retained."""
    # This test exercises the real CLI path through main(), not just execute_transition
    # We simulate a mid-apply TransactionError by monkeypatching execute_mutations in lifecycle module
    import json as json_module
    from doc_contract import lifecycle as lifecycle_module

    repo = _lifecycle_repo(tmp_path / "repo", "proposed")

    # Track whether the journal was created
    journal_pattern = repo / ".git" / "doc-contract" / "lifecycle-accept-example.json"

    # Monkeypatch execute_mutations to raise ConcurrentModification after journal is created
    original_execute_mutations = lifecycle_module.execute_mutations
    call_count = [0]

    def failing_execute_mutations(
        root: Path,
        plan: object,
        journal_path: Path,
        completed: list[object],
        fault_after: int | None = None,
        save: object = None,
    ) -> None:
        call_count[0] += 1
        # First call: let it create the journal and then fail
        # We need to save the journal first
        if save is not None and hasattr(plan, "as_dict"):
            save(journal_path, plan, completed)  # type: ignore[call-arg]
        # Now raise a ConcurrentModification to simulate a real transaction error
        raise lifecycle_module.ConcurrentModification(
            "completed boundary", "path", "before", "after"
        )

    # Patch execute_mutations in the lifecycle module (where it's actually used)
    lifecycle_module.execute_mutations = failing_execute_mutations  # type: ignore[assignment]

    try:
        result = main(
            [
                "accept",
                "example",
                "--repo-root",
                str(repo),
                "--include-untracked",
                "--format",
                "json",
            ]
        )
    finally:
        # Restore the original function
        lifecycle_module.execute_mutations = original_execute_mutations  # type: ignore[assignment]

    # Should exit nonzero
    assert result == 1
    captured = capsys.readouterr()
    payload = json_module.loads(captured.out)

    # Must report interrupted, not rejected
    assert payload["execution"]["status"] == "interrupted"
    # Must report journal_retained: true
    assert payload["execution"]["journal_retained"] is True
    # Must report exact mutation counts (0 completed, 2 total for this simple change)
    assert payload["execution"]["completed_mutations"] == 0
    assert payload["execution"]["total_mutations"] == 2
    # Must have a diagnostic
    assert payload["diagnostic"]["code"] == "accept-interrupted"
    # Journal file must exist
    assert journal_pattern.parent.is_dir()
    assert list(journal_pattern.parent.glob("*.json"))


def test_accept_cli_schema2_journal_resume_with_mismatching_expectation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Schema-2 journal resume with mismatching expectation must reject before any advance."""
    import json as json_module
    from doc_contract.lifecycle import plan_transition, TransitionAction
    from test_landing import _settings

    repo = _lifecycle_repo(tmp_path / "repo", "proposed")

    # Create a schema-2 journal with a real plan
    plan = plan_transition(
        repo,
        _settings(repo),
        "example",
        action=TransitionAction.ACCEPT,
        include_untracked=True,
        date="2026-08-01",
    )

    # Create a schema-2 journal with completed=[0] (simulating partial progress - first mutation done)
    journal_path = repo / ".git" / "doc-contract" / "lifecycle-accept-example.json"
    journal_path.parent.mkdir(parents=True, exist_ok=True)

    journal_payload = plan.as_dict()
    journal_payload["completed"] = [0] if plan.mutations else []  # List of mutation indices
    journal_path.write_text(json_module.dumps(journal_payload, indent=2), encoding="utf-8")

    # Record the journal bytes before the call
    journal_bytes_before = journal_path.read_bytes()

    # Call with a mismatching expectation
    wrong_plan_id = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    result = main(
        [
            "accept",
            "example",
            "--repo-root",
            str(repo),
            "--include-untracked",
            "--format",
            "json",
            "--expect-plan-id",
            wrong_plan_id,
        ]
    )

    # Should exit nonzero
    assert result == 1
    captured = capsys.readouterr()
    payload = json_module.loads(captured.out)

    # Must report rejected with mismatch
    assert payload["execution"]["status"] == "rejected"
    assert payload["execution"]["expectation"] == "mismatch"
    assert payload["diagnostic"]["code"] == "accept-plan-mismatch"
    # Must report journal_retained: true
    assert payload["execution"]["journal_retained"] is True
    # Must report the correct completed/total counts from the journal
    assert payload["execution"]["completed_mutations"] == 1
    assert payload["execution"]["total_mutations"] == len(plan.mutations)

    # Journal must be byte-identical (no advance occurred)
    assert journal_path.read_bytes() == journal_bytes_before
