# Copyright (C) 2026 https://ludditious.com/
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU Affero General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU Affero General Public License for more details.
#
#     You should have received a copy of the GNU Affero General Public License
#     along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Windows desktop UI for AdGuard Home sync."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from .app_config import (
    DEFAULT_OPTIONS,
    DEFAULT_SCHEDULE,
    config_path,
    load_app_config,
    new_target_id,
    save_app_config,
    to_sync_yaml_shape,
)
from .engine import run_sync, test_connection
from .run_log import append_run, clear_activity, read_activity
from .win_task import create_or_update_task, delete_task, query_task_summary, task_exists


class TargetDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, title: str, initial: dict | None = None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result: dict | None = None
        initial = initial or {}

        frm = ttk.Frame(self, padding=12)
        frm.grid(row=0, column=0, sticky="nsew")

        self.var_name = tk.StringVar(value=initial.get("name", ""))
        self.var_url = tk.StringVar(value=initial.get("url", "http://192.168.1.11:3000"))
        self.var_user = tk.StringVar(value=initial.get("username", "admin"))
        self.var_pass = tk.StringVar(value=initial.get("password", ""))
        self.var_enabled = tk.BooleanVar(value=initial.get("enabled", True))

        rows = [
            ("Display name", self.var_name),
            ("URL (http://ip:3000)", self.var_url),
            ("Username", self.var_user),
            ("Password", self.var_pass),
        ]
        for i, (label, var) in enumerate(rows):
            ttk.Label(frm, text=label).grid(row=i, column=0, sticky="w", pady=4)
            show = "*" if "pass" in label.lower() or var is self.var_pass else None
            ttk.Entry(frm, textvariable=var, width=42, show=show).grid(row=i, column=1, pady=4)
        ttk.Checkbutton(frm, text="Enabled", variable=self.var_enabled).grid(
            row=len(rows), column=1, sticky="w", pady=4
        )

        btns = ttk.Frame(frm)
        btns.grid(row=len(rows) + 1, column=0, columnspan=2, pady=(8, 0))
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Save", command=self._save).pack(side=tk.LEFT, padx=4)

        self.transient(parent)
        self.grab_set()
        self.wait_visibility()
        parent.update_idletasks()
        self.geometry(f"+{parent.winfo_rootx() + 40}+{parent.winfo_rooty() + 40}")

    def _save(self) -> None:
        url = self.var_url.get().strip()
        if not url:
            messagebox.showerror("Validation", "URL is required.", parent=self)
            return
        self.result = {
            "name": self.var_name.get().strip(),
            "url": url,
            "username": self.var_user.get().strip() or "admin",
            "password": self.var_pass.get(),
            "enabled": self.var_enabled.get(),
        }
        self.destroy()


class AGHomeSyncApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("AdGuard Home ToolBox")
        self.root.minsize(720, 520)
        self.cfg = load_app_config()
        self._build_ui()
        self._load_fields_from_config()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=8)
        outer.pack(fill=tk.BOTH, expand=True)

        nb = ttk.Notebook(outer)
        nb.pack(fill=tk.BOTH, expand=True)

        self.tab_source = ttk.Frame(nb, padding=10)
        self.tab_targets = ttk.Frame(nb, padding=10)
        self.tab_options = ttk.Frame(nb, padding=10)
        self.tab_schedule = ttk.Frame(nb, padding=10)
        self.tab_run = ttk.Frame(nb, padding=10)
        self.tab_log = ttk.Frame(nb, padding=10)
        nb.add(self.tab_source, text="Source")
        nb.add(self.tab_targets, text="Targets")
        nb.add(self.tab_options, text="Options")
        nb.add(self.tab_schedule, text="Schedule")
        nb.add(self.tab_run, text="Sync")
        nb.add(self.tab_log, text="Log")

        self._build_source_tab()
        self._build_targets_tab()
        self._build_options_tab()
        self._build_schedule_tab()
        self._build_run_tab()
        self._build_log_tab()

        status = ttk.Label(outer, text=f"Settings: {config_path()}", foreground="#555")
        status.pack(anchor="w", pady=(6, 0))

    def _build_source_tab(self) -> None:
        f = self.tab_source
        self.src_enabled = tk.BooleanVar()
        self.src_url = tk.StringVar()
        self.src_user = tk.StringVar()
        self.src_pass = tk.StringVar()

        ttk.Checkbutton(f, text="Source enabled (required for sync)", variable=self.src_enabled).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        fields = [
            ("Server URL", self.src_url),
            ("Username", self.src_user),
            ("Password", self.src_pass),
        ]
        for i, (label, var) in enumerate(fields, start=1):
            ttk.Label(f, text=label).grid(row=i, column=0, sticky="w", pady=4)
            show = "*" if label == "Password" else None
            ttk.Entry(f, textvariable=var, width=50, show=show).grid(row=i, column=1, sticky="w", pady=4)

        ttk.Button(f, text="Test source connection", command=self._test_source).grid(
            row=5, column=1, sticky="w", pady=12
        )
        ttk.Label(
            f,
            text="The source is the AdGuard Home instance all settings and lists are copied from.",
            wraplength=520,
        ).grid(row=6, column=0, columnspan=2, sticky="w")

    def _build_targets_tab(self) -> None:
        f = self.tab_targets
        cols = ("name", "url", "enabled")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=12)
        self.tree.heading("name", text="Name")
        self.tree.heading("url", text="URL")
        self.tree.heading("enabled", text="Enabled")
        self.tree.column("name", width=140)
        self.tree.column("url", width=320)
        self.tree.column("enabled", width=80, anchor="center")
        self.tree.grid(row=0, column=0, columnspan=4, sticky="nsew")

        sb = ttk.Scrollbar(f, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.grid(row=0, column=4, sticky="ns")

        ttk.Button(f, text="Add", command=self._add_target).grid(row=1, column=0, pady=8, sticky="w")
        ttk.Button(f, text="Edit", command=self._edit_target).grid(row=1, column=1, pady=8, sticky="w")
        ttk.Button(f, text="Delete", command=self._delete_target).grid(row=1, column=2, pady=8, sticky="w")
        ttk.Button(f, text="Test selected", command=self._test_target).grid(row=1, column=3, pady=8, sticky="w")

        f.rowconfigure(0, weight=1)
        f.columnconfigure(0, weight=1)

    def _build_options_tab(self) -> None:
        f = self.tab_options
        self.opt_vars: dict[str, tk.BooleanVar] = {}
        for i, (key, default) in enumerate(DEFAULT_OPTIONS.items()):
            var = tk.BooleanVar(value=default)
            self.opt_vars[key] = var
            label = key.replace("_", " ")
            ttk.Checkbutton(f, text=label, variable=var).grid(row=i, column=0, sticky="w", pady=2)

    def _build_schedule_tab(self) -> None:
        f = self.tab_schedule
        self.sched_enabled = tk.BooleanVar()
        self.sched_kind = tk.StringVar(value="minutes")
        self.sched_interval = tk.StringVar(value="30")
        self.sched_time = tk.StringVar(value="03:00")
        self.sched_dow = tk.StringVar(value="MON")
        self.task_status = tk.StringVar()

        ttk.Checkbutton(
            f, text="Enable scheduled sync (creates a Windows task)", variable=self.sched_enabled
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Label(f, text="Run every").grid(row=1, column=0, sticky="w")
        kind = ttk.Combobox(
            f,
            textvariable=self.sched_kind,
            values=("minutes", "hours", "daily", "weekly"),
            state="readonly",
            width=12,
        )
        kind.grid(row=1, column=1, sticky="w")
        kind.bind("<<ComboboxSelected>>", lambda _e: self._update_schedule_hints())

        ttk.Label(f, text="Interval / value").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(f, textvariable=self.sched_interval, width=8).grid(row=2, column=1, sticky="w", pady=4)
        self.lbl_interval_hint = ttk.Label(f, text="(minutes between runs)")
        self.lbl_interval_hint.grid(row=2, column=2, sticky="w", padx=8)

        ttk.Label(f, text="Time (HH:MM, daily/weekly)").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(f, textvariable=self.sched_time, width=8).grid(row=3, column=1, sticky="w", pady=4)

        ttk.Label(f, text="Day (weekly)").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Combobox(
            f,
            textvariable=self.sched_dow,
            values=("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"),
            state="readonly",
            width=8,
        ).grid(row=4, column=1, sticky="w", pady=4)

        btns = ttk.Frame(f)
        btns.grid(row=5, column=0, columnspan=3, pady=16, sticky="w")
        ttk.Button(btns, text="Apply / update Windows task", command=self._apply_schedule).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(btns, text="Remove Windows task", command=self._remove_schedule).pack(side=tk.LEFT)

        ttk.Label(f, textvariable=self.task_status, wraplength=560).grid(
            row=6, column=0, columnspan=3, sticky="w"
        )
        self._refresh_task_status()

    def _build_run_tab(self) -> None:
        f = self.tab_run
        top = ttk.Frame(f)
        top.pack(fill=tk.X)
        ttk.Button(top, text="Save settings", command=self._save_from_fields).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(top, text="Sync now", command=self._sync_now).pack(side=tk.LEFT)
        ttk.Label(
            f,
            text="Each sync and scheduled run is recorded on the Log tab.",
            wraplength=640,
        ).pack(anchor="w", pady=(12, 0))

    def _build_log_tab(self) -> None:
        f = self.tab_log
        top = ttk.Frame(f)
        top.pack(fill=tk.X)
        ttk.Button(top, text="Refresh", command=self._reload_log_view).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(top, text="Clear log", command=self._clear_log).pack(side=tk.LEFT)

        self.log = scrolledtext.ScrolledText(f, height=24, state=tk.DISABLED, wrap=tk.WORD)
        self.log.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self._reload_log_view()

    def _update_schedule_hints(self) -> None:
        k = self.sched_kind.get()
        if k == "minutes":
            self.lbl_interval_hint.config(text="(minutes between runs)")
        elif k == "hours":
            self.lbl_interval_hint.config(text="(hours between runs)")
        elif k == "daily":
            self.lbl_interval_hint.config(text="(ignored for daily — uses time below)")
        else:
            self.lbl_interval_hint.config(text="(ignored for weekly — uses day + time)")

    def _load_fields_from_config(self) -> None:
        src = self.cfg.get("source") or {}
        self.src_enabled.set(bool(src.get("enabled", True)))
        self.src_url.set(src.get("url", ""))
        self.src_user.set(src.get("username", "admin"))
        self.src_pass.set(src.get("password", ""))

        for t in self.tree.get_children():
            self.tree.delete(t)
        for t in self.cfg.get("targets") or []:
            self.tree.insert(
                "",
                tk.END,
                iid=t["id"],
                values=(t.get("name", ""), t.get("url", ""), "Yes" if t.get("enabled", True) else "No"),
            )

        opts = self.cfg.get("options") or {}
        for key, var in self.opt_vars.items():
            var.set(bool(opts.get(key, DEFAULT_OPTIONS.get(key, False))))

        sch = self.cfg.get("schedule") or {}
        self.sched_enabled.set(bool(sch.get("enabled", False)))
        self.sched_kind.set(sch.get("kind", "minutes"))
        self.sched_interval.set(str(sch.get("interval", 30)))
        self.sched_time.set(sch.get("time", "03:00"))
        self.sched_dow.set(sch.get("day_of_week", "MON"))
        self._update_schedule_hints()

    def _fields_to_config(self) -> None:
        self.cfg["source"] = {
            "url": self.src_url.get().strip(),
            "username": self.src_user.get().strip() or "admin",
            "password": self.src_pass.get(),
            "enabled": self.src_enabled.get(),
        }
        opts = {}
        for key, var in self.opt_vars.items():
            opts[key] = var.get()
        self.cfg["options"] = opts
        self.cfg["schedule"] = {
            "enabled": self.sched_enabled.get(),
            "kind": self.sched_kind.get(),
            "interval": int(self.sched_interval.get() or "1"),
            "time": self.sched_time.get().strip() or "03:00",
            "day_of_week": self.sched_dow.get(),
        }

    def _save_from_fields(self) -> None:
        try:
            self._fields_to_config()
            save_app_config(self.cfg)
            messagebox.showinfo("Saved", f"Settings saved to:\n{config_path()}", parent=self.root)
        except ValueError as e:
            messagebox.showerror("Save failed", str(e), parent=self.root)

    def _on_close(self) -> None:
        try:
            self._fields_to_config()
            save_app_config(self.cfg)
        except ValueError:
            pass
        self.root.destroy()

    def _reload_log_view(self) -> None:
        text = read_activity()
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        if text.strip():
            self.log.insert(tk.END, text)
        else:
            self.log.insert(tk.END, "(No activity yet. Run a sync or connection test.)\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _clear_log(self) -> None:
        if not messagebox.askyesno("Clear log", "Delete all log history?", parent=self.root):
            return
        clear_activity()
        self._reload_log_view()

    def _record_activity(self, title: str, body: str) -> None:
        append_run(title, body)
        self._reload_log_view()

    def _run_bg(self, work, on_done) -> None:
        def runner() -> None:
            try:
                result = work()
            except Exception as e:
                result = e
            self.root.after(0, lambda: on_done(result))

        threading.Thread(target=runner, daemon=True).start()

    def _test_source(self) -> None:
        self._save_from_fields()
        verify = self.opt_vars["verify_tls"].get()

        def work():
            return test_connection(
                self.cfg["source"]["url"],
                self.cfg["source"]["username"],
                self.cfg["source"]["password"],
                verify_tls=verify,
            )

        def done(res) -> None:
            self._show_test_result(res, label="Source")

        self._run_bg(work, done)

    def _show_test_result(self, res, *, label: str) -> None:
        if isinstance(res, Exception):
            msg = str(res)
            self._record_activity(f"{label} connection test", f"FAILED: {msg}")
            messagebox.showerror("Connection failed", msg, parent=self.root)
            return
        if res.ok:
            self._record_activity(f"{label} connection test", res.message)
            messagebox.showinfo(res.title, res.message, parent=self.root)
        else:
            self._record_activity(f"{label} connection test", f"{res.title}: {res.message}")
            messagebox.showerror(res.title, res.message, parent=self.root)

    def _selected_target(self) -> dict | None:
        sel = self.tree.selection()
        if not sel:
            return None
        tid = sel[0]
        for t in self.cfg.get("targets") or []:
            if t["id"] == tid:
                return t
        return None

    def _test_target(self) -> None:
        t = self._selected_target()
        if not t:
            messagebox.showwarning("Test", "Select a target first.", parent=self.root)
            return
        verify = self.opt_vars["verify_tls"].get()

        def work():
            return test_connection(t["url"], t["username"], t["password"], verify_tls=verify)

        def done(res) -> None:
            name = t.get("name") or t.get("url") or "Target"
            self._show_test_result(res, label=name)

        self._run_bg(work, done)

    def _add_target(self) -> None:
        dlg = TargetDialog(self.root, "Add target")
        self.root.wait_window(dlg)
        if not dlg.result:
            return
        entry = {**dlg.result, "id": new_target_id()}
        self.cfg.setdefault("targets", []).append(entry)
        self.tree.insert(
            "",
            tk.END,
            iid=entry["id"],
            values=(entry["name"], entry["url"], "Yes" if entry["enabled"] else "No"),
        )
        save_app_config(self.cfg)

    def _edit_target(self) -> None:
        t = self._selected_target()
        if not t:
            messagebox.showwarning("Edit", "Select a target first.", parent=self.root)
            return
        dlg = TargetDialog(self.root, "Edit target", initial=t)
        self.root.wait_window(dlg)
        if not dlg.result:
            return
        t.update(dlg.result)
        self.tree.item(
            t["id"],
            values=(t["name"], t["url"], "Yes" if t.get("enabled", True) else "No"),
        )
        save_app_config(self.cfg)

    def _delete_target(self) -> None:
        t = self._selected_target()
        if not t:
            messagebox.showwarning("Delete", "Select a target first.", parent=self.root)
            return
        if not messagebox.askyesno("Delete", f"Remove target {t.get('name') or t['url']}?", parent=self.root):
            return
        self.cfg["targets"] = [x for x in self.cfg.get("targets", []) if x["id"] != t["id"]]
        self.tree.delete(t["id"])
        save_app_config(self.cfg)

    def _refresh_task_status(self) -> None:
        if task_exists():
            self.task_status.set(query_task_summary())
        else:
            self.task_status.set("No Windows scheduled task registered.")

    def _apply_schedule(self) -> None:
        self._fields_to_config()
        save_app_config(self.cfg)
        ok, msg = create_or_update_task(self.cfg["schedule"])
        self._refresh_task_status()
        (messagebox.showinfo if ok else messagebox.showerror)("Schedule", msg, parent=self.root)

    def _remove_schedule(self) -> None:
        self.sched_enabled.set(False)
        self._fields_to_config()
        save_app_config(self.cfg)
        ok, msg = delete_task()
        self._refresh_task_status()
        (messagebox.showinfo if ok else messagebox.showerror)("Schedule", msg, parent=self.root)

    def _sync_now(self) -> None:
        self._fields_to_config()
        save_app_config(self.cfg)
        try:
            sync_cfg = to_sync_yaml_shape(self.cfg)
        except ValueError as e:
            messagebox.showerror("Sync", str(e), parent=self.root)
            return

        def work():
            return run_sync(sync_cfg)

        def done(res) -> None:
            if isinstance(res, Exception):
                self._record_activity("Manual sync", f"FAILED: {res}")
                messagebox.showerror("Sync failed", str(res), parent=self.root)
                return
            code, lines = res
            body = "\n".join(lines) + f"\n\nExit code: {code}"
            self._record_activity("Manual sync", body)
            if code == 0:
                messagebox.showinfo("Sync", "Sync completed successfully. See Log tab for details.", parent=self.root)
            else:
                messagebox.showwarning("Sync", "Sync finished with errors. See Log tab.", parent=self.root)

        self._run_bg(work, done)

    def run(self) -> None:
        self.root.mainloop()


def run_gui() -> None:
    AGHomeSyncApp().run()
