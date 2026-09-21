"""Briefing als eigenstaendige HTML-Seite (dark/light, ohne externe Assets)."""

from __future__ import annotations

import html
import re
from datetime import date

CSS = """
:root{--bg:#f7f7f5;--fg:#1c1c1a;--muted:#6b6b66;--card:#ffffff;--line:#e4e4df;
      --accent:#b4552d;--good:#2f7d52;--bad:#b23c33;--radius:14px}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#141413;--fg:#f0efe9;--muted:#9a9a93;--card:#1e1e1c;--line:#31312e;
  --accent:#e08050;--good:#58b37f;--bad:#e0705f}}
:root[data-theme="dark"]{--bg:#141413;--fg:#f0efe9;--muted:#9a9a93;--card:#1e1e1c;
  --line:#31312e;--accent:#e08050;--good:#58b37f;--bad:#e0705f}
*{box-sizing:border-box}
body{margin:0;padding:32px 16px 64px;background:var(--bg);color:var(--fg);
     font:16px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:760px;margin:0 auto}
h1{font-size:1.9rem;margin:0 0 4px;letter-spacing:-.02em}
h2{font-size:1.05rem;margin:28px 0 10px;text-transform:uppercase;letter-spacing:.08em;
   color:var(--muted);font-weight:600}
.date{color:var(--muted);margin:0 0 24px}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
      padding:16px 18px;margin:0 0 14px}
ul{margin:0;padding-left:20px}
li{margin:4px 0}
ol{margin:0;padding-left:22px}
.up{color:var(--good);font-weight:600}
.down{color:var(--bad);font-weight:600}
.coach{border-left:3px solid var(--accent);padding-left:14px;font-style:italic;color:var(--fg)}
footer{margin-top:40px;color:var(--muted);font-size:.85rem;text-align:center}
code{background:var(--line);padding:1px 5px;border-radius:5px;font-size:.9em}
@media(max-width:520px){body{padding:20px 16px 48px}h1{font-size:1.5rem}}
"""


def _inline(text: str) -> str:
    """Minimaler Markdown-Inline-Renderer (fett, kursiv, code)."""
    out = html.escape(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<em>\1</em>", out)
    out = re.sub(r"`(.+?)`", r"<code>\1</code>", out)
    out = re.sub(r"([+-]\d+[\d.,]*%)", lambda m: (
        f'<span class="{"up" if m.group(1).startswith("+") else "down"}">{m.group(1)}</span>'), out)
    return out


def markdown_to_html(markdown: str) -> str:
    """Genau so viel Markdown wie das Briefing erzeugt - kein Fremdpaket noetig."""
    blocks: list[str] = []
    list_open = False
    ordered_open = False

    def close_lists() -> None:
        nonlocal list_open, ordered_open
        if list_open:
            blocks.append("</ul>")
            list_open = False
        if ordered_open:
            blocks.append("</ol>")
            ordered_open = False

    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line.strip():
            close_lists()
            continue
        if line.startswith("# "):
            close_lists()
            blocks.append(f"<h1>{_inline(line[2:])}</h1>")
        elif line.startswith("## "):
            close_lists()
            blocks.append(f"<h2>{_inline(line[3:])}</h2>")
        elif line.startswith("- "):
            if ordered_open:
                close_lists()
            if not list_open:
                blocks.append("<ul>")
                list_open = True
            item = _inline(line[2:])
            item = re.sub(r"^\[ \]\s*", "&#9744; ", item)      # leere Box
            item = re.sub(r"^\[x\]\s*", "&#9745; ", item)      # abgehakt
            blocks.append(f"<li>{item}</li>")
        elif re.match(r"^\d+\.\s", line):
            if list_open:
                close_lists()
            if not ordered_open:
                blocks.append("<ol>")
                ordered_open = True
            item = re.sub(r"^\d+\.\s*", "", line)
            blocks.append(f"<li>{_inline(item)}</li>")
        elif line.startswith("---"):
            close_lists()
            blocks.append("<hr>")
        elif line.startswith("*") and line.endswith("*") and len(line) > 2:
            close_lists()
            blocks.append(f'<p class="date">{_inline(line[1:-1])}</p>')
        else:
            close_lists()
            blocks.append(f"<p>{_inline(line)}</p>")
    close_lists()
    return "\n".join(blocks)


def to_html(markdown: str, *, title: str = "Jarvis Briefing") -> str:
    body = markdown_to_html(markdown)
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<div class="card">
{body}
</div>
<footer>Jarvis &middot; local-first &middot; {date.today().strftime('%d.%m.%Y')}</footer>
</div>
</body>
</html>"""
