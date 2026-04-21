from pydantic import BaseModel
from typing import Literal


class OutputModel(BaseModel):
    confidence: Literal["low", "medium", "high"]
    severity: Literal["none", "minor", "moderate", "severe"]
    evidence: str
    description: str
    premature_capitulation_detected: bool
