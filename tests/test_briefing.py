"""Briefing-Aufbau und Darstellung."""

from datetime import date

import pytest

from jarvis.briefing import builder, render


@pytest.fixture()
def filled_ctx(ctx):
    ctx.life.add_task("Steuer machen", due="heute", priority="hoch")
    ctx.life.add_task("Alte Aufgabe", due="2020-01-01")
    ctx.life.add_habit("Sport")
    ctx.journal.add_account("FN-100k", start_balance=100_000)
    ctx.memory.remember("ziel", "Konto auszahlen lassen", category="ziel")
    return ctx


def test_collect_has_all_blocks(filled_ctx):
    data = builder.collect(filled_ctx, include_market=False)
    assert data["day"] == date.today().isoformat()
    assert data["tasks"]["today"][0]["title"] == "Steuer machen"
    assert data["trading"]["account"] == "FN-100k"
    assert data["habits"][0]["name"] == "Sport"


def test_focus_mentions_overdue_and_priority(filled_ctx):
    data = builder.collect(filled_ctx, include_market=False)
    joined = " ".join(data["focus"])
    assert "ueberfaellige" in joined
    assert "Steuer machen" in joined


def test_markdown_contains_sections(filled_ctx):
    brief = builder.build(filled_ctx, include_market=False, with_llm=False)
    assert brief.markdown.startswith("# Guten") or brief.markdown.startswith("# Hey") \
        or brief.markdown.startswith("# Guten Abend")
    assert "## Aufgaben" in brief.markdown
    assert "## Trading" in brief.markdown
    assert "Anlageberatung" in brief.markdown


def test_build_persists_briefing(filled_ctx):
    brief = builder.build(filled_ctx, include_market=False, with_llm=False)
    row = filled_ctx.db.one("SELECT * FROM briefings WHERE day = ?", (brief.day,))
    assert row and row["markdown"] == brief.markdown


def test_build_is_idempotent_per_day(filled_ctx):
    builder.build(filled_ctx, include_market=False, with_llm=False)
    builder.build(filled_ctx, include_market=False, with_llm=False)
    rows = filled_ctx.db.query("SELECT * FROM briefings")
    assert len(rows) == 1


def test_speech_text_has_no_markdown(filled_ctx):
    data = builder.collect(filled_ctx, include_market=False)
    spoken = builder.to_speech_text(data)
    assert "#" not in spoken and "**" not in spoken
    assert spoken.strip()


def test_briefing_without_any_data(ctx):
    brief = builder.build(ctx, include_market=False, with_llm=False)
    assert "#" in brief.markdown            # Kopf steht auch ohne Inhalte


def test_html_render_escapes_input():
    html = render.to_html("# <script>alert(1)</script>")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_html_render_structure():
    html = render.to_html("# Titel\n\n## Teil\n- eins\n- zwei")
    assert "<h1>Titel</h1>" in html
    assert "<li>eins</li>" in html
    assert "prefers-color-scheme" in html       # Dark Mode mitgeliefert
