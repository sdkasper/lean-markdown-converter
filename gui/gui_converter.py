# ─── APPLICATION METADATA ──────────────────────────────────────────────────
APP_NAME = "LeanProductivity MarkItDown Batch Converter with GUI"
VERSION = "01.02.20260220"
AUTHOR_NAME = "Sascha D. Kasper – LeanProductivity"
AUTHOR_URL = "https://sascha-kasper.com"
HELP_URL = "https://github.com/microsoft/markitdown"
# ──────────────────────────────────────────────────────────────────────────

import os
import sys
import json
import threading
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
    CONFIG_FILE = "conversion_config.json"
    LOGS_DIR = "logs"
else:
    CONFIG_FILE = os.path.join(_SCRIPT_DIR, "..", "conversion_config.json")
    LOGS_DIR = os.path.join(_SCRIPT_DIR, "..", "logs")
os.makedirs(LOGS_DIR, exist_ok=True)
SUPPORTED_EXTENSIONS = [
    ".bmp", ".csv", ".doc", ".docx", ".epub", ".gif", ".htm", ".html",
    ".ipynb", ".jpeg", ".jpg", ".json", ".m4a", ".mp3", ".msg", ".pdf", ".png",
    ".ppt", ".pptx", ".tiff", ".wav", ".xls", ".xlsx", ".xml"
]

# ─── FFMPEG / PYDUB SETUP ─────────────────────────────────────────────────
try:
    from pydub import AudioSegment
    AudioSegment.converter = resource_path(os.path.join("resources", "bin", "ffmpeg.exe"))
except ImportError:
    pass

# ─── GUI APP ──────────────────────────────────────────────────────────────
class FileConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.config = self.load_config()
        self.cancelled = False
        self.converting = False
        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def build_ui(self):
        # Input folder
        tk.Label(self.root, text="Input Folder:").grid(row=0, column=0, sticky="e", padx=5, pady=2)
        self.input_var = tk.StringVar(value=self.config.get("input_folder", ""))
        tk.Entry(self.root, textvariable=self.input_var, width=50).grid(row=0, column=1)
        tk.Button(self.root, text="Browse...", command=self.browse_input).grid(row=0, column=2)

        # Output folder
        tk.Label(self.root, text="Output Folder:").grid(row=1, column=0, sticky="e", padx=5, pady=2)
        self.output_var = tk.StringVar(value=self.config.get("output_folder", ""))
        tk.Entry(self.root, textvariable=self.output_var, width=50).grid(row=1, column=1)
        tk.Button(self.root, text="Browse...", command=self.browse_output).grid(row=1, column=2)

        # Extensions
        self.select_all_var = tk.BooleanVar(value=False)
        self.ext_vars = {}
        tk.Label(self.root, text="Select File Types:").grid(row=2, column=0, sticky="ne", padx=5, pady=(10,0))
        ext_frame = tk.Frame(self.root)
        ext_frame.grid(row=2, column=1, columnspan=2, sticky="w", pady=(10,0))
        tk.Checkbutton(ext_frame, text="Select All", variable=self.select_all_var, command=self.toggle_all).grid(row=0, column=0, sticky="w")
        for i, ext in enumerate(SUPPORTED_EXTENSIONS):
            var = tk.BooleanVar()
            default_exts = self.config.get("extensions", {})
            if isinstance(default_exts, list):
                var.set(ext in default_exts)
            else:
                var.set(default_exts.get(ext, False))
            self.ext_vars[ext] = var
            tk.Checkbutton(ext_frame, text=ext, variable=var).grid(row=(i//6)+1, column=(i%6), sticky="w", padx=2)

        # Options
        self.force_convert = tk.BooleanVar(value=self.config.get("force", False))
        self.enable_logging = tk.BooleanVar(value=self.config.get("logging", True))
        self.dry_run = tk.BooleanVar(value=self.config.get("dry_run", False))
        opt_frame = tk.Frame(self.root)
        opt_frame.grid(row=3, column=1, sticky="w", pady=(10,0))
        tk.Checkbutton(opt_frame, text="Force convert all files", variable=self.force_convert).pack(anchor="w")
        tk.Checkbutton(opt_frame, text="Enable logging to file", variable=self.enable_logging).pack(anchor="w")
        tk.Checkbutton(opt_frame, text="Dry run only", variable=self.dry_run).pack(anchor="w")

        # Progress bar
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(self.root, maximum=100, variable=self.progress_var, length=500)
        self.progress_bar.grid(row=4, column=0, columnspan=3, pady=(10,0), padx=10)
        self.progress_bar.grid_remove()

        # Buttons
        btn_frame = tk.Frame(self.root)
        btn_frame.grid(row=5, column=1, pady=15)
        self.start_btn = tk.Button(btn_frame, text="Start Conversion", command=self.on_start)
        self.start_btn.pack(side="left", padx=5)
        tk.Button(btn_frame, text="Cancel", command=self.cancel).pack(side="left", padx=5)

    def toggle_all(self):
        for var in self.ext_vars.values():
            var.set(self.select_all_var.get())

    def browse_input(self):
        path = filedialog.askdirectory()
        if path:
            self.input_var.set(path)

    def browse_output(self):
        path = filedialog.askdirectory()
        if path:
            self.output_var.set(path)

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
        self.progress_bar.grid()

        files_to_convert = []
        skipped = 0
        for root_dir, _, files in os.walk(input_dir):
            for file in files:
                src = Path(root_dir) / file
                if not self._is_safe_path(input_dir, src):
                    log_lines_pre = []
                    log_lines_pre.append(f"[{datetime.now()}] Skipped (traversal): {src}")
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
            if not messagebox.askyesno("Dry Run", msg + "\n\nProceed?" ):
                self.start_btn.config(state="normal")
                self.progress_bar.grid_remove()
                return

        self.converting = True
        threading.Thread(target=self.worker_thread, args=(files_to_convert, skipped), daemon=True).start()

    def worker_thread(self, tasks, skipped):
        converted = overwritten = failed = 0
        log_lines = []
        total = len(tasks)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_path = Path(LOGS_DIR) / f"conversion_log_{timestamp}.log"

        # Initialize converter once per thread
        md = MarkItDown()

        for i, (src, dst, existed) in enumerate(tasks, 1):
            if self.cancelled: break
            err = ""
            try:
                result = md.convert(src)
                Path(dst).parent.mkdir(parents=True, exist_ok=True)
                with open(dst, "w", encoding="utf-8") as f:
                    f.write(result.text_content)
                status = "overwritten" if existed else "converted"
            except Exception as e:
                status = "error"
                err = str(e)

            if status == "converted":
                converted += 1
                log_lines.append(f"[{datetime.now()}] Converted: {src}")
            elif status == "overwritten":
                overwritten += 1
                log_lines.append(f"[{datetime.now()}] Overwritten: {src}")
            else:
                failed += 1
                log_lines.append(f"[{datetime.now()}] Error: {src} -> {err}")

            self.root.after(0, lambda pct=(i/total)*100: self.progress_var.set(pct))

        summary = f"Converted: {converted}\nOverwritten: {overwritten}\nSkipped: {skipped}\nErrors: {failed}\n"
        logging_enabled = self.enable_logging.get()

        if logging_enabled:
            try:
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(log_lines))
            except Exception:
                log_path = None

        self.root.after(0, self._on_conversion_done, summary, logging_enabled, log_path)

    def _on_conversion_done(self, summary, logging_enabled, log_path):
        self.converting = False
        self.start_btn.config(state="normal")
        self.progress_bar.grid_remove()

        if logging_enabled and log_path:
            if messagebox.askyesno("Done", summary + "View log?"):
                try:
                    os.startfile(str(log_path))
                except Exception as e:
                    messagebox.showwarning("Log Open Failed", f"Could not open log: {e}")
        elif logging_enabled and not log_path:
            messagebox.showwarning("Done", summary + "Log file could not be saved.")
        else:
            messagebox.showinfo("Done", summary)

# ─── MAIN ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    root = tk.Tk()
    app = FileConverterApp(root)
    root.mainloop()
