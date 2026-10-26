"""Helpers in the CUPS filter script (loaded from cups/brhl3040cn-filter)."""

import importlib.machinery
import importlib.util
from pathlib import Path

import pytest

_FILTER = Path(__file__).resolve().parent.parent / "cups" / "brhl3040cn-filter"


@pytest.fixture(scope="module")
def cups_filter():
    loader = importlib.machinery.SourceFileLoader("brhl3040cn_filter", str(_FILTER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


_PPD = _FILTER.parent / "brhl3040cn.ppd"


def _ppd_paper_dimensions() -> dict[str, tuple[int, int]]:
    """PaperDimension of every PageSize in the PPD, in points."""
    dims = {}
    for line in _PPD.read_text(encoding="latin-1").splitlines():
        if line.startswith("*PaperDimension "):
            name = line.split()[1].split("/")[0]
            width, height = line.split('"')[1].split()
            dims[name] = (round(float(width)), round(float(height)))
    return dims


def test_ppd_page_sizes_are_the_driver_page_sizes():
    """Every PageSize of the PPD has a paperinfij2 size, and the other way round."""
    from settings import PageSize
    from xl2hb import PAPER_SIZES

    ppd = _ppd_paper_dimensions()
    assert set(ppd) == {size.value for size in PageSize} == set(PAPER_SIZES)


@pytest.mark.parametrize("page_size", sorted(_ppd_paper_dimensions()))
def test_gs_command_renders_the_whole_sheet(cups_filter, monkeypatch, page_size):
    """Ghostscript renders at the HL-3040CN paperinfij2 size, as Brother's psconvertij2."""
    from xl2hb import PAPER_SIZES

    monkeypatch.setattr(cups_filter, "find_gs", lambda: "gs")
    cmd = cups_filter.build_gs_command("job.ps", page_size)
    width, height = PAPER_SIZES[page_size]
    assert f"-g{width}x{height}" in cmd
    assert "-r600" in cmd
    assert not any(arg.startswith(("-sPAPERSIZE", "-dDEVICEWIDTHPOINTS")) for arg in cmd)
    assert cmd[-1] == "job.ps"
    assert cups_filter.PRINTABLE_OFFSET == (0, 0)


@pytest.mark.parametrize("page_size", ["Executive", "Env10", "EnvMonarch", "A4", "PRA5Rotated"])
def test_ghostscript_renders_the_requested_size(cups_filter, tmp_path, page_size):
    """Ghostscript's PPM has exactly the paperinfij2 size."""
    from xl2hb import PAPER_SIZES

    if cups_filter.shutil.which("gs") is None:
        pytest.skip("Ghostscript not installed")
    job = tmp_path / "job.ps"
    job.write_bytes(b"%!PS\nshowpage\n")
    proc = cups_filter.subprocess.Popen(
        cups_filter.build_gs_command(str(job), page_size),
        stdout=cups_filter.subprocess.PIPE,
        stderr=cups_filter.subprocess.DEVNULL,
    )
    try:
        header = proc.stdout.read(512)
    finally:
        proc.kill()
        proc.wait()
    fields = [line for line in header.split(b"\n")[:4] if not line.startswith(b"#")]
    width, height = (int(v) for v in fields[1].split())
    assert (width, height) == PAPER_SIZES[page_size]
