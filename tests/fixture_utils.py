"""Reading the zstd-compressed reference captures and comparing output against them.

The captures in ``tests/fixtures/`` are the output of Brother's own
HL-3040CN filter (see `capture_pages`). They are committed to the
repository, so a missing fixture is an error, not a skip.

Brother's filter writes the job time into ``@PJL PRINTLOG ITEM = 2``;
`freeze_printlog` makes the driver write the capture's own timestamp, so
outputs compare byte for byte, and `mask_printlog` hides the line where
the driver runs in another process.
"""

import functools
import io
import re
from pathlib import Path

import pytest
import zstandard

import xl2hb
from capture_pages import FIXTURES_DIR, MANIFEST, job_pages, rc_text
from extract_fixtures import PLANE_NAMES, CaptureFixture, parse_xl2hb_capture
from pipeline import filter_pages
from settings import PrintSettings

# Captures whose framing (PJL, blocks, plane buffers) the framing tests check:
# A4, default settings apart from the colour mode.
CAPTURE_NAMES = [
    "a4_white",
    "a4_black",
    "cyan_100",
    "red_100",
    "gray50_1000",
    "gray75_1000",
    "mono_gray50",
    "mono_ramp",
]

_PRINTLOG_TIME = re.compile(rb"@PJL PRINTLOG ITEM = 2,([^\n]*)\n")


@functools.cache
def read_fixture(name: str) -> bytes:
    """Read a zstd-compressed fixture by its original filename.

    Args:
        name: Original filename (e.g. ``"a4_white.xl2hb"``).

    Returns:
        Decompressed bytes.
    """
    return zstandard.ZstdDecompressor().decompressobj().decompress((FIXTURES_DIR / f"{name}.zst").read_bytes())


def read_capture(name: str) -> bytes:
    """The capture ``<name>.xl2hb``.

    Returns:
        Its bytes.
    """
    return read_fixture(f"{name}.xl2hb")


def printlog_time(data: bytes) -> str:
    """The PRINTLOG item 2 timestamp of a stream.

    Returns:
        The timestamp text, e.g. ``"Mon,26 Oct 2026 20:36:0"``.
    """
    match = _PRINTLOG_TIME.search(data)
    assert match, "no PRINTLOG ITEM = 2 line"
    return match.group(1).decode("ascii")


def mask_printlog(data: bytes) -> bytes:
    """Replace the PRINTLOG item 2 timestamp with a fixed marker.

    Returns:
        `data` with the first timestamp masked.
    """
    return _PRINTLOG_TIME.sub(rb"@PJL PRINTLOG ITEM = 2,<TIME>\n", data, count=1)


def freeze_printlog(monkeypatch: pytest.MonkeyPatch, capture: str) -> None:
    """Make the driver write the PRINTLOG timestamp of capture `capture`."""
    stamp = printlog_time(read_capture(capture))
    monkeypatch.setattr(xl2hb, "_printlog_timestamp", lambda: stamp)


def assert_bytes_equal(actual: bytes, expected: bytes, label: str) -> None:
    """Assert byte-for-byte equality, reporting the first difference on failure."""
    if actual == expected:
        return
    msg_parts = [f"{label}: length {len(actual)} vs {len(expected)}"]
    for i in range(min(len(actual), len(expected))):
        if actual[i] != expected[i]:
            start = max(0, i - 8)
            msg_parts.append(f"  First diff at byte {i}: got 0x{actual[i]:02x}, expected 0x{expected[i]:02x}")
            msg_parts.append(f"  Expected [{start}:{i + 8}]: {expected[start : i + 8].hex()}")
            msg_parts.append(f"  Actual   [{start}:{i + 8}]: {actual[start : i + 8].hex()}")
            break
    pytest.fail("\n".join(msg_parts))


def assert_matches_capture(name: str, out: bytes) -> None:
    """Assert that `out` equals the capture ``<name>.xl2hb``, timestamp masked."""
    assert_bytes_equal(mask_printlog(out), mask_printlog(read_capture(name)), name)


def capture_settings(name: str, tmp_path: Path) -> PrintSettings:
    """The settings of capture `name`, read from its rc file like the CLI does.

    Returns:
        Settings parsed from the capture's brhl3040cnrc.
    """
    rc = tmp_path / f"{name}.rc"
    rc.write_text(rc_text(MANIFEST[name].overrides))
    return PrintSettings.from_rc_file(str(rc))


def render_capture(name: str, tmp_path: Path, settings: PrintSettings | None = None) -> bytes:
    """Render the input of capture `name` through the pipeline.

    Returns:
        The XL2HB job, with `settings` or else the capture's own rc settings.
    """
    if settings is None:
        settings = capture_settings(name, tmp_path)
    out = io.BytesIO()
    filter_pages(job_pages(MANIFEST[name].page), settings, out)
    return out.getvalue()


@functools.cache
def parse_capture(name: str) -> CaptureFixture:
    """Parse the capture ``<name>.xl2hb`` once per session."""
    return parse_xl2hb_capture(read_capture(name), name)


def capture_block_params() -> list:
    """One pytest.param (capture_name, block_idx) per ReadImage block of every framing capture.

    IDs look like ``a4_black_block0_K_L0_x2249``.
    """
    params = []
    for name in CAPTURE_NAMES:
        for i, block in enumerate(parse_capture(name).blocks):
            plane = PLANE_NAMES.get(block.plane_id, f"P{block.plane_id}")
            tid = f"{name}_block{i}_{plane}_L{block.start_line}_x{len(block.entries)}"
            params.append(pytest.param(name, i, id=tid))
    return params
