"""Compatibility shims so the driver also runs on Python 3.11 (Debian 12, Raspberry Pi OS)."""

try:
    from collections.abc import Buffer  # Python 3.12+
except ImportError:  # pragma: no cover - exercised on 3.11 only
    Buffer = bytes | bytearray | memoryview  # type: ignore[misc]

__all__ = ["Buffer"]
