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
