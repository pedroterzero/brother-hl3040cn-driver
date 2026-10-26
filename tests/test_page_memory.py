"""A job holds at most one whole-page buffer at a time.

A4 pages are ~100 MB of RGB; on a Raspberry Pi 3 (1 GB) every extra page
that stays referenced counts. Pages are handed over as whole buffers when
they are flipped (BRReverse) or repeated (Copies without Collate), so the
pipeline must drop each page before the next one is read.
"""

import gc
import io
import weakref
from collections.abc import Iterator

import numpy as np
import pytest

from pipeline import chain_peeked, filter_pages
from settings import PrintSettings

W, H = 64, 48


class _Page(np.ndarray):
    """ndarray subclass, so that the test can hold weak references to pages."""


def _pages(count: int, alive: list, blank: frozenset[int] = frozenset()) -> Iterator[tuple[int, int, np.ndarray]]:
    """Yield `count` pages, those in `blank` pure white; before each one, check the previous pages are gone."""
    for i in range(count):
        gc.collect()
        assert all(ref() is None for ref in alive), f"page {len(alive)} still referenced while reading page {i + 1}"
        page = np.full((H, W * 3), 255, np.uint8).view(_Page)
        if i not in blank:
            page[10:20] = i * 20
        alive.append(weakref.ref(page))
        yield W, H, page
        del page


@pytest.mark.parametrize("copies", [1, 2])
@pytest.mark.parametrize("reverse", [False, True])
def test_previous_page_is_released_before_the_next_is_read(copies, reverse):
    alive: list = []
    settings = PrintSettings(copies=copies, reverse=reverse)
    pages = _pages(5, alive, blank=frozenset({1, 2}))
    first = next(pages)
    pages = chain_peeked(first, pages)
    del first
    filter_pages(pages, settings, io.BytesIO())
    assert len(alive) == 5
