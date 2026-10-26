"""
Ordered dithering tests.

Tests the dithering subsystem against the reverse-engineered dither.c
of the original driver and against its captures.

The driver uses ordered dithering with BRCD lookup tables,
supporting 1bpp (bitmap, Normal mode) and 4bpp (nibble, Fine mode)
output, one channel at a time.
"""

import pytest

# ---------------------------------------------------------------------------
# Dither module API
# ---------------------------------------------------------------------------


class TestDitherAPI:
    """Tests that the dither module exposes the expected API."""

    def test_module_exists(self):
        import dither  # noqa: F401

    def test_has_init_function(self):
        from dither import load_dither_tables  # noqa: F401

    def test_has_ordered_1ch_1bpp(self):
        from dither import dither_channel_1bpp  # noqa: F401

    def test_has_ordered_1ch_4bpp(self):
        from dither import dither_channel_4bpp  # noqa: F401


# ---------------------------------------------------------------------------
# 1bpp ordered dithering (bitmap mode, Normal resolution)
# ---------------------------------------------------------------------------


class TestOrdered1bpp:
    """Ordered dithering to 1-bit-per-pixel output."""

    def test_white_input_no_dots(self):
        """Pure white (255) should produce no dots at any position."""
        from dither import dither_channel_1bpp

        row = bytes([255] * 4760)
        result = dither_channel_1bpp(row, y=0, width=4760)
        assert not any(result)

    def test_black_input_all_dots(self):
        """Pure black (0) should produce all dots set."""
        from dither import dither_channel_1bpp

        row = bytes([0] * 4760)
        result = dither_channel_1bpp(row, y=0, width=4760)
        bpl = (4760 + 7) // 8
        assert len(result) == bpl
        # All bits set for active pixels
        for x in range(4760):
            byte_idx = x >> 3
            bit_mask = 0x80 >> (x & 7)
            assert result[byte_idx] & bit_mask, f"Pixel {x} should be set"

    def test_50pct_gray_coverage(self):
        """50% gray should produce approximately 50% dot coverage."""
        from dither import dither_channel_1bpp

        row = bytes([128] * 4760)
        result = dither_channel_1bpp(row, y=0, width=4760)
        bits_set = sum(b.bit_count() for b in result[:595])
        # Allow 10% tolerance
        assert 1900 < bits_set < 2860, f"Expected ~2380 bits, got {bits_set}"

    def test_monotonic_coverage(self):
        """Darker grays should produce more dots than lighter grays."""
        from dither import dither_channel_1bpp

        coverages = []
        for gray in [224, 192, 128, 64, 32]:
            row = bytes([gray] * 4760)
            result = dither_channel_1bpp(row, y=0, width=4760)
            bits = sum(b.bit_count() for b in result[:595])
            coverages.append(bits)
        # Each should be strictly greater than the previous
        for i in range(len(coverages) - 1):
            assert coverages[i] < coverages[i + 1], f"Coverage not monotonic: gray levels produced {coverages}"

    def test_position_dependent(self):
        """Different y positions should produce different patterns for same input."""
        from dither import dither_channel_1bpp

        row = bytes([128] * 4760)
        result_y0 = dither_channel_1bpp(row, y=0, width=4760)
        result_y1 = dither_channel_1bpp(row, y=1, width=4760)
        assert result_y0 != result_y1, "Dither should vary by y position"

    def test_deterministic(self):
        """Same input + position should produce same output."""
        from dither import dither_channel_1bpp

        row = bytes([128] * 4760)
        a = dither_channel_1bpp(row, y=42, width=4760)
        b = dither_channel_1bpp(row, y=42, width=4760)
        assert a == b


# ---------------------------------------------------------------------------
# 4bpp ordered dithering (nibble mode — 16 intensity levels per pixel)
# ---------------------------------------------------------------------------


class TestOrdered1ch4bpp:
    """Ordered dithering to 4-bit-per-pixel nibble-packed output."""

    def test_white_input_all_zero_nibbles(self):
        """Pure white (255) should produce all-zero nibbles."""
        from dither import dither_channel_4bpp

        row = bytes([255] * 4760)
        result = dither_channel_4bpp(row, y=0, width=4760)
        assert not any(result)

    def test_black_input_all_max_nibbles(self):
        """Pure black (0) should produce all 0xFF bytes (nibbles = 15)."""
        from dither import dither_channel_4bpp

        row = bytes([0] * 4760)
        result = dither_channel_4bpp(row, y=0, width=4760)
        assert all(b == 0xFF for b in result)

    def test_output_length(self):
        """Output should be (width + 1) // 2 bytes."""
        from dither import dither_channel_4bpp

        for width in [4760, 100, 32]:
            row = bytes([128] * width)
            result = dither_channel_4bpp(row, y=0, width=width)
            assert len(result) == (width + 1) // 2

    def test_output_length_odd_width(self):
        """Odd width: output is (width + 1) // 2, last low nibble padded to 0."""
        from dither import dither_channel_4bpp

        row = bytes([0] * 33)  # all black
        result = dither_channel_4bpp(row, y=0, width=33)
        assert len(result) == 17  # (33 + 1) // 2
        # Last byte: high nibble = 15 (pixel 32), low nibble = 0 (padding)
        assert result[-1] == 0xF0

    def test_nibble_packing_order(self):
        """First pixel goes into high nibble, second into low nibble."""
        from dither import dither_channel_4bpp

        # All black: every nibble = 15 → 0xFF per byte
        row = bytes([0] * 2)
        result = dither_channel_4bpp(row, y=0, width=2)
        assert result[0] == 0xFF

        # Single pixel (odd width): high nibble set, low nibble zero
        row = bytes([0] * 1)
        result = dither_channel_4bpp(row, y=0, width=1)
        assert result[0] == 0xF0

    def test_50pct_gray_coverage(self):
        """50% gray should produce nibbles averaging around 7-8."""
        from dither import dither_channel_4bpp

        row = bytes([128] * 4760)
        result = dither_channel_4bpp(row, y=0, width=4760)
        # Extract all nibbles and compute average
        nibbles = []
        for b in result:
            nibbles.append((b >> 4) & 0x0F)
            nibbles.append(b & 0x0F)
        nibbles = nibbles[:4760]  # trim to actual width
        avg = sum(nibbles) / len(nibbles)
        assert 6.0 < avg < 9.0, f"Expected avg nibble ~7-8, got {avg:.2f}"

    def test_monotonic_coverage(self):
        """Darker pixels should produce higher nibble sums."""
        from dither import dither_channel_4bpp

        sums = []
        for gray in [224, 192, 128, 64, 32]:
            row = bytes([gray] * 4760)
            result = dither_channel_4bpp(row, y=0, width=4760)
            nibble_sum = 0
            for b in result:
                nibble_sum += (b >> 4) & 0x0F
                nibble_sum += b & 0x0F
            sums.append(nibble_sum)
        for i in range(len(sums) - 1):
            assert sums[i] < sums[i + 1], f"Nibble sum not monotonic: {sums}"

    def test_position_dependent(self):
        """Different y positions should produce different output for same input."""
        from dither import dither_channel_4bpp

        row = bytes([128] * 4760)
        result_y0 = dither_channel_4bpp(row, y=0, width=4760)
        result_y1 = dither_channel_4bpp(row, y=1, width=4760)
        assert result_y0 != result_y1, "4bpp dither should vary by y position"

    def test_deterministic(self):
        """Same input + position should produce identical output."""
        from dither import dither_channel_4bpp

        row = bytes([128] * 4760)
        a = dither_channel_4bpp(row, y=42, width=4760)
        b = dither_channel_4bpp(row, y=42, width=4760)
        assert a == b

    def test_nibble_values_in_range(self):
        """All nibble values should be in [0, 15]."""
        from dither import dither_channel_4bpp

        for gray in [0, 64, 128, 192, 255]:
            row = bytes([gray] * 100)
            result = dither_channel_4bpp(row, y=7, width=100)
            for b in result:
                assert (b >> 4) <= 15
                assert (b & 0x0F) <= 15


# ---------------------------------------------------------------------------
# BRCD dither table loading
# ---------------------------------------------------------------------------


class TestBRCDTables:
    """The driver loads dither matrices from BRCD cache files."""

    def test_load_brcd_cache(self):
        """Should load dither tables from a BRCD cache file."""
        from pathlib import Path

        from dither import dither_channel_1bpp, dither_load_brcd

        lut_base = Path(__file__).resolve().parent.parent / "src" / "lut"
        k_path = str(lut_base / "0600-k_cache08.bin")
        if not Path(k_path).exists():
            pytest.skip("Original BRCD files not available")
        ch = dither_load_brcd(k_path)
        # The HL-3040CN K screen is 80x80.
        assert ch.width == 80
        assert ch.height == 80
        assert ch.threshold_matrix is not None
        assert ch.threshold_matrix.shape == (80, 80)
        # ink=0 (white) places no dots, full ink (black) fills every position.
        assert dither_channel_1bpp(bytes([255] * 80), 0, 80, ch) == bytes(10)
        assert dither_channel_1bpp(bytes(80), 0, 80, ch) == b"\xff" * 10

    def test_bayer_fallback(self):
        """Bayer matrix fallback produces valid dither tables."""
        from dither import load_dither_tables

        channels = load_dither_tables()
        assert "K" in channels
        assert "C" in channels
        assert "M" in channels
        assert "Y" in channels
        for ch in channels.values():
            assert ch.threshold_matrix is not None
            assert ch.threshold_matrix.shape == (32, 32)
            assert ch.width == 32
            assert ch.height == 32


# ---------------------------------------------------------------------------
# Capture-derived dithering verification
# ---------------------------------------------------------------------------


class TestCaptureVerification:
    """Verify dithering output matches original driver captures.

    These tests extract the actual dithered bitmap from captures
    (by decompressing the compressed plane data) and compare against
    our dithering output given the same PPM input.
    """

    @staticmethod
    def _plane_lines(cap, plane_id: int, plane_name: str, bpl: int):
        """Yield (line, decoded bitmap) for every non-empty entry of one plane of a capture."""
        from brother_decode import decode_plane

        for block in cap.blocks:
            if block.plane_id != plane_id:
                continue
            for entry_idx, entry in enumerate(block.entries):
                if entry:
                    yield block.start_line + entry_idx, decode_plane(entry, plane_name, n_bytes=bpl)

    def test_black_page_k_dither_matches(self, all_captures):
        """Every K line of a4_black decodes to the bitmap our dither makes of the black page.

        Black pixels are full K ink, so every dot is set; the two pixels of
        padding to the 32-pixel image width (4958 -> 4960) stay white.
        """
        from brfilter import rgb_to_cmyk_lut
        from capture_pages import page
        from dither import dither_channel_1bpp, load_dither_tables

        cap = all_captures["a4_black"]
        pixels = page("a4_black")
        height, width = pixels.shape[:2]
        sw = (width + 31) // 32 * 32
        bpl = sw // 8
        channels = load_dither_tables()
        lines = 0
        for line_idx, captured in self._plane_lines(cap, 0, "K", bpl):
            if line_idx >= height:
                continue
            k_int, _, _, _ = rgb_to_cmyk_lut(pixels[line_idx].tobytes(), width)
            ours = dither_channel_1bpp(k_int + b"\xff" * (sw - width), line_idx, sw, channels["K"])
            assert ours == captured, f"K line {line_idx} differs"
            lines += 1
        assert lines > 6000

    def test_cyan_band_dither_matches(self, all_captures):
        """K and Y lines of cyan_100 match our separation + BRCD dither of the page, re-encoded.

        Compared after encoding: the 12-bit RLE is lossy for dithered rows
        (different bitmaps can encode to the same bytes), so decoded
        bitmaps need not match.
        """
        from pathlib import Path

        from brfilter import rgb_to_cmyk_lut
        from brother_encode import encode_plane
        from capture_pages import page
        from dither import dither_channel_1bpp, load_brcd_tables

        cap = all_captures["cyan_100"]
        pixels = page("cyan_100")
        width = pixels.shape[1]
        lut_dir = str(Path(__file__).resolve().parent.parent / "src" / "lut")
        channels = load_brcd_tables(lut_dir)
        assert channels is not None, "BRCD tables missing; run scripts/extract_blobs.sh"
        sw = (width + 31) // 32 * 32
        pad = b"\xff" * (sw - width)

        total = 0
        for plane_id, plane_name, ch_idx in [(0, "K", 0), (3, "Y", 3)]:
            for block in cap.blocks:
                if block.plane_id != plane_id:
                    continue
                for entry_idx, entry in enumerate(block.entries):
                    line_idx = block.start_line + entry_idx
                    ch_int = rgb_to_cmyk_lut(pixels[line_idx].tobytes(), width)[ch_idx] + pad
                    ours = dither_channel_1bpp(ch_int, line_idx, sw, channels[plane_name])
                    assert encode_plane(ours, plane_name) == entry, f"{plane_name} line {line_idx} differs"
                    total += 1
        assert total > 0

    def test_gray75_dither_matches(self, all_captures):
        """Gray75 K-plane dither+compress should match gray75_1000 capture.

        Source: RGB(64,64,64) → via driver LUT → K intensity 155 (pixel-brightness).
        Compares compressed outputs (not decoded bitmaps) because the K-plane
        12-bit RLE is lossy for dithered patterns — different bitmaps can
        produce identical compressed bytes.
        """
        from pathlib import Path

        from brfilter import rgb_to_cmyk_lut
        from brother_encode import encode_plane

        cap = all_captures["gray75_1000"]

        k_blocks = [b for b in cap.blocks if b.plane_id == 0]
        assert k_blocks, "No K-plane blocks in gray75_1000"

        from dither import dither_channel_1bpp, load_brcd_tables

        lut_dir = str(Path(__file__).resolve().parent.parent / "src" / "lut")
        channels = load_brcd_tables(lut_dir)
        assert channels is not None, "BRCD tables missing; run scripts/extract_blobs.sh"
        sw = 4960  # A4 image width: 4958 rounded up to 32 pixels
        width = 4958

        # Gray75 source = RGB(64,64,64) → LUT → K intensity (pixel-brightness)
        rgb_row = bytes([64, 64, 64]) * width
        k_int, _, _, _ = rgb_to_cmyk_lut(rgb_row, width)
        pad = b"\xff" * (sw - width)
        gray_k_int = k_int + pad

        mismatches = 0
        total = 0
        for block in k_blocks:
            for entry_idx, entry in enumerate(block.entries):
                if not entry:
                    continue
                total += 1
                line_idx = block.start_line + entry_idx

                our_plane = dither_channel_1bpp(gray_k_int, line_idx, sw, channels["K"])
                our_compressed = encode_plane(our_plane, "K")

                if our_compressed != entry:
                    mismatches += 1

        assert mismatches == 0, f"{mismatches}/{total} K-plane compressed lines differ"


# ---------------------------------------------------------------------------
# Fine mode BRCD dither table loading
# ---------------------------------------------------------------------------


class TestFineBRCDTables:
    """Fine mode uses different BRCD cache files with different matrix dimensions."""

    def test_nibble_table_width_must_be_whole_bytes(self, tmp_path):
        """A Fine table is one byte per pixel; a width in bits that is not a multiple of 8 is rejected."""
        import struct

        from dither import dither_load_brcd

        width, height = 12, 2
        row_bytes = (width * height + 7) // 8
        path = tmp_path / "odd.bin"
        path.write_bytes(b"BRCD1\0" + struct.pack("<HH", width, height) + bytes(256 * row_bytes))
        dither_load_brcd(str(path))  # fine as a 1bpp table
        with pytest.raises(ValueError, match="multiple of 8"):
            dither_load_brcd(str(path), nibbles=True)

    def test_load_fine_brcd_channels(self):
        """Should load all 4 Fine BRCD channels."""
        from pathlib import Path

        from dither import load_brcd_tables

        lut_dir = str(Path(__file__).resolve().parent.parent / "src" / "lut")
        channels = load_brcd_tables(lut_dir, fine=True)
        if channels is None:
            pytest.skip("Fine BRCD files not available")
        assert set(channels.keys()) == {"K", "C", "M", "Y"}

    def test_fine_brcd_dimensions(self):
        """Fine BRCD channels have specific dimensions per channel."""
        from pathlib import Path

        from dither import load_brcd_tables

        lut_dir = str(Path(__file__).resolve().parent.parent / "src" / "lut")
        channels = load_brcd_tables(lut_dir, fine=True)
        if channels is None:
            pytest.skip("Fine BRCD files not available")
        # HL-3040CN capt screens: K and Y 96x12 bits, C and M 160x20 bits; one
        # byte (a 4-bit level) per pixel, so the cells are 12x12 and 20x20.
        assert {ch: (t.width, t.height) for ch, t in channels.items()} == {
            "K": (12, 12),
            "C": (20, 20),
            "M": (20, 20),
            "Y": (12, 12),
        }
        assert all(t.nibble_levels is not None and int(t.nibble_levels.max()) <= 15 for t in channels.values())

    def test_fine_4bpp_dithering_output_length(self):
        """4bpp dithering with Fine channels produces correct output length."""
        from pathlib import Path

        from dither import dither_channel_4bpp, load_brcd_tables

        lut_dir = str(Path(__file__).resolve().parent.parent / "src" / "lut")
        channels = load_brcd_tables(lut_dir, fine=True)
        if channels is None:
            pytest.skip("Fine BRCD files not available")

        width = 4960  # Fine A4 width
        row = bytes([128] * width)  # 50% gray
        result = dither_channel_4bpp(row, y=0, width=width, channel=channels["K"])
        assert len(result) == (width + 1) // 2  # 2480 bytes


# ---------------------------------------------------------------------------
# ndarray variants (hot path)
# ---------------------------------------------------------------------------


class TestArrVariants:
    """The *_arr variants must match the bytes API, including over-wide rows."""

    @pytest.mark.parametrize("fn_name", ["dither_channel_1bpp", "dither_channel_4bpp"])
    def test_wider_row_truncated_to_width(self, fn_name):
        """A row longer than `width` (uncropped PPM) is cut like the bytes API does."""
        import numpy as np

        import dither

        width = 4768
        row = np.arange(4958, dtype=np.uint32).astype(np.uint8)
        arr_fn = getattr(dither, f"{fn_name}_arr")
        bytes_fn = getattr(dither, fn_name)
        for y in range(3):
            assert arr_fn(row, y, width) == bytes_fn(row.tobytes(), y, width)


def test_native_1bpp_dither_matches_numpy(monkeypatch):
    """_dither_fast.dither_row_1bpp agrees with the numpy threshold path."""
    import numpy as np

    import dither

    if not dither.HAS_CYTHON_DITHER:
        pytest.skip("_dither_fast extension not built")
    rng = np.random.default_rng(1)
    channels = dither.load_dither_tables()
    for width in (4768, 4761, 5):
        row = rng.integers(0, 256, width + 190, dtype=np.uint8)
        strided = np.repeat(row, 2)[::2]  # non-contiguous view, as from a KCMY column
        for y in (0, 17, 31):
            native = dither.dither_channel_1bpp_arr(strided, y, width, channels["C"])
            monkeypatch.setattr(dither, "HAS_CYTHON_DITHER", False)
            reference = dither.dither_channel_1bpp_arr(strided, y, width, channels["C"])
            monkeypatch.setattr(dither, "HAS_CYTHON_DITHER", True)
            assert native == reference


# ---------------------------------------------------------------------------
# Missing BRCD blobs: Bayer fallback must be loud, but only once
# ---------------------------------------------------------------------------


class TestBayerFallbackWarning:
    """Missing dither tables change every page, so the fallback warns (once)."""

    @pytest.fixture(autouse=True)
    def _fresh_warning_state(self, monkeypatch):
        import dither

        monkeypatch.setattr(dither, "_bayer_fallback_warned", set())

    def _fallback_warnings(self, caplog):
        return [r for r in caplog.records if r.name == "dither" and r.levelname == "WARNING"]

    def test_missing_tables_warn_with_hint(self, tmp_path, caplog):
        from dither import load_dither_tables

        with caplog.at_level("WARNING", logger="dither"):
            load_dither_tables(str(tmp_path))
        warnings = self._fallback_warnings(caplog)
        assert len(warnings) == 1
        assert "scripts/extract_blobs.sh" in warnings[0].getMessage()
        assert "Bayer" in warnings[0].getMessage()

    def test_warning_is_logged_once_per_table(self, tmp_path, caplog):
        from dither import load_dither_tables

        with caplog.at_level("WARNING", logger="dither"):
            for _ in range(3):
                load_dither_tables(str(tmp_path))
                load_dither_tables(str(tmp_path), fine=True)
        assert len(self._fallback_warnings(caplog)) == 1

        with caplog.at_level("WARNING", logger="dither"):
            load_dither_tables(str(tmp_path), toner_save=True)
            load_dither_tables(str(tmp_path), toner_save=True)
        warnings = self._fallback_warnings(caplog)
        assert len(warnings) == 2
        assert "-TS_cache08.bin" in warnings[1].getMessage()

    def test_present_tables_do_not_warn(self, caplog):
        from pathlib import Path

        from dither import load_dither_tables

        lut_dir = Path(__file__).resolve().parent.parent / "src" / "lut"
        if not (lut_dir / "0600-k_cache08.bin").exists():
            pytest.skip("BRCD blobs not extracted")
        with caplog.at_level("WARNING", logger="dither"):
            load_dither_tables(str(lut_dir))
        assert not self._fallback_warnings(caplog)
