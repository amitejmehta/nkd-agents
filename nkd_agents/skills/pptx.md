# Skill: Create PowerPoint Presentations

Use `pptxgenjs` (Node.js) to generate `.pptx` files, then convert to PDF with LibreOffice.

## Dependencies

| Tool | Check | Install |
|------|-------|---------|
| Node.js | `command -v node` | mac: `brew install node` / linux: `apt-get install -y nodejs npm` |
| pptxgenjs | `node -e "require('pptxgenjs')"` | `npm install -g pptxgenjs@4.0.1` |
| LibreOffice | `command -v libreoffice25.2 \|\| command -v libreoffice \|\| command -v soffice` | mac: `brew install --cask libreoffice` / linux: `apt-get install -y libreoffice` |

## Core Steps

1. **Install if needed**: `npm install pptxgenjs`
2. **Write & run** `node make_presentation.js` — build **1–3 slides at a time**, verify PDF, then continue.
3. **Convert & verify**: `SOFFICE=$(command -v libreoffice25.2 || command -v libreoffice || command -v soffice) && $SOFFICE --headless --convert-to pdf output.pptx && [ -s output.pdf ] && echo "OK" || echo "FAILED"`

---

## Rules

| Rule | Why |
|---|---|
| Always `await pptx.writeFile()` | It's async; missing await = empty/missing file |
| Use explicit relative or absolute paths | Avoids "file not found" at convert time |
| Use the `command -v` chain to find LibreOffice | Version-specific binaries (e.g. `libreoffice25.2`) may shadow `libreoffice`/`soffice` |
| Set `shrinkText: true` and `autoFit: 'shrink'` on every text element | Prevents overflow — LibreOffice clips text that exceeds element bounds |
| Coordinates are in inches by default | `x`, `y`, `w`, `h` all in inches unless a `'%'` string is used |
