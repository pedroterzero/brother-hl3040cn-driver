"""
Full pipeline tests (PPM -> XL2HB) for HL-3040CN behaviour.

Byte identity with Brother's filter for every capture is checked in
tests/test_captures.py; these tests pin down the individual behaviours
behind it (job framing, page setup, copies, reverse print, colour mode,
Fine framing) on small inputs.
"""

import io
import struct

import numpy as np
import pytest

from brfilter import (
    ColorMatching,
    InputSlot,
    MediaType,
    MonoColor,
    PageSize,
    PrintSettings,
    Resolution,
    filter_page,
    filter_pages,
    read_ppm,
)
from capture_pages import A4_H, A4_W, job_pages
from fixture_utils import assert_bytes_equal, freeze_printlog, read_capture, render_capture
from pipeline import page_copies, page_repeats

UEL = b"\x1b%-12345X"
BEGIN_PAGE_OPS = b"\xf8\x34\x43"  # SimplexPageMode attribute, then BeginPage
REVERSE_MARKER = b"\xc0\x10\xf8\x81"  # attr 0x81 = 0x10 ahead of BeginPage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ppm_bytes(width: int, height: int, r: int, g: int, b: int) -> bytes:
    """Create a uniform-color PPM in memory."""
    return f"P6\n{width} {height}\n255\n".encode("ascii") + bytes([r, g, b]) * (width * height)


def _run_pipeline(width: int, height: int, pixel_data: bytes, settings=None) -> bytes:
    """Run the filter pipeline and return the XL2HB output."""
    out = io.BytesIO()
    filter_page(width, height, pixel_data, settings or PrintSettings(), out)
    return out.getvalue()


def _pipeline_from_ppm(ppm_data: bytes, settings=None) -> bytes:
    """Parse PPM then run pipeline."""
    result = read_ppm(io.BytesIO(ppm_data))
    assert result is not None, "test PPM is malformed"
    w, h, _, pixels = result
    return _run_pipeline(w, h, pixels, settings)


def _run_job(pages, settings) -> bytes:
    out = io.BytesIO()
    filter_pages(pages, settings, out)
    return out.getvalue()


def _attr_uint16(data: bytes, attr_id: int) -> int:
    idx = data.index(bytes([0xF8, attr_id]))
    return struct.unpack("<H", data[idx - 2 : idx])[0]


def _attr_ubyte(data: bytes, attr_id: int) -> int:
    return data[data.index(bytes([0xF8, attr_id])) - 1]


def _attr_uint16_xy(data: bytes, attr_id: int) -> tuple[int, int]:
    idx = data.index(bytes([0xF8, attr_id]))
    return struct.unpack("<HH", data[idx - 4 : idx])


# ---------------------------------------------------------------------------
# Job framing
# ---------------------------------------------------------------------------


class TestOutputStructure:
    """The job framing of brhl3040cnfilter: PJL job block, one XL2HB session, EOJ trailer."""

    @pytest.fixture
    def out(self):
        return _pipeline_from_ppm(_make_ppm_bytes(100, 100, 255, 255, 255))

    def test_starts_with_uel_and_job(self, out):
        assert out.startswith(UEL + b'@PJL \n@PJL JOB NAME="Print Job"\n')

    def test_ends_with_eoj_trailer(self, out):
        """CloseDataSource, EndSession, then UEL @PJL EOJ UEL."""
        assert out.endswith(b"\x49\x42" + UEL + b'@PJL EOJ NAME="Print Job"\n' + UEL)

    def test_one_session(self, out):
        assert out.count(b") BROTHER XL2HB;1;0\n") == 1
        assert out.count(b"\xf8\x89\x41") == 1  # UnitsPerMeasure, BeginSession

    def test_page_origin_is_sheet_corner(self, out):
        """The image covers the whole sheet: SetPageOrigin (0, 0)."""
        assert b"\xd3\x00\x00\x00\x00\xf8\x2a\x75" in out

    def test_simplex_page_mode(self, out):
        """SimplexPageMode = 0 on every page; the HL-3040CN has no duplex unit."""
        assert b"\xc0\x00" + BEGIN_PAGE_OPS in out
        assert b"\xf8\x35" not in out

    def test_white_page_has_no_read_image(self, out):
        payload = out[out.index(b") BROTHER XL2HB") : out.rindex(UEL + b"@PJL EOJ")]
        assert 0xB1 not in payload

    def test_black_page_has_read_image(self):
        out = _pipeline_from_ppm(_make_ppm_bytes(A4_W, 100, 0, 0, 0))
        assert b"\xf8\x81\xb1" in out


def test_white_page_matches_capture(monkeypatch):
    """A4 white page with the settings of Brother's default rc (Copies=0)."""
    freeze_printlog(monkeypatch, "a4_white")
    out = _run_job(job_pages("a4_white"), PrintSettings(copies=0))
    assert_bytes_equal(out, read_capture("a4_white"), "a4_white")


# ---------------------------------------------------------------------------
# Page geometry
# ---------------------------------------------------------------------------


class TestGeometry:
    @pytest.mark.parametrize(
        ("size", "wh"),
        [
            ("A4", (4960, 6975)),
            ("Letter", (5120, 6558)),
            ("Legal", (5120, 8358)),
            ("PRA5Rotated", (4896, 3466)),
            ("JISB6", (3040, 4300)),
            ("BrA4Long", (4960, 9525)),
            ("EnvPRC5Rotated", (5216, 2558)),
        ],
    )
    def test_begin_image_size(self, size, wh):
        """SourceWidth/Height and DestinationSize as brhl3040cnfilter writes them."""
        out = _run_pipeline(1, 1, b"\xff\xff\xff", PrintSettings(page_size=PageSize(size)))
        assert (_attr_uint16(out, 0x6C), _attr_uint16(out, 0x6B)) == wh
        assert _attr_uint16_xy(out, 0x67) == wh

    def test_rows_below_source_height_are_sent(self):
        """Rows run to the paper height (A4 6981), past SourceHeight 6975."""
        page = np.full((A4_H, A4_W, 3), 255, np.uint8)
        page[A4_H - 1, :10] = 0
        out = _run_job([(A4_W, A4_H, page)], PrintSettings())
        assert _attr_uint16(out, 0x6D) == A4_H - 1  # StartLine of the only block

    def test_wider_input_is_cut_at_the_image_width(self):
        """A PPM wider than the sheet is cropped, not wrapped."""
        width, height = 5200, 16
        pixel_data = bytes(range(256)) * (width * height * 3 // 256) + bytes(width * height * 3 % 256)
        assert _run_pipeline(width, height, pixel_data)


# ---------------------------------------------------------------------------
# Page setup: trays, media, copies
# ---------------------------------------------------------------------------


class TestPageSetup:
    @pytest.mark.parametrize(
        ("slot", "attr"),
        [
            (InputSlot.AUTO, b"\xc0\x01\xf8\x26"),
            (InputSlot.TRAY1, b"\xc1\xe9\x03\xf8\x26"),
            (InputSlot.MANUAL, b"\xc0\x02\xf8\x26"),
        ],
    )
    def test_input_slot_goes_into_media_source(self, slot, attr):
        """BeginPage MediaSource as brhl3040cnfilter writes it; no PJL SOURCETRAY."""
        out = _pipeline_from_ppm(_make_ppm_bytes(A4_W, 10, 0, 0, 0), PrintSettings(input_slot=slot))
        assert attr in out
        assert b"SOURCETRAY" not in out

    def test_bond_is_sent_as_transparency(self):
        out = _run_pipeline(1, 1, b"\xff\xff\xff", PrintSettings(media_type=MediaType.BOND))
        assert b"\xc8\xc0\x0ddTransparency\xf8\x27" in out

    @pytest.mark.parametrize(
        ("copies", "collate", "repeats", "page_copies_value"),
        [
            (0, False, 1, 0),  # Brother's rc default
            (1, False, 1, 1),
            (3, False, 3, 3),  # every page 3 times, each with PageCopies 3
            (3, True, 1, 1),  # every page once, PageCopies 1
            (1, True, 1, 1),
        ],
    )
    def test_copies_and_collate(self, copies, collate, repeats, page_copies_value):
        settings = PrintSettings(copies=copies, collate=collate)
        assert page_repeats(settings) == repeats
        assert page_copies(settings) == page_copies_value
        pages = [(1, 1, b"\x00\x00\x00"), (1, 1, b"\xff\xff\xff")]
        out = _run_job(pages, settings)
        assert out.count(BEGIN_PAGE_OPS) == 2 * repeats
        pc = struct.pack("<H", page_copies_value)
        assert out.count(b"\xc1" + pc + b"\xf8\x31\xb0") == 2 * repeats  # BeginImage
        assert out.count(b"\xc1" + pc + b"\xf8\x31\x44") == 2 * repeats  # EndPage

    def test_uncollated_copies_repeat_each_page_in_place(self):
        """Copies without collation: p1 p1 p2 p2, not p1 p2 p1 p2."""
        black, white = (1, 1, b"\x00\x00\x00"), (1, 1, b"\xff\xff\xff")
        out = _run_job([black, white], PrintSettings(copies=2))
        pages = out.split(BEGIN_PAGE_OPS)[1:]
        assert [b"\xb1" in p for p in pages] == [True, True, False, False]


# ---------------------------------------------------------------------------
# Reverse print
# ---------------------------------------------------------------------------


def _asymmetric_pages(n: int) -> list[tuple[int, int, np.ndarray]]:
    """A4 pages whose content is asymmetric in x and y, so flips and reordering show up."""
    colours = [(0, 255, 255), (255, 0, 255), (255, 255, 0), (0, 0, 0)]
    pages = []
    for i in range(n):
        page = np.full((A4_H, A4_W, 3), 255, np.uint8)
        page[300 + i * 100 : 420 + i * 100, 200:1400] = (0, 0, 0)
        page[4000:4150, 2600 + i * 200 : 4500] = colours[i]
        pages.append((A4_W, A4_H, page))
    return pages


class TestReversePrint:
    """BRReverse on the HL-3040CN: every page is marked and sent mirrored top to bottom.

    The printer prints it rotated by 180 degrees; the page order stays as it is.
    """

    def test_each_page_is_marked_and_mirrored_in_order(self):
        pages = _asymmetric_pages(3)
        reverse = _run_job(pages, PrintSettings(reverse=True))
        mirrored = _run_job([(w, h, p[::-1]) for w, h, p in pages], PrintSettings())
        assert reverse.count(REVERSE_MARKER) == 3
        assert reverse.count(REVERSE_MARKER + b"\xc0\x00\xf8\x28") == 3  # right before Orientation
        assert reverse.replace(REVERSE_MARKER, b"") == mirrored

    def test_short_page_is_padded_to_the_sheet_before_mirroring(self):
        """Rows missing below a short page become white rows at the top of the mirrored page."""
        page = np.zeros((100, A4_W, 3), np.uint8)
        full = np.full((A4_H, A4_W, 3), 255, np.uint8)
        full[:100] = 0
        reverse = _run_job([(A4_W, 100, page)], PrintSettings(reverse=True))
        mirrored = _run_job([(A4_W, A4_H, full[::-1])], PrintSettings())
        assert reverse.replace(REVERSE_MARKER, b"") == mirrored

    def test_matches_brother_capture(self, tmp_path, monkeypatch):
        freeze_printlog(monkeypatch, "multi2_reverse")
        assert_bytes_equal(render_capture("multi2_reverse", tmp_path), read_capture("multi2_reverse"), "reverse")


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


def _as_row_blocks(page: np.ndarray, block_rows: int):
    rows = page.reshape(page.shape[0], -1)
    return (rows[i : i + block_rows] for i in range(0, rows.shape[0], block_rows))


@pytest.mark.parametrize(
    "settings",
    [PrintSettings(), PrintSettings(reverse=True), PrintSettings(copies=2)],
    ids=["plain", "reverse", "copies"],
)
def test_streamed_row_blocks_match_whole_pages(settings):
    """Pages given as row blocks (as page_stream delivers them) render identically."""
    pages = _asymmetric_pages(2)
    expected = _run_job(pages, settings)
    streamed = [(w, h, _as_row_blocks(p, 333)) for w, h, p in pages]
    assert _run_job(streamed, settings) == expected


# ---------------------------------------------------------------------------
# Colour mode
# ---------------------------------------------------------------------------


class TestMonoMode:
    def test_only_k_plane(self):
        out = _pipeline_from_ppm(_make_ppm_bytes(A4_W, 10, 128, 0, 0), PrintSettings(mono_color=MonoColor.MONO))
        assert b"RENDERMODE=GRAYSCALE" in out
        # ReadImage colour-treatment attribute (plane id) for C/M/Y never appears.
        for plane_id in (1, 2, 3):
            assert bytes([0xC1, plane_id, 0x00, 0xF8, 0x81, 0xB1]) not in out
        assert bytes([0xC1, 0x00, 0x00, 0xF8, 0x81, 0xB1]) in out

    def test_band_config_marks_grayscale(self):
        """Word 2 of the BeginImage band config is 0 for a grayscale image."""
        out = _run_pipeline(1, 1, b"\x00\x00\x00", PrintSettings(mono_color=MonoColor.MONO))
        assert b"\xc9\xc1\x17\x00\x00\x00\x03\x00\x00\x00" in out

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"saturation": 20},
            {"color_matching": ColorMatching.VIVID},
            {"improve_gray": True},
            {"enhance_black": True},
        ],
        ids=["saturation", "vivid", "improve_gray", "enhance_black"],
    )
    def test_colour_only_settings_are_ignored(self, kwargs, tmp_path, monkeypatch):
        """Brother's output for mono_ramp is the same with these colour settings."""
        freeze_printlog(monkeypatch, "mono_ramp")
        out = render_capture("mono_ramp", tmp_path, PrintSettings(mono_color=MonoColor.MONO, copies=0, **kwargs))
        assert_bytes_equal(out, read_capture("mono_ramp"), "mono_ramp")


class TestColourMode:
    @pytest.mark.parametrize(
        ("mono_color", "lines"),
        [
            (MonoColor.AUTO, (b"RENDERMODE=COLOR", b"COLORADAPT=ON")),
            (MonoColor.FULL_COLOR, (b"RENDERMODE=COLOR", b"COLORADAPT=OFF")),
            (MonoColor.MONO, (b"RENDERMODE=GRAYSCALE", b"COLORADAPT=OFF")),
        ],
    )
    def test_render_mode_and_color_adapt(self, mono_color, lines):
        out = _run_pipeline(1, 1, b"\x00\x00\x00", PrintSettings(mono_color=mono_color))
        for line in lines:
            assert line in out

    def test_auto_sends_gray_pages_in_colour(self):
        """Auto does not switch gray pages to mono: C, M and Y planes are sent (capture auto_gray50)."""
        out = _run_pipeline(4, 1, b"\x80" * 12, PrintSettings())
        assert b"RENDERMODE=COLOR" in out
        assert any(bytes([0xC1, plane_id, 0x00, 0xF8, 0x81, 0xB1]) in out for plane_id in (1, 2, 3))

    def test_toner_save_keeps_economode_off(self):
        """Toner save uses the -TS dither tables; ECONOMODE stays OFF, as in the original."""
        out = _run_pipeline(1, 1, b"\x00\x00\x00", PrintSettings(toner_save=True))
        assert b"ECONOMODE=OFF" in out
        assert b"ECONOMODE=ON" not in out


# ---------------------------------------------------------------------------
# Fine mode framing
# ---------------------------------------------------------------------------


class TestFineResolution:
    """Fine mode framing as in Brother's fine_* captures.

    RESOLUTION=600 and a 600x600 session as in Normal mode, APTMODE=ON4,
    ColorDepth 1, the Normal source height and the width rounded up to 8
    pixels (A4: 4960 x 6975).
    """

    @pytest.fixture
    def fine(self):
        return _run_pipeline(1, 1, b"\xff\xff\xff", PrintSettings(resolution=Resolution.FINE))

    @pytest.fixture
    def normal(self):
        return _run_pipeline(1, 1, b"\xff\xff\xff", PrintSettings())

    def test_source_size(self, fine):
        assert (_attr_uint16(fine, 0x6C), _attr_uint16(fine, 0x6B)) == (4960, 6975)

    @pytest.mark.parametrize(("size", "width"), [("Letter", 5104), ("JISB6", 3024), ("A6", 2480)])
    def test_width_rounded_to_8(self, size, width):
        settings = PrintSettings(resolution=Resolution.FINE, page_size=PageSize(size))
        assert _attr_uint16(_run_pipeline(1, 1, b"\xff\xff\xff", settings), 0x6C) == width

    def test_color_depth(self, fine, normal):
        assert _attr_ubyte(fine, 0x62) == 1
        assert _attr_ubyte(normal, 0x62) == 0

    def test_session_units_stay_600(self, fine, normal):
        assert _attr_uint16_xy(normal, 0x89) == (600, 600)
        assert _attr_uint16_xy(fine, 0x89) == (600, 600)

    def test_pjl(self, fine, normal):
        assert b"RESOLUTION=600" in fine
        assert b"APTMODE=ON4" in fine
        assert b"APTMODE=OFF" in normal
