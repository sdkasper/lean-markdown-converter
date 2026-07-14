"""Lean Markdown Converter — shared core package.

All conversion logic, config I/O, path safety, binary discovery, and LLM
client construction lives here. The gui/ and cli/ packages are thin
presentation layers over these modules.
"""

from core.constants import APP_NAME, VERSION

__all__ = ["APP_NAME", "VERSION"]
