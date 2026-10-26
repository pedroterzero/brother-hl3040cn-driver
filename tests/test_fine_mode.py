"""Fine mode (600x2400 dpi, APTMODE=ON4) byte-exact against brhl3040cnfilter.

The Fine captures (BRResolution=Fine in tests/fixtures/manifest.tsv) are
rendered through both Fine paths: per line in Python (dither.py,
fine_encoder.py) and, when it is built, the native band kernel
(_fine_fast). tests/test_captures.py takes whichever path production
takes; this module pins down each one.
"""

import pytest

import pipeline
from capture_pages import MANIFEST
from fixture_utils import assert_bytes_equal, capture_settings, freeze_printlog, read_capture, render_capture
from settings import Resolution

FINE_CAPTURES = [name for name, capture in MANIFEST.items() if capture.overrides.get("BRResolution") == "Fine"]


def test_fine_captures_cover_colour_mono_and_colour_settings():
    assert {"fine_a4_white", "fine_a4_black", "mixed_fine", "mono_ramp_fine"} <= set(FINE_CAPTURES)
    assert len(FINE_CAPTURES) >= 10


@pytest.mark.parametrize("kernel", [False, True], ids=["per-line", "band-kernel"])
@pytest.mark.parametrize("name", FINE_CAPTURES)
def test_fine_capture_matches_original(name, kernel, tmp_path, monkeypatch):
    if kernel and not pipeline.HAS_FINE_BAND_KERNEL:
        pytest.skip("_fine_fast extension not built")
    monkeypatch.setattr(pipeline, "HAS_FINE_BAND_KERNEL", kernel)
    settings = capture_settings(name, tmp_path)
    assert settings.resolution == Resolution.FINE
    freeze_printlog(monkeypatch, name)
    assert_bytes_equal(render_capture(name, tmp_path, settings), read_capture(name), name)
