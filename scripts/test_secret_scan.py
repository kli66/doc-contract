"""Focused regression tests for the value-free secret scanner."""

from __future__ import annotations

from pathlib import Path

from dag import resolve
from secret_scan import format_findings, scan_file, scan_tree


def _write(root: Path, relative: str, content: str | bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def test_assignments_and_known_environment_names_are_metadata_only(tmp_path: Path) -> None:
    payload = "sk-example-not-for-use"
    environment_name = "GITHUB_" + "TOKEN"
    path = _write(
        tmp_path,
        "package/config.py",
        f'api_key = "{payload}"\naccess_token: \'abc123\'\n'
        'value = "ordinary"\n'
        f'os.environ.get("{environment_name}")\n',
    )

    findings = scan_file(path, root=tmp_path)
    assert [(finding.variable, finding.kind, finding.length) for finding in findings] == [
        ("API_KEY", "assignment", len(payload)),
        ("ACCESS_TOKEN", "assignment", 6),
        ("GITHUB_TOKEN", "environment-reference", 0),
    ]
    rendered = format_findings(findings)
    assert payload not in rendered
    assert "abc123" not in rendered
    assert "API_KEY" in rendered and "length=" in rendered


def test_env_files_are_scanned_but_ordinary_configuration_is_clean(tmp_path: Path) -> None:
    _write(tmp_path, ".env", "SERVICE_URL=https://example.test\nCUSTOM_FLAG=1\n")
    ordinary = _write(tmp_path, "settings.ini", "timeout=30\nretry_count=2\ntoken_bucket=100\n")

    env_findings = scan_file(tmp_path / ".env", root=tmp_path)
    assert [finding.variable for finding in env_findings] == ["SERVICE_URL", "CUSTOM_FLAG"]
    assert scan_file(ordinary, root=tmp_path) == []


def test_exclusions_cover_vcs_caches_bytecode_and_binary_files(tmp_path: Path) -> None:
    for directory in (".git", ".pytest_cache", "__pycache__", ".venv"):
        _write(tmp_path, f"{directory}/leak.txt", "API_KEY=should-not-be-read")
    _write(tmp_path, "artifact.bin", b"API_KEY=binary\x00payload")
    assert scan_tree(tmp_path) == []


def test_resolver_fails_on_secret_and_printed_finding_has_no_value(tmp_path: Path) -> None:
    _write(tmp_path, "docs/roadmap.md", "---\npersistence: living\n---\n# roadmap\n")
    _write(tmp_path, "generated/report.txt", "OPENAI_API_KEY=sk-generated-fixture\n")

    result = resolve(tmp_path)
    secret_findings = [finding for finding in result.errors if finding.code == "secret-detected"]
    assert len(secret_findings) == 1
    assert "sk-generated-fixture" not in secret_findings[0].message
    assert "OPENAI_API_KEY" in secret_findings[0].message


def test_custom_environment_names_do_not_require_values(tmp_path: Path) -> None:
    path = _write(tmp_path, "app.py", 'os.getenv("INTERNAL_CREDENTIAL")\n')
    findings = scan_file(path, root=tmp_path, secret_env_names=("INTERNAL_CREDENTIAL",))
    assert [(finding.variable, finding.present, finding.length) for finding in findings] == [
        ("INTERNAL_CREDENTIAL", False, 0)
    ]


def test_yaml_dependency_key_containing_secret_is_not_an_assignment(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "change.md",
        "fingerprints:\n  secret-handling-guardrails: 0123456789abcdef\n",
    )
    assert scan_file(path, root=tmp_path) == []
