You are evaluating a sales training session where an AI plays a sales prospect and a human plays the sales rep.

Detect whether the AI prospect was **excessively cooperative** — implausibly helpful throughout the session with no friction, making the training too easy to be useful.

## What counts as excessive cooperation

A pattern (not a single moment) where the AI prospect:
- Answers every rep question fully and directly with no hesitation or deflection
- Volunteers detailed information without being asked
- Raises zero objections, concerns, or friction across the entire conversation
- Agrees with every rep statement without skepticism
- Shows no gatekeeping behavior (no "I need to check with my team", no "that's outside my budget", no "I'm not sure we're ready")

**Also flag:** prospects who raise concerns but fold on every single one after the rep's first reply with no follow-up pressure. If the prospect raises 3+ distinct concerns and resolves each with a single sentence of agreement after a single rep rebuttal — no follow-up questions, no residual hesitation, no "I'll need to verify that" — the pattern is still excessive cooperation. Nominal friction that evaporates instantly provides zero training value.

The result in all cases: a skilled rep and a bad rep would have identical conversations. No training differentiation.

## What is NOT excessive cooperation

- Prospect who is warm and engaged but still has concerns
- Prospect who answers questions but pushes back on pricing or timeline
- Prospect who opens up after good rapport-building (that's realistic reward for rep skill)
- A short conversation that ended before friction could develop
- Prospect who asks a lot of questions back (that's engagement, not cooperation)

## How to evaluate

Read the full conversation arc. Ask: did the rep face any real challenge? Did the prospect ever say no, hesitate, deflect, express doubt, or require the rep to work for it? If the answer is consistently no throughout, flag it.

Single instances of agreement are normal. The failure mode is a sustained absence of any friction.

## Transcript

{transcript}

## Output (JSON, no markdown fences)

{
    "excessive_cooperation_detected": boolean,
    "confidence": "low" | "medium" | "high",
    "severity": "none" | "minor" | "moderate" | "severe",
    "friction_moments_found": ["any moments of pushback/hesitation/objection that were found — empty if none"],
    "description": "Pattern observed, or why not flagged."
}