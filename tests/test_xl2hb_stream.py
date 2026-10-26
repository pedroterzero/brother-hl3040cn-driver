"""
Full stream integration tests.

Reconstructs XL2HB output from parsed capture data with XL2HBWriter and
compares it byte for byte against the captures of Brother's HL-3040CN
filter: this checks the session, page and image framing independently of
the colour pipeline.
"""

import itertools
import logging
from io import BytesIO

import pytest

from fixture_utils import CAPTURE_NAMES, assert_bytes_equal
from xl2hb import XL2HBWriter, get_image_dimensions

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reconstruct_stream(cap) -> bytes:
    """Rebuild the full XL2HB file from a parsed CaptureFixture.

    The framing captures are A4 pages printed with Brother's default rc
    (Copies=0) apart from the colour mode.
    """
    color = not cap.filename.startswith("mono_")
    buf = BytesIO()
    buf.write(cap.pjl_header)

    w = XL2HBWriter(buf)
    w.write_stream_header()
    w.write_begin_session()
    w.write_open_data_source()
    w.write_begin_page()
    w.write_set_page_origin()

    sw, sh = get_image_dimensions("A4")
    w.write_begin_image(sw, sh, copies=0, color=color)

    for block in cap.blocks:
        w.write_read_image(block.start_line, block.block_height, block.plane_id, block.expected_blob)

    w.write_end_image()
    w.write_end_page(copies=0)
    w.write_close_data_source()
    w.write_end_session()

    buf.write(cap.pjl_footer)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Full stream reconstruction tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", CAPTURE_NAMES)
def test_reconstructed_stream_matches_capture(all_captures, name):
    cap = all_captures[name]
    assert_bytes_equal(_reconstruct_stream(cap), cap.raw, name)


class TestCaptureContents:
    def test_white_page_has_no_blocks(self, all_captures):
        assert all_captures["a4_white"].blocks == []

    def test_mono_sends_only_k(self, all_captures):
        for name in ("mono_gray50", "mono_ramp"):
            assert {b.plane_id for b in all_captures[name].blocks} == {0}

    def test_red_has_only_m_and_y(self, all_captures):
        assert {b.plane_id for b in all_captures["red_100"].blocks} == {2, 3}

    def test_a4_black_flush_boundaries(self, all_captures):
        """a4_black: K blocks of 2249 lines each, the last one ending at the paper height (6981)."""
        blocks = all_captures["a4_black"].blocks
        assert [b.start_line for b in blocks] == [0, 2249, 4498, 6747]
        assert {b.plane_id for b in blocks} == {0}
        assert blocks[-1].start_line + blocks[-1].block_height == 6981


# ---------------------------------------------------------------------------
# Flush order verification
# ---------------------------------------------------------------------------


class TestFlushOrder:
    def test_m_before_y(self, all_captures):
        """In multi-plane captures, M(2) appears before Y(3)."""
        plane_ids = [b.plane_id for b in all_captures["red_100"].blocks]
        assert plane_ids.index(2) < plane_ids.index(3)

    def test_blocks_ending_on_an_empty_line_follow_cmyk_order(self, all_captures):
        """Planes flushed by the same empty line come out C, M, Y, K (cyan_100, gray50_1000).

        The full block order of every capture is checked byte for byte in
        tests/test_captures.py; a plane flushed because its buffer is nearly
        full can end on the same line as one flushed later.
        """
        flush_rank = {1: 0, 2: 1, 3: 2, 0: 3}
        pairs = 0
        for name in ("cyan_100", "gray50_1000"):
            blocks = all_captures[name].blocks
            for a, b in itertools.pairwise(blocks):
                if a.start_line + len(a.entries) == b.start_line + len(b.entries):
                    assert flush_rank[a.plane_id] < flush_rank[b.plane_id]
                    pairs += 1
        assert pairs


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestUnknownMediaDefaults:
    """Unknown media size/type should fall back to defaults with a warning."""

    def test_unknown_media_size(self, caplog):
        """Unknown media size defaults to A4 (enum 2) and logs a warning."""
        buf = BytesIO()
        w = XL2HBWriter(buf)
        with caplog.at_level(logging.WARNING, logger="xl2hb"):
            w.write_begin_page(media_size="A3")
        assert "Unknown media size" in caplog.text
        assert b"\xc0\x02\xf8\x25" in buf.getvalue()  # TAG_UBYTE 0x02 TAG_ATTR ATTR_MEDIA_SIZE

    def test_unknown_media_type(self, caplog):
        """Unknown media type (e.g. Glossy, which the HL-3040CN lacks) defaults to dRegular."""
        buf = BytesIO()
        w = XL2HBWriter(buf)
        with caplog.at_level(logging.WARNING, logger="xl2hb"):
            w.write_begin_page(media_type="Glossy")
        assert "Unknown media type" in caplog.text
        assert b"dRegular" in buf.getvalue()

    @pytest.mark.parametrize(("name", "xy"), [("PRA5Rotated", (2059, 1466)), ("JISB6", (1276, 1820))])
    def test_custom_media_size(self, name, xy):
        """A5 long edge and JIS B6 go out as CustomMediaSize in 0.1 mm, no MediaSize."""
        buf = BytesIO()
        XL2HBWriter(buf).write_begin_page(media_size=name)
        x, y = xy
        expected = b"\xd1" + x.to_bytes(2, "little") + y.to_bytes(2, "little") + b"\xf8\x2f\xc0\x02\xf8\x30"
        assert expected in buf.getvalue()
        assert b"\xf8\x25" not in buf.getvalue()
