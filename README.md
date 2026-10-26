# Brother HL-3040CN Driver

[![CI](https://github.com/pedroterzero/brother-hl3040cn-driver/actions/workflows/ci.yml/badge.svg)](https://github.com/pedroterzero/brother-hl3040cn-driver/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](LICENSE)

Open-source CUPS driver for the Brother HL-3040CN color laser printer.
Written in Python with optional Cython acceleration, runs anywhere CUPS
does, including ARM (Raspberry Pi). Brother only ships an i386 binary
filter for this printer.

This is a fork of [cl445/brother-hl4150cdn-driver](https://github.com/cl445/brother-hl4150cdn-driver)
by Claas Flint, the driver for the HL-4150CDN. Both printers speak
Brother's XL2HB language and Brother's filters for them share most of
their code; the fork changes what the HL-3040CN filter does differently
(see [What differs from the HL-4150CDN](#what-differs-from-the-hl-4150cdn)).
Almost everything else, including the Fine mode codec and the native
band kernels, is upstream's work.

## Status

The output is byte-identical to Brother's own filter (`brhl3040cnfilter`
from `hl3040cnlpr-1.1.2-1`) for all 99 reference captures in
`tests/fixtures/`, apart from the job time Brother's filter writes into
`@PJL PRINTLOG ITEM = 2`. The captures cover:

- Normal (600 dpi) and Fine (600x2400 dpi, 10 captures) resolution;
- all 22 paper sizes of the PPD;
- colour matching Normal, Vivid and None, improve gray, enhance black,
  toner save, brightness, contrast, saturation and the RGB keys, alone
  and combined;
- grayscale (`Mono`), `Auto` and `Color`;
- all media types and the three paper sources;
- copies with and without collation, reverse print and multi-page jobs.

The CUPS filter, the CLI, the pure-Python code and the Cython modules all
produce the same bytes. An earlier build of this port with the same
output is in daily use on an HL-3040CN.

## Requirements

- Python 3.11+ (Debian 12 and Raspberry Pi OS ship 3.11)
- Ghostscript (the CUPS pipeline rasterizes PostScript to PPM)
- CUPS
- `curl` and `ar` (Debian: `binutils`) for `scripts/extract_blobs.sh`
- Optional, for speed: a C compiler and the Python headers (Debian:
  `sudo apt install build-essential python3-dev`). `install.sh` then
  builds the Cython modules (RLE encoders, colour lookup, dither, the
  Fine codec and band renderers that use several cores); without them
  the driver falls back to pure Python, which is several times slower
  (Fine mode about 30 times).
- About 260 MB of disk space for the precomputed inverse colour LUTs
  (Normal and Vivid colour matching, each with and without improve gray;
  64 MiB each). `install.sh` computes them, which takes a few minutes on
  a Raspberry Pi. Their file names carry a hash of the colour grids they
  were computed from, so re-run `install.sh` after `extract_blobs.sh`;
  until then the filter ignores LUTs built from other grids and
  interpolates.
- Linux. `install.sh` refuses to run on macOS, where the CUPS filter and
  PPD directories are on the SIP-protected system volume.
- Brother's HL-3040CN LPR driver package. `scripts/extract_blobs.sh`
  downloads `hl3040cnlpr-1.1.2-1.i386.deb` from Brother, checks its MD5
  and copies the printer's calibration tables into `src/lut/` and
  `src/color_data/`. They are not part of this repository.

## Install

```bash
git clone https://github.com/pedroterzero/brother-hl3040cn-driver.git
cd brother-hl3040cn-driver

./scripts/extract_blobs.sh
sudo cups/install.sh --add-printer socket://<printer-ip>:9100
```

`install.sh` puts the driver into `/usr/local/lib/brhl3040cn/` with its
own virtual environment (NumPy from PyPI), installs the CUPS filter
`brhl3040cn-filter` and `brhl3040cn.ppd`, and with `--add-printer` creates
the queue `Brother_HL-3040CN`. Without `--add-printer` it only installs
the filter and PPD.

Pick the device URI that matches how the printer is attached:

| Connection | URI | Discover |
|---|---|---|
| Ethernet / Wi-Fi | `socket://<printer-ip>:9100` | the printer's network settings page |
| USB | the `usb://Brother/...` URI CUPS lists | `lpinfo --include-schemes usb -l -v` |

To register the queue by hand:

```bash
sudo lpadmin -p Brother_HL-3040CN -E \
  -v <device-uri> \
  -P /usr/share/cups/model/brhl3040cn.ppd
```

`sudo cups/uninstall.sh --remove-printer` cleans up.

### Sharing the printer (AirPrint)

To print from phones, tablets and other computers on the network, let
CUPS share the queue. With Avahi running, CUPS advertises shared queues
over DNS-SD, and iOS, iPadOS and macOS see them as AirPrint printers:

```bash
sudo cupsctl --share-printers
sudo lpadmin -p Brother_HL-3040CN -o printer-is-shared=true
```

### Upgrading

Pull, then re-run `./scripts/extract_blobs.sh` and `sudo cups/install.sh`.
Existing queues keep their old copy of the PPD; to pick up new options,
re-assign it. This resets the queue's default options:

```bash
sudo lpadmin -p Brother_HL-3040CN -P /usr/share/cups/model/brhl3040cn.ppd
```

## Settings

All options are PPD-driven and surfaced in the standard print dialog.
Pass them as `-o key=value` to `lp` / `lpr` for scripting.

| Option | Values | Notes |
|---|---|---|
| `PageSize` | A4 (default), Letter, Legal, Executive, A5, PRA5Rotated (A5 long edge), A6, ISOB5, ISOB6, JISB5, JISB6, EnvDL, EnvC5, Env10 (Com-10), EnvMonarch, Br3x5 (3 x 5), BrA4Long (A4 Long), FanFoldGermanLegal (Folio), EnvPRC5Rotated (DL long edge), Postcard (Hagaki), EnvYou4 (Envelope #4), EnvChou3 (Envelope MAX) | The whole sheet is rendered, at the size of Brother's paper table |
| `BRInputSlot` | AutoSelect, Tray1, Manual | |
| `BRResolution` | 600dpi (Normal), 600x2400dpi (Fine) | |
| `BRMonoColor` | Auto, FullColor (Color), Mono | Auto sends colour pages and lets the printer decide |
| `BRMediaType` | Plain, Thin, Thick, Thicker, Bond, Envelope, EnvThin, EnvThick, Recycled, Postcard, Label | |
| `BRColorMatching` | Normal, Vivid, None | Each selects its own colour tables |
| `BRGray` | OFF, ON (default) | Improve gray: the ImpGray colour tables |
| `BREnhanceBlkPrt` | OFF, ON | Enhance black: rich black for pure black |
| `BRTonerSaveMode` | OFF, ON | Toner-save dither tables |
| `BRReverse` | OFF, ON | Reverse print: every page is turned by 180 degrees; the page order is kept |
| `BRImproveOutput` | OFF, BRLessPaperCurl, BRFixIntensity | Reduce paper curl, improve toner fixing |
| `BRBrightness` | -20 … 20 | |
| `BRContrast` | -20 … 20 | |
| `BRRed`, `BRGreen`, `BRBlue` | -20 … 20 | Per-channel input shift |
| `BRSaturation` | -20 … 20 | |

Copies come from the standard `-n` / `copies` option; the PPD lets CUPS
make them (`cupsManualCopies`). The HL-3040CN has no duplex unit, no
second tray and no glossy media.

## CLI without CUPS

The CLI reads every PPM page on stdin into one job, like Brother's
filter, and reads Brother's rc file format (`--rc`, e.g. the
`brhl3040cnrc` from Brother's package). The pages must be rendered at
the paper table size (A4: 4958 x 6981 pixels at 600 dpi), as the CUPS
filter does with `gs -r600 -g4958x6981`.

```bash
# PPM in, XL2HB raw stream out
cat page.ppm | python3 src/brfilter.py --paper Letter --toner-save > page.xl2hb

# Send straight to the printer (network)
cat page.ppm | python3 src/brfilter.py | nc <printer-ip> 9100
```

## How correctness was established

Brother's `brhl3040cnfilter` was run natively on x86 (it is an i386
binary) inside a container without network access, on generated test
pages with an rc file for each combination of settings. Its output
streams are the reference captures in `tests/fixtures/`: `manifest.tsv`
lists the page and the rc settings of each, and `tests/capture_pages.py`
regenerates the pages. `tests/test_captures.py` renders every page with
the same rc file and compares the result with the capture byte for byte.

The calibration tables (colour grids, dither screens, the mono curve)
are Brother's and are never redistributed: `scripts/extract_blobs.sh`
takes them from Brother's own package on your machine.

### What differs from the HL-4150CDN

The two filters share the raster back end (band and plane buffers, all
RLE encoders, the Fine codec) and the colour code. The HL-3040CN filter
differs in:

- PJL: a job block after the UEL (`@PJL JOB NAME`, `PRINTLOG` items 1-4
  with the job time in UTC, `STRINGCODESET`, `LOGINUSER`) and an
  `@PJL EOJ` trailer.
- Geometry: Brother's paper table is the whole sheet, so the image
  starts at the sheet corner (`SetPageOrigin 0,0`), the width is rounded
  up to 32 pixels (Fine: 8) and the height is
  `h * 72 // 600 * 600 // 72`. A5 long edge and JIS B6 are sent as a
  custom media size in tenths of a millimetre; A4 Long is added.
- Options: trays Auto, Tray 1 and Manual; no duplex, glossy or skip
  blank. Bond is sent as Transparency. Without collation each page is
  repeated `Copies` times; the rc default `Copies=0` is sent as is.
  Reverse print sends every page bottom-up with the page marker that
  duplex models use for long-edge back sides; the printer prints it
  turned by 180 degrees.
- Colour: its own colour grids and dither screens (`_cache08`); Fine
  uses separate (CAPT) grids; toner save changes only the dither
  screens; grayscale goes through a tone curve instead of the identity.
- rc spellings `Color` and `PostCard`; an unknown `BRMonoColor` means
  Auto.

### Other models

Brother's Linux drivers for the HL-3045CN, HL-3070CW, HL-3075CW,
DCP-9010CN, MFC-9120CN and MFC-9320CW belong to the same filter family
as `brhl3040cnfilter`. This driver may work for them, possibly with their
own paper tables and calibration data, but none of them has been tested.

## Development

The development tools (`uv`, `nox`, `ruff`, `pyrefly`, `deptry`) are only
needed for working on the driver:

```bash
uv sync --all-extras
./scripts/extract_blobs.sh      # the tests need the calibration tables
uv run nox --list

# common sessions
uv run nox -s lint            # ruff
uv run nox -s format_check    # ruff format --check
uv run nox -s typecheck       # pyrefly
uv run nox -s deps            # deptry
uv run nox -s tests           # pytest on Python 3.11 and 3.13 (about 5200 tests)
```

The Cython modules are optional in development too; build them in place
with:

```bash
uv run --with cython,setuptools python setup_cython.py build_ext --inplace
```

The reference captures in `tests/fixtures/` are zstd-compressed XL2HB
streams from Brother's filter, listed in `tests/fixtures/manifest.tsv`;
pytest decompresses them on demand. To add one, add its page to
`tests/capture_pages.py`, capture Brother's output for it, save it as
`tests/fixtures/<name>.xl2hb.zst` and add a manifest line; the capture
tests pick it up.

### Comparing with Brother's filter

`scripts/fine_diff.py` renders a test page or job with both drivers and
diffs the XL2HB streams. It runs Brother's filter from the package that
`extract_blobs.sh` unpacked, in an i386 Docker container without
network:

```bash
uv run python scripts/fine_diff.py hramp --lines 64 --rc Brightness=-20
uv run python scripts/fine_diff.py edges --paper Letter --rc BRResolution=Normal
uv run python scripts/fine_diff.py bars --pages 3 --rc BRReverse=ON
```

`fine_diff.py` defaults to Fine mode on A4 and masks the PRINTLOG job
time. It prints `IDENTICAL` or the first differing byte; for a
single-page Fine job it also decodes Brother's scanlines and reports,
per plane, whether the dithered data or the encoder differs. Brother's
output is cached in `build/fine-diff-cache/`. Run it with `--help` for
the test patterns and options. Upstream's emulator and gdb tracer for
the Fine codec and dither (`native_codec.py`, `trace_dither.py`) work on
the HL-4150CDN binary and stay upstream.

## License

[GPL-3.0-or-later](LICENSE), as upstream. The PPD in `cups/` is derived
from Brother's GPL-2.0-or-later HL-4150CDN and HL-3040CN PPDs; see the
file header for attribution. The Brother calibration tables that
`extract_blobs.sh` pulls in remain under their own licence and never
enter this repository.

## Trademarks

Brother, HL-3040CN and HL-4150CDN are trademarks of Brother Industries,
Ltd. This project is an independent, community-driven driver and is not
affiliated with, endorsed by, or sponsored by Brother Industries, Ltd.
