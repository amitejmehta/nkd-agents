"""Custom programmatic check for stage_directions eval.

Supplements the llm_judge by also regex-scanning the raw output JSON
for the detected boolean — fast sanity check before the judge runs.
"""

import json
import re


def output_is_valid_json(output: str, **kwargs: object) -> tuple[bool, str]:
    """Ensure output parses as JSON with required fields."""
    try:
        data = json.loads(output)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}"
    required = {"stage_directions_detected", "evidence", "description"}
    missing = required - data.keys()
    if missing:
        return False, f"Missing fields: {missing}"
    return True, "JSON valid with required fields"


def stage_directions_field_is_bool(output: str, **kwargs: object) -> tuple[bool, str]:
    """stage_directions_detected must be a boolean."""
    try:
        data = json.loads(output)
        val = data.get("stage_directions_detected")
    except (json.JSONDecodeError, AttributeError):
        return False, "Could not parse JSON"
    if not isinstance(val, bool):
        return False, f"stage_directions_detected is {type(val).__name__}, expected bool"
    return True, f"stage_directions_detected is bool: {val}"


def evidence_is_list(output: str, **kwargs: object) -> tuple[bool, str]:
    """evidence field must be a list."""
    try:
        data = json.loads(output)
        val = data.get("evidence")
    except (json.JSONDecodeError, AttributeError):
        return False, "Could not parse JSON"
    if not isinstance(val, list):
        return False, f"evidence is {type(val).__name__}, expected list"
    return True, "evidence is a list"


def asterisk_pattern_caught(output: str, transcript: str = "", **kwargs: object) -> tuple[bool, str]:
    """If transcript contains *word* patterns, detected must be true."""
    if not transcript:
        return True, "No transcript provided — skip"
    has_asterisk = bool(re.search(r"\*[^*]+\*", transcript))
    if not has_asterisk:
        return True, "No asterisk patterns in transcript — skip"
    try:
        data = json.loads(output)
        detected = data.get("stage_directions_detected", False)
    except (json.JSONDecodeError, AttributeError):
        return False, "Could not parse JSON"
    if not detected:
        return False, "Asterisk stage directions in transcript but detected=false"
    return True, "Asterisk patterns correctly flagged"
