"""Session-wide pytest fixtures."""

import pytest

import xl2hb
from extract_fixtures import CaptureFixture
from fixture_utils import CAPTURE_NAMES, parse_capture

# PRINTLOG item 2 is the time of the job. Tests that render a job twice and
# compare the outputs must not see the clock tick in between.
FIXED_PRINTLOG_TIME = "Mon,26 Oct 2026 20:36:0"


@pytest.fixture(autouse=True)
def _fixed_printlog_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(xl2hb, "_printlog_timestamp", lambda: FIXED_PRINTLOG_TIME)


@pytest.fixture(scope="session")
def all_captures() -> dict[str, CaptureFixture]:
    """The parsed framing captures, keyed by name."""
    return {name: parse_capture(name) for name in CAPTURE_NAMES}
