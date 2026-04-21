from pydantic import BaseModel
from typing import Literal


class OutputModel(BaseModel):
    confidence: Literal["low", "medium", "high"]
    severity: Literal["none", "minor", "moderate", "severe"]
    missing_objections: list[str]
    description: str
    phantom_objection_detected: bool
