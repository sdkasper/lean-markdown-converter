"""Smoke tests for the tkinter GUI layer (gui/app.py).

Wiring-only tests: widget construction, extension checkbox state, image
conversion toggle behavior, provider preset prefill, config round-trip,
and the on_start() validation/error paths. No real conversion runs here
(that is covered by tests/core/test_engine.py) and no real OS dialogs or
windows are ever shown - everything runs headless via root.withdraw() and
monkeypatched messagebox functions.

Guarded to skip cleanly on machines with no display (CI runners, etc.).
"""

import time

import pytest

tk = pytest.importorskip("tkinter")
from tkinter import TclError, messagebox  # noqa: E402

import gui.app as gui_app_module  # noqa: E402
from gui.app import FileConverterApp  # noqa: E402
from core.config import ConverterConfig, load_config as core_load_config  # noqa: E402
from core.constants import EXT_GROUPS  # noqa: E402
from core.llm_factory import LLMConfigError  # noqa: E402


# ─── FIXTURES ───────────────────────────────────────────────────────────────

@pytest.fixture
def tk_root():
    # Rapid create/destroy of Tk roots across tests can hit a transient
    # TclError on some Windows setups (the Tcl interpreter's internal
    # cleanup from the previous root races the next Tk() call). Retry a
    # couple of times before concluding there is genuinely no display.
    root = None
    last_err = None
    for _ in range(3):
        try:
            root = tk.Tk()
            break
        except TclError as e:
            last_err = e
            time.sleep(0.05)
    if root is None:
        pytest.skip(f"no display available: {last_err}")
    root.withdraw()
    yield root
    try:
        root.update_idletasks()
        root.destroy()
    except TclError:
        pass


@pytest.fixture(autouse=True)
def _stable_binaries(monkeypatch):
    """Deterministic binary discovery regardless of the dev machine's setup."""
    monkeypatch.setattr(gui_app_module, "write_startup_diagnostic", lambda: None)
    monkeypatch.setattr(gui_app_module, "configure_pydub", lambda: True)
    monkeypatch.setattr(gui_app_module, "audio_available", lambda: True)
    monkeypatch.setattr(gui_app_module, "exiftool_available", lambda: True)


@pytest.fixture(autouse=True)
def _no_real_dialogs(monkeypatch):
    """Never let a test pop a real blocking OS dialog."""
    monkeypatch.setattr(messagebox, "showerror", lambda *a, **k: None)
    monkeypatch.setattr(messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(messagebox, "showwarning", lambda *a, **k: None)
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)


@pytest.fixture
def app(tk_root, monkeypatch):
    """A FileConverterApp with a blank in-memory config (no real config file touched)."""
    monkeypatch.setattr(gui_app_module, "load_config", lambda: ConverterConfig())
    return FileConverterApp(tk_root)


# ─── TESTS ──────────────────────────────────────────────────────────────────

def test_app_constructs_without_error(app):
    assert isinstance(app, FileConverterApp)
    assert app.root.title() != ""


def test_extension_vars_match_ext_groups(app):
    expected = {ext for exts in EXT_GROUPS.values() for ext in exts}
    assert set(app.ext_vars.keys()) == expected


def test_select_all_toggles_all_vars(app):
    app.select_all_var.set(True)
    app.toggle_all()
    assert all(var.get() for var in app.ext_vars.values())

    app.select_all_var.set(False)
    app.toggle_all()
    assert not any(var.get() for var in app.ext_vars.values())


def test_group_toggle_flips_members(app):
    group = "Documents"
    members = EXT_GROUPS[group]

    app.group_all_vars[group].set(True)
    app._toggle_group(group)
    assert all(app.ext_vars[ext].get() for ext in members)

    app.group_all_vars[group].set(False)
    app._toggle_group(group)
    assert not any(app.ext_vars[ext].get() for ext in members)


def test_image_master_toggle_disables_without_unchecking(app):
    app.ext_vars[".jpg"].set(True)

    app.image_conversion_enabled.set(False)
    app._on_image_toggle()
    assert str(app.ext_widgets[".jpg"].cget("state")) == "disabled"
    assert app.ext_vars[".jpg"].get() is True  # never unchecked

    app.image_conversion_enabled.set(True)
    app._on_image_toggle()
    assert str(app.ext_widgets[".jpg"].cget("state")) == "normal"
    assert app.ext_vars[".jpg"].get() is True


def test_provider_switch_prefills_ollama(app):
    app.image_conversion_enabled.set(True)
    app.image_mode.set("ocr")
    app._on_mode_change()

    app.image_provider.set("ollama")
    app._on_provider_change()

    assert app.image_base_url.get() == "http://localhost:11434/v1"
    assert app.image_model.get() == "glm-ocr"


def test_config_round_trip(app, tmp_path):
    app.input_var.set(str(tmp_path / "in"))
    app.output_var.set(str(tmp_path / "out"))
    for ext, var in app.ext_vars.items():
        var.set(ext == ".pdf")
    app.force_convert.set(True)
    app.enable_logging.set(False)
    app.dry_run.set(True)
    app.image_conversion_enabled.set(True)
    app.image_mode.set("ocr")
    app.image_provider.set("gemini")
    app.image_api_key.set("secret-key")
    app.image_model.set("gemini-flash-latest")
    app.image_base_url.set("https://example.invalid/")

    cfg_path = tmp_path / "roundtrip_config.json"
    app._save_config(cfg_path)

    loaded = core_load_config(cfg_path)
    assert loaded.input_folder == str(tmp_path / "in")
    assert loaded.output_folder == str(tmp_path / "out")
    assert loaded.extensions.get(".pdf") is True
    assert loaded.extensions.get(".docx") is False
    assert loaded.force is True
    assert loaded.logging is False
    assert loaded.dry_run is True
    assert loaded.image_conversion["enabled"] is True
    assert loaded.image_conversion["mode"] == "ocr"
    assert loaded.image_conversion["api_key"] == "secret-key"


def test_start_with_nonexistent_input_shows_error(app, tmp_path, monkeypatch):
    errors = []
    monkeypatch.setattr(messagebox, "showerror", lambda title, msg: errors.append((title, msg)))

    class _ThreadShouldNotSpawn:
        def __init__(self, *a, **k):
            raise AssertionError("worker thread should not be spawned")

    monkeypatch.setattr(gui_app_module.threading, "Thread", _ThreadShouldNotSpawn)

    app.input_var.set(str(tmp_path / "does-not-exist"))
    app.on_start()

    assert errors, "showerror should have been called for a missing input folder"


def test_dry_run_does_not_write_files(app, tmp_path, monkeypatch):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "a.csv").write_text("col1,col2\n1,2\n", encoding="utf-8")
    output_dir = tmp_path / "out"

    app.input_var.set(str(input_dir))
    app.output_var.set(str(output_dir))
    for ext, var in app.ext_vars.items():
        var.set(ext == ".csv")
    app.dry_run.set(True)

    infos = []
    monkeypatch.setattr(messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))

    class _ThreadShouldNotSpawn:
        def __init__(self, *a, **k):
            raise AssertionError("worker thread should not be spawned during a dry run")

    monkeypatch.setattr(gui_app_module.threading, "Thread", _ThreadShouldNotSpawn)

    app.on_start()

    assert infos, "dry run summary dialog should have been shown"
    assert not list(output_dir.rglob("*.md"))


def test_llm_config_error_shows_error_and_reenables_start(app, tmp_path, monkeypatch):
    input_dir = tmp_path / "in2"
    input_dir.mkdir()
    (input_dir / "a.csv").write_text("col1,col2\n1,2\n", encoding="utf-8")
    output_dir = tmp_path / "out2"

    app.input_var.set(str(input_dir))
    app.output_var.set(str(output_dir))
    for ext, var in app.ext_vars.items():
        var.set(ext == ".csv")
    app.dry_run.set(False)

    def _boom(image_conversion):
        raise LLMConfigError("simulated LLM config failure")

    monkeypatch.setattr(gui_app_module, "build_markitdown", _boom)

    errors = []
    monkeypatch.setattr(messagebox, "showerror", lambda title, msg: errors.append((title, msg)))

    app.on_start()

    assert errors, "showerror should have been called for an LLMConfigError"
    assert str(app.start_btn.cget("state")) == "normal"
