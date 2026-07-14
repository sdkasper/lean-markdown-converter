"""Tkinter GUI for the Lean Markdown Converter.

Thin presentation layer over the shared ``core`` package: this module owns
only widget wiring, layout, and thread orchestration. All business logic
(file discovery, conversion, config I/O, binary discovery, LLM client
construction) lives in ``core`` and is called through, never duplicated.

Ported from the pre-2.0.0 ``gui/gui_converter.py`` widget tree (layout,
ttk Vista theme, debounce pattern, threading shape). Everything that used
to be inline logic in that file (module-level ffmpeg setup, _is_safe_path,
config I/O, the walk/convert loop, the broken Gemini adapter) has been
replaced with calls into ``core``.
"""

import subprocess
import threading
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core.binaries import (
    audio_available,
    configure_pydub,
    exiftool_available,
    write_startup_diagnostic,
)
from core.config import ConverterConfig, load_config, save_config
from core.constants import APP_NAME, AUDIO_EXTENSIONS, EXT_GROUPS, VERSION
from core.engine import run_conversion
from core.llm_factory import LLMConfigError, PROVIDER_PRESETS, build_markitdown
from core.logging_util import RunLogger, format_summary
from core.paths import logs_dir, resource_path
from core.scanner import collect_files, count_files


# ─── GUI APP ────────────────────────────────────────────────────────────────

class FileConverterApp:
    """Tkinter front end wiring widgets to the shared core conversion API."""

    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} v{VERSION}")
        self.root.minsize(640, 480)

        # Startup diagnostics + pydub wiring — once, at construction time.
        write_startup_diagnostic()
        configure_pydub()

        self.audio_ok = audio_available()
        self.exiftool_ok = exiftool_available()

        self.config = load_config()
        self._cancelled = False
        self._scan_gen = 0
        self._scan_after_id = None
        self._last_log_path = None
        self._run_logger = None

        self._set_icon()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Window setup ────────────────────────────────────────────────────────

    def _set_icon(self):
        """Best-effort window icon load. Never fatal if missing/unsupported."""
        try:
            icon_path = resource_path("resources/LeanProductivity.ico")
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
        except Exception:
            pass

    def _build_ui(self):
        # ── Theming ──────────────────────────────────────────────────────
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except Exception:
            pass
        self.root.configure(padx=10, pady=10)
        self.root.columnconfigure(1, weight=1)

        # ── Input folder ─────────────────────────────────────────────────
        ttk.Label(self.root, text="Input Folder:").grid(row=0, column=0, sticky="e", padx=5, pady=2)
        self.input_var = tk.StringVar(value=self.config.input_folder)
        ttk.Entry(self.root, textvariable=self.input_var, width=50).grid(row=0, column=1, sticky="ew")
        ttk.Button(self.root, text="Browse...", command=self.browse_input).grid(row=0, column=2, padx=(4, 0))
        self.input_info_label = ttk.Label(self.root, text="", foreground="gray")
        self.input_info_label.grid(row=1, column=1, sticky="w", padx=2)
        self.input_var.trace_add("write", self._schedule_scan)

        # ── Output folder ────────────────────────────────────────────────
        ttk.Label(self.root, text="Output Folder:").grid(row=2, column=0, sticky="e", padx=5, pady=(8, 2))
        self.output_var = tk.StringVar(value=self.config.output_folder)
        out_entry = ttk.Entry(self.root, textvariable=self.output_var, width=50)
        out_entry.grid(row=2, column=1, sticky="ew", pady=(8, 2))
        out_entry.bind("<FocusOut>", self._validate_output_path)
        ttk.Button(self.root, text="Browse...", command=self.browse_output).grid(row=2, column=2, padx=(4, 0), pady=(8, 2))
        self.output_warn_label = ttk.Label(self.root, text="", foreground="blue")
        self.output_warn_label.grid(row=3, column=1, sticky="w", padx=2)
        self._validate_output_path()

        # ── Extensions ───────────────────────────────────────────────────
        self.select_all_var = tk.BooleanVar(value=False)
        self.ext_vars = {}
        self.group_all_vars = {}
        self.ext_widgets = {}       # ext -> Checkbutton widget (grey-out targets)
        self.group_all_widgets = {}  # group name -> Checkbutton widget
        ttk.Label(self.root, text="File Types:").grid(row=4, column=0, sticky="ne", padx=5, pady=(10, 0))
        ext_frame = ttk.Frame(self.root)
        ext_frame.grid(row=4, column=1, columnspan=2, sticky="w", pady=(10, 0))

        ttk.Checkbutton(ext_frame, text="Select All", variable=self.select_all_var,
                        command=self.toggle_all).grid(row=0, column=0, sticky="w", columnspan=2)

        default_exts = self.config.extensions
        row_offset = 1
        for group_name, exts in EXT_GROUPS.items():
            grp_var = tk.BooleanVar(value=False)
            self.group_all_vars[group_name] = grp_var
            grp_chk = ttk.Checkbutton(ext_frame, text=group_name, variable=grp_var,
                                       command=lambda g=group_name: self._toggle_group(g))
            grp_chk.grid(row=row_offset, column=0, sticky="w", padx=(0, 8))
            self.group_all_widgets[group_name] = grp_chk

            col = 1
            for ext in exts:
                var = tk.BooleanVar(value=default_exts.get(ext, False))
                var.trace_add("write", self._schedule_scan)
                self.ext_vars[ext] = var
                ext_chk = ttk.Checkbutton(ext_frame, text=ext, variable=var)
                ext_chk.grid(row=row_offset, column=col, sticky="w", padx=2)
                self.ext_widgets[ext] = ext_chk
                col += 1
            row_offset += 1

        # Audio availability warning (greys out the whole group, non-toggleable).
        self.audio_warning_label = ttk.Label(
            ext_frame,
            text="ffmpeg/ffprobe not found - audio conversion unavailable",
            foreground="#b8860b", wraplength=480, justify="left")
        self.audio_warning_label.grid(row=row_offset, column=0, columnspan=6, sticky="w", pady=(4, 0))
        if not self.audio_ok:
            for ext in AUDIO_EXTENSIONS:
                widget = self.ext_widgets.get(ext)
                if widget is not None:
                    widget.config(state="disabled")
            audio_group_widget = self.group_all_widgets.get("Audio")
            if audio_group_widget is not None:
                audio_group_widget.config(state="disabled")
        else:
            self.audio_warning_label.grid_remove()

        # ── Image Conversion ─────────────────────────────────────────────
        img_cfg = self.config.image_conversion
        self.image_conversion_enabled = tk.BooleanVar(value=img_cfg.get("enabled", False))
        self.image_mode = tk.StringVar(value=img_cfg.get("mode", "exif"))
        self.image_provider = tk.StringVar(value=img_cfg.get("provider", "gemini"))
        self.image_api_key = tk.StringVar(value=img_cfg.get("api_key", ""))
        self.image_model = tk.StringVar(value=img_cfg.get("model", "gemini-flash-latest"))
        self.image_base_url = tk.StringVar(value=img_cfg.get("base_url", ""))

        img_frame = ttk.LabelFrame(self.root, text="Image Conversion")
        img_frame.grid(row=5, column=0, columnspan=3, sticky="ew", padx=5, pady=(10, 0))
        img_frame.columnconfigure(1, weight=1)

        self.image_enable_chk = ttk.Checkbutton(
            img_frame, text="Enable image conversion (.jpg/.jpeg/.png)",
            variable=self.image_conversion_enabled, command=self._on_image_toggle)
        self.image_enable_chk.grid(row=0, column=0, columnspan=3, sticky="w", padx=5, pady=(4, 2))

        mode_frame = ttk.Frame(img_frame)
        mode_frame.grid(row=1, column=0, columnspan=3, sticky="w", padx=5)
        self.image_mode_exif_radio = ttk.Radiobutton(
            mode_frame, text="EXIF metadata only", variable=self.image_mode,
            value="exif", command=self._on_mode_change)
        self.image_mode_exif_radio.pack(side="left", padx=(0, 10))
        self.image_mode_ocr_radio = ttk.Radiobutton(
            mode_frame, text="Full OCR / description (needs an LLM)", variable=self.image_mode,
            value="ocr", command=self._on_mode_change)
        self.image_mode_ocr_radio.pack(side="left")

        ttk.Label(img_frame, text="Provider:").grid(row=2, column=0, sticky="e", padx=5, pady=2)
        self.image_provider_combo = ttk.Combobox(
            img_frame, textvariable=self.image_provider, values=tuple(PROVIDER_PRESETS.keys()),
            state="readonly", width=15)
        self.image_provider_combo.grid(row=2, column=1, sticky="w", padx=5, pady=2)
        self.image_provider_combo.bind("<<ComboboxSelected>>", self._on_provider_change)

        ttk.Label(img_frame, text="API Key:").grid(row=3, column=0, sticky="e", padx=5, pady=2)
        self.image_api_key_entry = ttk.Entry(img_frame, textvariable=self.image_api_key, show="*", width=40)
        self.image_api_key_entry.grid(row=3, column=1, columnspan=2, sticky="ew", padx=5, pady=2)

        ttk.Label(img_frame, text="Model:").grid(row=4, column=0, sticky="e", padx=5, pady=2)
        self.image_model_entry = ttk.Entry(img_frame, textvariable=self.image_model, width=40)
        self.image_model_entry.grid(row=4, column=1, columnspan=2, sticky="ew", padx=5, pady=2)

        ttk.Label(img_frame, text="Base URL:").grid(row=5, column=0, sticky="e", padx=5, pady=2)
        self.image_base_url_entry = ttk.Entry(img_frame, textvariable=self.image_base_url, width=40)
        self.image_base_url_entry.grid(row=5, column=1, columnspan=2, sticky="ew", padx=5, pady=2)

        self.image_exiftool_warning = ttk.Label(
            img_frame,
            text="exiftool not found - EXIF extraction will produce empty output",
            foreground="#b8860b", wraplength=480, justify="left")
        self.image_exiftool_warning.grid(row=6, column=0, columnspan=3, sticky="w", padx=5, pady=(2, 4))
        self.image_exiftool_warning.grid_remove()

        self._on_image_toggle()

        # ── Options ──────────────────────────────────────────────────────
        self.force_convert = tk.BooleanVar(value=self.config.force)
        self.enable_logging = tk.BooleanVar(value=self.config.logging)
        self.dry_run = tk.BooleanVar(value=self.config.dry_run)
        opt_frame = ttk.Frame(self.root)
        opt_frame.grid(row=6, column=1, sticky="w", pady=(10, 0))
        ttk.Checkbutton(opt_frame, text="Force convert all files", variable=self.force_convert).pack(anchor="w")
        ttk.Checkbutton(opt_frame, text="Enable logging to file", variable=self.enable_logging).pack(anchor="w")
        ttk.Checkbutton(opt_frame, text="Dry run only", variable=self.dry_run).pack(anchor="w")

        # ── Progress ─────────────────────────────────────────────────────
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_frame = ttk.Frame(self.root)
        self.progress_frame.grid(row=7, column=0, columnspan=3, pady=(10, 0), padx=10, sticky="ew")
        self.progress_bar = ttk.Progressbar(self.progress_frame, maximum=100,
                                             variable=self.progress_var, length=500)
        self.progress_bar.pack(side="left", fill="x", expand=True)
        self.progress_label = ttk.Label(self.progress_frame, text="", width=10, anchor="e")
        self.progress_label.pack(side="left", padx=(6, 0))
        self.progress_frame.grid_remove()

        # ── Status ───────────────────────────────────────────────────────
        self.status_label = ttk.Label(self.root, text="", foreground="gray")
        self.status_label.grid(row=8, column=0, columnspan=2, sticky="w", padx=5, pady=(4, 0))
        self.view_log_btn = ttk.Button(self.root, text="View Log", command=self._open_log)
        self.view_log_btn.grid(row=8, column=2, sticky="e", padx=(4, 0), pady=(4, 0))
        self.view_log_btn.grid_remove()

        # ── Buttons ──────────────────────────────────────────────────────
        btn_frame = ttk.Frame(self.root)
        btn_frame.grid(row=9, column=1, pady=15)
        self.start_btn = ttk.Button(btn_frame, text="Start Conversion", command=self.on_start)
        self.start_btn.pack(side="left", padx=5)
        self.cancel_btn = ttk.Button(btn_frame, text="Cancel", command=self.cancel)
        self.cancel_btn.pack(side="left", padx=5)

        if self.input_var.get():
            self._schedule_scan()

    # ── Debounced live file count ────────────────────────────────────────────

    def _schedule_scan(self, *_):
        """Debounce file count scan on input path or extension change."""
        if self._scan_after_id:
            self.root.after_cancel(self._scan_after_id)
        self._scan_after_id = self.root.after(400, self._validate_and_scan_input)

    def _validate_and_scan_input(self):
        """Check input path exists and scan file count on a background thread."""
        p = Path(self.input_var.get())
        if not p.is_dir():
            self.input_info_label.config(text="Path not found", foreground="red")
            return
        self.input_info_label.config(text="Scanning...", foreground="gray")
        self._scan_gen += 1
        gen = self._scan_gen
        exts = {e for e, v in self.ext_vars.items() if v.get()}

        def _scan():
            count = count_files(p, exts)
            self.root.after(0, lambda: self._apply_scan_result(count, gen))

        threading.Thread(target=_scan, daemon=True).start()

    def _apply_scan_result(self, count, gen):
        """Update the file count label only if this scan is still current."""
        if gen != self._scan_gen:
            return
        txt = f"{count} file{'s' if count != 1 else ''} found"
        self.input_info_label.config(text=txt, foreground="green" if count > 0 else "orange")

    def _validate_output_path(self, *_):
        """Show a hint label when the output path doesn't exist yet."""
        p = Path(self.output_var.get())
        if self.output_var.get() and not p.is_dir():
            self.output_warn_label.config(text="Will be created", foreground="blue")
        else:
            self.output_warn_label.config(text="")

    # ── Extension checkbox helpers ───────────────────────────────────────────

    def toggle_all(self):
        val = self.select_all_var.get()
        for var in self.ext_vars.values():
            var.set(val)
        for var in self.group_all_vars.values():
            var.set(val)

    def _toggle_group(self, group_name):
        val = self.group_all_vars[group_name].get()
        for ext in EXT_GROUPS[group_name]:
            self.ext_vars[ext].set(val)

    # ── Image conversion panel ───────────────────────────────────────────────

    def _on_image_toggle(self):
        """Master toggle: grey out (but never uncheck) the .jpg/.jpeg/.png
        checkboxes and the Images group checkbox based on the master switch.
        """
        enabled = self.image_conversion_enabled.get()
        ext_state = "normal" if enabled else "disabled"

        for ext in (".jpg", ".jpeg", ".png"):
            widget = self.ext_widgets.get(ext)
            if widget is not None:
                widget.config(state=ext_state)
        images_group_widget = self.group_all_widgets.get("Images")
        if images_group_widget is not None:
            images_group_widget.config(state=ext_state)

        self.image_mode_exif_radio.config(state=ext_state)
        self.image_mode_ocr_radio.config(state=ext_state)

        self._on_mode_change()

    def _on_mode_change(self):
        """Enable OCR provider/key/model/url fields only in active OCR mode;
        refresh the exiftool warning visibility for EXIF mode.
        """
        enabled = self.image_conversion_enabled.get()
        is_ocr = self.image_mode.get() == "ocr"
        ocr_active = enabled and is_ocr

        self.image_provider_combo.config(state=("readonly" if ocr_active else "disabled"))
        if ocr_active:
            self._on_provider_change()
        else:
            self.image_api_key_entry.config(state="disabled")
            self.image_model_entry.config(state="disabled")
            self.image_base_url_entry.config(state="disabled")

        show_warning = enabled and not is_ocr and not self.exiftool_ok
        if show_warning:
            self.image_exiftool_warning.grid()
        else:
            self.image_exiftool_warning.grid_remove()

    def _on_provider_change(self, *_):
        """Prefill model/base_url from PROVIDER_PRESETS on provider switch and
        toggle the api_key/model/base_url widget states accordingly.
        """
        provider = self.image_provider.get()
        preset = PROVIDER_PRESETS.get(provider, PROVIDER_PRESETS["gemini"])
        self.image_base_url.set(preset["base_url"])
        self.image_model.set(preset["model"])

        enabled = self.image_conversion_enabled.get()
        ocr_active = enabled and self.image_mode.get() == "ocr"

        self.image_api_key_entry.config(state=("normal" if (ocr_active and preset["needs_key"]) else "disabled"))
        self.image_model_entry.config(state=("normal" if ocr_active else "disabled"))
        self.image_base_url_entry.config(state=("normal" if ocr_active else "disabled"))

    def _current_image_conversion_dict(self) -> dict:
        return {
            "enabled": self.image_conversion_enabled.get(),
            "mode": self.image_mode.get(),
            "provider": self.image_provider.get(),
            "api_key": self.image_api_key.get(),
            "model": self.image_model.get(),
            "base_url": self.image_base_url.get(),
        }

    # ── Config persistence ───────────────────────────────────────────────────

    def browse_input(self):
        path = filedialog.askdirectory()
        if path:
            self.input_var.set(path)

    def browse_output(self):
        path = filedialog.askdirectory()
        if path:
            self.output_var.set(path)
            self._validate_output_path()

    def _build_config(self) -> ConverterConfig:
        return ConverterConfig(
            input_folder=self.input_var.get(),
            output_folder=self.output_var.get(),
            extensions={ext: var.get() for ext, var in self.ext_vars.items()},
            force=self.force_convert.get(),
            logging=self.enable_logging.get(),
            dry_run=self.dry_run.get(),
            image_conversion=self._current_image_conversion_dict(),
        )

    def _save_config(self, path=None):
        """Persist current widget state via core.config.save_config.

        *path* is an optional override (used by tests); production callers
        rely on the default core.paths.config_file_path() location. Never
        logs/prints the API key — it only ever lives in the config dict.
        """
        try:
            save_config(self._build_config(), path)
        except OSError as e:
            messagebox.showwarning("Config Save Failed", f"Could not save settings: {e}")

    # ── Conversion lifecycle ─────────────────────────────────────────────────

    def on_start(self):
        input_dir = Path(self.input_var.get())
        output_dir = Path(self.output_var.get())
        selected_exts = {ext for ext, var in self.ext_vars.items() if var.get()}

        if not input_dir.is_dir():
            messagebox.showerror("Invalid input", "Input folder does not exist.")
            return

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Invalid output", f"Could not create output folder: {e}")
            return

        if not selected_exts:
            messagebox.showwarning("No extensions", "Please select at least one file type.")
            return

        self._save_config()

        scan = collect_files(input_dir, output_dir, selected_exts, force=self.force_convert.get())
        tasks = scan.tasks

        if not tasks:
            messagebox.showinfo("Nothing to convert", "No files to convert (all up to date or none matched).")
            return

        if self.dry_run.get():
            msg = (
                f"Dry Run:\n\nWould convert: {len(tasks)}\n"
                f"Skipped (up to date): {scan.skipped_up_to_date}\n"
                f"Skipped (unsafe path): {scan.skipped_unsafe}"
            )
            messagebox.showinfo("Dry Run", msg)
            return

        try:
            md = build_markitdown(self._current_image_conversion_dict())
        except LLMConfigError as e:
            messagebox.showerror("Image Conversion Error", str(e))
            return

        self._cancelled = False
        self.start_btn.config(state="disabled")
        self.cancel_btn.config(text="Cancel", state="normal")
        self.status_label.config(text="")
        self.view_log_btn.grid_remove()
        self.progress_frame.grid()

        self._run_logger = RunLogger(logs_dir(), VERSION, self.enable_logging.get())

        threading.Thread(target=self._worker_thread, args=(tasks, md), daemon=True).start()

    def _worker_thread(self, tasks, md):
        counts = run_conversion(
            tasks, md,
            on_progress=lambda i, total, name: self.root.after(0, self._update_progress, i, total, name),
            should_cancel=lambda: self._cancelled,
            run_logger=self._run_logger,
        )
        log_path = self._run_logger.finalize(format_summary(counts))
        self.root.after(0, self._on_conversion_done, counts, log_path)

    def _update_progress(self, i, total, filename):
        self.progress_var.set((i / total) * 100 if total else 0)
        self.progress_label.config(text=f"{i} / {total}")
        self.status_label.config(text=f"Converting: {filename}...", foreground="gray")

    def _on_conversion_done(self, counts, log_path):
        self.start_btn.config(state="normal")
        self.cancel_btn.config(text="Cancel", state="normal")
        self.progress_frame.grid_remove()

        self._last_log_path = log_path

        parts = [f"{counts.converted} converted", f"{counts.overwritten} overwritten",
                 f"{counts.skipped_empty} skipped"]
        if counts.failed:
            parts.append(f"{counts.failed} error{'s' if counts.failed != 1 else ''}")
        if counts.cancelled:
            parts.append("cancelled")

        if counts.failed or counts.cancelled:
            color = "red" if counts.failed else "orange"
        elif counts.skipped_empty and not counts.converted and not counts.overwritten:
            color = "orange"
        else:
            color = "green"

        self.status_label.config(text="Done: " + ", ".join(parts), foreground=color)

        if self._last_log_path:
            self.view_log_btn.grid()
        else:
            self.view_log_btn.grid_remove()

    def cancel(self):
        self._cancelled = True
        self.cancel_btn.config(text="Cancelling...", state="disabled")
        self.status_label.config(text="Cancelling...", foreground="orange")

    def _open_log(self):
        if self._last_log_path:
            try:
                subprocess.Popen(["notepad.exe", str(self._last_log_path)])
            except Exception as e:
                messagebox.showwarning("Log Open Failed", str(e))

    def _on_close(self):
        self._cancelled = True
        self._save_config()
        self.root.destroy()
