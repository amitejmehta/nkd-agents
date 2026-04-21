from pydantic import BaseModel
from typing import Literal


class OutputModel(BaseModel):
    confidence: Literal["low", "medium", "high"]
    severity: Literal["none", "minor", "moderate", "severe"]
    friction_moments_found: list[str]
    description: str
    excessive_cooperation_detected: bool
