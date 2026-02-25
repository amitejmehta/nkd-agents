Summarize this conversation into a structured markdown document that captures everything needed to continue seamlessly — without losing important context — while discarding raw tool call/result noise.

Use the `edit_file` tool to write the summary to `~/.nkd-agents/sessions/<unix_timestamp>_<descriptive-1-3-word-phrase>.md` (use the actual current unix timestamp; derive the short phrase from the session's main topic, lowercase, hyphen-separated). Then confirm the path to the user.

Produce output in the following structure. Omit any section that has nothing to report (do not include empty headings).

---

## Goal / Context

Describe the overall purpose of this session: what the user was trying to accomplish and any important background context established at the start.

## Key Decisions

Bullet-point list of significant decisions, conclusions, or design choices made during the session. Include the rationale where it was discussed.

## Files Read

List every file that was read, with its full path. One path per line. Do not reproduce file contents.

## Files Created / Edited

List every file that was created or modified, with its full path. One path per line. Briefly note what changed (one sentence max per file).

## Commands Run

List bash commands that were executed and any notable output (errors, key results, counts, etc.). Keep output snippets short — just enough to convey the outcome.

## Images / PDFs Referenced

List paths or URLs of any images or PDF documents that were loaded or referenced. Do not re-embed binary content.

## Current State / Unfinished Work

Describe where things stand right now: what has been completed, what is partially done, and what still needs to be done. Be specific — list filenames, function names, or task names where relevant.

## Other Important Context

Any other information that would be needed to continue this conversation intelligently: environment assumptions, constraints the user mentioned, things that were tried and failed, open questions, etc.
