from dataclasses import dataclass


@dataclass(slots=True)
class Artist:
    id: int
    name: str
    normalized_name: str
