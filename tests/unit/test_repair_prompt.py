from __future__ import annotations

from pathlib import Path

from jinja2 import Template

PROMPT_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "cardinal" / "llm" / "prompts" / "repair_sql.j2"
)


def load_repair_prompt_template() -> Template:
    return Template(
        PROMPT_PATH.read_text(encoding="utf-8"),
    )


def test_repair_prompt_renders_required_fields() -> None:
    template = load_repair_prompt_template()

    prompt = template.render(
        schema_dump="CREATE TABLE marts.orders (order_id INTEGER);",
        question="How many orders are there?",
        failed_sql="SELECT order_count FROM marts.orders;",
        failure_class="UNKNOWN_COLUMN",
        error_message="UNKNOWN_COLUMN: order_count",
        candidates=["order_id", "customer_id"],
    )

    assert "CREATE TABLE marts.orders" in prompt
    assert "How many orders are there?" in prompt
    assert "SELECT order_count FROM marts.orders;" in prompt
    assert "UNKNOWN_COLUMN" in prompt
    assert "UNKNOWN_COLUMN: order_count" in prompt
    assert "- order_id" in prompt
    assert "- customer_id" in prompt
    assert "{{ " not in prompt
    assert "{% " not in prompt


def test_repair_prompt_renders_cost_budget() -> None:
    template = load_repair_prompt_template()

    prompt = template.render(
        schema_dump="CREATE TABLE marts.orders (order_id INTEGER);",
        question="How many orders are there?",
        failed_sql="SELECT COUNT(*) FROM marts.orders;",
        failure_class="TIMEOUT",
        error_message="canceling statement due to statement timeout",
        candidates=[],
        cost_budget=50000,
    )

    assert "TIMEOUT" in prompt
    assert "50000" in prompt
    assert "Current cost budget:" in prompt


def test_repair_prompt_omits_empty_candidates() -> None:
    template = load_repair_prompt_template()

    prompt = template.render(
        schema_dump="CREATE TABLE marts.orders (order_id INTEGER);",
        question="How many orders are there?",
        failed_sql="SELECT COUNT(*) FROM marts.orders;",
        failure_class="SYNTAX",
        error_message="syntax error",
        candidates=[],
    )

    assert "Candidate identifiers:" not in prompt
