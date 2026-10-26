"""
PJL header/footer tests.

The PJL job block and EOJ trailer of brhl3040cnfilter, checked line by
line and against the captures.
"""

import time

import pytest

import xl2hb
from capture_pages import MANIFEST
from fixture_utils import CAPTURE_NAMES, mask_printlog, printlog_time, read_capture
from xl2hb import generate_pjl_footer, generate_pjl_header

UEL = b"\x1b%-12345X"

# conftest freezes xl2hb._printlog_timestamp for every test; this is the real one.
_REAL_PRINTLOG_TIMESTAMP = xl2hb._printlog_timestamp

_JOB_BLOCK = [
    "@PJL ",
    '@PJL JOB NAME="Print Job"',
    "@PJL PRINTLOG ITEM = 1,PRINTER",
    "@PJL PRINTLOG ITEM = 2,<TIME>",
    "@PJL PRINTLOG ITEM = 3,anonymous",
    "@PJL PRINTLOG ITEM = 4,Linux",
    "@PJL SET STRINGCODESET=HPROMAN8",
    '@PJL SET LOGINUSER="anonymous"',
]


def _lines(header: bytes) -> list[str]:
    assert header.startswith(UEL)
    return mask_printlog(header)[len(UEL) :].decode("ascii").split("\n")


class TestPJLHeader:
    def test_header_starts_with_uel(self):
        assert generate_pjl_header().startswith(UEL), "Header must start with UEL"

    def test_header_ends_with_enter_language(self):
        assert generate_pjl_header().endswith(b"@PJL ENTER LANGUAGE=XL2HB\n")

    def test_lines_end_in_lf_only(self):
        assert b"\r" not in generate_pjl_header()

    def test_job_block_comes_first(self):
        assert _lines(generate_pjl_header())[: len(_JOB_BLOCK)] == _JOB_BLOCK

    def test_default_header(self):
        """Brother's default rc (Auto colour, Normal) gives exactly these lines."""
        assert _lines(generate_pjl_header()) == [
            *_JOB_BLOCK,
            "@PJL SET ECONOMODE=OFF",
            "@PJL SET RENDERMODE=COLOR",
            "@PJL SET COLORADAPT=ON",
            "@PJL SET LESSPAPERCURL=OFF",
            "@PJL SET FIXINTENSITYUP=OFF",
            "@PJL SET APTMODE=OFF",
            "@PJL SET RESOLUTION=600",
            "@PJL ENTER LANGUAGE=XL2HB",
            "",
        ]

    def test_header_economode_on(self):
        assert b"ECONOMODE=ON" in generate_pjl_header(economode=True)

    def test_header_grayscale(self):
        header = generate_pjl_header(color=False)
        assert b"RENDERMODE=GRAYSCALE" in header
        assert b"COLORADAPT=OFF" in header

    def test_coloradapt_off_for_explicit_colour(self):
        header = generate_pjl_header(color=True, color_adapt=False)
        assert b"RENDERMODE=COLOR" in header
        assert b"COLORADAPT=OFF" in header

    def test_aptmode(self):
        assert b"APTMODE=ON4" in generate_pjl_header(apt_mode=True)
        assert b"APTMODE=OFF" in generate_pjl_header(apt_mode=False)

    @pytest.mark.parametrize(("kwarg", "line"), [("improve_gray", b"IMPROVEGRAY=ON"), ("ucrgcr", b"UCRGCRFORIMAGE=ON")])
    def test_colour_only_lines(self, kwarg, line):
        assert line in generate_pjl_header(color=True, **{kwarg: True})
        assert line.split(b"=")[0] not in generate_pjl_header(color=False, **{kwarg: True})
        assert line.split(b"=")[0] not in generate_pjl_header()

    @pytest.mark.parametrize("command", [b"SOURCETRAY", b"RET=", b"PAGEPROTECT", b"MANUALDPX"])
    def test_commands_the_original_never_sends(self, command):
        """brhl3040cnfilter knows these commands but never sends them for this model."""
        assert command not in generate_pjl_header(color=True, apt_mode=True, improve_gray=True, ucrgcr=True)

    def test_command_order_matches_original(self):
        text = generate_pjl_header(color=True, apt_mode=True, improve_gray=True, ucrgcr=True).decode("ascii")
        commands = [
            "JOB NAME=",
            "PRINTLOG ITEM = 1",
            "LOGINUSER=",
            "ECONOMODE=",
            "RENDERMODE=",
            "COLORADAPT=",
            "LESSPAPERCURL=",
            "FIXINTENSITYUP=",
            "APTMODE=",
            "IMPROVEGRAY=",
            "UCRGCRFORIMAGE=",
            "RESOLUTION=",
            "ENTER LANGUAGE=",
        ]
        positions = [text.find(cmd) for cmd in commands]
        assert -1 not in positions
        assert positions == sorted(positions)


class TestPrintlogTimestamp:
    """PRINTLOG item 2: "%s,%d %s %d %d:%d:%d" of gmtime(), unpadded."""

    @pytest.mark.parametrize(
        ("epoch", "expected"),
        [
            (1793046960, "Mon,26 Oct 2026 20:36:0"),
            (1767225600, "Thu,1 Jan 2026 0:0:0"),
            (1782863999, "Tue,30 Jun 2026 23:59:59"),
            (1773532805, "Sun,15 Mar 2026 0:0:5"),
        ],
    )
    def test_format(self, monkeypatch, epoch, expected):
        then = time.gmtime(epoch)
        monkeypatch.setattr(time, "gmtime", lambda: then)
        assert _REAL_PRINTLOG_TIMESTAMP() == expected

    @pytest.mark.parametrize("name", CAPTURE_NAMES)
    def test_capture_timestamps_have_this_format(self, name):
        stamp = printlog_time(read_capture(name))
        day, rest = stamp.split(",")
        assert day in {"Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"}
        mday, month, year, hms = rest.split(" ")
        assert month in {"Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"}
        assert all(not part.startswith("0") or part == "0" for part in (mday, *hms.split(":")))
        assert len(year) == 4


class TestPJLFooter:
    def test_footer_closes_the_job(self):
        assert generate_pjl_footer() == UEL + b'@PJL EOJ NAME="Print Job"\n' + UEL


class TestPJLMatchesCaptures:
    @pytest.mark.parametrize("name", list(MANIFEST))
    def test_every_capture_has_the_job_block_and_trailer(self, name):
        data = read_capture(name)
        header = data[: data.index(b") BROTHER XL2HB")]
        assert _lines(header)[: len(_JOB_BLOCK)] == _JOB_BLOCK
        assert data.endswith(b"\x49\x42" + generate_pjl_footer())

    def test_default_header_matches_capture(self):
        """a4_white was printed with Brother's default rc."""
        data = read_capture("a4_white")
        header = data[: data.index(b") BROTHER XL2HB")]
        assert mask_printlog(header) == mask_printlog(generate_pjl_header())
