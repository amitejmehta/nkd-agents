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
2. **Create the skeleton** — call `edit_file` with `path="make_presentation.js"`, `old_str="create_file"`, and `new_str` set to the full skeleton below. Do not use bash to write this file.
   ```js
   const pptx = new (require('pptxgenjs'))();

   function txt(s, content, opts = {}) {
     s.addText(content, Object.assign({}, opts, { shrinkText: true, autoFit: true }));
   }

   // slides go here

   (async () => { await pptx.writeFile({ fileName: 'slide_deck.pptx' }); })();
   ```
3. **Repeat until all slides are done** — fill in **a maximum of 1–2 slides at a time, never more**:
   a. Write the 1–2 slides (MAX) and run `node make_presentation.js` (NOTE: MUST use `edit_file` tool here)
   b. Convert:
      ```bash
      SOFFICE=$(command -v libreoffice25.2 || command -v libreoffice || command -v soffice) && $SOFFICE --headless --convert-to pdf slide_deck.pptx
      ```
   c. Read `slide_deck.pdf` via `read_file`. Verify every page for:
      - No text overflow (all text fits within slide boundaries)
      - No element overlap
      - Visual elements render correctly
      - Charts and graphs are complete — no missing data, truncated series, or empty plot areas
      - Every `addText` call goes through `txt()`
   d. If any page has overflow, overlap, rendering issues, or a missing `txt()` call, fix the offending slide and re-run before adding more slides.