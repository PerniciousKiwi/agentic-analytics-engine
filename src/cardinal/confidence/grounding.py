from __future__ import annotations

import re
from typing import Any

_NUMBER_PATTERN = re.compile(
    r"""
    (?<!\w)
    [-+]?
    (?:
        \d{1,3}(?:,\d{3})+
        |
        \d+
    )
    (?:\.\d+)?
    %?
    (?!\w)
    """,
    re.VERBOSE,
)

_QUOTED_PATTERN = re.compile(
    r"""["']([^"']+)["']"""
)

_CAPITALIZED_PATTERN = re.compile(
    r"""
    \b
    (?:
        [A-Z]{2,}
        |
        [A-Z][A-Za-zÀ-ÖØ-öø-ÿ'-]+
        (?:\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'-]+)+
    )
    \b
    """,
    re.VERBOSE,
)


def stringify_result_set(
    rows: list[list[Any]] | list[tuple[Any, ...]],
) -> str:
    return " ".join(
        str(value)
        for row in rows
        for value in row
        if value is not None
    )


def extract_grounding_claims(
    answer: str,
) -> list[str]:
    """Extract simple factual claims that can be checked against SQL rows."""

    claims: list[str] = []

    claims.extend(
        match.group(0)
        for match in _NUMBER_PATTERN.finditer(answer)
    )

    claims.extend(
        match.group(1).strip()
        for match in _QUOTED_PATTERN.finditer(answer)
        if match.group(1).strip()
    )

    claims.extend(
        match.group(0).strip()
        for match in _CAPITALIZED_PATTERN.finditer(answer)
        if match.group(0).strip()
    )

    seen: set[str] = set()
    unique_claims: list[str] = []

    for claim in claims:
        normalized = claim.casefold()

        if normalized in seen:
            continue

        seen.add(normalized)
        unique_claims.append(claim)

    return unique_claims


def grounding_score(
    answer: str,
    rows: list[list[Any]] | list[tuple[Any, ...]],
) -> float:
    """Return fraction of extracted claims visibly grounded in result rows."""

    claims = extract_grounding_claims(answer)

    if not claims:
        return 1.0

    result_text = stringify_result_set(rows).casefold()

    grounded = sum(
        _claim_is_grounded(
            claim,
            result_text,
        )
        for claim in claims
    )

    return grounded / len(claims)


def _claim_is_grounded(
    claim: str,
    result_text: str,
) -> bool:
    normalized_claim = claim.casefold().replace(",", "")

    normalized_result = result_text.replace(",", "")

    return normalized_claim in normalized_result