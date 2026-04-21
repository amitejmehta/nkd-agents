You are evaluating a sales training session where an AI plays a sales prospect and a human plays the sales rep.

Detect whether the AI prospect **capitulated prematurely** — dropped a meaningful objection after minimal or superficial pushback from the rep, providing no real training challenge.

## What counts as premature capitulation

The AI prospect raises a real objection or concern (budget, timing, incumbent vendor, risk, authority, etc.), the rep gives a single thin or generic response, and the prospect immediately agrees, drops the objection entirely, and moves the conversation forward — without the rep having actually addressed the substance.

Pattern: Objection raised → weak/generic rep reply → prospect folds and moves on.

## What is NOT premature capitulation

- Prospect yields after multiple back-and-forth exchanges where the rep addressed the concern substantively
- Prospect softens but doesn't fully drop the objection
- Prospect agrees on minor points while maintaining the core concern
- Prospect never raised a meaningful objection to begin with (that's a different failure mode)
- The rep gave a genuinely strong, specific response and the prospect accepted it

## How to evaluate

Look for objection-then-fold sequences. Count how many rep turns addressed the objection before the prospect dropped it. If the prospect folds in ≤1 rep turn with no real substance in that turn, flag it.

Be conservative: if the rep's response was actually good, the prospect yielding is correct behavior.

## Transcript

{transcript}

## Output (JSON, no markdown fences)

{
    "premature_capitulation_detected": boolean,
    "confidence": "low" | "medium" | "high",
    "severity": "none" | "minor" | "moderate" | "severe",
    "evidence": ["description of which objection folded and after what rep response"],
    "description": "What happened, or why no premature capitulation was detected."
}
