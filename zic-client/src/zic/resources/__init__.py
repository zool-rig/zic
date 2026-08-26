from pathlib import Path


def get_resource(name: str) -> str | None:
    path = Path(__file__).parent / name
    return str(path) if path.exists() else None
