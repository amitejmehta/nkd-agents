from pydantic import BaseModel


class OutputModel(BaseModel):
    evidence: list[str]
    description: str
    stage_directions_detected: bool
