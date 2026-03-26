"""Custom checks for this prompt. Runs via pytest.

Add functions here for checks that go beyond the built-in types
(contains, regex, max_length, etc.). The runner imports this module
and calls any function matching check type names.

Each function takes (output: str, **check_params) -> tuple[bool, str].
Returns (passed, reason).
"""


def tone_is_professional(output: str, **kwargs: object) -> tuple[bool, str]:
    """Example custom check. Replace with your own."""
    informal = ["lol", "gonna", "wanna", "tbh", "ngl"]
    found = [w for w in informal if w.lower() in output.lower()]
    if found:
        return False, f"Informal language found: {found}"
    return True, "Tone OK"