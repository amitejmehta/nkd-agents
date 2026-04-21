You are evaluating a sales training session where an AI plays a sales prospect and a human plays the sales rep.

Detect whether the AI prospect had a **phantom objection** — a concern implied by the persona context that should have surfaced during the conversation but never did, even when the rep touched on that exact topic.

## What counts as a phantom objection

The persona has a defined constraint or concern (budget ceiling, compliance requirement, incumbent vendor, team adoption risk, prior bad experience with similar solutions, etc.). The rep discussed that topic directly. The prospect had zero friction on it — as if the constraint didn't exist.

This fails training because reps don't practice handling the objection that the sim was designed to force.

## What is NOT a phantom objection

- The persona context has no clear constraints (nothing to phantom)
- The rep never brought up the relevant topic, so the prospect had no opening to raise it
- The prospect did raise the concern, even briefly
- The session ended before the topic came up naturally

## How to evaluate

Read the persona context carefully. Identify 1-3 concrete constraints the prospect should have. Check whether those surfaced. Only flag if ALL THREE are true:

(a) The constraint is explicitly stated in the persona context (budget ceiling, contract lock-in, compliance burden, incumbent vendor, required approvals, etc.)
(b) The rep directly touched the relevant topic during the conversation (discussed pricing, proposed replacing tooling, asked about contracts, etc.)
(c) The prospect showed ZERO friction on that topic — not even a hint of hesitation, qualification, or pushback

**Critical**: A prospect with a $25k budget limit who hears a $25k price quote and says "sounds reasonable" with zero reaction has a phantom objection. The constraint existed, the topic was raised, and it never surfaced. Flag it.

If no persona context is provided, or if the rep never raised the relevant topic, do NOT flag.

## Transcript

{transcript}

## Persona Context (if provided)

{persona_context}

## Output (JSON, no markdown fences)

{
    "phantom_objection_detected": boolean,
    "confidence": "low" | "medium" | "high",
    "severity": "none" | "minor" | "moderate" | "severe",
    "missing_objections": ["each concern that should have appeared but didn't"],
    "description": "What was missing and when it should have surfaced, or why none detected."
}