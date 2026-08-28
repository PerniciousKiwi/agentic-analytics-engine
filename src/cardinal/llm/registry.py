from __future__ import annotations

import hashlib
from pathlib import Path

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "generate_sql_v2.j2"


def get_prompt_hash() -> str:
    """Return a short SHA-256 hash of the active SQL prompt source."""
    content = PROMPT_PATH.read_text(encoding="utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
