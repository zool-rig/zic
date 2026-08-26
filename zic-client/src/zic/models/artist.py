from pydantic import BaseModel


class Artist(BaseModel):
    id: int
    name: str
    normalized_name: str
