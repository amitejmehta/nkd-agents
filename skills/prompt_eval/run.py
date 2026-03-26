"""Prompt eval runner. Loads a prompt directory, executes test cases, writes results.

Usage: python skills/prompt_eval/run.py prompts/<name> [--model MODEL]
"""

import asyncio
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from nkd_agents.anthropic import llm, output_format, user

# --- Built-in checks ---


def check_contains(output: str, value: str, **_: object) -> tuple[bool, str]:
    ok = value in output
    return ok, f"{'Found' if ok else 'Missing'}: {value!r}"


def check_not_contains(output: str, value: str, **_: object) -> tuple[bool, str]:
    ok = value not in output
    return ok, f"{'Absent' if ok else 'Found'}: {value!r}"


def check_regex(
    output: str, pattern: str, must_match: bool = True, **_: object
) -> tuple[bool, str]:
    matched = bool(re.search(pattern, output))
    ok = matched == must_match
    return ok, f"regex {pattern!r} {'matched' if matched else 'no match'}"


def check_max_length(output: str, value: int, **_: object) -> tuple[bool, str]:
    ok = len(output) <= value
    return ok, f"length {len(output)}/{value}"


def check_min_length(output: str, value: int, **_: object) -> tuple[bool, str]:
    ok = len(output) >= value
    return ok, f"length {len(output)}/{value}"


BUILTIN_CHECKS = {
    "contains": check_contains,
    "not_contains": check_not_contains,
    "regex": check_regex,
    "max_length": check_max_length,
    "min_length": check_min_length,
}


# --- Custom checks loader ---


def load_custom_checks(prompt_dir: Path) -> dict[str, object]:
    checks_file = prompt_dir / "checks.py"
    if not checks_file.exists():
        return {}
    spec = importlib.util.spec_from_file_location("custom_checks", checks_file)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {
        name: getattr(mod, name)
        for name in dir(mod)
        if callable(getattr(mod, name)) and not name.startswith("_")
    }


# --- LLM-as-judge ---


class JudgeResult(BaseModel):
    reason: str
    passed: bool


JUDGE_SYSTEM = """You are evaluating an AI assistant's output. First explain your reasoning, then score as PASS or FAIL.

{judge_criteria}"""

JUDGE_USER = """**Expected behavior**: {expected_behavior}

**Actual output**:
{output}"""


async def judge(
    client: AsyncAnthropic,
    output: str,
    expected_behavior: str,
    judge_criteria: str,
    model: str,
) -> tuple[bool, str]:
    system = JUDGE_SYSTEM.replace("{judge_criteria}", judge_criteria)
    prompt = JUDGE_USER.replace("{expected_behavior}", expected_behavior).replace(
        "{output}", output
    )
    msgs = [user(prompt)]
    result_str = await llm(
        client,
        msgs,
        model=model,
        max_tokens=256,
        system=system,
        output_config={"format": output_format(JudgeResult)},
    )
    result = JudgeResult.model_validate_json(result_str)
    return result.passed, result.reason


# --- Runner ---


async def run_case(
    client: AsyncAnthropic, prompt_text: str, case: dict, model: str
) -> dict:
    """Run a single test case against the prompt. Returns result dict.

    prompt_as: where prompt.md goes (default "system", or "user" for first message)

    mode "scripted" (default):
        turns is a list of messages with role "user" or "assistant".
        User turns trigger llm(). Assistant turns are injected as-is (prescribed history).
        Eval runs against the last generated assistant output.

    mode "simulated":
        sim_user_prompt: system prompt for the simulated user
        sim_turns: number of back-and-forth exchanges to generate
        turns[0]: the opening user message to kick off the conversation
        Eval runs against the full transcript (last assistant output for checks).
    """
    mode = case.get("mode", "scripted")
    prompt_as = case.get("prompt_as", "system")
    vars = case.get("vars", {})

    # Template variables into prompt and turns
    if vars:
        prompt_text = prompt_text.format(**vars)
        case = {
            **case,
            "turns": [
                {**t, "content": t["content"].format(**vars)} for t in case["turns"]
            ],
        }

    # Set up system prompt and initial messages based on prompt_as
    system = prompt_text if prompt_as == "system" else None
    msgs: list = []
    if prompt_as == "user":
        msgs.append(user(prompt_text))
        await llm(
            client,
            msgs,
            (),
            model=model,
            max_tokens=4096,
            **({"system": system} if system else {}),
        )

    llm_kwargs = {"model": model, "max_tokens": 4096}
    if system:
        llm_kwargs["system"] = system

    output = ""

    if mode == "simulated":
        # Two LLMs converse: the prompt-under-test as assistant, sim_user_prompt as simulated user
        sim_user_prompt = case["sim_user_prompt"]
        sim_turns = case.get("sim_turns", 3)
        sim_msgs: list = []  # separate history for simulated user

        # Kick off with the first user turn
        first_turn = case["turns"][0]["content"]
        msgs.append(user(first_turn))
        output = await llm(client, msgs, **llm_kwargs)

        for _ in range(sim_turns - 1):
            # Simulated user generates next user message based on conversation so far
            # Feed it the conversation from the user's perspective
            sim_msgs.append(
                user(f"The assistant said: {output}\n\nRespond as the user would.")
            )
            sim_response = await llm(
                client, sim_msgs, model=model, max_tokens=4096, system=sim_user_prompt
            )

            # Feed simulated user's response back to the prompt-under-test
            msgs.append(user(sim_response))
            output = await llm(client, msgs, **llm_kwargs)
    else:
        # Scripted: replay turns exactly
        for turn in case["turns"]:
            role = turn.get("role", "user")
            if role == "assistant":
                msgs.append(
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": turn["content"]}],
                    }
                )
            else:
                msgs.append(user(turn["content"]))
                output = await llm(client, msgs, **llm_kwargs)

    return {"id": case["id"], "output": output, "msgs": msgs}


async def run_checks(
    client: AsyncAnthropic,
    case: dict,
    output: str,
    custom_checks: dict,
    model: str,
) -> tuple[bool, list[dict]]:
    """Run all checks for a case. Returns (all_passed, check_results)."""
    results = []

    if case.get("eval_method") == "llm_judge":
        passed, reason = await judge(
            client,
            output,
            case["expected_behavior"],
            case.get("judge_prompt", ""),
            model,
        )
        results.append({"type": "llm_judge", "passed": passed, "reason": reason})
    else:
        for check in case.get("checks", []):
            check_type = check["type"]
            check_params = {k: v for k, v in check.items() if k != "type"}
            fn = BUILTIN_CHECKS.get(check_type) or custom_checks.get(check_type)
            if not fn:
                results.append(
                    {
                        "type": check_type,
                        "passed": False,
                        "reason": f"Unknown check: {check_type}",
                    }
                )
                continue
            passed, reason = fn(output, **check_params)
            results.append({"type": check_type, "passed": passed, "reason": reason})

    all_passed = all(r["passed"] for r in results) if results else True
    return all_passed, results


async def main(prompt_dir: str, model: str = "claude-haiku-4-5-20251001") -> None:
    d = Path(prompt_dir)
    prompt_text = (d / "prompt.md").read_text()
    cases = json.loads((d / "tests.json").read_text())
    custom_checks = load_custom_checks(d)

    client = AsyncAnthropic()
    results = []

    for case in cases:
        run = await run_case(client, prompt_text, case, model)
        passed, check_results = await run_checks(
            client, case, run["output"], custom_checks, model
        )
        result = {
            "id": case["id"],
            "passed": passed,
            "output": run["output"],
            "checks": check_results,
        }
        if not passed:
            reasons = [c["reason"] for c in check_results if not c["passed"]]
            result["reason"] = "; ".join(reasons)
        results.append(result)
        status = "✓" if passed else "✗"
        print(f"  {status} {case['id']}: {case.get('description', '')}")
        if not passed:
            print(f"    {result['reason']}")

    # Summary
    passed_count = sum(1 for r in results if r["passed"])
    total = len(results)
    print(f"\n{passed_count}/{total} passed")

    # Write results
    results_dir = d / "results"
    results_dir.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H_%M_%S")
    out_file = results_dir / f"{ts}.json"
    out_file.write_text(json.dumps(results, indent=2))
    print(f"Results: {out_file}")

    sys.exit(0 if passed_count == total else 1)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("Usage: python skills/prompt_eval/run.py prompts/<name> [--model MODEL]")
        sys.exit(1)
    prompt_dir = args[0]
    model = (
        args[args.index("--model") + 1]
        if "--model" in args
        else "claude-haiku-4-5-20251001"
    )
    asyncio.run(main(prompt_dir, model))
