# Skill: Create PowerPoint Presentations

Use `pptxgenjs` (Node.js) to generate `.pptx` files, then convert to PDF with LibreOffice.

## Core Steps (always the same)

1. **Write** a Node.js script using `pptxgenjs` that builds slides and calls `pptx.writeFile()`
2. **Install if needed**: `npm install pptxgenjs`
3. **Run** the script: `node make_presentation.js`
4. **Convert & verify**: `libreoffice --headless --convert-to pdf output.pptx && [ -s output.pdf ] && echo "OK" || echo "FAILED"`

---

## Key pptxgenjs Patterns

Always wrap in an `async` IIFE — `writeFile()` is async and missing `await` produces an empty file.

```js
(async () => {
  const PptxGenJS = require('pptxgenjs');
  const pptx = new PptxGenJS();
  pptx.layout = 'LAYOUT_WIDE'; // optional; default 10x7.5in, wide 13.33x7.5in

  const slide = pptx.addSlide();

  // Text
  slide.addText('Title', { x: 0.5, y: 0.5, w: 9, h: 1.5, fontSize: 36, bold: true, color: '363636', align: 'center' });

  // Bullet list
  slide.addText(
    [{ text: 'Point one', options: { bullet: true } }, { text: 'Point two', options: { bullet: true } }],
    { x: 0.5, y: 2, w: 9, h: 3, fontSize: 20 }
  );

  // Image (local path or URL)
  slide.addImage({ path: './logo.png', x: 0.5, y: 5.5, w: 2, h: 1 });

  // Shape (e.g. solid banner)
  slide.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: '100%', h: 1.2, fill: { color: '1F4E79' } });

  await pptx.writeFile({ fileName: 'output.pptx' });
  console.log('Done');
})();
```

---

## Rules

| Rule | Why |
|---|---|
| Always `await pptx.writeFile()` | It's async; missing await = empty/missing file |
| Use explicit relative or absolute paths | Avoids "file not found" surprises at convert time |
| Use `libreoffice --headless`, not `soffice` | `soffice` may launch a GUI on some systems |
| Check `[ -s file.pdf ]` not just `[ -f file.pdf ]` | LibreOffice writes a 0-byte file on conversion failure |
| Coordinates are in inches by default | `x`, `y`, `w`, `h` all in inches unless a `'%'` string is used |
