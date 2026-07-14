"""Thin entry point for the Lean Markdown Converter GUI (PyInstaller target).

No business logic here - just Tk root creation, FileConverterApp wiring,
and mainloop. Keep this file minimal since PyInstaller uses it as the
build entry point.
"""

import multiprocessing
import tkinter as tk

from gui.app import FileConverterApp


def main():
    multiprocessing.freeze_support()
    root = tk.Tk()
    FileConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
