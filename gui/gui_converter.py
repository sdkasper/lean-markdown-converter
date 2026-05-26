# ─── APPLICATION METADATA ──────────────────────────────────────────────────
APP_NAME = "Lean Markdown Converter"
VERSION = "1.0.9"
AUTHOR_NAME = "Sascha D. Kasper – LeanProductivity"
AUTHOR_URL = "https://sascha-kasper.com"
HELP_URL = "https://github.com/microsoft/markitdown"
# ──────────────────────────────────────────────────────────────────────────

import os
import sys
import json
import subprocess
import threading
import traceback
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from markitdown import MarkItDown

# ─── RUNTIME PATH HANDLER FOR PYINSTALLER ─────────────────────────────────
def resource_path(rel_path):
    """Handles paths whether running from script or bundled exe."""
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, rel_path)
    return os.path.join(os.path.abspath("."), rel_path)

# ─── CONSTANTS ─────────────────────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):
    _APP_DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "LeanProductivity")
    os.makedirs(_APP_DATA_DIR, exist_ok=True)
    CONFIG_FILE = os.path.join(_APP_DATA_DIR, "config.json")
    LOGS_DIR = os.path.join(_APP_DATA_DIR, "logs")
else:
    CONFIG_FILE = os.path.join(_SCRIPT_DIR, "..", "conversion_config.json")
    LOGS_DIR = os.path.join(_SCRIPT_DIR, "..", "logs")
os.makedirs(LOGS_DIR, exist_ok=True)
SUPPORTED_EXTENSIONS = [
    ".csv", ".doc", ".docx", ".epub", ".htm", ".html",
    ".ipynb", ".json", ".m4a", ".mp3", ".msg", ".pdf",
    ".ppt", ".pptx", ".wav", ".xls", ".xlsx", ".xml"
]
EXT_GROUPS = {
    "Documents":    [".doc", ".docx", ".epub", ".msg", ".pdf", ".ppt", ".pptx"],
    "Spreadsheets": [".csv", ".xls", ".xlsx"],
    "Audio":        [".m4a", ".mp3", ".wav"],
    "Web / Data":   [".htm", ".html", ".ipynb", ".json", ".xml"],
}

# ─── FFMPEG / PYDUB SETUP ─────────────────────────────────────────────────
# Check if ffmpeg is in PATH before setting custom paths
# M4A audio transcription fails with custom absolute paths when system ffmpeg is available
try:
    from pydub import AudioSegment
    # Try to find ffmpeg AND ffprobe in PATH using 'where' command
    ffmpeg_in_path = subprocess.run(["where", "ffmpeg"], capture_output=True, text=True).returncode == 0
    ffprobe_in_path = subprocess.run(["where", "ffprobe"], capture_output=True, text=True).returncode == 0

    # Only set custom paths if BOTH binaries are NOT in PATH (e.g., bundled exe)
    if not ffmpeg_in_path or not ffprobe_in_path:
        ffmpeg_path = resource_path(os.path.join("resources", "bin", "ffmpeg.exe"))
        ffprobe_path = resource_path(os.path.join("resources", "bin", "ffprobe.exe"))
        if os.path.exists(ffmpeg_path) and os.path.exists(ffprobe_path):
            AudioSegment.converter = ffmpeg_path
            AudioSegment.ffprobe = ffprobe_path
except (ImportError, Exception):
    pass

# ─── STARTUP DIAGNOSTIC ───────────────────────────────────────────────────
def _write_startup_diagnostic():
    """Write one-time startup summary to a persistent log for troubleshooting."""
    try:
        diag_path = Path(LOGS_DIR) / "startup_diagnostic.log"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        ffmpeg_where = subprocess.run(["where", "ffmpeg"], capture_output=True, text=True)
        ffprobe_where = subprocess.run(["where", "ffprobe"], capture_output=True, text=True)
        ffmpeg_path_found = ffmpeg_where.returncode == 0
        ffprobe_path_found = ffprobe_where.returncode == 0
        ffmpeg_path_val = ffmpeg_where.stdout.strip().splitlines()[0] if ffmpeg_path_found else "not in PATH"
        ffprobe_path_val = ffprobe_where.stdout.strip().splitlines()[0] if ffprobe_path_found else "not in PATH"

        bundled_ffmpeg = resource_path(os.path.join("resources", "bin", "ffmpeg.exe"))
        bundled_ffprobe = resource_path(os.path.join("resources", "bin", "ffprobe.exe"))
        b_ffmpeg_exists = os.path.exists(bundled_ffmpeg)
        b_ffprobe_exists = os.path.exists(bundled_ffprobe)
        b_ffmpeg_size = os.path.getsize(bundled_ffmpeg) if b_ffmpeg_exists else 0
        b_ffprobe_size = os.path.getsize(bundled_ffprobe) if b_ffprobe_exists else 0

        try:
            from pydub import AudioSegment
            active_ffmpeg = getattr(AudioSegment, "converter", "pydub default")
            active_ffprobe = getattr(AudioSegment, "ffprobe", "pydub default")
        except ImportError:
            active_ffmpeg = active_ffprobe = "pydub not available"

        lines = [
            f"[{ts}] === Lean Markdown Converter v{VERSION} Startup Diagnostic ===",
            f"[{ts}] ffmpeg in PATH: {ffmpeg_path_found} ({ffmpeg_path_val})",
            f"[{ts}] ffprobe in PATH: {ffprobe_path_found} ({ffprobe_path_val})",
            f"[{ts}] Active ffmpeg path: {active_ffmpeg}",
            f"[{ts}] Active ffprobe path: {active_ffprobe}",
            f"[{ts}] Bundled ffmpeg: exists={b_ffmpeg_exists}, size={b_ffmpeg_size} bytes ({bundled_ffmpeg})",
            f"[{ts}] Bundled ffprobe: exists={b_ffprobe_exists}, size={b_ffprobe_size} bytes ({bundled_ffprobe})",
            f"[{ts}] Frozen (exe): {getattr(sys, 'frozen', False)}",
            "",
        ]
        with open(diag_path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:
        pass  # Never crash startup due to diagnostics

_write_startup_diagnostic()

# ─── GUI APP ──────────────────────────────────────────────────────────────
class FileConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} v{VERSION}")
        self.config = self.load_config()
        self.cancelled = False
        self.converting = False
        self._scan_gen = 0
        self._scan_after_id = None
        self._last_log_path = None
        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def build_ui(self):
        # ── Theming ──────────────────────────────────────────────────────
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except Exception:
            pass
        self.root.configure(padx=10, pady=10)
        self.root.minsize(640, 480)
        self.root.columnconfigure(1, weight=1)

        # ── Input folder ─────────────────────────────────────────────────
        ttk.Label(self.root, text="Input Folder:").grid(row=0, column=0, sticky="e", padx=5, pady=2)
        self.input_var = tk.StringVar(value=self.config.get("input_folder", ""))
        ttk.Entry(self.root, textvariable=self.input_var, width=50).grid(row=0, column=1, sticky="ew")
        ttk.Button(self.root, text="Browse…", command=self.browse_input).grid(row=0, column=2, padx=(4, 0))
        self.input_info_label = ttk.Label(self.root, text="", foreground="gray")
        self.input_info_label.grid(row=1, column=1, sticky="w", padx=2)
        self.input_var.trace_add("write", self._schedule_scan)

        # ── Output folder ────────────────────────────────────────────────
        ttk.Label(self.root, text="Output Folder:").grid(row=2, column=0, sticky="e", padx=5, pady=(8, 2))
        self.output_var = tk.StringVar(value=self.config.get("output_folder", ""))
        out_entry = ttk.Entry(self.root, textvariable=self.output_var, width=50)
        out_entry.grid(row=2, column=1, sticky="ew", pady=(8, 2))
        out_entry.bind("<FocusOut>", self._validate_output_path)
        ttk.Button(self.root, text="Browse…", command=self.browse_output).grid(row=2, column=2, padx=(4, 0), pady=(8, 2))
        self.output_warn_label = ttk.Label(self.root, text="", foreground="blue")
        self.output_warn_label.grid(row=3, column=1, sticky="w", padx=2)

        # ── Extensions ───────────────────────────────────────────────────
        self.select_all_var = tk.BooleanVar(value=False)
        self.ext_vars = {}
        self.group_all_vars = {}
        ttk.Label(self.root, text="File Types:").grid(row=4, column=0, sticky="ne", padx=5, pady=(10, 0))
        ext_frame = ttk.Frame(self.root)
        ext_frame.grid(row=4, column=1, columnspan=2, sticky="w", pady=(10, 0))

        # Master "Select All" toggle
        ttk.Checkbutton(ext_frame, text="Select All", variable=self.select_all_var,
                        command=self.toggle_all).grid(row=0, column=0, sticky="w", columnspan=2)

        # Per-group rows
        row_offset = 1
        for group_name, exts in EXT_GROUPS.items():
            grp_var = tk.BooleanVar(value=False)
            self.group_all_vars[group_name] = grp_var
            ttk.Checkbutton(ext_frame, text=group_name, variable=grp_var,
                            command=lambda g=group_name: self._toggle_group(g)).grid(
                row=row_offset, column=0, sticky="w", padx=(0, 8))
            default_exts = self.config.get("extensions", {})
            col = 1
            for ext in exts:
                var = tk.BooleanVar()
                if isinstance(default_exts, list):
                    var.set(ext in default_exts)
                else:
                    var.set(default_exts.get(ext, False))
                self.ext_vars[ext] = var
                ttk.Checkbutton(ext_frame, text=ext, variable=var).grid(
                    row=row_offset, column=col, sticky="w", padx=2)
                col += 1
            row_offset += 1

        # ── Options ──────────────────────────────────────────────────────
        self.force_convert = tk.BooleanVar(value=self.config.get("force", False))
        self.enable_logging = tk.BooleanVar(value=self.config.get("logging", True))
        self.dry_run = tk.BooleanVar(value=self.config.get("dry_run", False))
        opt_frame = ttk.Frame(self.root)
        opt_frame.grid(row=5, column=1, sticky="w", pady=(10, 0))
        ttk.Checkbutton(opt_frame, text="Force convert all files", variable=self.force_convert).pack(anchor="w")
        ttk.Checkbutton(opt_frame, text="Enable logging to file", variable=self.enable_logging).pack(anchor="w")
        ttk.Checkbutton(opt_frame, text="Dry run only", variable=self.dry_run).pack(anchor="w")

        # ── Progress ─────────────────────────────────────────────────────
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_frame = ttk.Frame(self.root)
        self.progress_frame.grid(row=6, column=0, columnspan=3, pady=(10, 0), padx=10, sticky="ew")
        self.progress_bar = ttk.Progressbar(self.progress_frame, maximum=100,
                                            variable=self.progress_var, length=500)
        self.progress_bar.pack(side="left", fill="x", expand=True)
        self.progress_label = ttk.Label(self.progress_frame, text="", width=10, anchor="e")
        self.progress_label.pack(side="left", padx=(6, 0))
        self.progress_frame.grid_remove()

        # ── Status ───────────────────────────────────────────────────────
        self.status_label = ttk.Label(self.root, text="", foreground="gray")
        self.status_label.grid(row=7, column=0, columnspan=2, sticky="w", padx=5, pady=(4, 0))
        self.view_log_btn = ttk.Button(self.root, text="View Log", command=self._open_log)
        self.view_log_btn.grid(row=7, column=2, sticky="e", padx=(4, 0), pady=(4, 0))
        self.view_log_btn.grid_remove()

        # ── Buttons ──────────────────────────────────────────────────────
        btn_frame = ttk.Frame(self.root)
        btn_frame.grid(row=8, column=1, pady=15)
        self.start_btn = ttk.Button(btn_frame, text="Start Conversion", command=self.on_start)
        self.start_btn.pack(side="left", padx=5)
        self.cancel_btn = ttk.Button(btn_frame, text="Cancel", command=self.cancel)
        self.cancel_btn.pack(side="left", padx=5)

        # Trigger initial scan if path already loaded from config
        if self.input_var.get():
            self._schedule_scan()

    # ── Helper methods ────────────────────────────────────────────────────

    def _schedule_scan(self, *_):
        """Debounce file count scan on input path change."""
        if self._scan_after_id:
            self.root.after_cancel(self._scan_after_id)
        self._scan_after_id = self.root.after(400, self._validate_and_scan_input)

    def _validate_and_scan_input(self):
        """Check input path exists and scan file count in background."""
        p = Path(self.input_var.get())
        if not p.is_dir():
            self.input_info_label.config(text="Path not found", foreground="red")
            return
        self.input_info_label.config(text="Scanning…", foreground="gray")
        self._scan_gen += 1
        gen = self._scan_gen
        exts = {e for e, v in self.ext_vars.items() if v.get()}
        def _scan():
            count = sum(1 for _, _, fs in os.walk(str(p)) for f in fs if Path(f).suffix.lower() in exts)
            self.root.after(0, lambda: self._apply_scan_result(count, gen))
        threading.Thread(target=_scan, daemon=True).start()

    def _apply_scan_result(self, count, gen):
        """Update file count label if scan is still current."""
        if gen != self._scan_gen:
            return
        txt = f"{count} file{'s' if count != 1 else ''} found"
        self.input_info_label.config(text=txt, foreground="green" if count > 0 else "orange")

    def _validate_output_path(self, *_):
        """Show warning if output path doesn't exist (will be created)."""
        p = Path(self.output_var.get())
        if self.output_var.get() and not p.is_dir():
            self.output_warn_label.config(text="Will be created", foreground="blue")
        else:
            self.output_warn_label.config(text="")

    def _toggle_group(self, group_name):
        """Toggle all extensions in a category."""
        val = self.group_all_vars[group_name].get()
        for ext in EXT_GROUPS[group_name]:
            self.ext_vars[ext].set(val)
        self._schedule_scan()

    def _open_log(self):
        """Open last log file in Notepad."""
        if self._last_log_path:
            try:
                subprocess.Popen(["notepad.exe", str(self._last_log_path)])
            except Exception as e:
                messagebox.showwarning("Log Open Failed", str(e))

    def _update_progress(self, i, total, filename):
        """Update progress bar percentage and file counter + status label."""
        self.progress_var.set((i / total) * 100)
        self.progress_label.config(text=f"{i} / {total}")
        self.status_label.config(text=f"Converting: {filename}…", foreground="gray")

    # ── Core methods ──────────────────────────────────────────────────────

    def toggle_all(self):
        val = self.select_all_var.get()
        for var in self.ext_vars.values():
            var.set(val)
        for var in self.group_all_vars.values():
            var.set(val)
        self._schedule_scan()

    def browse_input(self):
        path = filedialog.askdirectory()
        if path:
            self.input_var.set(path)

    def browse_output(self):
        path = filedialog.askdirectory()
        if path:
            self.output_var.set(path)
            self._validate_output_path()

    def save_config(self):
        data = {
            "input_folder": self.input_var.get(),
            "output_folder": self.output_var.get(),
            "extensions": {ext: var.get() for ext, var in self.ext_vars.items()},
            "force": self.force_convert.get(),
            "logging": self.enable_logging.get(),
            "dry_run": self.dry_run.get()
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            messagebox.showwarning("Config Save Failed", f"Could not save settings: {e}")

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                messagebox.showwarning("Config Load Failed", "Could not read settings file. Using defaults.")
        return {}

    def cancel(self):
        if self.converting:
            self.cancelled = True
            self.cancel_btn.config(text="Cancelling…", state="disabled")
            self.status_label.config(text="Cancelling…", foreground="orange")

    def _on_close(self):
        self.cancelled = True
        self.root.destroy()

    @staticmethod
    def _is_safe_path(base_dir: Path, target: Path) -> bool:
        """Return True if target resolves to a path within base_dir (prevents symlink/junction traversal)."""
        try:
            target.resolve().relative_to(base_dir.resolve())
            return True
        except ValueError:
            return False

    def on_start(self):
        input_dir = Path(self.input_var.get())
        output_dir = Path(self.output_var.get())
        selected_exts = {ext for ext, var in self.ext_vars.items() if var.get()}

        if not input_dir.is_dir():
            messagebox.showerror("Invalid input", "Input folder does not exist.")
            return
        if not output_dir.is_dir():
            output_dir.mkdir(parents=True, exist_ok=True)
        if not selected_exts:
            messagebox.showwarning("No extensions", "Please select at least one file type.")
            return

        self.save_config()
        self.cancelled = False
        self.start_btn.config(state="disabled")
        self.status_label.config(text="")
        self.view_log_btn.grid_remove()
        self.progress_frame.grid()

        files_to_convert = []
        skipped = 0
        for root_dir, _, files in os.walk(input_dir):
            for file in files:
                src = Path(root_dir) / file
                if not self._is_safe_path(input_dir, src):
                    continue
                if src.suffix.lower() in selected_exts:
                    rel = src.relative_to(input_dir)
                    dst = output_dir / rel.with_suffix(".md")
                    if not self._is_safe_path(output_dir, dst):
                        continue
                    existed = dst.exists()
                    if existed and not self.force_convert.get() and dst.stat().st_mtime >= src.stat().st_mtime:
                        skipped += 1
                        continue
                    files_to_convert.append((str(src), str(dst), existed))

        if self.dry_run.get():
            msg = (f"Dry Run:\n\nTotal: {len(files_to_convert)+skipped}\nConvert: {len(files_to_convert)}\nSkipped: {skipped}")
            if not messagebox.askyesno("Dry Run", msg + "\n\nProceed?"):
                self.start_btn.config(state="normal")
                self.progress_frame.grid_remove()
                return

        self.converting = True
        threading.Thread(target=self.worker_thread, args=(files_to_convert, skipped), daemon=True).start()

    def worker_thread(self, tasks, skipped):
        converted = overwritten = failed = 0
        log_lines = []
        total = len(tasks)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_path = Path(LOGS_DIR) / f"conversion_log_{timestamp}.log"
        _AUDIO_EXTS = {".mp3", ".m4a", ".wav"}
        audio_attempted = audio_converted = audio_failed = 0

        # Initialize converter once per thread
        md = MarkItDown()

        for i, (src, dst, existed) in enumerate(tasks):
            if self.cancelled:
                break
            err = ""
            src_ext = Path(src).suffix.lower()
            is_audio = src_ext in _AUDIO_EXTS
            if is_audio:
                audio_attempted += 1

            # ── Pre-conversion checks ─────────────────────────────────────
            src_path = Path(src)
            if not src_path.exists():
                status = "error"
                err = "Source file not found"
                log_lines.append(f"[{datetime.now()}] PreCheck FAIL (missing): {src}")
            else:
                try:
                    src_path.open("rb").close()
                except OSError as open_err:
                    status = "error"
                    err = f"Cannot read source: {open_err}"
                    log_lines.append(f"[{datetime.now()}] PreCheck FAIL (unreadable): {src} -> {err}")
                else:
                    dst_parent = Path(dst).parent
                    try:
                        dst_parent.mkdir(parents=True, exist_ok=True)
                        _tmp = dst_parent / f".writable_check_{timestamp}.tmp"
                        _tmp.touch()
                        _tmp.unlink()
                    except OSError as dir_err:
                        status = "error"
                        err = f"Output dir not writable: {dir_err}"
                        log_lines.append(
                            f"[{datetime.now()}] PreCheck FAIL (output dir): {os.path.basename(src)} -> {err}"
                        )
                    else:
                        # ── Conversion ────────────────────────────────────
                        status = None
                        try:
                            result = md.convert(src)
                            content = result.text_content or ""
                            if not content.strip():
                                status = "empty"
                                log_lines.append(f"[{datetime.now()}] Skipped (empty output): {src}")
                            else:
                                with open(dst, "w", encoding="utf-8") as f:
                                    f.write(content)
                                status = "overwritten" if existed else "converted"
                        except Exception as e:
                            status = "error"
                            tb = traceback.format_exc()
                            exc_type = type(e).__name__
                            err = str(e)
                            if is_audio:
                                log_lines.append(
                                    f"[{datetime.now()}] Audio Conversion Error: {src} -> "
                                    f"{exc_type}: {err[:120]}"
                                )
                                # Append truncated traceback on next line
                                tb_short = tb.replace("\n", " | ")[:180]
                                log_lines.append(f"[{datetime.now()}] Traceback: {tb_short}")
                            else:
                                log_lines.append(f"[{datetime.now()}] Error: {src} -> {exc_type}: {err[:150]}")

            if status == "converted":
                converted += 1
                if is_audio:
                    audio_converted += 1
                log_lines.append(f"[{datetime.now()}] Converted: {src}")
            elif status == "overwritten":
                overwritten += 1
                if is_audio:
                    audio_converted += 1
                log_lines.append(f"[{datetime.now()}] Overwritten: {src}")
            elif status == "empty":
                skipped += 1
                # log line already appended inside the empty-content guard
            elif status == "error":
                failed += 1
                if is_audio:
                    audio_failed += 1
                # error log already appended above

            self.root.after(0, self._update_progress, i + 1, total, os.path.basename(src))

        # ── End-of-run summary ────────────────────────────────────────────
        total_attempted = converted + overwritten + failed
        success_rate = (
            f"{(converted + overwritten) * 100 // total_attempted}%"
            if total_attempted else "n/a"
        )
        summary = (
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Summary: "
            f"{audio_attempted} audio files ({audio_converted} converted, {audio_failed} failed), "
            f"{total_attempted} total files ({converted + overwritten} converted, {failed} failed), "
            f"success rate {success_rate}"
        )
        log_lines.append(summary)

        logging_enabled = self.enable_logging.get()

        if logging_enabled:
            try:
                with open(log_path, "w", encoding="utf-8") as f:
                    header = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Lean Markdown Converter v{VERSION}\n"
                    f.write(header)
                    f.write("\n".join(log_lines))
            except Exception:
                log_path = None

        counts = (converted, overwritten, skipped, failed)
        self.root.after(0, self._on_conversion_done, counts, logging_enabled, log_path)

    def _on_conversion_done(self, counts, logging_enabled, log_path):
        converted, overwritten, skipped, failed = counts
        self.converting = False
        self.start_btn.config(state="normal")
        self.cancel_btn.config(text="Cancel", state="normal")
        self.progress_frame.grid_remove()

        self._last_log_path = log_path if (logging_enabled and log_path) else None

        parts = [f"{converted} converted", f"{overwritten} overwritten", f"{skipped} skipped"]
        if failed:
            parts.append(f"{failed} error{'s' if failed != 1 else ''}")

        color = "red" if failed else ("orange" if skipped and not converted else "green")
        self.status_label.config(text="Done - " + ", ".join(parts), foreground=color)

        if self._last_log_path:
            self.view_log_btn.grid()
        else:
            self.view_log_btn.grid_remove()

# ─── MAIN ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    root = tk.Tk()
    app = FileConverterApp(root)
    root.mainloop()
