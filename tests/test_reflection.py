"""Reflection configuration, adapter execution, and proposal tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from doc_contract.config import (
    ConfigError,
    load_settings,
)
from doc_contract.reflection import (
    ReflectionError,
    plan_reflection,
)


def _write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _repo(
    root: Path,
    *,
    config_content: str | None = None,
) -> Path:
    if config_content is None:
        config_content = """schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"
"""
    _write(root, ".doc-contract.toml", config_content)
    _write(root, "docs/roadmap.md", "---\npersistence: living\n---\n# Roadmap\n")
    return root


# --------------------------------------------------------------------------- Configuration tests


def test_reflection_not_configured_is_none_by_default(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    settings = load_settings(repo)
    assert settings.reflection is None


def test_reflection_sources_are_parsed_and_validated(tmp_path: Path) -> None:
    config = """schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]

[[reflection.sources]]
name = "local"
argv = ["python", "-c", "print('test')"]

[[reflection.sources]]
name = "another"
argv = ["echo", "hello"]

[reflection.analyzer]
argv = ["python", "-c", "pass"]
trust = "local"
"""
    repo = _repo(tmp_path / "repo", config_content=config)
    settings = load_settings(repo)
    assert settings.reflection is not None
    assert len(settings.reflection.sources) == 2
    assert settings.reflection.sources[0].name == "local"
    assert settings.reflection.sources[0].argv == ("python", "-c", "print('test')")
    assert settings.reflection.sources[1].name == "another"
    assert settings.reflection.analyzer is not None
    assert settings.reflection.analyzer.trust == "local"


def test_reflection_rejects_empty_source_name(tmp_path: Path) -> None:
    config = """schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[[reflection.sources]]
name = ""
argv = ["python", "-c", "pass"]
"""
    repo = _repo(tmp_path / "repo", config_content=config)
    with pytest.raises(ConfigError) as exc:
        load_settings(repo)
    assert exc.value.code == "config-invalid"


def test_reflection_rejects_shell_string_argv(tmp_path: Path) -> None:
    config = """schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[[reflection.sources]]
name = "bad"
argv = "python -c pass"
"""
    repo = _repo(tmp_path / "repo", config_content=config)
    with pytest.raises(ConfigError) as exc:
        load_settings(repo)
    assert exc.value.code == "config-invalid"


def test_reflection_rejects_empty_argv_element(tmp_path: Path) -> None:
    config = """schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[[reflection.sources]]
name = "bad"
argv = ["python", ""]
"""
    repo = _repo(tmp_path / "repo", config_content=config)
    with pytest.raises(ConfigError) as exc:
        load_settings(repo)
    assert exc.value.code == "config-invalid"


def test_reflection_rejects_invalid_trust_mode(tmp_path: Path) -> None:
    config = """schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]

[[reflection.sources]]
name = "local"
argv = ["python", "-c", "pass"]

[reflection.analyzer]
argv = ["python", "-c", "pass"]
trust = "untrusted"
"""
    repo = _repo(tmp_path / "repo", config_content=config)
    with pytest.raises(ConfigError) as exc:
        load_settings(repo)
    assert exc.value.code == "config-invalid"


def test_reflection_rejects_duplicate_source_names(tmp_path: Path) -> None:
    config = """schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]

[[reflection.sources]]
name = "dup"
argv = ["python", "-c", "pass"]

[[reflection.sources]]
name = "dup"
argv = ["python", "-c", "pass"]
"""
    repo = _repo(tmp_path / "repo", config_content=config)
    with pytest.raises(ConfigError) as exc:
        load_settings(repo)
    assert exc.value.code == "config-invalid"


def test_reflection_default_limits_are_pinned() -> None:
    """REQ-055: Default limits are pinned to the recorded values."""
    from doc_contract.config import (
        DEFAULT_ANALYZER_STDOUT_CAP,
        DEFAULT_ANALYZER_TIMEOUT_SECONDS,
        DEFAULT_MAX_CANDIDATE_REQUIREMENTS,
        DEFAULT_MAX_CANDIDATE_TASKS,
        DEFAULT_MAX_FINDINGS,
        DEFAULT_MAX_NOMINATIONS,
        DEFAULT_MAX_RECOMMENDATIONS,
        DEFAULT_MAX_RECORDS_PER_SOURCE,
        DEFAULT_MAX_TOTAL_RECORDS,
        DEFAULT_SOURCE_STDOUT_CAP,
        DEFAULT_SOURCE_TIMEOUT_SECONDS,
        DEFAULT_SUMMARY_CAP_UTF8_BYTES,
    )

    assert DEFAULT_SOURCE_TIMEOUT_SECONDS == 60
    assert DEFAULT_ANALYZER_TIMEOUT_SECONDS == 180
    assert DEFAULT_SOURCE_STDOUT_CAP == 1_048_576
    assert DEFAULT_ANALYZER_STDOUT_CAP == 1_048_576
    assert DEFAULT_MAX_RECORDS_PER_SOURCE == 500
    assert DEFAULT_MAX_TOTAL_RECORDS == 2000
    assert DEFAULT_SUMMARY_CAP_UTF8_BYTES == 2048
    assert DEFAULT_MAX_FINDINGS == 200
    assert DEFAULT_MAX_RECOMMENDATIONS == 100
    assert DEFAULT_MAX_NOMINATIONS == 50
    assert DEFAULT_MAX_CANDIDATE_REQUIREMENTS == 50
    assert DEFAULT_MAX_CANDIDATE_TASKS == 50


def test_reflection_accepts_valid_limit_overrides(tmp_path: Path) -> None:
    config = """schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]
source_timeout_seconds = 120
max_records_per_source = 100

[[reflection.sources]]
name = "local"
argv = ["python", "-c", "pass"]
"""
    repo = _repo(tmp_path / "repo", config_content=config)
    settings = load_settings(repo)
    assert settings.reflection is not None
    assert settings.reflection.source_timeout_seconds == 120
    assert settings.reflection.max_records_per_source == 100


def test_reflection_rejects_non_positive_limit(tmp_path: Path) -> None:
    config = """schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]
source_timeout_seconds = 0

[[reflection.sources]]
name = "local"
argv = ["python", "-c", "pass"]
"""
    repo = _repo(tmp_path / "repo", config_content=config)
    with pytest.raises(ConfigError) as exc:
        load_settings(repo)
    assert exc.value.code == "config-invalid"


# --------------------------------------------------------------------------- Reflection execution tests


def test_reflection_not_configured_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """REQ-051: reflection-not-configured exits 2."""
    from doc_contract.cli import main

    repo = _repo(tmp_path / "repo")
    assert main(["reflect", "--repo-root", str(repo)]) == 2
    captured = capsys.readouterr()
    assert "reflection-not-configured" in captured.err


def test_unknown_source_name_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """REQ-051: unknown source name exits 2."""
    from doc_contract.cli import main

    config = """schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]

[[reflection.sources]]
name = "local"
argv = ["python", "-c", "pass"]
"""
    repo = _repo(tmp_path / "repo", config_content=config)
    assert main(["reflect", "--source", "unknown", "--repo-root", str(repo)]) == 2
    captured = capsys.readouterr()
    assert "source-unknown" in captured.err


def test_zero_evidence_returns_insufficient_evidence_status(tmp_path: Path) -> None:
    """REQ-050: zero evidence returns insufficient-evidence status."""
    config = """schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]

[[reflection.sources]]
name = "empty"
argv = ["python", "-c", "print('')"]
"""
    repo = _repo(tmp_path / "repo", config_content=config)
    settings = load_settings(repo)
    plan = plan_reflection(repo, settings)
    assert plan.report.status == "insufficient-evidence"
    assert plan.report.evidence == ()
    assert plan.report.recommendations == ()
    assert plan.proposal_id is None


def test_zero_evidence_with_write_proposal_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """REQ-050: zero evidence with --write-proposal exits 1."""
    from doc_contract.cli import main

    config = """schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]

[[reflection.sources]]
name = "empty"
argv = ["python", "-c", "print('')"]
"""
    repo = _repo(tmp_path / "repo", config_content=config)
    assert main(["reflect", "--write-proposal", "test-proposal", "--repo-root", str(repo)]) == 1
    captured = capsys.readouterr()
    assert "proposal-no-remediation" in captured.err


def test_source_adapter_timeout_is_enforced(tmp_path: Path) -> None:
    """REQ-015: source adapter timeout is enforced."""
    config = f"""schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]
source_timeout_seconds = 1

[[reflection.sources]]
name = "slow"
argv = ["{sys.executable}", "-c", "import time; time.sleep(10)"]
"""
    repo = _repo(tmp_path / "repo", config_content=config)
    settings = load_settings(repo)
    with pytest.raises(ReflectionError) as exc:
        plan_reflection(repo, settings)
    assert exc.value.code == "source-timeout"


def test_source_adapter_nonzero_exit_is_reported(tmp_path: Path) -> None:
    """REQ-015: source adapter nonzero exit is reported."""
    config = f"""schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]

[[reflection.sources]]
name = "failing"
argv = ["{sys.executable}", "-c", "raise SystemExit(1)"]
"""
    repo = _repo(tmp_path / "repo", config_content=config)
    settings = load_settings(repo)
    with pytest.raises(ReflectionError) as exc:
        plan_reflection(repo, settings)
    assert exc.value.code == "source-failed"


def test_source_adapter_malformed_jsonl_is_rejected(tmp_path: Path) -> None:
    """REQ-016: source adapter malformed JSONL is rejected."""
    config = f"""schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]

[[reflection.sources]]
name = "bad"
argv = ["{sys.executable}", "-c", "print('not json')"]
"""
    repo = _repo(tmp_path / "repo", config_content=config)
    settings = load_settings(repo)
    with pytest.raises(ReflectionError) as exc:
        plan_reflection(repo, settings)
    assert exc.value.code == "source-output-malformed"


def test_diagnostics_are_value_free(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """REQ-012: diagnostics are value-free and don't expose raw values."""
    from doc_contract.cli import main

    config = f"""schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]

[[reflection.sources]]
name = "test"
argv = ["{sys.executable}", "-c", "import sys; sys.exit(42)"]
"""
    repo = _repo(tmp_path / "repo", config_content=config)
    assert main(["reflect", "--repo-root", str(repo)]) == 1
    captured = capsys.readouterr()
    # Should not expose the exit code 42 in the message
    assert "42" not in captured.err
    assert "source-failed" in captured.err


def test_adapter_output_is_not_echoed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """REQ-012: adapter output is not echoed in diagnostics."""
    from doc_contract.cli import main

    config = f"""schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]

[[reflection.sources]]
name = "test"
argv = ["{sys.executable}", "-c", "print('SECRET_API_KEY=sk-12345')"]
"""
    repo = _repo(tmp_path / "repo", config_content=config)
    assert main(["reflect", "--repo-root", str(repo)]) == 1
    captured = capsys.readouterr()
    # Should not echo the secret-looking output
    assert "SECRET_API_KEY" not in captured.out
    assert "SECRET_API_KEY" not in captured.err
    assert "sk-12345" not in captured.out
    assert "sk-12345" not in captured.err


# --------------------------------------------------------------------------- CLI tests


def test_reflect_cli_json_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI --format json produces valid JSON output."""
    from doc_contract.cli import main

    # Create a simple source that outputs valid evidence
    # The repository name is derived from the directory name
    repo_name = "repo"
    evidence_json = json.dumps({
        "schema_version": 1,
        "record_id": "test-1",
        "repository": repo_name,
        "observed_at": "2026-01-01T00:00:00Z",
        "kind": "test",
        "digest": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        "byte_length": 100,
    })
    # Escape for Python string
    escaped = evidence_json.replace('"', '\\"')
    config = f"""schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]

[[reflection.sources]]
name = "test"
argv = ["{sys.executable}", "-c", "print('{escaped}')"]
"""
    repo = _repo(tmp_path / repo_name, config_content=config)
    assert main(["reflect", "--repo-root", str(repo), "--format", "json"]) == 0
    captured = capsys.readouterr()
    # Should be valid JSON
    result = json.loads(captured.out)
    assert result["status"] == "no-findings"
    assert result["repository"] == repo_name


def test_reflect_cli_text_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI --format text produces human-readable output."""
    from doc_contract.cli import main

    repo_name = "repo"
    evidence_json = json.dumps({
        "schema_version": 1,
        "record_id": "test-1",
        "repository": repo_name,
        "observed_at": "2026-01-01T00:00:00Z",
        "kind": "test",
        "digest": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        "byte_length": 100,
    })
    escaped = evidence_json.replace('"', '\\"')
    config = f"""schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]

[[reflection.sources]]
name = "test"
argv = ["{sys.executable}", "-c", "print('{escaped}')"]
"""
    repo = _repo(tmp_path / repo_name, config_content=config)
    assert main(["reflect", "--repo-root", str(repo), "--format", "text"]) == 0
    captured = capsys.readouterr()
    # Text output shows plan summary
    assert "reflection plan" in captured.out
    assert repo_name in captured.out


def test_reflect_cli_since_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI --since flag is passed to adapters."""
    from doc_contract.cli import main

    repo_name = "repo"
    evidence_json = json.dumps({
        "schema_version": 1,
        "record_id": "test-1",
        "repository": repo_name,
        "observed_at": "2026-01-01T00:00:00Z",
        "kind": "test",
        "digest": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        "byte_length": 100,
    })
    escaped = evidence_json.replace('"', '\\"')
    config = f"""schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]

[[reflection.sources]]
name = "test"
argv = ["{sys.executable}", "-c", "print('{escaped}')"]
"""
    repo = _repo(tmp_path / repo_name, config_content=config)
    assert main(["reflect", "--repo-root", str(repo), "--since", "2026-01-01"]) == 0
    captured = capsys.readouterr()
    assert "since: 2026-01-01" in captured.out


# --------------------------------------------------------------------------- Proposal write tests (F-010)


def test_successful_proposal_write_creates_files(tmp_path: Path) -> None:
    """REQ-025: successful proposal write creates change.md and updates roadmap."""
    import subprocess

    repo_name = "repo"
    evidence_json = json.dumps({
        "schema_version": 1,
        "record_id": "test-1",
        "repository": repo_name,
        "observed_at": "2026-01-01T00:00:00Z",
        "kind": "test",
        "digest": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        "byte_length": 100,
    })
    escaped = evidence_json.replace('"', '\\"')
    # Analyzer that produces substantial remediation - write to a temp file
    analyzer_script = tmp_path / "analyzer.py"
    analyzer_script.write_text('''
import json
import sys
request = json.load(sys.stdin)
result = {
    "findings": [],
    "recommendations": [],
    "nominations": [],
    "remediation": {
        "why": "Test remediation for proposal creation",
        "requirements": [{"text": "Test requirement", "evidence_ids": ["test:test-1"]}],
        "tasks": [{"text": "Test task", "evidence_ids": ["test:test-1"]}],
        "files_owned": ["src/test.py"],
        "exclusions": [],
        "verification": "Run tests"
    }
}
print(json.dumps(result))
''', encoding="utf-8")
    config = f"""schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]

[[reflection.sources]]
name = "test"
argv = ["{sys.executable}", "-c", "print('{escaped}')"]

[reflection.analyzer]
argv = ["{sys.executable}", "{analyzer_script}"]
trust = "local"
"""
    repo = tmp_path / repo_name
    _write(repo, ".doc-contract.toml", config)
    # Roadmap with Remediation section and DAG markers
    roadmap_content = """---
persistence: living
---
# Roadmap

## Remediation

<!-- BEGIN GENERATED DAG (regenerate: doc-contract update --repo-root .) -->
```mermaid
flowchart TD
```
<!-- END GENERATED DAG -->
"""
    _write(repo, "docs/roadmap.md", roadmap_content)

    # Initialize git repo
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init", "-q"], cwd=repo, check=True, capture_output=True)

    settings = load_settings(repo)
    from doc_contract.reflection import execute_reflection

    outcome = execute_reflection(
        repo,
        settings,
        write_proposal=True,
        proposal_id="test-proposal",
    )

    # Verify proposal was created
    assert outcome.plan is not None
    assert outcome.plan.proposal_id == "test-proposal"
    proposal_path = repo / "docs/changes/test-proposal/change.md"
    assert proposal_path.exists()
    content = proposal_path.read_text(encoding="utf-8")
    assert "status: proposed" in content
    assert "Status: Proposed (not accepted)" in content

    # Verify roadmap was updated
    roadmap_path = repo / "docs/roadmap.md"
    roadmap_new = roadmap_path.read_text(encoding="utf-8")
    assert "docs/changes/test-proposal/" in roadmap_new
    assert "(proposed)" in roadmap_new

    # Verify final findings were computed
    assert outcome.final_findings is not None


def test_dry_run_does_not_write_files(tmp_path: Path) -> None:
    """REQ-025: dry-run (write_proposal=False) does not write any files."""
    import subprocess

    repo_name = "repo"
    evidence_json = json.dumps({
        "schema_version": 1,
        "record_id": "test-1",
        "repository": repo_name,
        "observed_at": "2026-01-01T00:00:00Z",
        "kind": "test",
        "digest": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        "byte_length": 100,
    })
    escaped = evidence_json.replace('"', '\\"')
    analyzer_script = tmp_path / "analyzer.py"
    analyzer_script.write_text('''
import json
import sys
request = json.load(sys.stdin)
result = {
    "findings": [],
    "recommendations": [],
    "nominations": [],
    "remediation": {
        "why": "Test remediation",
        "requirements": [],
        "tasks": [],
        "files_owned": [],
        "exclusions": [],
        "verification": "Run tests"
    }
}
print(json.dumps(result))
''', encoding="utf-8")
    config = f"""schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]

[[reflection.sources]]
name = "test"
argv = ["{sys.executable}", "-c", "print('{escaped}')"]

[reflection.analyzer]
argv = ["{sys.executable}", "{analyzer_script}"]
trust = "local"
"""
    repo = tmp_path / repo_name
    _write(repo, ".doc-contract.toml", config)
    roadmap_content = """---
persistence: living
---
# Roadmap

## Remediation

<!-- BEGIN GENERATED DAG (regenerate: doc-contract update --repo-root .) -->
```mermaid
flowchart TD
```
<!-- END GENERATED DAG -->
"""
    _write(repo, "docs/roadmap.md", roadmap_content)

    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init", "-q"], cwd=repo, check=True, capture_output=True)

    settings = load_settings(repo)
    from doc_contract.reflection import execute_reflection

    # Record state before
    proposal_path = repo / "docs/changes/test-proposal/change.md"
    assert not proposal_path.exists()

    execute_reflection(
        repo,
        settings,
        write_proposal=False,
        proposal_id="test-proposal",
    )

    # Verify no files were written
    assert not proposal_path.exists()
    assert not (repo / "docs/changes/test-proposal").exists()
    # No journal should exist
    assert not (repo / ".git" / "doc-contract").exists()


def test_destination_collision_is_rejected(tmp_path: Path) -> None:
    """REQ-025: destination collision is rejected."""
    import subprocess

    repo_name = "repo"
    evidence_json = json.dumps({
        "schema_version": 1,
        "record_id": "test-1",
        "repository": repo_name,
        "observed_at": "2026-01-01T00:00:00Z",
        "kind": "test",
        "digest": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        "byte_length": 100,
    })
    escaped = evidence_json.replace('"', '\\"')
    analyzer_script = tmp_path / "analyzer.py"
    analyzer_script.write_text('''
import json
import sys
request = json.load(sys.stdin)
result = {
    "findings": [],
    "recommendations": [],
    "nominations": [],
    "remediation": {
        "why": "Test remediation",
        "requirements": [],
        "tasks": [],
        "files_owned": [],
        "exclusions": [],
        "verification": "Run tests"
    }
}
print(json.dumps(result))
''', encoding="utf-8")
    config = f"""schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]

[[reflection.sources]]
name = "test"
argv = ["{sys.executable}", "-c", "print('{escaped}')"]

[reflection.analyzer]
argv = ["{sys.executable}", "{analyzer_script}"]
trust = "local"
"""
    repo = tmp_path / repo_name
    _write(repo, ".doc-contract.toml", config)
    roadmap_content = """---
persistence: living
---
# Roadmap

## Remediation

<!-- BEGIN GENERATED DAG (regenerate: doc-contract update --repo-root .) -->
```mermaid
flowchart TD
```
<!-- END GENERATED DAG -->
"""
    _write(repo, "docs/roadmap.md", roadmap_content)

    # Pre-create the proposal directory
    _write(repo, "docs/changes/existing-proposal/change.md", "---\nid: existing-proposal\n---\n# Existing")

    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init", "-q"], cwd=repo, check=True, capture_output=True)

    settings = load_settings(repo)
    from doc_contract.reflection import execute_reflection

    with pytest.raises(ReflectionError) as exc:
        execute_reflection(
            repo,
            settings,
            write_proposal=True,
            proposal_id="existing-proposal",
        )
    assert exc.value.code == "proposal-exists"


# --------------------------------------------------------------------------- F-012: Timestamp and digest validation regression tests


def test_malformed_timestamp_is_rejected(tmp_path: Path) -> None:
    """F-012: malformed timestamp is rejected with evidence-field-invalid."""
    repo_name = "repo"
    evidence_json = json.dumps({
        "schema_version": 1,
        "record_id": "test-1",
        "repository": repo_name,
        "observed_at": "not-a-timestamp",
        "kind": "test",
        "digest": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        "byte_length": 100,
    })
    escaped = evidence_json.replace('"', '\\"')
    config = f"""schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]

[[reflection.sources]]
name = "test"
argv = ["{sys.executable}", "-c", "print('{escaped}')"]
"""
    repo = _repo(tmp_path / repo_name, config_content=config)
    settings = load_settings(repo)
    with pytest.raises(ReflectionError) as exc:
        plan_reflection(repo, settings)
    assert exc.value.code == "evidence-field-invalid"
    # Diagnostic must be value-free (no timestamp value in message)
    assert "not-a-timestamp" not in exc.value.detail


def test_malformed_digest_is_rejected(tmp_path: Path) -> None:
    """F-012: malformed digest is rejected with evidence-field-invalid."""
    repo_name = "repo"
    evidence_json = json.dumps({
        "schema_version": 1,
        "record_id": "test-1",
        "repository": repo_name,
        "observed_at": "2026-01-01T00:00:00Z",
        "kind": "test",
        "digest": "zzzz-not-a-sha256",
        "byte_length": 100,
    })
    escaped = evidence_json.replace('"', '\\"')
    config = f"""schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]

[[reflection.sources]]
name = "test"
argv = ["{sys.executable}", "-c", "print('{escaped}')"]
"""
    repo = _repo(tmp_path / repo_name, config_content=config)
    settings = load_settings(repo)
    with pytest.raises(ReflectionError) as exc:
        plan_reflection(repo, settings)
    assert exc.value.code == "evidence-field-invalid"
    # Diagnostic must be value-free (no digest value in message)
    assert "zzzz-not-a-sha256" not in exc.value.detail
    assert "zzzz-not-a-sha256" not in exc.value.detail


def test_valid_timestamp_and_digest_parse_successfully(tmp_path: Path) -> None:
    """F-012: valid timestamp and digest parse successfully."""
    repo_name = "repo"
    evidence_json = json.dumps({
        "schema_version": 1,
        "record_id": "test-1",
        "repository": repo_name,
        "observed_at": "2026-01-01T00:00:00Z",
        "kind": "test",
        "digest": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        "byte_length": 100,
    })
    escaped = evidence_json.replace('"', '\\"')
    config = f"""schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]

[[reflection.sources]]
name = "test"
argv = ["{sys.executable}", "-c", "print('{escaped}')"]
"""
    repo = _repo(tmp_path / repo_name, config_content=config)
    settings = load_settings(repo)
    plan = plan_reflection(repo, settings)
    assert plan.report.status == "no-findings"
    assert len(plan.report.evidence) == 1
    # Verify digest is normalized to lowercase
    assert plan.report.evidence[0].digest == "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"


def test_timestamp_accepts_various_iso8601_forms(tmp_path: Path) -> None:
    """F-012: timestamp accepts various ISO-8601 forms."""
    repo_name = "repo"
    # Test YYYY-MM-DD form
    evidence_json = json.dumps({
        "schema_version": 1,
        "record_id": "test-1",
        "repository": repo_name,
        "observed_at": "2026-01-01",
        "kind": "test",
        "digest": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        "byte_length": 100,
    })
    escaped = evidence_json.replace('"', '\\"')
    config = f"""schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]

[[reflection.sources]]
name = "test"
argv = ["{sys.executable}", "-c", "print('{escaped}')"]
"""
    repo = _repo(tmp_path / repo_name, config_content=config)
    settings = load_settings(repo)
    plan = plan_reflection(repo, settings)
    assert plan.report.status == "no-findings"


def test_digest_is_normalized_to_lowercase(tmp_path: Path) -> None:
    """F-012: digest is normalized to lowercase."""
    repo_name = "repo"
    # Use uppercase digest
    evidence_json = json.dumps({
        "schema_version": 1,
        "record_id": "test-1",
        "repository": repo_name,
        "observed_at": "2026-01-01T00:00:00Z",
        "kind": "test",
        "digest": "9F86D081884C7D659A2FEAA0C55AD015A3BF4F1B2B0B822CD15D6C15B0F00A08",
        "byte_length": 100,
    })
    escaped = evidence_json.replace('"', '\\"')
    config = f"""schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]

[[reflection.sources]]
name = "test"
argv = ["{sys.executable}", "-c", "print('{escaped}')"]
"""
    repo = _repo(tmp_path / repo_name, config_content=config)
    settings = load_settings(repo)
    plan = plan_reflection(repo, settings)
    assert plan.report.status == "no-findings"
    # Verify digest is normalized to lowercase
    assert plan.report.evidence[0].digest == "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"


# --------------------------------------------------------------------------- F-013: Summary byte cap regression tests


def test_summary_byte_cap_enforced_on_multibyte_utf8(tmp_path: Path) -> None:
    """F-013: summary byte cap is enforced on multibyte UTF-8 strings."""
    repo_name = "repo"
    # Create a summary with multibyte UTF-8 characters that exceeds the 2048-byte cap
    # Each Chinese character is 3 bytes in UTF-8, so 800 chars = 2400 bytes
    multibyte_char = "中"  # 3 bytes in UTF-8
    long_summary = multibyte_char * 800  # 2400 bytes
    evidence_json = json.dumps({
        "schema_version": 1,
        "record_id": "test-1",
        "repository": repo_name,
        "observed_at": "2026-01-01T00:00:00Z",
        "kind": "test",
        "digest": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        "byte_length": 100,
        "summary": long_summary,
    })
    escaped = evidence_json.replace('"', '\\"')
    config = f"""schema_version = 1
repo_name = "fixture"
roadmap = "docs/roadmap.md"

[root_nodes]
roadmap = "docs/roadmap.md"

[capability]
mode = "skip"

[reflection]

[[reflection.sources]]
name = "test"
argv = ["{sys.executable}", "-c", "print('{escaped}')"]
"""
    repo = _repo(tmp_path / repo_name, config_content=config)
    settings = load_settings(repo)
    plan = plan_reflection(repo, settings)
    assert plan.report.status == "no-findings"
    assert len(plan.report.evidence) == 1
    # Verify summary is truncated and redacted
    assert plan.report.evidence[0].redacted is True
    # Verify the truncated summary is within the byte cap
    truncated_summary = plan.report.evidence[0].summary
    assert truncated_summary is not None
    assert len(truncated_summary.encode("utf-8")) <= settings.reflection.summary_cap
    # Verify it's not empty (some content preserved)
    assert len(truncated_summary) > 0