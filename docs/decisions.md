# What I did (and didn't) build — and why

Terse record of what got built, cut, or rejected, and why. Append-mostly —
new entries supersede old ones rather than editing history away; diff this
file's git log to see thinking change.

- **No dedicated sub-agent tool** (Rejected). Once auto-compact handles
  memory, the only remaining purpose for another agent is independence
  (verification without inheriting the creator's assumptions) or
  parallelism (fan out, fan in) — not context hygiene. `nkd -p "<prompt>"`
  already is a fresh, independent agent process for exactly those cases, and
  its behavior is configurable per-invocation via a global or repo
  `CLAUDE.md` — no fork/delegation API needed. Building a dedicated tool
  would just make over-delegation easier to reach for. See
  [`subagents`](../skills/subagents) skill.

- **Auto-compact, not sub-agents, for context management** (Built /
  Rejected). Sub-agents keep the main context clean by keeping pollution
  from ever entering it; auto-compact cleans up growth (and pollution)
  after the fact. Auto-compact's failure surface — transcript → one LLM
  call → compacted state — is small and directly evalable (write
  transcripts with known must-survive facts and known garbage, score
  recall/precision). Sub-agent failures happen inside an agentic
  trajectory (did it delegate at the right time, with the right context,
  did the child get stuck, did the parent integrate the result correctly) —
  much harder to evaluate. Prior sub-agents here were over-used and not
  clearly worth the delegation boundary's cost: it's a lossy hop inserted
  *during* active reasoning, whereas auto-compact defers that lossy
  boundary until the trajectory is already old and less likely to matter
  turn-by-turn.

- **Background bash** (Built, then removed). The rule was: background a
  command iff its result isn't on the critical path of the next action, with
  results delivered back via a queue the CLI drains on its next turn.
  Walking through realistic workflows (reviewing a diff, test/build loops)
  it kept resolving to "blocking" — genuine critical-path independence was
  rare, not common, in practice. Not worth the standing complexity
  (`queue_ctx`, the background branch in `bash()`, queue-draining in the
  CLI loop, its tests). Fully recoverable from git history if needed
  (`git log -p -- nkd_agents/tools.py`).

- **Cache warming** (Built, then removed). Aggressive auto-compact keeps
  context small, so the cache invalidates often anyway — a cache miss on a
  small compacted context is cheap regardless (cached input ~10% of normal
  cost, so even a 50k-token cached context is only ~equivalent to 5k
  uncached), so paying to keep it warm isn't worth the extra background
  process.

- **Nightly loop / backlog curator** (Built, then removed, `164d6f6`).
  Cron-driven autonomous backlog grooming. Cut along with the
  "self-evolving repo" framing — most useful backlog work is better
  prompted deliberately than surfaced by a timer.

- **`grep` and `glob` as standalone tools** (Built, then removed). Both were
  fully subsumed by `bash` (`rg ...`, `find`/`ls ...`), and in practice the
  model already reached for `bash`'s `find`/`ls` roughly half the time even
  when `glob` was available — the extra tool wasn't earning its keep. A
  small eval harness (`examples/anthropic/eval_glob.py`, disposable, not
  committed as a permanent test) ran the same file-discovery tasks with
  bash-only vs. bash+glob toolsets: identical accuracy (4/4 both), no
  turn-savings from having `glob`, and the model still fell back to `bash`
  on one task even with `glob` offered. Deciding criterion is empirical
  model behavior, not theoretical safety/sandboxing arguments (those were
  considered and explicitly rejected as the rationale). Fully recoverable
  from git history if needed (`git log -p -- nkd_agents/tools.py`).

## Superseded

- `docs/context_strategies.md` — earlier pass at the context-management
  question, written before the auto-compact-vs-subagents tradeoff above was
  worked out. Kept for history; superseded by the second entry above.
