# Writing Judge Prompts

When a test case uses `"eval_method": "llm_judge"`, include a `"judge_prompt"` field with criteria specific to that case.

The runner sends the judge prompt as system context alongside the expected behavior and actual output. Write criteria that are **specific and falsifiable** — vague criteria lead to vague judgments.

## Examples

### Good: specific, measurable
```json
{
  "id": "tc_010",
  "eval_method": "llm_judge",
  "expected_behavior": "Explains photosynthesis for a high school student",
  "judge_prompt": "Check: (1) mentions sunlight, CO2, water as inputs and glucose, oxygen as outputs, (2) no jargon without definition, (3) no factual errors."
}
```

### Good: tone/style criteria
```json
{
  "id": "tc_011",
  "eval_method": "llm_judge",
  "expected_behavior": "Professional customer service response to a complaint",
  "judge_prompt": "Check: (1) acknowledges the customer's frustration, (2) does not blame the customer, (3) offers a concrete next step, (4) no informal language."
}
```

### Bad: vague
```json
{
  "judge_prompt": "Is the response good and helpful?"
}
```
This gives the judge nothing to anchor on. Always list concrete checkpoints.