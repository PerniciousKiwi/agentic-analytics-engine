from pathlib import Path

from jinja2 import Template

PROMPT_PATH = Path("src/cardinal/llm/prompts/generate_sql_v2.j2")


def test_retrieval_prompt_contains_schema_and_metrics() -> None:
    template = Template(
        PROMPT_PATH.read_text(encoding="utf-8"),
    )

    rendered = template.render(
        sql_dialect="PostgreSQL",
        schema_context="TABLE: marts.fct_orders",
        metrics_context="Metric: revenue",
        question="What is total revenue?",
    )

    assert "[SCHEMA — AUTHORITATIVE PHYSICAL DATABASE CONTEXT]" in rendered
    assert "[/SCHEMA — AUTHORITATIVE PHYSICAL DATABASE CONTEXT]" in rendered
    assert "[METRICS — AUTHORITATIVE DEFINITIONS]" in rendered
    assert "[/METRICS — AUTHORITATIVE DEFINITIONS]" in rendered

    assert "PostgreSQL" in rendered
    assert "What is total revenue?" in rendered
