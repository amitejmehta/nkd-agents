# Prospect Sim Evals

Six single-responsibility binary evaluators for prospect sim sessions (AI plays sales prospect, human plays sales rep).

| Eval | Detects |
|---|---|
| `character_break` | AI stops being a buyer; pivots to seller, coach, or interviewer |
| `premature_capitulation` | AI drops a meaningful objection after ≤1 thin rep response |
| `phantom_objection` | Persona-implied constraint never surfaces even when topic is raised |
| `persona_inconsistency` | AI contradicts its own stated facts (title, authority, knowledge, timeline) |
| `stage_directions` | AI uses `*action*`, `[tone]`, or `(narration)` in its turns |
| `excessive_cooperation` | AI is uniformly helpful with no friction — rep faces no real challenge |

## Running

```bash
# All evals
bash prompts/prospect_sim/run_all.sh

# Single eval
python skills/prompt_eval/run.py prompts/prospect_sim/character_break

# Different model
bash prompts/prospect_sim/run_all.sh --model claude-sonnet-4-5
```

## Design Principles

- One `prompt.md` per failure mode — single binary output (`detected: true/false`)
- All test cases use `llm_judge` — these are semantic judgments, not string matches
- `stage_directions` also has `checks.py` with programmatic regex backup
- `phantom_objection` and `persona_inconsistency` accept an optional `persona_context` variable
- Conservative defaults in every prompt — only flag with specific evidence

## Adding to sim_agents

To wire these into the ECS eval pipeline (like the existing evals in `sim_agents/`):

1. Convert each `prompt.md` to a `.j2` template in `sim_agents/prompts/evals/`
2. Add a corresponding `*Result` Pydantic model in `sim_agents/models/evals.py`
3. Add to `SIM_TYPE_EVALS` in `sim_agents/_evaluate_session.py` under the prospect sim type int
