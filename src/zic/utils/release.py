import importlib.metadata

# Name of the package on PyPI. Not "zic": PyPI deems it too similar to an
# existing project ("zlc", as it treats i and l alike). The module and the
# command are still "zic".
DISTRIBUTION_NAME = "zic-player"

RELEASE_DATE_KEYWORD = "release-date:"


def find_release_date(keywords_fields: list[str]) -> str | None:
    """The release date, stored as a "release-date:YYYY-MM-DD" keyword in
    pyproject.toml to be readable through importlib.metadata. Packaging
    joins all the keywords into one comma-separated field."""
    for field in keywords_fields:
        for keyword in field.split(","):
            keyword = keyword.strip()
            if keyword.startswith(RELEASE_DATE_KEYWORD):
                return keyword.removeprefix(RELEASE_DATE_KEYWORD) or None
    return None


def package_metadata() -> importlib.metadata.PackageMetadata:
    return importlib.metadata.metadata(DISTRIBUTION_NAME)


def package_version() -> str:
    return importlib.metadata.version(DISTRIBUTION_NAME)
