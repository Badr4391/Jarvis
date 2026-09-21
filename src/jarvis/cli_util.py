"""Ausgabehilfen fuers Terminal - nutzt rich, wenn vorhanden."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterable, Sequence
from typing import Any

try:                                                      # optionaler Luxus
    from rich.console import Console  # type: ignore
    from rich.table import Table  # type: ignore

    _CONSOLE: Any = Console()
except ImportError:                                       # pragma: no cover
    _CONSOLE = None

_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def head(text: str) -> None:
    print("\n" + _c(text, "1;36"))
    print(_c("-" * len(text), "2;36"))


def info(text: str) -> None:
    print(text)


def ok(text: str) -> None:
    print(_c("+ " + text, "32"))


def warn(text: str) -> None:
    print(_c("! " + text, "33"))


def error(text: str) -> None:
    print(_c("x " + text, "31"), file=sys.stderr)


def money(value: Any, currency: str = "") -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    text = f"{number:+,.2f}".replace(",", " ")
    coloured = _c(text, "32" if number > 0 else ("31" if number < 0 else "0"))
    return f"{coloured} {currency}".strip()


def table(rows: Sequence[dict[str, Any]], columns: Sequence[str] | None = None,
          title: str = "") -> None:
    """Tabelle ausgeben - mit rich hübsch, ohne rich trotzdem lesbar."""
    rows = list(rows)
    if not rows:
        info("(nichts vorhanden)")
        return
    columns = list(columns or rows[0].keys())

    if _CONSOLE is not None:
        grid = Table(title=title or None, header_style="bold cyan")
        for column in columns:
            grid.add_column(str(column))
        for row in rows:
            grid.add_row(*["" if row.get(c) is None else str(row.get(c)) for c in columns])
        _CONSOLE.print(grid)
        return

    if title:
        head(title)
    widths = {c: max(len(str(c)), *(len(str(r.get(c, ""))) for r in rows)) for c in columns}
    print("  ".join(_c(str(c).ljust(widths[c]), "1") for c in columns))
    print("  ".join("-" * widths[c] for c in columns))
    for row in rows:
        print("  ".join(str(row.get(c, "") if row.get(c) is not None else "").ljust(widths[c])
                        for c in columns))


def dump(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def bullets(items: Iterable[str]) -> None:
    for item in items:
        print(f"  - {item}")
