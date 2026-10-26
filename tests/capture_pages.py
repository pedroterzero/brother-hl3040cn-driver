"""Input pages and rc files of the reference captures in tests/fixtures/.

The captures were made by running Brother's own HL-3040CN filter
(brhl3040cnfilter 1.1.2-1) on the pages generated here, with the rc file
`rc_text(overrides)`; `fixtures/manifest.tsv` lists the page and the rc
overrides of every capture. Multi-page inputs join page names with '+'.

The generators are numpy versions of the pure-Python ones the captures
were made with, and produce the same bytes.
"""

import functools
from dataclasses import dataclass
from pathlib import Path

import numpy as np

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# HL-3040CN paperinfij2: whole sheet in pixels at 600 dpi, keyed by the rc
# PageSize value (Brother's spelling). Deliberately a copy, not
# xl2hb.PAPER_SIZES: the tests check the driver against it.
PAPER: dict[str, tuple[int, int]] = {
    "A4": (4958, 6981),
    "Letter": (5100, 6564),
    "Legal": (5100, 8364),
    "Executive": (4350, 6264),
    "A5": (3500, 4922),
    "PRA5Rotated": (4868, 3474),
    "A6": (2475, 3464),
    "B5": (4158, 5872),
    "B6": (2958, 4122),
    "JISB5": (4300, 6039),
    "JISB6": (3017, 4300),
    "EnvDL": (2600, 5164),
    "EnvC5": (3825, 5372),
    "Env10": (2475, 5664),
    "EnvMonarch": (2325, 4464),
    "Br3x5": (1800, 2964),
    "BrA4Long": (4958, 9531),
    "FanFoldGermanLegal": (5100, 7764),
    "EnvPRC5Rotated": (5200, 2564),
    "PostCard": (2367, 3456),
    "EnvYou4": (2483, 5516),
    "EnvChou3": (2832, 5516),
}

A4_W, A4_H = PAPER["A4"]

# brhl3040cnrc as Brother ships it; every capture's rc file is this with
# the manifest overrides applied.
DEFAULT_RC: dict[str, str] = {
    "MediaType": "Plain",
    "PageSize": "A4",
    "InputSlot": "AutoSelect",
    "BRResolution": "Normal",
    "Copies": "0",
    "Collate": "OFF",
    "BRReverse": "OFF",
    "BRMonoColor": "Auto",
    "BRColorMatching": "Normal",
    "BRGray": "OFF",
    "BREnhanceBlkPrt": "OFF",
    "TonerSaveMode": "OFF",
    "BRImproveOutput": "OFF",
    "Brightness": "0",
    "Contrast": "0",
    "RedKey": "0",
    "GreenKey": "0",
    "BlueKey": "0",
    "Saturation": "0",
    "Language": "us",
}


def rc_text(overrides: dict[str, str]) -> str:
    """The brhl3040cnrc file of a capture.

    Returns:
        File content, `[HL3040CN]` section with every key.
    """
    rc = {**DEFAULT_RC, **overrides}
    return "[HL3040CN]\n" + "".join(f"{key}={value}\n" for key, value in rc.items())


@dataclass(frozen=True)
class Capture:
    """One row of fixtures/manifest.tsv."""

    name: str
    page: str
    overrides: dict[str, str]

    @property
    def pages(self) -> list[str]:
        """Component pages of the input, in job order."""
        return self.page.split("+")


def load_manifest() -> list[Capture]:
    """Read fixtures/manifest.tsv.

    Returns:
        Every capture, in manifest order.
    """
    rows = (FIXTURES_DIR / "manifest.tsv").read_text().splitlines()[1:]
    captures = []
    for row in rows:
        if not row:
            continue
        name, page, overrides = [*row.split("\t"), ""][:3]
        captures.append(Capture(name, page, dict(item.split("=", 1) for item in overrides.split())))
    return captures


MANIFEST: dict[str, Capture] = {c.name: c for c in load_manifest()}


# --- page generators --------------------------------------------------------

_M32 = np.uint64(0xFFFFFFFF)


def _hash_noise(w: int, rows: int, extra: int = 0) -> np.ndarray:
    """(rows, w, 3) noise: ((x*2654435761 mod 2^32 + y*40503 + ch*97 + extra) mod 2^32) >> 13 & 255."""
    x = np.arange(w, dtype=np.uint64)[None, :, None]
    y = np.arange(rows, dtype=np.uint64)[:, None, None]
    ch = np.arange(3, dtype=np.uint64)[None, None, :]
    v = (((x * np.uint64(2654435761)) & _M32) + y * np.uint64(40503) + ch * np.uint64(97) + np.uint64(extra)) & _M32
    return ((v >> np.uint64(13)) & np.uint64(255)).astype(np.uint8)


def _uniform(rgb: tuple[int, int, int]) -> np.ndarray:
    return np.broadcast_to(np.array(rgb, np.uint8), (A4_H, A4_W, 3))


def _band(y0: int, y1: int, rgb: tuple[int, int, int]) -> np.ndarray:
    page = np.full((A4_H, A4_W, 3), 255, np.uint8)
    page[y0:y1] = rgb
    return page


def _ramps() -> np.ndarray:
    """Gray ramp rows 500..1500, colour ramp rows 2000..2600, white elsewhere."""
    page = np.full((A4_H, A4_W, 3), 255, np.uint8)
    x = np.arange(A4_W) * 256 // A4_W
    page[500:1500] = np.repeat(x, 3).reshape(A4_W, 3).astype(np.uint8)
    page[2000:2600] = np.stack([x, 255 - x, (np.arange(A4_W) * 7) & 255], axis=1).astype(np.uint8)
    return page


# Colours on which the original's 80-bit x87 saturation arithmetic differs
# from exact floor division at saturation +20 or +7.
X87_SATURATION_PIXELS = [
    (59, 30, 1), (4, 164, 124), (181, 6, 216), (231, 9, 83), (90, 156, 13), (16, 107, 120), (228, 193, 18),
    (22, 250, 136), (118, 28, 208), (237, 37, 187), (95, 238, 51), (73, 127, 241), (242, 110, 99), (135, 245, 223),
    (30, 1, 59), (204, 6, 171), (127, 242, 12), (19, 65, 157), (209, 117, 25), (32, 170, 124), (132, 40, 224),
    (249, 49, 149), (151, 197, 59), (73, 96, 165), (192, 139, 86), (100, 208, 154), (140, 117, 209), (245, 139, 192),
]  # fmt: skip


def _mixed() -> np.ndarray:
    """Busy A4 page: hash noise, sparse two-tone pixels, per-row colours, ramps, patches, black.

    Exercises literal/run/context-skip transitions in all four plane
    encoders and the per-pixel colour adjustments.
    """
    w = A4_W
    page = np.full((A4_H, w, 3), 255, np.uint8)
    page[100:164] = _hash_noise(w, 64)
    x = np.arange(w, dtype=np.uint64)[None, :]
    y = np.arange(64, dtype=np.uint64)[:, None]
    bit = (((((x * np.uint64(7919)) & _M32) + y * np.uint64(104729)) & _M32) >> np.uint64(5)) & np.uint64(1)
    page[200:264] = np.where(bit[..., None] == 1, 230, 30).astype(np.uint8)
    rows = np.arange(64)
    page[300:364] = np.stack([(rows * 37) & 255, (rows * 91 + 50) & 255, (rows * 53 + 120) & 255], 1)[:, None, :]
    ramp = np.arange(w) * 256 // w
    page[400:464] = np.stack([ramp, 255 - ramp, np.full(w, 128)], axis=1).astype(np.uint8)
    for j, x0 in enumerate(range(0, w, 170)):
        page[500:564, x0 : x0 + 85] = ((j * 67) & 255, (j * 151 + 30) & 255, (j * 23 + 200) & 255)
        page[600:664, x0 : x0 + 170] = X87_SATURATION_PIXELS[j % len(X87_SATURATION_PIXELS)]
    page[700:764, : w // 2] = 0  # pure black: K only, or rich black with BREnhanceBlkPrt
    page[700:764, w // 2 :] = (0, 0, 1)
    return page


def edges_page(size: str) -> np.ndarray:
    """Whole sheet: hash noise at the top, a ramp at the bottom, a blue bar on the right edge.

    Returns:
        (h, w, 3) uint8 page at the paperinfij2 size of `size`.
    """
    w, h = PAPER[size]
    page = np.full((h, w, 3), 255, np.uint8)
    page[20:80] = _hash_noise(w, 60, extra=1)
    page[h - 60 :] = ((np.arange(w) * 7 + 1) & 255).astype(np.uint8)[None, :, None]
    page[:, w - 30 :] = (0, 90, 200)
    return page


_PAGES = {
    "a4_white": lambda: _uniform((255, 255, 255)),
    "a4_black": lambda: _uniform((0, 0, 0)),
    "cyan_100": lambda: _band(3000, 3100, (0, 255, 255)),
    "red_100": lambda: _band(3000, 3100, (255, 0, 0)),
    "gray50_1000": lambda: _band(1000, 2000, (128, 128, 128)),
    "gray75_1000": lambda: _band(1000, 2000, (64, 64, 64)),
    "mixgreen_100": lambda: _band(2000, 2100, (30, 200, 90)),
    "ramps": _ramps,
    "mixed": _mixed,
    **{f"edges_{size}": functools.partial(edges_page, size) for size in PAPER},
}

PAGE_NAMES = tuple(_PAGES)


@functools.lru_cache(maxsize=2)
def page(name: str) -> np.ndarray:
    """A capture input page as a read-only (h, w, 3) uint8 array.

    Returns:
        The page; cached, so callers must not modify it.
    """
    arr = np.ascontiguousarray(_PAGES[name]())
    arr.flags.writeable = False
    return arr


def job_pages(spec: str) -> list[tuple[int, int, np.ndarray]]:
    """The (width, height, pixels) pages of a '+'-joined manifest page spec.

    Returns:
        Pages in job order, as `pipeline.filter_pages` takes them.
    """
    pages = []
    for name in spec.split("+"):
        arr = page(name)
        pages.append((arr.shape[1], arr.shape[0], arr))
    return pages


def ppm_bytes(name: str) -> bytes:
    """A capture input page as a binary PPM file.

    Returns:
        P6 header plus pixel data.
    """
    arr = page(name)
    return f"P6\n{arr.shape[1]} {arr.shape[0]}\n255\n".encode("ascii") + arr.tobytes()
