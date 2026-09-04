import json

from dataclasses import dataclass, field


@dataclass(slots=True)
class Genre:
    id: int
    name: str
    _raw_position: str = field(repr=False, compare=False)
    position: list[float] = field(init=False)

    def __post_init__(self) -> None:
        self.position: list[float] = json.loads(self._raw_position)
