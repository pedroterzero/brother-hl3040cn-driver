"""
Print settings tests.

PrintSettings defaults, brhl3040cnrc parsing, and the HL-3040CN paper,
media and PJL tables.
"""

from pathlib import Path

import pytest

from brfilter import MediaType, MonoColor, PrintSettings
from capture_pages import DEFAULT_RC, PAPER, rc_text
from settings import MEDIA_SOURCE, InputSlot, PageSize
from xl2hb import (
    CUSTOM_MEDIA_SIZE_UNITS,
    MEDIA_SIZE,
    MEDIA_TYPE_STRINGS,
    PAPER_SIZES,
    generate_pjl_header,
    get_image_dimensions,
    get_image_dimensions_fine,
)

# ---------------------------------------------------------------------------
# Default settings
# ---------------------------------------------------------------------------


class TestDefaultSettings:
    def test_defaults(self):
        s = PrintSettings()
        assert s.media_type == "Plain"
        assert s.page_size == "A4"
        assert s.input_slot == "AutoSelect"
        assert s.resolution == "Normal"
        assert s.copies == 1
        assert s.collate is False
        assert s.mono_color == "Auto"
        assert s.color_matching == "Normal"
        assert s.improve_gray is False
        assert s.enhance_black is False
        assert s.toner_save is False
        assert s.improve_output == "OFF"
        assert (s.brightness, s.contrast, s.red, s.green, s.blue, s.saturation) == (0, 0, 0, 0, 0, 0)
        assert not hasattr(s, "duplex")  # no duplex unit, no skip blank on the HL-3040CN
        assert not hasattr(s, "skip_blank")
        assert s.reverse is False


# ---------------------------------------------------------------------------
# RC file parsing
# ---------------------------------------------------------------------------


class TestRCFileParsing:
    @pytest.fixture
    def write_rc(self, tmp_path):
        def write(content: str) -> str:
            path = tmp_path / "brhl3040cnrc"
            path.write_text(content)
            return str(path)

        return write

    def test_brothers_default_rc(self, write_rc):
        """Brother's shipped rc: Copies=0, everything else matches the dataclass defaults."""
        s = PrintSettings.from_rc_file(write_rc(rc_text({})))
        assert s == PrintSettings(copies=0)

    def test_parse_standard_rc(self, write_rc):
        rc = write_rc(
            rc_text(
                {
                    "MediaType": "Thick",
                    "PageSize": "Letter",
                    "InputSlot": "Tray1",
                    "BRResolution": "Fine",
                    "Copies": "3",
                    "Collate": "ON",
                    "BRReverse": "ON",
                    "BRMonoColor": "Mono",
                    "BRColorMatching": "Vivid",
                    "BRGray": "ON",
                    "BREnhanceBlkPrt": "ON",
                    "TonerSaveMode": "ON",
                    "BRImproveOutput": "BRLessPaperCurl",
                    "Brightness": "10",
                    "Contrast": "-5",
                    "RedKey": "3",
                    "GreenKey": "-2",
                    "BlueKey": "1",
                    "Saturation": "8",
                }
            )
        )
        s = PrintSettings.from_rc_file(rc)
        assert s.media_type == "Thick"
        assert s.page_size == "Letter"
        assert s.input_slot == "Tray1"
        assert s.resolution == "Fine"
        assert s.copies == 3
        assert s.collate is True
        assert s.reverse is True
        assert s.mono_color == "Mono"
        assert s.color_matching == "Vivid"
        assert s.improve_gray is True
        assert s.enhance_black is True
        assert s.toner_save is True
        assert s.improve_output == "BRLessPaperCurl"
        assert (s.brightness, s.contrast, s.red, s.green, s.blue, s.saturation) == (10, -5, 3, -2, 1, 8)

    def test_parse_minimal_rc(self, write_rc):
        s = PrintSettings.from_rc_file(write_rc("[HL3040CN]\nMediaType=Env\n"))
        assert s.media_type == MediaType.ENVELOPE
        assert s.page_size == "A4"  # default preserved
        assert s.copies == 1

    def test_empty_rc_gives_defaults(self, write_rc):
        assert PrintSettings.from_rc_file(write_rc("")) == PrintSettings()

    @pytest.mark.parametrize(
        ("key", "value", "attr", "expected"),
        [
            ("MediaType", "BOND", "media_type", MediaType.BOND),
            ("MediaType", "Env", "media_type", MediaType.ENVELOPE),
            ("MediaType", "PostCard", "media_type", MediaType.POSTCARD),
            ("PageSize", "B5", "page_size", PageSize.ISOB5),
            ("PageSize", "B6", "page_size", PageSize.ISOB6),
            ("PageSize", "PostCard", "page_size", PageSize.POSTCARD),
            ("PageSize", "BrA4Long", "page_size", PageSize.BR_A4_LONG),
            ("BRMonoColor", "Color", "mono_color", MonoColor.FULL_COLOR),
        ],
    )
    def test_brother_spellings(self, write_rc, key, value, attr, expected):
        """brhl3040cnrc spells these differently from this driver's PPD."""
        s = PrintSettings.from_rc_file(write_rc(rc_text({key: value})))
        assert getattr(s, attr) == expected

    @pytest.mark.parametrize("value", ["FullColor", "Colour", "color", ""])
    def test_mono_color_is_read_strictly(self, write_rc, value):
        """Brother's filter treats any BRMonoColor but Auto/Color/Mono as Auto (capture mixed_fullcolor)."""
        s = PrintSettings.from_rc_file(write_rc(rc_text({"BRMonoColor": value})))
        assert s.mono_color == MonoColor.AUTO

    @pytest.mark.parametrize(("key", "value"), [("MediaType", "Glossy"), ("InputSlot", "Tray2"), ("PageSize", "A3")])
    def test_values_the_hl3040cn_does_not_have(self, write_rc, key, value):
        with pytest.raises(ValueError, match=value):
            PrintSettings.from_rc_file(write_rc(rc_text({key: value})))

    def test_parse_original_rc(self):
        """Parse the rc file of Brother's driver (extracted by scripts/extract_blobs.sh)."""
        rc_path = (
            Path(__file__).resolve().parent.parent
            / ".brother-blobs/extracted/opt/brother/Printers/hl3040cn/inf/brhl3040cnrc"
        )
        if not rc_path.exists():
            pytest.skip("Brother driver not extracted; run scripts/extract_blobs.sh")
        assert rc_path.read_text().split() == rc_text({}).split()
        assert PrintSettings.from_rc_file(str(rc_path)) == PrintSettings(copies=0)

    def test_default_rc_keys(self):
        """The keys of brhl3040cnrc: no Duplex, BRSkipBlank or Glossy on this model."""
        assert "Duplex" not in DEFAULT_RC
        assert "BRSkipBlank" not in DEFAULT_RC
        assert {"Copies", "Collate", "BRReverse"} <= set(DEFAULT_RC)


# ---------------------------------------------------------------------------
# Paper sizes
# ---------------------------------------------------------------------------

# rc PageSize -> PageSize value of this driver, where they differ.
_DRIVER_NAME = {"B5": "ISOB5", "B6": "ISOB6", "PostCard": "Postcard"}


def _pixels_to_tenth_mm(px: int) -> int:
    """brhl3040cnfilter's CustomMediaSize: px -> whole points -> 1/120 inch -> 600 dpi -> 0.1 mm."""
    return px * 72 // 600 * 120 // 72 * 5 * 25400 // 60000


class TestPaperSizes:
    def test_every_rc_size_has_a_page_size(self):
        assert {PageSize(name).value for name in PAPER} == {s.value for s in PageSize}

    @pytest.mark.parametrize("rc_name", list(PAPER))
    def test_paper_is_the_whole_sheet_of_paperinfij2(self, rc_name):
        assert PAPER_SIZES[PageSize(rc_name)] == PAPER[rc_name]

    @pytest.mark.parametrize("rc_name", list(PAPER))
    def test_image_dimensions(self, rc_name):
        """Width rounded up to 32 pixels, height = paper height in whole points at 600 dpi."""
        w, h = PAPER[rc_name]
        size = PageSize(rc_name)
        assert get_image_dimensions(size) == ((w + 31) // 32 * 32, h * 72 // 600 * 600 // 72)
        assert get_image_dimensions_fine(size) == ((w + 7) // 8 * 8, h * 72 // 600 * 600 // 72)

    @pytest.mark.parametrize(
        ("name", "media_size"),
        [
            ("A4", 2),
            ("Letter", 0),
            ("Legal", 1),
            ("Executive", 3),
            ("A5", 16),
            ("PRA5Rotated", (2059, 1466)),
            ("A6", 17),
            ("ISOB5", 12),
            ("ISOB6", b"B6"),
            ("JISB5", 11),
            ("JISB6", (1276, 1820)),
            ("EnvDL", 9),
            ("EnvC5", 8),
            ("Env10", 6),
            ("EnvMonarch", 7),
            ("Br3x5", b"3x5"),
            ("BrA4Long", b"A4Long"),
            ("FanFoldGermanLegal", b"Folio"),
            ("EnvPRC5Rotated", b"DL Long Edge"),
            ("Postcard", 14),
            ("EnvYou4", b"Envelope #4"),
            ("EnvChou3", b"Envelope MAX"),
        ],
    )
    def test_media_size(self, name, media_size):
        """MediaSize as brhl3040cnfilter writes it: enum, name string, or CustomMediaSize."""
        assert MEDIA_SIZE[name] == media_size

    @pytest.mark.parametrize("name", ["PRA5Rotated", "JISB6"])
    def test_custom_media_size_from_paperinfij2(self, name):
        w, h = PAPER_SIZES[name]
        assert MEDIA_SIZE[name] == (_pixels_to_tenth_mm(w), _pixels_to_tenth_mm(h))
        assert CUSTOM_MEDIA_SIZE_UNITS == 2


# ---------------------------------------------------------------------------
# Media types and sources
# ---------------------------------------------------------------------------


class TestMediaTypes:
    """Wire strings as brhl3040cnfilter writes them for each MediaType."""

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Plain", b"dRegular"),
            ("Thin", b"dThin"),
            ("Thick", b"dThick"),
            ("Thicker", b"dThick2"),
            ("Bond", b"dTransparency"),
            ("Envelope", b"dEnvelopes"),
            ("EnvThin", b"dEnvthin"),
            ("EnvThick", b"dEnvthick"),
            ("Recycled", b"dRecycled"),
            ("Postcard", b"dPostcard"),
            ("Label", b"dLabel"),
        ],
    )
    def test_media_type_strings(self, name, expected):
        assert MEDIA_TYPE_STRINGS[name] == expected

    def test_every_media_type_has_a_wire_string(self):
        assert set(MEDIA_TYPE_STRINGS) == {m.value for m in MediaType}

    def test_no_glossy(self):
        assert "Glossy" not in MEDIA_TYPE_STRINGS
        with pytest.raises(ValueError, match="Glossy"):
            MediaType("Glossy")


class TestMediaSources:
    def test_hl3040cn_sources(self):
        """Auto 1, Tray 1 1001, manual feed 2; no Tray 2 or MP tray."""
        assert MEDIA_SOURCE == {InputSlot.AUTO: 1, InputSlot.TRAY1: 1001, InputSlot.MANUAL: 2}
        assert {s.value for s in InputSlot} == {"AutoSelect", "Tray1", "Manual"}


# ---------------------------------------------------------------------------
# PJL settings propagation
# ---------------------------------------------------------------------------


class TestPJLSettingsPropagation:
    def test_less_paper_curl(self):
        assert b"LESSPAPERCURL=ON" in generate_pjl_header(less_paper_curl=True)

    def test_fix_intensity(self):
        assert b"FIXINTENSITYUP=ON" in generate_pjl_header(fix_intensity=True)

    def test_resolution_600(self):
        assert b"RESOLUTION=600" in generate_pjl_header(resolution=600)


# ---------------------------------------------------------------------------
# Toner save
# ---------------------------------------------------------------------------


class TestTonerSave:
    def test_toner_save_reduces_coverage(self):
        """Brother's toner-save dither tables (-TS_cache08) put fewer dots on a mid-gray row."""
        import numpy as np

        from dither import dither_channel_1bpp_arr, load_dither_tables

        lut_dir = str(Path(__file__).resolve().parent.parent / "src" / "lut")
        width = 256
        row = np.full(width, 128, dtype=np.uint8)

        normal_ch = load_dither_tables(lut_dir)
        ts_ch = load_dither_tables(lut_dir, toner_save=True)

        normal_dots = 0
        ts_dots = 0
        for y in range(32):
            normal_out = dither_channel_1bpp_arr(row, y, width, normal_ch["K"])
            ts_out = dither_channel_1bpp_arr(row, y, width, ts_ch["K"])
            normal_dots += np.unpackbits(np.frombuffer(normal_out, dtype=np.uint8)).sum()
            ts_dots += np.unpackbits(np.frombuffer(ts_out, dtype=np.uint8)).sum()

        assert ts_dots < normal_dots, f"Toner save dots ({ts_dots}) should be fewer than normal ({normal_dots})"
