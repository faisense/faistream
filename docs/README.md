# Documentation

| File | What it is |
|---|---|
| [architecture.md](architecture.md) | How faistream works, with diagrams. GitHub shows it directly. |
| [architecture.pdf](architecture.pdf) | The same document as a PDF. Generated: don't edit it by hand. |
| [diagrams/](diagrams/) | The diagrams, as editable `.drawio.svg` files. |

## Edit a diagram

Each `.drawio.svg` file is an ordinary SVG image with the editable draw.io drawing stored
inside it, so GitHub shows it as a picture and draw.io opens it for editing. Use either:

- **VS Code** with the free [Draw.io Integration](https://marketplace.visualstudio.com/items?itemName=hediet.vscode-drawio) extension: open the file and edit it in place, or
- **draw.io** ([desktop app](https://www.drawio.com/) or [app.diagrams.net](https://app.diagrams.net)): File > Open, then save back to the same file.

Keep the `.drawio.svg` extension so the drawing stays editable. Arrows are attached to boxes and
the grouped boxes (service, same device, other machine) are containers, so moving a box or a
group keeps everything connected.

Colours used, to keep new shapes consistent:

| Role | Fill | Line |
|---|---|---|
| Normal box | `#ffffff` | `#8c9e98` |
| Group | `#e7eeeb` | `#c9d4d0` |
| Same device (shared memory) | `#d2ede6` | `#0a7563` |
| Network | `#f6e6cc` | `#9c5a00` |
| Secondary text | | `#586a64` |

## Rebuild the PDF

After changing `architecture.md` or a diagram:

```bash
uv run --with markdown --with playwright python docs/build_pdf.py
```

The first run downloads a headless Chromium (about 100 MB) to print with. The PDF gets a title
page with contents, then one page per `##` section.
