"""Unit tests for makelib.version module in makelib-seo."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.makelib.version import (
    VersionError,
    bump_version,
    classify_branch_bump,
    is_valid_branch_name,
    parse_version,
    update_project_version,
)


def test_is_valid_branch_name() -> None:
    """Verify branch naming validation rules."""
    valid_branches = [
        "main",
        "feat/add-secrets",
        "feature/oauth2-flow",
        "fix/missing-semicolon",
        "patch/security-hotfix",
        "major/v2-rewrite",
        "breaking/remove-deprecated",
        "docs/update-readme",
        "chore/bump-dependencies",
        "refactor/split-makefile",
        "ci/matrix-runner",
    ]
    for branch in valid_branches:
        assert is_valid_branch_name(branch), f"Expected valid: {branch}"

    invalid_branches = [
        "my-feature",
        "dev",
        "testing",
        "feature_with_underscores",
        "FEAT/uppercase",
        "feat/",
        "fix/has space in name",
    ]
    for branch in invalid_branches:
        assert not is_valid_branch_name(branch), f"Expected invalid: {branch}"


def test_classify_branch_bump() -> None:
    """Verify branch name classification into SemVer bump types."""
    assert classify_branch_bump("major/v2-launch") == "major"
    assert classify_branch_bump("breaking/drop-py39") == "major"
    assert classify_branch_bump("feat/add-target") == "minor"
    assert classify_branch_bump("feature/auth") == "minor"
    assert classify_branch_bump("fix/typo") == "patch"
    assert classify_branch_bump("docs/changelog") == "patch"
    assert classify_branch_bump("chore/clean") == "patch"
    assert classify_branch_bump("ci/github-action") == "patch"


def test_parse_version() -> None:
    """Verify semantic version parsing and errors."""
    assert parse_version("0.1.0") == (0, 1, 0)
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert parse_version("10.20.30") == (10, 20, 30)
    assert parse_version("0.1.0-rev.2") == (0, 1, 0)
    assert parse_version("v2.0.1-rc.1+build123") == (2, 0, 1)

    with pytest.raises(VersionError, match="Invalid SemVer string"):
        parse_version("invalid-version")

    with pytest.raises(VersionError, match="Invalid SemVer string"):
        parse_version("1.2")


def test_bump_version() -> None:
    """Verify major, minor, and patch increments."""
    # Patch bump
    assert bump_version("0.1.0", "patch") == "0.1.1"
    assert bump_version("1.2.3", "patch") == "1.2.4"
    assert bump_version("0.1.0-rev.2", "patch") == "0.1.1"

    # Minor bump (resets patch)
    assert bump_version("0.1.0", "minor") == "0.2.0"
    assert bump_version("1.2.3", "minor") == "1.3.0"
    assert bump_version("0.1.0-rev.2", "minor") == "0.2.0"

    # Major bump (resets minor and patch)
    assert bump_version("0.1.0", "major") == "1.0.0"
    assert bump_version("1.2.3", "major") == "2.0.0"
    assert bump_version("0.1.0-rev.2", "major") == "1.0.0"

    # Unknown bump type
    with pytest.raises(VersionError, match="Unknown bump type"):
        bump_version("0.1.0", "unknown")


def test_update_project_version(tmp_path: Path) -> None:
    """Verify update_project_version modifies pyproject.toml and package.json."""
    fake_pyproject = tmp_path / "pyproject.toml"
    fake_pyproject.write_text(
        '[project]\nname = "test"\nversion = "0.1.0"\n', encoding="utf-8"
    )

    fake_pkg = tmp_path / "package.json"
    fake_pkg.write_text('{"version": "0.1.0"}\n', encoding="utf-8")

    update_project_version(
        "0.2.0",
        pyproject_path=fake_pyproject,
        package_json_path=fake_pkg,
    )

    assert 'version = "0.2.0"' in fake_pyproject.read_text(encoding="utf-8")
    assert '"0.2.0"' in fake_pkg.read_text(encoding="utf-8")

    # Non-existent files should be skipped cleanly
    update_project_version(
        "0.3.0",
        pyproject_path=tmp_path / "missing.toml",
        package_json_path=tmp_path / "missing.json",
    )
