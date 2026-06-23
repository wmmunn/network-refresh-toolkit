from __future__ import annotations

import logging
import os
import platform
import queue
import subprocess
import threading
import traceback
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import ttkbootstrap as tb
    TTKBOOTSTRAP_AVAILABLE = True
except Exception:
    tb = None
    TTKBOOTSTRAP_AVAILABLE = False

from .cli import DEFAULT_CONFIG_PATH_TEMPLATES, DEFAULT_DEVICES_PATH_TEMPLATES, DEFAULT_NETWORK_ID, validate_settings
from .client import DownloaderError, ForwardClient
from .models import AuthSettings, DownloaderSettings, ExitCode
from .output import configure_logging, log_event


APP_NAME = "Forward Networks Config Downloader"
APP_VERSION = "0.4"


class App(tb.Window if TTKBOOTSTRAP_AVAILABLE else tk.Tk):
    def __init__(self):
        if TTKBOOTSTRAP_AVAILABLE:
            super().__init__(themename="flatly")
        else:
            super().__init__()

        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1040x680")
        self.minsize(900, 560)

        self.base_url = tk.StringVar(value=os.environ.get("FWD_BASE_URL", "https://fwd.app"))
        self.api_prefix = tk.StringVar(value=os.environ.get("FWD_API_PREFIX", "/api"))
        self.network_id = tk.StringVar(value=os.environ.get("FORWARD_NETWORKS_NETWORK_ID", DEFAULT_NETWORK_ID))
        self.hostname = tk.StringVar()
        self.snapshot_id = tk.StringVar()
        self.config_file = tk.StringVar()
        self.output_dir = tk.StringVar(value=str(Path.cwd() / "manifests"))
        self.status = tk.StringVar(value="Ready. Enter a hostname and pull the running-config.")
        self.environment_status = tk.StringVar()
        self.advanced_visible = tk.BooleanVar(value=False)
        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.last_output_path: Path | None = None
        self.last_log_path: Path | None = None

        self._build_ui()
        self.refresh_environment_status()

    def _button(self, parent, text: str, command, bootstyle: str = ""):
        if TTKBOOTSTRAP_AVAILABLE:
            return tb.Button(parent, text=text, command=command, bootstyle=bootstyle or "secondary")
        return ttk.Button(parent, text=text, command=command)

    def _build_ui(self) -> None:
        if TTKBOOTSTRAP_AVAILABLE:
            self.style.configure("Tool.TLabelframe.Label", font=("Segoe UI", 10, "bold"))

        top = ttk.Frame(self, padding=14)
        top.pack(fill="x")

        header = ttk.Frame(top)
        header.grid(row=0, column=0, sticky="we", pady=(0, 12))
        ttk.Label(header, text=APP_NAME, font=("Segoe UI", 17, "bold")).pack(side="left")
        ttk.Label(header, text=f"v{APP_VERSION}", font=("Segoe UI", 10), foreground="#5c6b73").pack(
            side="left", padx=(8, 0), pady=(6, 0)
        )
        ttk.Label(
            header,
            text="Read-only API retrieval; credentials remain in environment variables.",
            foreground="#5c6b73",
        ).pack(side="right", pady=(6, 0))
        top.columnconfigure(0, weight=1)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        workflow_tab = ttk.Frame(notebook, padding=12)
        reference_tab = ttk.Frame(notebook, padding=12)
        notebook.add(workflow_tab, text="Download Workflow")
        notebook.add(reference_tab, text="Connection Reference")

        input_frame = ttk.LabelFrame(
            workflow_tab,
            text="Pull Running Config",
            padding=10,
            style="Tool.TLabelframe" if TTKBOOTSTRAP_AVAILABLE else "",
        )
        input_frame.pack(fill="x")

        ttk.Label(input_frame, text="Switch hostname").grid(row=0, column=0, sticky="w", pady=5)
        hostname_entry = ttk.Entry(input_frame, textvariable=self.hostname, width=58, font=("Segoe UI", 11))
        hostname_entry.grid(row=0, column=1, sticky="we", padx=8, pady=5)
        hostname_entry.focus_set()

        ttk.Label(input_frame, text="Snapshot ID").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(input_frame, textvariable=self.snapshot_id, width=58).grid(row=1, column=1, sticky="we", padx=8, pady=5)
        ttk.Label(
            input_frame,
            text="Leave blank to use the latest completed snapshot.",
            foreground="#5c6b73",
        ).grid(row=1, column=2, sticky="w", pady=5)

        ttk.Label(input_frame, text="Output folder").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Entry(input_frame, textvariable=self.output_dir, width=58).grid(row=2, column=1, sticky="we", padx=8, pady=5)
        self._button(input_frame, "Browse", self.pick_output_dir, "primary-outline").grid(row=2, column=2, pady=5)

        input_frame.columnconfigure(1, weight=1)

        env_notice = ttk.Label(
            workflow_tab,
            text=(
                "Environment variables required: FORWARD_NETWORKS_KEY, "
                "FORWARD_NETWORKS_SECRET, and FORWARD_NETWORKS_NETWORK_ID. "
                "Values are never displayed or written by this tool."
            ),
            foreground="#7a4b00",
            wraplength=960,
            padding=(0, 8, 0, 0),
        )
        env_notice.pack(fill="x")

        actions = ttk.Frame(workflow_tab, padding=(0, 12, 0, 8))
        actions.pack(fill="x")
        self.pull_button = self._button(actions, "Pull Running Config", self.pull_config, "success")
        self.pull_button.pack(side="left", padx=(0, 6))
        self._button(actions, "Open Last Config", self.open_last_output, "primary-outline").pack(side="left", padx=6)
        self._button(actions, "Open Output Folder", self.open_output_folder, "primary-outline").pack(side="left", padx=6)
        self._button(actions, "Open Logs Folder", self.open_logs_folder, "primary-outline").pack(side="left", padx=6)
        self._button(actions, "Clear", self.clear, "secondary-outline").pack(side="left", padx=6)
        self._button(actions, "Exit", self.destroy, "secondary-outline").pack(side="right")

        self.advanced_frame = ttk.LabelFrame(
            workflow_tab,
            text="Advanced Settings",
            padding=10,
            style="Tool.TLabelframe" if TTKBOOTSTRAP_AVAILABLE else "",
        )
        self.build_advanced_frame()

        self.readiness_frame = ttk.LabelFrame(
            workflow_tab,
            text="Environment Readiness",
            padding=10,
            style="Tool.TLabelframe" if TTKBOOTSTRAP_AVAILABLE else "",
        )
        self.readiness_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(
            self.readiness_frame,
            textvariable=self.environment_status,
            foreground="#5c6b73",
        ).pack(side="left", fill="x", expand=True)
        self._button(
            self.readiness_frame,
            "Refresh",
            self.refresh_environment_status,
            "secondary-outline",
        ).pack(side="right")

        self.advanced_button = self._button(
            workflow_tab,
            "Show Advanced Settings",
            self.toggle_advanced,
            "secondary-outline",
        )
        self.advanced_button.pack(anchor="w", pady=(0, 8))

        self.summary = ttk.Label(
            workflow_tab,
            textvariable=self.status,
            padding=(0, 2, 0, 10),
            font=("Segoe UI", 11, "bold"),
        )
        self.summary.pack(fill="x")

        detail_frame = ttk.LabelFrame(workflow_tab, text="Run Detail", padding=8)
        detail_frame.pack(fill="both", expand=True)
        self.detail_text = tk.Text(detail_frame, height=18, wrap="word", font=("Consolas", 10), relief="flat", borderwidth=1)
        self.detail_text.pack(fill="both", expand=True)

        reference_tab.columnconfigure(0, weight=1)
        reference_tab.columnconfigure(1, weight=1)
        reference_tab.rowconfigure(0, weight=1)

        auth_frame = ttk.LabelFrame(reference_tab, text="Authentication and Scope", padding=12)
        auth_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        auth_text = tk.Text(
            auth_frame,
            wrap="word",
            font=("Segoe UI", 10),
            relief="flat",
            borderwidth=1,
        )
        auth_text.pack(fill="both", expand=True)
        auth_text.insert(
            "1.0",
            "Required environment variables:\n"
            "- FORWARD_NETWORKS_KEY\n"
            "- FORWARD_NETWORKS_SECRET\n\n"
            "Optional environment variables:\n"
            "- FORWARD_NETWORKS_NETWORK_ID\n"
            "- FWD_BASE_URL\n"
            "- FWD_API_PREFIX\n\n"
            "The tool performs read-only API requests. It does not connect to devices, "
            "send commands, or write credentials to source, logs, or downloaded files.",
        )
        auth_text.configure(state="disabled")

        behavior_frame = ttk.LabelFrame(reference_tab, text="Download Behavior", padding=12)
        behavior_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        behavior_text = tk.Text(
            behavior_frame,
            wrap="word",
            font=("Segoe UI", 10),
            relief="flat",
            borderwidth=1,
        )
        behavior_text.pack(fill="both", expand=True)
        behavior_text.insert(
            "1.0",
            "- Leave Snapshot ID blank to select the latest completed snapshot.\n"
            "- Enter the Forward Networks hostname exactly as represented in the snapshot.\n"
            "- Config file normally defaults to hostname + ',configuration.txt'.\n"
            "- Advanced settings allow tenant-specific API and file-name overrides.\n"
            "- Downloaded configs are written as plain text for operator review.\n"
            "- Run details and errors are written to the local logs folder.\n\n"
            "No downloaded configuration is executed or pushed to a device.",
        )
        behavior_text.configure(state="disabled")

        ttk.Label(
            self,
            text="Created by William Munn",
            foreground="#5c6b73",
            font=("Segoe UI", 8, "italic"),
            padding=(14, 0, 14, 8),
        ).pack(fill="x")

    def build_advanced_frame(self) -> None:
        rows = [
            ("Base URL", self.base_url),
            ("API prefix", self.api_prefix),
            ("Network ID", self.network_id),
            ("Config file override", self.config_file),
        ]
        for row_index, (label, var) in enumerate(rows):
            ttk.Label(self.advanced_frame, text=label).grid(row=row_index, column=0, sticky="w", pady=4)
            ttk.Entry(self.advanced_frame, textvariable=var, width=92).grid(row=row_index, column=1, sticky="we", padx=8, pady=4)
        ttk.Label(
            self.advanced_frame,
            text="Config file normally defaults to hostname + ',configuration.txt'. Credentials are read from environment variables.",
            foreground="#5c6b73",
        ).grid(row=len(rows), column=1, sticky="w", padx=8, pady=(0, 2))
        self.advanced_frame.columnconfigure(1, weight=1)

    def toggle_advanced(self) -> None:
        if self.advanced_visible.get():
            self.advanced_frame.pack_forget()
            self.advanced_visible.set(False)
            self.advanced_button.config(text="Show Advanced Settings")
        else:
            self.advanced_frame.pack(
                fill="x",
                pady=(0, 8),
                before=self.readiness_frame,
            )
            self.advanced_visible.set(True)
            self.advanced_button.config(text="Hide Advanced Settings")

    def environment_status_text(self) -> str:
        credential_state = "credentials found" if os.environ.get("FORWARD_NETWORKS_KEY") and os.environ.get("FORWARD_NETWORKS_SECRET") else "credentials missing"
        network_state = f"network ID {self.network_id.get()}" if self.network_id.get() else "network ID missing"
        return f"Environment: {credential_state}; {network_state}."

    def refresh_environment_status(self) -> None:
        self.environment_status.set(self.environment_status_text())

    def pick_output_dir(self) -> None:
        selected = filedialog.askdirectory(title="Select output folder")
        if selected:
            self.output_dir.set(selected)

    def settings(self) -> DownloaderSettings:
        hostname = self.hostname.get().strip()
        config_file = self.config_file.get().strip() or (f"{hostname},configuration.txt" if hostname else None)
        return DownloaderSettings(
            base_url=self.base_url.get().strip() or "https://fwd.app",
            api_prefix=self.api_prefix.get().strip(),
            network_id=self.network_id.get().strip(),
            snapshot_id=self.snapshot_id.get().strip() or None,
            hostname=hostname,
            location_id=None,
            config_file=config_file,
            devices_path_templates=DEFAULT_DEVICES_PATH_TEMPLATES,
            config_path_templates=DEFAULT_CONFIG_PATH_TEMPLATES,
            output_dir=Path(self.output_dir.get().strip() or "manifests"),
            logs_dir=Path.cwd() / "logs",
            timeout_seconds=30.0,
            line_page_size=200,
            max_line_pages=500,
            auth=AuthSettings(
                mode="basic",
                key=os.environ.get("FORWARD_NETWORKS_KEY"),
                secret=os.environ.get("FORWARD_NETWORKS_SECRET"),
            ),
        )

    def pull_config(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        try:
            settings = self.settings()
            validate_settings(settings)
            if not settings.hostname:
                raise DownloaderError(ExitCode.CONFIG_ERROR, "Hostname is required.")
        except DownloaderError as exc:
            self.status.set(str(exc))
            messagebox.showwarning("Missing input", str(exc))
            return

        self.pull_button.config(state="disabled")
        self.status.set("Pulling running-config from Forward Networks...")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("end", f"Hostname: {settings.hostname}\n")
        self.detail_text.insert("end", f"Network ID: {settings.network_id}\n")
        self.detail_text.insert("end", f"Snapshot: {settings.snapshot_id or 'latest completed'}\n")
        self.detail_text.insert("end", f"Config file: {settings.config_file}\n\n")

        self.worker = threading.Thread(target=self._run_download, args=(settings,), daemon=True)
        self.worker.start()
        self.after(150, self._poll_result)

    def _run_download(self, settings: DownloaderSettings) -> None:
        log_path = configure_logging(settings.logs_dir)
        try:
            result = ForwardClient(settings).download()
        except DownloaderError as exc:
            log_event(logging.ERROR, "download_failed", exit_code=int(exc.exit_code), error=str(exc))
            self.result_queue.put(("error", (exc, log_path)))
        except Exception as exc:
            log_event(logging.ERROR, "unexpected_error", error=str(exc), traceback=traceback.format_exc())
            self.result_queue.put(("unexpected", (exc, log_path, traceback.format_exc())))
        else:
            self.result_queue.put(("success", (result, log_path)))

    def _poll_result(self) -> None:
        try:
            kind, payload = self.result_queue.get_nowait()
        except queue.Empty:
            self.after(150, self._poll_result)
            return

        self.pull_button.config(state="normal")
        if kind == "success":
            result, log_path = payload
            self.last_output_path = Path(result.output_path)
            self.last_log_path = Path(log_path)
            self.status.set(f"Wrote running-config: {result.output_path}")
            self.detail_text.insert("end", f"Saved: {result.output_path}\n")
            self.detail_text.insert("end", f"Snapshot: {result.snapshot_id}\n")
            self.detail_text.insert("end", f"Log: {log_path}\n")
            messagebox.showinfo("Config downloaded", f"Running-config saved:\n{result.output_path}")
        elif kind == "error":
            exc, log_path = payload
            self.last_log_path = Path(log_path)
            self.status.set(str(exc))
            self.detail_text.insert("end", f"ERROR: {exc}\nLog: {log_path}\n")
            messagebox.showerror("Download failed", f"{exc}\n\nLog: {log_path}")
        else:
            exc, log_path, tb_text = payload
            self.last_log_path = Path(log_path)
            self.status.set(f"Unexpected error: {exc}")
            self.detail_text.insert("end", f"ERROR: {exc}\nLog: {log_path}\n\n{tb_text}\n")
            messagebox.showerror("Unexpected error", f"{exc}\n\nLog: {log_path}")

    def open_last_output(self) -> None:
        if not self.last_output_path or not self.last_output_path.is_file():
            messagebox.showwarning(
                "Config Not Found",
                "Pull a running-config successfully before opening the last config.",
            )
            return
        open_path(self.last_output_path)

    def open_output_folder(self) -> None:
        folder = Path(self.output_dir.get().strip() or "manifests")
        folder.mkdir(parents=True, exist_ok=True)
        open_path(folder)

    def open_logs_folder(self) -> None:
        folder = self.last_log_path.parent if self.last_log_path else Path.cwd() / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        open_path(folder)

    def clear(self) -> None:
        self.hostname.set("")
        self.snapshot_id.set("")
        self.config_file.set("")
        self.last_output_path = None
        self.status.set("Ready. Enter a hostname and pull the running-config.")
        self.detail_text.delete("1.0", "end")
        self.refresh_environment_status()

def open_path(path: Path) -> None:
    resolved = path.resolve()
    system = platform.system()
    if system == "Windows":
        os.startfile(resolved)
    elif system == "Darwin":
        subprocess.run(["open", str(resolved)], check=False)
    else:
        webbrowser.open(resolved.as_uri())



def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
