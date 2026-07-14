"""Thin entry point for the Lean Markdown Converter GUI (PyInstaller target).

No business logic here - just Tk root creation, FileConverterApp wiring,
and mainloop. Keep this file minimal since PyInstaller uses it as the
build entry point.

--selftest mode: runs the frozen-bundle diagnostic (LLM client construction
per provider, markitdown/magika imports) and writes selftest_report.json
next to the config dir, exiting 0/1. Exists because the v1.1.0 frozen
builds failed exactly at LLM client construction, which was only
detectable by hand-clicking the GUI; this makes it machine-checkable.
"""

import multiprocessing
import sys


def run_selftest() -> int:
    """Exercise the failure-prone construction paths inside the (possibly
    frozen) bundle and write a JSON report. Returns process exit code."""
    import json
    import time
    from pathlib import Path

    started = time.time()
    checks = {}

    def check(name, fn):
        try:
            fn()
            checks[name] = "PASS"
        except Exception as e:
            import traceback
            checks[name] = f"FAIL: {type(e).__name__}: {e}\n{traceback.format_exc()}"

    check("import_markitdown", lambda: __import__("markitdown"))
    check("import_magika", lambda: __import__("magika"))
    check("import_openai", lambda: __import__("openai"))
    check("markitdown_plain_construct", lambda: __import__("markitdown").MarkItDown())

    from core.llm_factory import build_markitdown

    def ocr(provider, key="selftest-dummy-key"):
        md = build_markitdown({
            "enabled": True, "mode": "ocr", "provider": provider,
            "api_key": key, "model": "", "base_url": "",
        })
        assert md._llm_client is not None

    check("ocr_construct_gemini", lambda: ocr("gemini"))
    check("ocr_construct_ollama", lambda: ocr("ollama", ""))
    check("exif_construct", lambda: build_markitdown({"enabled": True, "mode": "exif"}))

    from core.binaries import write_startup_diagnostic
    check("startup_diagnostic", write_startup_diagnostic)

    from core.constants import VERSION
    from core.paths import app_data_dir, is_frozen
    report = {
        "version": VERSION,
        "frozen": is_frozen(),
        "duration_seconds": round(time.time() - started, 2),
        "checks": checks,
    }
    report_path = Path(app_data_dir()) / "selftest_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if all(v == "PASS" for v in checks.values()) else 1


def main():
    multiprocessing.freeze_support()

    if "--selftest" in sys.argv:
        sys.exit(run_selftest())

    import tkinter as tk
    from gui.app import FileConverterApp

    root = tk.Tk()
    FileConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
