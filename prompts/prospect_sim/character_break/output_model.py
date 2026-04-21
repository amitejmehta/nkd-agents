from pydantic import BaseModel
from typing import Literal


class OutputModel(BaseModel):
    confidence: Literal["low", "medium", "high"]
    severity: Literal["none", "minor", "moderate", "severe"]
    evidence: list[str]
    first_occurrence_utterance: int | None
    description: str
    character_break_detected: bool
