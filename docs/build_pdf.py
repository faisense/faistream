"""Build docs/architecture.pdf from docs/architecture.md and the draw.io diagrams.

    uv run --with markdown --with playwright python docs/build_pdf.py

The first run downloads a headless Chromium (about 100 MB) to print with.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown
from playwright.sync_api import Error, sync_playwright

DOCS = Path(__file__).resolve().parent
SOURCE = DOCS / "architecture.md"
OUTPUT = DOCS / "architecture.pdf"

CSS = """
@page { size: A4 landscape; margin: 14mm 16mm 16mm; }
body {
  margin: 0; color: #16201d;
  font: 13.5px/1.5 -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif;
}
code { font-family: Menlo, Consolas, monospace; font-size: 0.92em; }
a { color: inherit; text-decoration: none; }
header { break-after: page; padding-top: 18mm; max-width: 175mm; }
header h1 { font-size: 34px; margin: 0 0 12px; }
header > p:first-of-type { font-size: 16px; }
header ul {
  display: grid; grid-template-columns: 1fr 1fr; gap: 6px 28px; padding: 0; list-style: none;
}
header li { border-top: 1px solid #c9d4d0; padding-top: 6px; }
header h3 { margin: 18px 0 4px; font-size: 16px; }
header ol { margin: 0; padding-left: 20px; }
section { break-after: page; }
section:last-child { break-after: auto; }
h2 { font-size: 22px; margin: 0 0 6px; }
section p { max-width: 200mm; margin: 0 0 8px; }
section img {
  display: block; width: 100%; max-height: 128mm; object-fit: contain; margin: 6px auto;
}
em { color: #586a64; font-size: 12px; font-style: normal; }
"""

FOOTER = (
    '<div style="font:8px Helvetica,Arial,sans-serif;color:#586a64;width:100%;padding:0 16mm;'
    'display:flex;justify-content:space-between"><span>faistream · architecture</span>'
    '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>'
)


def to_html(text: str) -> str:
    """One page for the introduction and contents, then one page per ``##`` section."""
    intro, *sections = re.split(r"(?m)^(?=## )", text)

    def render(md: str) -> str:
        return markdown.markdown(md, extensions=["extra"])

    titles = [section.splitlines()[0].removeprefix("## ") for section in sections]
    contents = "".join(f"<li>{t}, page {i + 2}</li>" for i, t in enumerate(titles))
    body = f"<header>{render(intro)}<h3>Contents</h3><ol>{contents}</ol></header>"
    body += "".join(f"<section>{render(section)}</section>" for section in sections)
    # Relative image paths -> absolute file URIs, so the browser can load the diagrams.
    body = re.sub(
        r'src="(?!https?:|file:)([^"]+)"',
        lambda m: f'src="{(DOCS / m.group(1)).resolve().as_uri()}"',
        body,
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8"><title>faistream Architecture</title>'
        f"<style>{CSS}</style></head><body>{body}</body></html>"
    )


def print_pdf(html_path: Path) -> None:
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Error:
            print("Downloading a headless Chromium to print with (first run only)...")
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium-headless-shell"],
                check=True,
            )
            browser = p.chromium.launch()
        page = browser.new_page()
        page.emulate_media(media="print", color_scheme="light")
        page.goto(html_path.as_uri(), wait_until="networkidle")
        page.pdf(
            path=str(OUTPUT),
            prefer_css_page_size=True,
            print_background=True,
            display_header_footer=True,
            header_template="<div></div>",
            footer_template=FOOTER,
        )
        browser.close()


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        html_path = Path(tmp) / "architecture.html"
        html_path.write_text(to_html(SOURCE.read_text()), encoding="utf-8")
        print_pdf(html_path)
    print(f"wrote {OUTPUT.relative_to(DOCS.parent)}")


if __name__ == "__main__":
    main()
