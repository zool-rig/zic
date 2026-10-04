"""Release checks and README preparation, run by the release workflow.

    python .github/scripts/prepare_release.py v0.1.0

- the tag must match the version in pyproject.toml;
- the "release-date:YYYY-MM-DD" keyword must be today's date (one day of
  leeway for time zones), as the About dialog shows it;
- README links relative to the repository are made absolute, pinned to the
  tag: PyPI renders the README without the repository around it.

Standard library only: runs without installing the project."""

import re
import sys
import tomllib
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "zool-rig/zic"
RELEASE_DATE_KEYWORD = "release-date:"
MAX_DATE_GAP_DAYS = 1


def fail(message: str) -> None:
    print(f"::error::{message}")
    sys.exit(1)


def check_version(tag: str, project: dict) -> None:
    version = project["version"]
    if tag != f"v{version}":
        fail(f"Tag {tag} doesn't match the version in pyproject.toml ({version}).")
    print(f"Version {version} matches the tag.")


def check_release_date(project: dict, today: date) -> None:
    dates = [
        keyword.removeprefix(RELEASE_DATE_KEYWORD)
        for keyword in project.get("keywords", [])
        if keyword.startswith(RELEASE_DATE_KEYWORD)
    ]
    if not dates:
        fail(f"No '{RELEASE_DATE_KEYWORD}YYYY-MM-DD' keyword in pyproject.toml.")
    try:
        release_date = date.fromisoformat(dates[0])
    except ValueError:
        fail(f"Invalid release date in pyproject.toml: {dates[0]!r}.")
    if abs((release_date - today).days) > MAX_DATE_GAP_DAYS:
        fail(
            f"Release date in pyproject.toml is {release_date}, not today "
            f"({today}): update it before tagging."
        )
    print(f"Release date {release_date} is up to date.")


def absolute_readme(readme: str, ref: str) -> str:
    """Rewrites links to repository files ("images/x.png", "LICENSE"...)
    into GitHub URLs; leaves web links and #anchors alone."""
    raw = f"https://raw.githubusercontent.com/{REPOSITORY}/{ref}/"
    blob = f"https://github.com/{REPOSITORY}/blob/{ref}/"

    def link(match: re.Match) -> str:
        prefix, target = match.group(1), match.group(2)
        is_image = prefix.startswith(("src=", "!["))
        return f"{prefix}{raw if is_image else blob}{target}"

    relative = r"(?!https?://|#|mailto:)([^)\"\s]+)"
    readme = re.sub(r'(src=")' + relative, link, readme)
    return re.sub(r"(!?\[[^\]]*\]\()" + relative, link, readme)


def main() -> None:
    if len(sys.argv) != 2:
        fail("Usage: prepare_release.py <tag>")
    tag = sys.argv[1]
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]

    check_version(tag, project)
    check_release_date(project, datetime.now(UTC).date())

    readme_path = ROOT / "README.md"
    readme_path.write_text(absolute_readme(readme_path.read_text(), tag))
    print(f"README links pinned to {tag}.")


if __name__ == "__main__":
    main()
