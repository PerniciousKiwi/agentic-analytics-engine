from unittest.mock import AsyncMock

import pytest

from cardinal.confidence.synthesis import (
    AnswerSynthesizer,
)


@pytest.mark.asyncio
async def test_synthesizer_uses_temperature_zero() -> None:
    client = AsyncMock()

    client.complete.return_value.text = (
        "There were 100 orders."
    )

    synthesizer = AnswerSynthesizer(
        client,
    )

    answer = await synthesizer.synthesize(
        "How many orders?",
        [[100]],
    )

    assert answer == "There were 100 orders."

    call = client.complete.await_args

    assert call.kwargs["temperature"] == 0.0
    assert call.kwargs["max_tokens"] == 150