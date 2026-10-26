"""Byte identity with Brother's HL-3040CN filter, for every reference capture.

Each capture in tests/fixtures/manifest.tsv is Brother's brhl3040cnfilter
output for a generated page (or a '+'-joined multi-page job) and an rc
file. The driver renders the same input with the same rc file and must
produce the same bytes; the PRINTLOG timestamp is frozen to the capture's.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from capture_pages import FIXTURES_DIR, MANIFEST, PAPER, ppm_bytes, rc_text
from fixture_utils import (
    assert_bytes_equal,
    assert_matches_capture,
    freeze_printlog,
    mask_printlog,
    read_capture,
    render_capture,
)

_CLI = Path(__file__).resolve().parent.parent / "src" / "cli.py"


def test_manifest_covers_every_capture():
    fixtures = {p.name.removesuffix(".xl2hb.zst") for p in FIXTURES_DIR.glob("*.xl2hb.zst")}
    assert fixtures == set(MANIFEST)
    assert len(MANIFEST) == 99


def test_manifest_page_sizes_are_paperinfij2_sizes():
    sizes = {c.overrides.get("PageSize", "A4") for c in MANIFEST.values()}
    assert sizes == set(PAPER)


@pytest.mark.parametrize("name", list(MANIFEST))
def test_matches_brother_capture(name, tmp_path, monkeypatch):
    """Same input and rc file as the capture -> the same bytes as brhl3040cnfilter."""
    freeze_printlog(monkeypatch, name)
    assert_bytes_equal(render_capture(name, tmp_path), read_capture(name), name)


def _run_cli(name: str, tmp_path: Path) -> bytes:
    rc = tmp_path / "brhl3040cnrc"
    rc.write_text(rc_text(MANIFEST[name].overrides))
    stdin = b"".join(ppm_bytes(page) for page in MANIFEST[name].pages)
    proc = subprocess.run([sys.executable, str(_CLI), "--rc", str(rc)], input=stdin, capture_output=True, check=True)
    return proc.stdout


@pytest.mark.parametrize(
    "name",
    ["multi3", "multi3_mono", "multi2_reverse", "multi2_copies2", "multi2_copies2_collate", "mono_ramp"],
)
def test_cli_matches_brother_capture(name, tmp_path):
    """The CLI reads every PPM page on stdin into one job, like Brother's filter."""
    assert_matches_capture(name, _run_cli(name, tmp_path))


def test_cli_without_input_fails(tmp_path):
    proc = subprocess.run([sys.executable, str(_CLI)], input=b"", capture_output=True, check=False)
    assert proc.returncode == 1
    assert b"No PPM data" in proc.stderr
    assert proc.stdout == b""


def test_masked_timestamp_differs_only_in_printlog():
    """Captures differ only in PRINTLOG item 2 once it is masked (sanity check of the masking)."""
    a, b = read_capture("mixed_baseline"), read_capture("mixed_fullcolor")
    assert a != b
    assert mask_printlog(a) == mask_printlog(b)
