from __future__ import annotations

import logging
import os
import sys
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .cli import (
    DEFAULT_BOUNDARY_PATTERN,
    DEFAULT_DEVICES_PATH_TEMPLATES,
    DEFAULT_NETWORK_ID,
    DEFAULT_TOPOLOGY_PATH_TEMPLATES,
    configure_logging,
    validate_settings,
)
from .client import ForwardTopologyClient, MapperError
from .models import AuthSettings, MapperSettings
from .render import write_blueprint


APP_TITLE = "Forward Networks Topology Mapper"
APP_VERSION = "v0.4.0"


def default_output_dir() -> str:
    return str(Path("..") / "docs")


def bundled_sample_payload_path() -> Path:
    if getattr(sys, "frozen", False):
        base_path = Path(getattr(sys, "_MEIPASS", Path.cwd()))
        return base_path / "examples" / "sanitized-topology.json"
    return Path(__file__).resolve().parents[2] / "examples" / "sanitized-topology.json"


def bundled_icon_path() -> Path:
    if getattr(sys, "frozen", False):
        base_path = Path(getattr(sys, "_MEIPASS", Path.cwd()))
        return base_path / "assets" / "topology_mapper.ico"
    return Path(__file__).resolve().parents[2] / "assets" / "topology_mapper.ico"


def set_window_icon(root: tk.Tk) -> None:
    icon_path = bundled_icon_path()
    if icon_path.exists():
        try:
            root.iconbitmap(default=str(icon_path))
        except tk.TclError:
            pass


def build_settings_from_values(values: dict[str, str]) -> MapperSettings:
    use_offline_text = values.get("use_offline", "")
    use_offline = use_offline_text.lower() in {"1", "true", "yes", "on"}
    if "use_offline" not in values:
        use_offline = bool(values.get("local_payload", "").strip())
    local_payload_text = values.get("local_payload", "").strip() if use_offline else ""
    snapshot_id = values.get("snapshot_id", "").strip() or None
    auth_mode = values.get("auth_mode", "basic").strip() or "basic"
    api_token = values.get("api_token", "").strip() or None
    output_dir = Path(values.get("output_dir", "").strip() or default_output_dir())
    logs_dir = Path(values.get("logs_dir", "").strip() or "logs")
    timeout_text = values.get("timeout_seconds", "").strip() or "30"

    return MapperSettings(
        base_url=values.get("base_url", "").strip() or "https://fwd.app",
        api_prefix=values.get("api_prefix", "").strip() or "/api",
        network_id=values.get("network_id", "").strip() or DEFAULT_NETWORK_ID,
        snapshot_id=snapshot_id,
        hostname=values.get("hostname", "").strip(),
        topology_path_templates=DEFAULT_TOPOLOGY_PATH_TEMPLATES,
        devices_path_templates=DEFAULT_DEVICES_PATH_TEMPLATES,
        output_dir=output_dir,
        logs_dir=logs_dir,
        timeout_seconds=float(timeout_text),
        boundary_pattern=values.get("boundary_pattern", "").strip() or DEFAULT_BOUNDARY_PATTERN,
        local_payload=Path(local_payload_text) if local_payload_text else None,
        auth=AuthSettings(
            mode=auth_mode,  # type: ignore[arg-type]
            token=api_token,
            key=os.environ.get("FORWARD_NETWORKS_KEY"),
            secret=os.environ.get("FORWARD_NETWORKS_SECRET"),
        ),
    )


def run_mapper(settings: MapperSettings, progress=None):
    log_path = configure_logging(settings.logs_dir)
    try:
        if progress:
            progress("Stage 1/5: Validating settings...")
        validate_settings(settings)
        if progress:
            progress("Stage 2/5: Reading topology source...")
        blueprint = ForwardTopologyClient(settings).build_blueprint()
        if progress:
            progress("Stage 4/5: Writing Markdown and SVG outputs...")
        result = write_blueprint(blueprint, settings.output_dir)
        logging.info(
            "gui_mapper_success hostname=%s snapshot_id=%s markdown=%s svg=%s",
            blueprint.target.hostname,
            blueprint.snapshot_id,
            result.markdown_path,
            result.svg_path,
        )
        return blueprint, result, log_path
    finally:
        logging.shutdown()


class TopologyMapperApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        set_window_icon(self.root)
        self.root.geometry("1040x820")
        self.root.minsize(900, 700)

        self.vars = {
            "hostname": tk.StringVar(),
            "base_url": tk.StringVar(value=os.environ.get("FWD_BASE_URL", "https://fwd.app")),
            "api_prefix": tk.StringVar(value=os.environ.get("FWD_API_PREFIX", "/api")),
            "network_id": tk.StringVar(value=os.environ.get("FORWARD_NETWORKS_NETWORK_ID", DEFAULT_NETWORK_ID)),
            "snapshot_id": tk.StringVar(),
            "auth_mode": tk.StringVar(value=os.environ.get("FWD_AUTH_MODE", "basic")),
            "api_token": tk.StringVar(value=os.environ.get("FWD_API_TOKEN", "")),
            "boundary_pattern": tk.StringVar(value=DEFAULT_BOUNDARY_PATTERN),
            "use_offline": tk.StringVar(value="0"),
            "local_payload": tk.StringVar(),
            "output_dir": tk.StringVar(value=default_output_dir()),
            "logs_dir": tk.StringVar(value="logs"),
            "timeout_seconds": tk.StringVar(value="30"),
        }
        self.running = False
        self.last_output_dir: Path | None = None
        self.last_markdown_path: Path | None = None
        self.last_svg_path: Path | None = None
        self.last_log_path: Path | None = None
        self.configure_styles()
        self.build_gui()

    def configure_styles(self) -> None:
        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.style.configure("App.TFrame", background="#eef2f6")
        self.style.configure("Card.TFrame", background="#ffffff")
        self.style.configure(
            "Card.TLabelframe",
            background="#ffffff",
            bordercolor="#d8dee9",
            borderwidth=1,
            relief="solid",
        )
        self.style.configure(
            "Card.TLabelframe.Label",
            background="#eef2f6",
            foreground="#1d3344",
            font=("Segoe UI", 10, "bold"),
        )
        self.style.configure("Card.TLabel", background="#ffffff", foreground="#536879", font=("Segoe UI", 9))
        self.style.configure("Hint.TLabel", background="#ffffff", foreground="#6b7780", font=("Segoe UI", 9))
        self.style.configure("Summary.TLabel", background="#ffffff", foreground="#223b4d", font=("Segoe UI", 9))
        self.style.configure("Status.TLabel", background="#e8edf1", foreground="#223b4d", font=("Segoe UI", 9))
        self.style.configure("TEntry", fieldbackground="#ffffff", bordercolor="#cbd5e1", lightcolor="#cbd5e1", darkcolor="#cbd5e1", padding=5)
        self.style.configure("TCombobox", fieldbackground="#ffffff", padding=4)
        self.style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 7), foreground="#ffffff", background="#0877d1")
        self.style.map("Primary.TButton", background=[("active", "#0b6fbf"), ("disabled", "#8fbce1")], foreground=[("disabled", "#eef6ff")])
        self.style.configure("Secondary.TButton", font=("Segoe UI", 9), padding=(12, 6), foreground="#1d3344", background="#f8fafc")
        self.style.map("Secondary.TButton", background=[("active", "#e8eef7"), ("disabled", "#edf2f7")], foreground=[("disabled", "#94a3b8")])
        self.style.configure("TCheckbutton", background="#ffffff", foreground="#223b4d", font=("Segoe UI", 9))

    def action_button(self, parent, text: str, command, variant: str = "secondary", state: str = "normal") -> tk.Button:
        colors = {
            "primary": {"bg": "#0877d1", "fg": "#ffffff", "activebackground": "#0b6fbf", "activeforeground": "#ffffff"},
            "secondary": {"bg": "#f8fafc", "fg": "#1d3344", "activebackground": "#e8eef7", "activeforeground": "#1d3344"},
        }
        selected = colors[variant]
        button = tk.Button(
            parent,
            text=text,
            command=command,
            state=state,
            bg=selected["bg"],
            fg=selected["fg"],
            activebackground=selected["activebackground"],
            activeforeground=selected["activeforeground"],
            disabledforeground="#64748b",
            relief="solid",
            borderwidth=1,
            highlightthickness=0,
            font=("Segoe UI", 9 if variant == "secondary" else 10, "bold" if variant == "primary" else "normal"),
            padx=14,
            pady=5,
            cursor="hand2",
        )
        return button

    def build_gui(self) -> None:
        self.root.configure(bg="#eef2f6")

        header = tk.Frame(self.root, bg="#172033")
        header.pack(fill="x")
        tk.Label(
            header,
            text=f"{APP_TITLE}  {APP_VERSION}",
            bg="#172033",
            fg="white",
            font=("Segoe UI", 18, "bold"),
        ).pack(side="left", padx=18, pady=(12, 2))
        tk.Label(
            header,
            text="Read-only topology blueprint and SVG map generator",
            bg="#172033",
            fg="#cbd5e1",
            font=("Segoe UI", 9),
        ).pack(side="right", padx=18, pady=18)

        body = ttk.Frame(self.root, style="App.TFrame")
        body.pack(fill="both", expand=True, padx=14, pady=14)

        safety = tk.Label(
            body,
            text="Read-only: this tool queries Forward Networks data and writes local reports. It does not connect to devices or make network changes.",
            bg="#e8f3ff",
            fg="#1c496d",
            anchor="w",
            font=("Segoe UI", 9, "bold"),
        )
        safety.pack(fill="x", pady=(0, 10), ipady=6, padx=1)

        summary = ttk.LabelFrame(body, text="Run Summary", style="Card.TLabelframe")
        summary.pack(fill="x", pady=(0, 10))
        self.mode_summary_var = tk.StringVar()
        self.auth_summary_var = tk.StringVar()
        self.output_summary_var = tk.StringVar()
        self.last_result_var = tk.StringVar(value="Last result: Not run yet")
        self._summary_label(summary, 0, self.mode_summary_var)
        self._summary_label(summary, 1, self.auth_summary_var)
        self._summary_label(summary, 2, self.output_summary_var)
        self._summary_label(summary, 3, self.last_result_var)

        inputs = ttk.LabelFrame(body, text="1. Target", style="Card.TLabelframe")
        inputs.pack(fill="x", pady=(0, 10))
        self._entry(inputs, 0, "Target hostname", "hostname", required=True)
        ttk.Label(inputs, text="Enter the exact Forward Networks device hostname for the access switch you want to map.", style="Hint.TLabel").grid(row=0, column=2, sticky="w", padx=(0, 10), pady=5)
        self._entry(inputs, 1, "Network ID", "network_id")
        self._entry(inputs, 2, "Snapshot ID", "snapshot_id", hint="Blank uses latest successful snapshot.")

        api = ttk.LabelFrame(body, text="2. Forward API / Auth", style="Card.TLabelframe")
        api.pack(fill="x", pady=(0, 10))
        self._entry(api, 0, "Base URL", "base_url")
        self._entry(api, 1, "API prefix", "api_prefix")
        ttk.Label(api, text="Auth mode", style="Card.TLabel").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        ttk.Combobox(api, textvariable=self.vars["auth_mode"], values=["basic", "bearer"], state="readonly", width=16).grid(row=2, column=1, sticky="w", padx=10, pady=5)
        self._entry(api, 3, "Bearer token", "api_token", show="*", hint="Basic auth uses FORWARD_NETWORKS_KEY and FORWARD_NETWORKS_SECRET from environment.")

        output = ttk.LabelFrame(body, text="3. Output", style="Card.TLabelframe")
        output.pack(fill="x", pady=(0, 10))
        self._entry(output, 0, "Output directory", "output_dir", browse=self.browse_output_dir)
        self._entry(output, 1, "Logs directory", "logs_dir", browse=self.browse_logs_dir)
        self._entry(output, 2, "Stop expansion at devices matching", "boundary_pattern")
        self._entry(output, 3, "Timeout seconds", "timeout_seconds")

        offline = ttk.LabelFrame(body, text="Advanced / Offline Test Mode", style="Card.TLabelframe")
        offline.pack(fill="x", pady=(0, 10))
        ttk.Checkbutton(
            offline,
            text="Use offline test JSON instead of Forward API",
            variable=self.vars["use_offline"],
            onvalue="1",
            offvalue="0",
            command=self.refresh_ui_state,
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=5)
        self.offline_fields = ttk.Frame(offline, style="Card.TFrame")
        self.offline_fields.grid(row=1, column=0, columnspan=3, sticky="ew")
        self._entry(
            self.offline_fields,
            0,
            "Offline test JSON",
            "local_payload",
            browse=self.browse_local_payload,
            hint="Leave blank for normal Forward API runs.",
        )
        offline.columnconfigure(0, weight=1)

        actions = ttk.Frame(body, style="App.TFrame")
        actions.pack(fill="x", pady=(0, 10))
        self.run_button = self.action_button(actions, "Build Topology Map", self.start_run, "primary")
        self.run_button.pack(side="left", padx=(0, 8))
        self.action_button(actions, "Load Sample Offline Data", self.use_sample_payload).pack(side="left", padx=4)
        self.action_button(actions, "Clear Output", self.clear_output).pack(side="right")
        self.open_folder_button = self.action_button(actions, "Open Output Folder", self.open_output_folder, state="disabled")
        self.open_folder_button.pack(side="right", padx=4)
        self.open_svg_button = self.action_button(actions, "Open SVG", self.open_svg, state="disabled")
        self.open_svg_button.pack(side="right", padx=4)
        self.open_markdown_button = self.action_button(actions, "Open Markdown", self.open_markdown, state="disabled")
        self.open_markdown_button.pack(side="right", padx=4)

        self.output_text = tk.Text(body, wrap="word", height=9, bg="#101c26", fg="#e8eef3", insertbackground="white", font=("Consolas", 10), relief="flat")
        self.output_text.pack(fill="both", expand=True)
        self.output_text.tag_configure("info", foreground="#e8eef3")
        self.output_text.tag_configure("success", foreground="#7ee787")
        self.output_text.tag_configure("error", foreground="#ff7b72")

        self.status_var = tk.StringVar(value="Ready. Enter a target hostname to build a topology map.")
        ttk.Label(self.root, textvariable=self.status_var, anchor="w", style="Status.TLabel").pack(fill="x", padx=0, pady=0, ipady=6)
        self.refresh_ui_state()
        for key in ("auth_mode", "output_dir", "use_offline", "local_payload", "api_token"):
            self.vars[key].trace_add("write", lambda *_args: self.refresh_ui_state())

    def _entry(self, parent, row: int, label: str, key: str, required: bool = False, browse=None, hint: str = "", show: str | None = None) -> None:
        label_text = f"{label}{' *' if required else ''}"
        ttk.Label(parent, text=label_text, style="Card.TLabel").grid(row=row, column=0, sticky="w", padx=10, pady=6)
        entry = ttk.Entry(parent, textvariable=self.vars[key], show=show or "")
        entry.grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        if browse:
            ttk.Button(parent, text="Browse", command=browse, style="Secondary.TButton").grid(row=row, column=2, sticky="ew", padx=(0, 10), pady=5)
        elif hint:
            ttk.Label(parent, text=hint, anchor="w", style="Hint.TLabel").grid(row=row, column=2, sticky="w", padx=(0, 10), pady=5)
        parent.columnconfigure(1, weight=1)

    def _summary_label(self, parent, column: int, variable: tk.StringVar) -> None:
        ttk.Label(
            parent,
            textvariable=variable,
            anchor="w",
            style="Summary.TLabel",
        ).grid(row=0, column=column, sticky="ew", padx=10, pady=8)
        parent.columnconfigure(column, weight=1)

    def refresh_ui_state(self) -> None:
        offline_enabled = self.vars["use_offline"].get() == "1"
        if offline_enabled:
            self.offline_fields.grid()
        else:
            self.offline_fields.grid_remove()

        mode = "Offline test JSON" if offline_enabled else "Forward API"
        self.mode_summary_var.set(f"Mode: {mode}")

        auth_mode = self.vars["auth_mode"].get()
        if offline_enabled:
            auth_text = "Auth: Not used in offline mode"
        elif auth_mode == "bearer":
            auth_text = "Auth: Bearer token entered" if self.vars["api_token"].get().strip() else "Auth: Bearer token missing"
        else:
            key_detected = "detected" if os.environ.get("FORWARD_NETWORKS_KEY") else "missing"
            secret_detected = "detected" if os.environ.get("FORWARD_NETWORKS_SECRET") else "missing"
            auth_text = f"Auth: Env key {key_detected}, secret {secret_detected}"
        self.auth_summary_var.set(auth_text)
        self.output_summary_var.set(f"Output: {self.vars['output_dir'].get().strip() or default_output_dir()}")

    def browse_local_payload(self) -> None:
        filename = filedialog.askopenfilename(title="Select offline test topology JSON", filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if filename:
            self.vars["local_payload"].set(filename)

    def browse_output_dir(self) -> None:
        folder = filedialog.askdirectory(title="Select output directory")
        if folder:
            self.vars["output_dir"].set(folder)

    def browse_logs_dir(self) -> None:
        folder = filedialog.askdirectory(title="Select logs directory")
        if folder:
            self.vars["logs_dir"].set(folder)

    def use_sample_payload(self) -> None:
        sample = bundled_sample_payload_path()
        if sample.exists():
            self.vars["use_offline"].set("1")
            self.vars["local_payload"].set(str(sample))
            if not self.vars["hostname"].get().strip():
                self.vars["hostname"].set("ACCESS-SW01")
            self.write_output(f"Selected offline test data: {sample}\n", "info")
        else:
            messagebox.showwarning("Sample not found", f"Could not find offline sample data:\n{sample}")

    def clear_output(self) -> None:
        self.output_text.delete("1.0", "end")

    def values(self) -> dict[str, str]:
        return {key: var.get() for key, var in self.vars.items()}

    def start_run(self) -> None:
        if self.running:
            return
        try:
            settings = build_settings_from_values(self.values())
        except ValueError as exc:
            messagebox.showerror("Invalid settings", f"Check numeric fields.\n\n{exc}")
            return
        if not settings.hostname:
            messagebox.showwarning("Missing hostname", "Enter the target switch hostname.")
            return
        self.running = True
        self.run_button.configure(state="disabled")
        self.set_result_buttons_enabled(False)
        self.last_result_var.set("Last result: Running")
        self.status_var.set("Stage 1/5: Validating settings...")
        self.write_output(f"\nStarting topology build for {settings.hostname}...\n", "info")
        threading.Thread(target=self.worker, args=(settings,), daemon=True).start()

    def worker(self, settings: MapperSettings) -> None:
        try:
            blueprint, result, log_path = run_mapper(settings, self.post_progress)
        except MapperError as exc:
            self.root.after(0, lambda: self.finish_error(f"{exc}\nExit code: {int(exc.exit_code)}"))
        except Exception:
            self.root.after(0, lambda: self.finish_error(traceback.format_exc()))
        else:
            self.root.after(0, lambda: self.status_var.set("Stage 5/5: Finalizing outputs..."))
            self.root.after(0, lambda: self.finish_success(blueprint.snapshot_id, result.markdown_path, result.svg_path, log_path))

    def post_progress(self, message: str) -> None:
        self.root.after(0, lambda: self.status_var.set(message))

    def finish_success(self, snapshot_id: str, markdown_path: Path, svg_path: Path, log_path: Path) -> None:
        self.running = False
        self.run_button.configure(state="normal")
        self.last_output_dir = markdown_path.parent
        self.last_markdown_path = markdown_path
        self.last_svg_path = svg_path
        self.last_log_path = log_path
        self.set_result_buttons_enabled(True)
        self.status_var.set(f"Complete. Wrote outputs for snapshot {snapshot_id}.")
        self.last_result_var.set(f"Last result: Success, snapshot {snapshot_id}")
        self.write_output(f"SUCCESS: Wrote topology blueprint from snapshot {snapshot_id}\n", "success")
        self.write_output(f"Markdown: {markdown_path}\n", "success")
        self.write_output(f"SVG:      {svg_path}\n", "success")
        self.write_output(f"Log:      {log_path}\n", "info")

    def finish_error(self, message: str) -> None:
        self.running = False
        self.run_button.configure(state="normal")
        self.set_result_buttons_enabled(False)
        self.status_var.set("Topology build failed. See details.")
        self.last_result_var.set("Last result: Failed")
        self.write_output(f"ERROR: {message}\n", "error")

    def write_output(self, text: str, tag: str = "info") -> None:
        self.output_text.insert("end", text, tag)
        self.output_text.see("end")

    def set_result_buttons_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.open_markdown_button.configure(state=state)
        self.open_svg_button.configure(state=state)
        self.open_folder_button.configure(state=state)

    def open_markdown(self) -> None:
        self.open_path(self.last_markdown_path)

    def open_svg(self) -> None:
        self.open_path(self.last_svg_path)

    def open_output_folder(self) -> None:
        self.open_path(self.last_output_dir)

    def open_path(self, path: Path | None) -> None:
        if not path:
            return
        if not path.exists():
            messagebox.showwarning("Path not found", f"Could not find:\n{path}")
            return
        os.startfile(path)  # type: ignore[attr-defined]


def main() -> None:
    root = tk.Tk()
    TopologyMapperApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
