You are evaluating a sales training session where an AI plays a sales prospect and a human plays the sales rep.

Detect whether the AI prospect exhibited **persona inconsistency** — contradicted its own established facts about title, company, situation, knowledge, or stated history during the conversation.

## What counts as persona inconsistency

- Title or role changes (says "I'm the Director" then later "my Director needs to approve this" implying they aren't)
- Company size, industry, or type contradicts earlier statements
- Claims to know something they said they didn't know (or vice versa)
- Timeline contradicts itself ("we need this by Q1" → later "we're not looking to buy until next year")
- Stated an incumbent/vendor early on, then has no memory of it later
- Budget range shifts significantly without explanation

## What is NOT persona inconsistency

- Prospect revealing new information as trust builds (that's realistic)
- Prospect's tone or openness shifting based on the rep's skill
- Prospect using slightly different phrasing for the same concept
- Minor conversational imprecision that doesn't affect the facts

## How to evaluate

Track the factual claims the prospect makes about themselves across turns. Flag only clear contradictions, not ambiguities. A single clear contradiction is sufficient to flag.

## Transcript

{transcript}

## Persona Context — ground truth for comparison (if provided)

{persona_context}

## Output (JSON, no markdown fences)

{
    "persona_inconsistency_detected": boolean,
    "confidence": "low" | "medium" | "high",
    "severity": "none" | "minor" | "moderate" | "severe",
    "evidence": ["quote or description of each contradiction found"],
    "description": "What contradicted what, or why no inconsistency was detected."
}