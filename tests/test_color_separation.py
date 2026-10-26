"""
Color separation tests (RGB -> CMYK).

Colour-table selection, the LUT-based separation and its dithering. The
byte-exact separation of real pages is covered by the capture tests in
tests/test_full_pipeline.py.
"""

import pytest

from brfilter import ColorMatching, MediaType, PrintSettings, Resolution, rgb_to_cmyk_lut
from color_lut import ColorTable
from dither import dither_channel_1bpp
from transforms import color_table

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rgb_row(r: int, g: int, b: int, width: int = 4760) -> bytes:
    """Create a uniform RGB scanline."""
    return bytes([r, g, b]) * width


# ---------------------------------------------------------------------------
# Ordered dithering of separated channels
# ---------------------------------------------------------------------------


class TestOrderedDithering:
    """Tests for proper ordered dithering -- the driver uses a matrix-based
    dither, not simple thresholding."""

    def test_50pct_gray_produces_halftone_pattern(self):
        """50% gray should produce a halftone pattern, not uniform output.
        The driver uses ordered dithering to distribute dots.
        With the 3D LUT, gray ink is spread across CMYK channels."""
        k_int, c_int, m_int, y_int = rgb_to_cmyk_lut(_make_rgb_row(128, 128, 128), 4760)
        # Dither all channels and count total dots
        k = dither_channel_1bpp(k_int, y=0, width=4760)
        c = dither_channel_1bpp(c_int, y=0, width=4760)
        m = dither_channel_1bpp(m_int, y=0, width=4760)
        y_d = dither_channel_1bpp(y_int, y=0, width=4760)
        # At least some channel should have meaningful coverage
        total_bits = sum(b.bit_count() for b in (k + c + m + y_d)[: 595 * 4])
        assert total_bits > 500, f"50% gray should produce dots across CMYK, got {total_bits}"

    def test_25pct_gray_sparser_than_50pct(self):
        """25% gray should have fewer dots than 50% gray."""
        k_25_int, _, _, _ = rgb_to_cmyk_lut(_make_rgb_row(191, 191, 191), 4760)
        k_50_int, _, _, _ = rgb_to_cmyk_lut(_make_rgb_row(128, 128, 128), 4760)
        k_25 = dither_channel_1bpp(k_25_int, y=0, width=4760)
        k_50 = dither_channel_1bpp(k_50_int, y=0, width=4760)
        bits_25 = sum(b.bit_count() for b in k_25[:595])
        bits_50 = sum(b.bit_count() for b in k_50[:595])
        assert bits_25 < bits_50

    def test_dither_varies_by_line(self):
        """Different scanlines should produce different dot patterns
        (the dither matrix is position-dependent)."""
        k_int, _, _, _ = rgb_to_cmyk_lut(_make_rgb_row(128, 128, 128), 4760)
        k_y0 = dither_channel_1bpp(k_int, y=0, width=4760)
        k_y1 = dither_channel_1bpp(k_int, y=1, width=4760)
        assert k_y0 != k_y1, "Dither should vary by y position"

    def test_brcd_table_loading(self):
        """The driver loads dither matrices from BRCD cache files."""
        from pathlib import Path

        from dither import load_brcd_tables

        lut_dir = str(Path(__file__).resolve().parent.parent / "src" / "lut")
        if not (Path(lut_dir) / "0600-k_cache08.bin").exists():
            pytest.skip("Original BRCD files not available")
        channels = load_brcd_tables(lut_dir)
        assert channels is not None
        # HL-3040CN 0600 cache08 screens: K, C and M 80x80, Y 24x24
        assert (channels["K"].width, channels["K"].height) == (80, 80)
        assert (channels["C"].width, channels["M"].width) == (80, 80)
        assert (channels["Y"].width, channels["Y"].height) == (24, 24)


# ---------------------------------------------------------------------------
# Colour table selection
# ---------------------------------------------------------------------------


class TestColorTables:
    """Colour grid selection as in `lookup_color_transform_table`."""

    @pytest.mark.parametrize(
        ("settings", "expected"),
        [
            (PrintSettings(), ColorTable("rgb")),
            (PrintSettings(color_matching=ColorMatching.VIVID), ColorTable("srgb")),
            (PrintSettings(color_matching=ColorMatching.NONE), ColorTable("cmyk")),
            (PrintSettings(improve_gray=True), ColorTable("rgb", improve_gray=True)),
            # The HL-3040CN has no toner-save or glossy grids: toner save only
            # switches the dither files, the media type changes nothing.
            (PrintSettings(toner_save=True), ColorTable("rgb")),
            (PrintSettings(media_type=MediaType.BOND), ColorTable("rgb")),
            # Fine takes the CAPT grids.
            (PrintSettings(resolution=Resolution.FINE), ColorTable("rgb", variant="fine")),
            (
                PrintSettings(resolution=Resolution.FINE, color_matching=ColorMatching.VIVID, improve_gray=True),
                ColorTable("srgb", improve_gray=True, variant="fine"),
            ),
            (PrintSettings(enhance_black=True), ColorTable("rgb", rich_black=True)),
            (PrintSettings(enhance_black=True, color_matching=ColorMatching.NONE), ColorTable("cmyk")),
        ],
    )
    def test_table_for_settings(self, settings, expected):
        assert color_table(settings) == expected

    @pytest.mark.parametrize(
        ("table", "rgb", "expected"),
        [
            (ColorTable("rgb"), (0, 255, 255), (255, 62, 255, 243)),
            (ColorTable("rgb"), (255, 0, 0), (255, 255, 43, 65)),
            (ColorTable("rgb"), (128, 128, 128), (240, 175, 199, 192)),
            (ColorTable("rgb", improve_gray=True), (128, 128, 128), (149, 255, 255, 255)),
            (ColorTable("rgb", variant="fine"), (128, 128, 128), (255, 168, 191, 191)),
            (ColorTable("srgb"), (0, 255, 255), (255, 0, 255, 255)),
            (ColorTable("cmyk"), (30, 200, 90), (255, 35, 236, 113)),
            (ColorTable("cmyk"), (200, 100, 50), (255, 235, 124, 60)),
        ],
    )
    def test_separation_matches_original(self, table, rgb, expected):
        """(K, C, M, Y) as brhl3040cnfilter separates these solid colours (checked against its captures)."""
        k, c, m, y = rgb_to_cmyk_lut(_make_rgb_row(*rgb, width=1), 1, table)
        assert (k[0], c[0], m[0], y[0]) == expected

    def test_rich_black_takes_grid_entry_zero(self):
        k, c, m, y = rgb_to_cmyk_lut(_make_rgb_row(0, 0, 0, width=1), 1, ColorTable("rgb", rich_black=True))
        assert (k[0], c[0], m[0], y[0]) == (0, 255 - 45, 255 - 34, 255 - 40)
        k, c, m, y = rgb_to_cmyk_lut(_make_rgb_row(0, 0, 0, width=1), 1, ColorTable("rgb"))
        assert (k[0], c[0], m[0], y[0]) == (0, 255, 255, 255)


# Brightness / contrast / RGB-key adjustments are covered byte-for-byte
# by the cyan_100_* captures in tests/test_captures.py.
