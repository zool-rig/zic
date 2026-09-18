import os

from secret_type import secret
from secret_type.typing.types import StringLike
from typing import Self


class DiscogsSecret:
    def __init__(self, key: str, token: str) -> None:
        self._key: StringLike = secret(key)
        self._token: StringLike = secret(token)

    @classmethod
    def from_env(cls) -> Self:
        return cls(
            os.environ.get("ZIC_INGESTOR_DISCOGS_KEY", ""),
            os.environ.get("ZIC_INGESTOR_DISCOGS_TOKEN", "")
        )

    @property
    def key(self) -> StringLike:
        return self._key

    @key.setter
    def key(self, key: str) -> None:
        self._key = secret(key or "")

    @property
    def token(self) -> StringLike:
        return self._token

    @token.setter
    def token(self, token: str) -> None:
        self._token = secret(token or "")


class InvalidDiscogsSecrets(Exception):
    def __init__(self) -> None:
        super().__init__(
            "Please provide a Discogs key and a token from the CLI options"
            " or from environment variables : ZIC_INGESTOR_DISCOGS_KEY and ZIC_INGESTOR_DISCOGS_TOKEN"
        )
