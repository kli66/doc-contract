"""Portable, fail-closed document-contract resolver."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    from ._version import __version__
except ImportError:
    try:
        __version__ = version("doc-contracts")
    except PackageNotFoundError:
        __version__ = "0.0.0"
