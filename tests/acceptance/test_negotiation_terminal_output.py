from io import StringIO

import pytest

from maintenance_agent.application.messages import TerminalFrame
from maintenance_agent.infrastructure.cli_transport import AsyncStdoutWriter


@pytest.mark.asyncio
async def test_terminal_output_is_exactly_two_physical_lines() -> None:
    output = StringIO()
    writer = AsyncStdoutWriter(output)
    await writer.write_terminal(
        TerminalFrame("WO-1", "scheduled", "SCHEDULED_FOR:2026-10-12T10:00:00+02:00")
    )
    assert output.getvalue() == (
        "WOID:WO-1|RESULT:scheduled\nSCHEDULED_FOR:2026-10-12T10:00:00+02:00\n"
    )


@pytest.mark.asyncio
async def test_review_terminal_line_escapes_source_newlines() -> None:
    output = StringIO()
    await AsyncStdoutWriter(output).write_terminal(
        TerminalFrame("WO-2", "requires_review", r"REASON:No response\nfrom handyman")
    )
    assert output.getvalue().splitlines() == [
        "WOID:WO-2|RESULT:requires_review",
        r"REASON:No response\nfrom handyman",
    ]
