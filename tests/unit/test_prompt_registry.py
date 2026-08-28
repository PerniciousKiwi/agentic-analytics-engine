from pathlib import Path

from cardinal.llm.registry import get_prompt_hash


def test_prompt_hash_uses_generate_sql_v2() -> None:
    prompt_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "cardinal"
        / "llm"
        / "prompts"
        / "generate_sql_v2.j2"
    )

    assert prompt_path.exists()

    assert len(get_prompt_hash()) == 12
