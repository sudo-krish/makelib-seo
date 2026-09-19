"""Semantic versioning and branch classification engine for makelib-seo."""

from __future__ import annotations

import json
import re
from pathlib import Path

BRANCH_REGEX = (
    r"^(feat|feature|fix|patch|major|breaking|docs|chore|refactor|ci)/[a-z0-9._-]+$"
)
SEMVER_REGEX = r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$"


class VersionError(Exception):
    """Raised when version parsing or bumping fails."""


def is_valid_branch_name(branch: str) -> bool:
    """Validate branch name against the strict classification schema."""
    if branch == "main":
        return True
    return bool(re.match(BRANCH_REGEX, branch))


def classify_branch_bump(branch: str) -> str:
    """Classify SemVer bump type based on branch prefix."""
    clean_branch = branch.strip()
    if clean_branch.startswith(("major/", "breaking/")):
        return "major"
    if clean_branch.startswith(("feat/", "feature/")):
        return "minor"
    return "patch"


def parse_version(version_str: str) -> tuple[int, int, int]:
    """Parse a semantic version string into (major, minor, patch) integers."""
    match = re.match(SEMVER_REGEX, version_str.strip())
    if not match:
        raise VersionError(
            f"Invalid SemVer string '{version_str}'. Expected format: 'X.Y.Z'"
        )
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def bump_version(version_str: str, bump_type: str) -> str:
    """Increment a semantic version by major, minor, or patch part."""
    major, minor, patch = parse_version(version_str)
    normalized = bump_type.lower().strip()

    if normalized == "major":
        return f"{major + 1}.0.0"
    if normalized == "minor":
        return f"{major}.{minor + 1}.0"
    if normalized == "patch":
        return f"{major}.{minor}.{patch + 1}"

    raise VersionError(
        f"Unknown bump type '{bump_type}'. Must be 'major', 'minor', or 'patch'."
    )


def update_project_version(
    new_version: str,
    pyproject_path: Path | str = "pyproject.toml",
    package_json_path: Path | str = "package.json",
) -> None:
    """Update version declarations in pyproject.toml and package.json."""
    p_path = Path(pyproject_path)
    if p_path.is_file():
        content = p_path.read_text(encoding="utf-8")
        updated = re.sub(
            r'^version\s*=\s*".*?"',
            f'version = "{new_version}"',
            content,
            flags=re.MULTILINE,
        )
        p_path.write_text(updated, encoding="utf-8")

    pkg_path = Path(package_json_path)
    if pkg_path.is_file():
        try:
            d = json.loads(pkg_path.read_text(encoding="utf-8"))
            d["version"] = new_version
            pkg_path.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass
