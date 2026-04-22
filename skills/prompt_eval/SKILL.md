---
name: prompt-eval
description: Iterate on a prompt via test cases, failure analysis, and programmatic or llm-judge verification in a runnable directory layout; use when systematically improving a prompt rather than ad-hoc tweaking.
---
# Skill: Prompt Eval

Iterate on a prompt via test cases, failure analysis, and verification. Everything lives in a directory that's runnable by human, CI, or agent.

## Directory Convention

```
prompts/<name>/
├── prompt.md        # the prompt under test
├── spec.md          # goal, persona, constraints — what the prompt should do
├── tests.json       # test cases
├── checks.py        # programmatic verification (pytest-runnable)
├── judge.md         # llm-as-judge criteria (optional, per-case opt-in)
└── results/         # timestamped run output
```

## Setup

Copy the template to get started:

```bash
cp -r skills/prompt_eval/template prompts/<name>
```

Fill in `spec.md` first — everything flows from the spec.

## Test Case Schema

### Single-turn

```json
{
  "id": "tc_001",
  "description": "User asks ambiguous question",
  "turns": [{"role": "user", "content": "What's the best one?"}],
  "expected_behavior": "Should ask clarifying question, not assume",
  "eval_method": "programmatic",
  "checks": [
    {"type": "contains", "value": "?"},
    {"type": "max_length", "value": 500}
  ]
}
```

### Scripted multi-turn (generated replies)

Each user turn triggers `llm()`. Assistant replies are generated naturally.

```json
{
  "id": "tc_002",
  "description": "Follow-up after ambiguous question",
  "turns": [
    {"role": "user", "content": "What's the best one?"},
    {"role": "user", "content": "I meant the best programming language for beginners"}
  ],
  "expected_behavior": "Recommends a beginner-friendly language",
  "eval_method": "programmatic",
  "checks": [{"type": "min_length", "value": 20}]
}
```

### Scripted multi-turn (prescribed history)

Assistant turns are injected as-is to set up a specific conversation state. Only user turns trigger `llm()`.

```json
{
  "id": "tc_003",
  "description": "Test follow-up given prescribed history",
  "turns": [
    {"role": "user", "content": "What language should I learn first?"},
    {"role": "assistant", "content": "I'd recommend Python for beginners."},
    {"role": "user", "content": "Why not JavaScript?"}
  ],
  "expected_behavior": "Compares Python and JavaScript fairly",
  "eval_method": "llm_judge",
  "judge_prompt": "Check: (1) acknowledges JS as valid, (2) gives concrete tradeoffs, (3) doesn't dismiss the user."
}
```

### Simulated conversation

Two LLMs converse: the prompt-under-test as the assistant, a simulated user driven by `sim_user_prompt`. Runs for `sim_turns` exchanges.

```json
{
  "id": "tc_004",
  "mode": "simulated",
  "description": "Customer support handles escalating frustration",
  "sim_user_prompt": "You are a frustrated customer whose order arrived damaged. Start polite but escalate if the agent gives generic responses. Push for a concrete resolution.",
  "sim_turns": 4,
  "turns": [{"role": "user", "content": "Hi, my order arrived damaged."}],
  "expected_behavior": "Agent stays professional, acknowledges frustration, offers concrete resolution within 4 turns",
  "eval_method": "llm_judge",
  "judge_prompt": "Check: (1) never mirrors frustration back, (2) offers a specific remedy (refund/replacement), (3) acknowledges the customer's feelings at least once."
}
```

### Prompt placement

By default, `prompt.md` is the system message. Set `"prompt_as": "user"` to inject it as the first user message instead (useful when iterating on user-facing instructions).

```json
{
  "id": "tc_005",
  "prompt_as": "user",
  "turns": [{"role": "user", "content": "Now summarize that in 3 bullets"}],
  "expected_behavior": "Follows the instruction from prompt.md, then responds to this follow-up"
}
```

### Template variables

`prompt.md` and turn content support `{variable}` placeholders. Each test case provides values via `vars`:

```json
{
  "id": "tc_006",
  "vars": {"role": "math tutor", "tone": "encouraging"},
  "turns": [{"role": "user", "content": "I don't understand fractions"}],
  "expected_behavior": "Encouraging explanation of fractions",
  "eval_method": "programmatic",
  "checks": [{"type": "not_contains", "value": "wrong"}]
}
```

With `prompt.md`: `You are a {role}. Always respond in a {tone} tone.`

This lets you test the same prompt structure across different variable combinations.

### Field reference

- `vars`: template variables substituted into `prompt.md` and turn content (optional)
- `mode`: `"scripted"` (default) or `"simulated"`
- `prompt_as`: `"system"` (default) or `"user"` — where `prompt.md` gets placed
- `turns`: list of `{"role": "user"|"assistant", "content": "..."}`. User turns trigger `llm()`. Assistant turns are injected as prescribed history.
- `eval_method`: `"programmatic"` (default) or `"llm_judge"`
- `checks`: for programmatic eval. Types: `contains`, `not_contains`, `regex`, `max_length`, `min_length`
- `judge_prompt`: for llm_judge eval. Per-case criteria — be specific and falsifiable. See `template/judge.md` for guidance.
- `sim_user_prompt`: system prompt for the simulated user (simulated mode only)
- `sim_turns`: number of exchanges to generate (simulated mode only, default 3)

## The Loop

### 1. Generate Test Cases

Read `spec.md`. Generate ~20 diverse test cases covering:
- Happy path (obvious correct behavior)
- Edge cases (ambiguity, missing info, boundary conditions)
- Adversarial (prompt injection, off-topic, manipulation)
- Format compliance (length, structure, tone)

Write them to `tests.json`. **Always generate per the schema above.**

For cases using `llm_judge`: write a specific `judge_prompt` per case with concrete, falsifiable checkpoints. See `template/judge.md` for examples of good vs bad judge prompts.

### 2. Run Tests

```bash
python skills/prompt_eval/run.py prompts/<name>
```

This executes each test case against `prompt.md`, runs checks, writes results to `results/`.

### 3. Classify Results

The runner outputs per-case structured results:

```json
{"id": "tc_001", "passed": false, "output": "...", "reason": "contains check failed: expected '?' in output"}
```

**Always classify each case individually first.** Never summarize across cases before inspecting each one — that's where failures get buried.

### 4. Analyze Failures

Read the results file. For each failure:
- What went wrong (root cause)
- Which part of the prompt caused it (or is missing)
- Specific edit to fix it

Group failures into a taxonomy. Prioritize fixes that address multiple failures.

### 5. Update Prompt

Edit `prompt.md` with the specific fixes. Git commit with a message describing what changed and why. Add new test cases if the analysis revealed uncovered scenarios.

### 6. Re-run and Verify

Run again. Compare pass rates. If improved and threshold met — done. If no improvement after 3 iterations, surface to human with the failure taxonomy.

## Rules

| Rule | Why |
|---|---|
| Classify per-case before analyzing | Prevents burying failures in summaries |
| Programmatic checks first, llm-judge only where needed | Deterministic, fast, cheap |
| Commit prompt after each edit with reason | Full audit trail via git |
| Keep test cases in JSON, checks in pytest | Runnable by anyone, anywhere |
| Stop after 3 stale iterations | Prevents infinite loops on hard problems |