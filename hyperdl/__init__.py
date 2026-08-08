"""Hyper Downloader - pacote principal."""

APP_NAME = "Hyper Downloader"
__version__ = "4.1.0"

from hyperdl.core import downloader, splitter  # noqa: E402

__all__ = ["downloader", "splitter", "APP_NAME", "__version__"]
