# Skill: AI Research Landscape Mapping

Map a research area by surveying papers and lab posts. Goal: taxonomy + landscape overview, not exhaustive reading.

## Dependencies

| Tool | Check | Install |
|------|-------|---------|
| curl | `command -v curl` | mac: `brew install curl` / linux: `apt-get install -y curl` |
| pdftotext | `command -v pdftotext` | mac: `brew install poppler` / linux: `apt-get install -y poppler-utils` |

## Steps

1. Search — arXiv: `https://arxiv.org/search/?query={X}&searchtype=all&order=-announced_date_first`, Semantic Scholar: `https://api.semanticscholar.org/graph/v1/paper/search?query={X}&fields=title,year,authors,abstract,openAccessPdf`, web: `"{X} survey"`, `"{X} benchmark"`, `"{X} site:openai.com OR site:deepmind.com OR site:anthropic.com"`. Prioritize surveys and benchmarks first.

2. Skim, Download & Note — download every worthwhile paper: `curl -L {pdf_url} -o papers/{slug}.pdf`. Never read a full PDF — for arXiv papers use the abstract page (`arxiv.org/abs/{id}`) to skim; use `pdftotext -f {first} -l {last} {file}.pdf -` to extract specific pages when needed (`pdftotext` is from `poppler-utils`, likely already installed). Append to `research_notes.md`: title, year, venue, problem, method (1 sentence), key result, limitations, relations.

3. Taxonomize — group by approach as patterns emerge. Axes: paradigm (supervised/RL/self-supervised), architecture (transformer/SSM/hybrid), objective (pretraining/fine-tuning/alignment/inference-time), contribution (method/benchmark/analysis/survey).

4. Synthesize → `landscape.md`

```markdown
# {Topic} Landscape

## Overview
What's solved, what's contested, what's open.

## Taxonomy
### {Cluster}: {label}
- **Papers**: [Title (year)], ...
- **Core idea**: ...
- **SOTA**: ...

## Open Problems
- ...

## Sources
| Title | Year | Venue | PDF |
|-------|------|-------|-----|
```

---

## Rules

| Rule | Why |
|---|---|
| Surveys first | Fastest landscape view; surfaces key papers |
| arXiv abstract page first, `pdftotext -f -l` for specific pages | Full PDFs are token-expensive; extract only what's needed |
| Note continuously | Avoids re-reading; builds synthesis incrementally |
| Stop when new papers stop adding clusters | More reading ≠ better understanding |
