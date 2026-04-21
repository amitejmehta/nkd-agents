from pydantic import BaseModel
from typing import Literal


class OutputModel(BaseModel):
    confidence: Literal["low", "medium", "high"]
    severity: Literal["none", "minor", "moderate", "severe"]
    evidence: list[str]
    description: str
    persona_inconsistency_detected: bool
