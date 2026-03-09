import json
import os
from datetime import datetime
from tkinter import messagebox
from typing import Optional

import customtkinter as ctk

import database
from vlc_monitor import VLCMonitor

# ── Theme ────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ACCENT = "#4da6ff"
ACCENT_GREEN = "#4dff88"
CARD_BG = "#1e1f2e"
HEADER_BG = "#13131f"
DANGER = "#c0392b"
DANGER_HOVER = "#a93226"
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


# ── Dialogs ───────────────────────────────────────────────────────────────────

class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, config: dict, on_save):
        super().__init__(parent)
        self.title("VLC Settings")
        self.geometry("400x320")
        self.resizable(False, False)
        self.grab_set()
        self.lift()

        self._on_save = on_save

        ctk.CTkLabel(
            self, text="VLC HTTP Interface", font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(24, 4))
        ctk.CTkLabel(
            self,
            text="Enable in VLC → Tools → Preferences → Show All\n"
                 "→ Interface → Main interfaces → ☑ Web\n"
                 "→ Lua HTTP → set a Password → restart VLC",
            font=ctk.CTkFont(size=11),
            text_color="gray55",
            justify="center",
        ).pack(pady=(0, 16))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(padx=40, fill="x")
        form.columnconfigure(1, weight=1)

        def row(label, var, r, show=""):
            ctk.CTkLabel(form, text=label, anchor="w").grid(
                row=r, column=0, sticky="w", pady=6
            )
            e = ctk.CTkEntry(form, textvariable=var, show=show)
            e.grid(row=r, column=1, padx=(12, 0), sticky="ew", pady=6)

        self._host = ctk.StringVar(value=config.get("host", "localhost"))
        self._port = ctk.StringVar(value=str(config.get("port", 8080)))
        self._pwd = ctk.StringVar(value=config.get("password", ""))
        row("Host:", self._host, 0)
        row("Port:", self._port, 1)
        row("Password:", self._pwd, 2, show="•")

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=20)
        ctk.CTkButton(btns, text="Save", width=110, command=self._save).pack(
            side="left", padx=6
        )
        ctk.CTkButton(
            btns,
            text="Cancel",
            width=110,
            fg_color="gray25",
            hover_color="gray35",
            command=self.destroy,
        ).pack(side="left", padx=6)

    def _save(self):
        try:
            port = int(self._port.get())
        except ValueError:
            messagebox.showerror("Error", "Port must be a number.", parent=self)
            return
        self._on_save({"host": self._host.get(), "port": port, "password": self._pwd.get()})
        self.destroy()


class EditShowDialog(ctk.CTkToplevel):
    def __init__(self, parent, show: Optional[dict], on_save):
        super().__init__(parent)
        is_new = show is None
        self.title("Add Show" if is_new else "Edit Show")
        self.geometry("360x280")
        self.resizable(False, False)
        self.grab_set()
        self.lift()

        self._show = show
        self._on_save = on_save

        heading = "Add New Show" if is_new else f"Edit  ·  {show['name']}"
        ctk.CTkLabel(self, text=heading, font=ctk.CTkFont(size=15, weight="bold")).pack(
            pady=(22, 16)
        )

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(padx=40, fill="x")
        form.columnconfigure(1, weight=1)

        def row(label, var, r, width=None):
            ctk.CTkLabel(form, text=label, anchor="w").grid(
                row=r, column=0, sticky="w", pady=7
            )
            kw = {"textvariable": var}
            if width:
                kw["width"] = width
            e = ctk.CTkEntry(form, **kw)
            e.grid(row=r, column=1, padx=(12, 0), sticky="ew", pady=7)

        self._name = ctk.StringVar(value="" if is_new else show["name"])
        self._season = ctk.StringVar(value=str(1 if is_new else show["current_season"]))
        self._episode = ctk.StringVar(value=str(1 if is_new else show["current_episode"]))

        r = 0
        if is_new:
            row("Show Name:", self._name, r)
            r += 1
        row("Season:", self._season, r)
        r += 1
        row("Episode:", self._episode, r)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=22)
        ctk.CTkButton(btns, text="Save", width=110, command=self._save).pack(
            side="left", padx=6
        )
        ctk.CTkButton(
            btns,
            text="Cancel",
            width=110,
            fg_color="gray25",
            hover_color="gray35",
            command=self.destroy,
        ).pack(side="left", padx=6)

    def _save(self):
        name = (self._name.get() if self._show is None else self._show["name"]).strip()
        if not name:
            messagebox.showerror("Error", "Show name cannot be empty.", parent=self)
            return
        try:
            season = int(self._season.get())
            episode = int(self._episode.get())
        except ValueError:
            messagebox.showerror("Error", "Season and episode must be numbers.", parent=self)
            return
        self._on_save(name, season, episode, self._show)
        self.destroy()


# ── Show Card ─────────────────────────────────────────────────────────────────

class ShowCard(ctk.CTkFrame):
    def __init__(self, parent, show: dict, on_edit, on_delete, **kwargs):
        super().__init__(parent, corner_radius=14, fg_color=CARD_BG, **kwargs)
        self._show = show
        self._on_edit = on_edit
        self._on_delete = on_delete
        self._build()

    def _build(self):
        pad = {"padx": 16, "pady": 4}

        # Show name
        ctk.CTkLabel(
            self,
            text=self._show["name"],
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 2))

        # Big episode badge
        ep = f"S{self._show['current_season']:02d}  E{self._show['current_episode']:02d}"
        ctk.CTkLabel(
            self,
            text=ep,
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=ACCENT,
            anchor="w",
        ).pack(fill="x", **pad)

        # Last watched
        lw = self._show.get("last_watched") or ""
        if lw:
            try:
                lw = datetime.strptime(lw, "%Y-%m-%d %H:%M:%S").strftime("%b %d, %Y")
            except ValueError:
                pass
            lw_text = f"Last watched  {lw}"
        else:
            lw_text = "Never watched"

        ctk.CTkLabel(
            self,
            text=lw_text,
            font=ctk.CTkFont(size=11),
            text_color="gray50",
            anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 10))

        # Buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 14))

        ctk.CTkButton(
            btn_row,
            text="Edit",
            width=64,
            height=28,
            font=ctk.CTkFont(size=12),
            command=lambda: self._on_edit(self._show),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row,
            text="Remove",
            width=76,
            height=28,
            font=ctk.CTkFont(size=12),
            fg_color=DANGER,
            hover_color=DANGER_HOVER,
            command=lambda: self._on_delete(self._show),
        ).pack(side="left")

    def refresh(self, show: dict):
        self._show = show
        for w in self.winfo_children():
            w.destroy()
        self._build()


# ── Main App Window ───────────────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("KeepTrack")
        self.geometry("960x660")
        self.minsize(640, 420)

        database.init_db()
        self._config = self._load_config()
        self._notif_job: Optional[str] = None

        self._monitor = VLCMonitor(
            self._config["host"], self._config["port"], self._config["password"]
        )
        self._monitor.on_episode_detected = self._on_episode_detected
        self._monitor.on_connection_change = self._on_connection_change

        self._build_ui()
        self._refresh()
        self._monitor.start()

    # ── Config ────────────────────────────────────────────────────────────────

    def _load_config(self) -> dict:
        defaults = {"host": "localhost", "port": 8080, "password": ""}
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH) as f:
                    defaults.update(json.load(f))
            except Exception:
                pass
        return defaults

    def _save_config(self):
        with open(CONFIG_PATH, "w") as f:
            json.dump(self._config, f, indent=2)

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # Use grid for the root so we can insert the notification row cleanly
        self.grid_rowconfigure(0, weight=0)  # header
        self.grid_rowconfigure(1, weight=0)  # notification bar (hidden initially)
        self.grid_rowconfigure(2, weight=1)  # content
        self.grid_columnconfigure(0, weight=1)

        # ── Header ────────────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color=HEADER_BG, corner_radius=0, height=64)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.columnconfigure(1, weight=1)

        # Left: logo
        logo_frame = ctk.CTkFrame(header, fg_color="transparent")
        logo_frame.grid(row=0, column=0, padx=20, pady=12, sticky="w")

        ctk.CTkLabel(
            logo_frame,
            text="KeepTrack",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=ACCENT,
        ).pack(side="left")
        ctk.CTkLabel(
            logo_frame,
            text="  ·  TV Show Tracker",
            font=ctk.CTkFont(size=12),
            text_color="gray45",
        ).pack(side="left")

        # Right: status + buttons
        right = ctk.CTkFrame(header, fg_color="transparent")
        right.grid(row=0, column=2, padx=20, pady=12, sticky="e")

        self._dot = ctk.CTkLabel(right, text="●", font=ctk.CTkFont(size=14), text_color="gray35")
        self._dot.pack(side="left", padx=(0, 4))
        self._vlc_lbl = ctk.CTkLabel(
            right, text="VLC: Disconnected", font=ctk.CTkFont(size=12), text_color="gray45"
        )
        self._vlc_lbl.pack(side="left", padx=(0, 18))

        ctk.CTkButton(
            right,
            text="⚙  Settings",
            width=96,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color="gray22",
            hover_color="gray32",
            command=self._open_settings,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            right,
            text="＋  Add Show",
            width=100,
            height=32,
            font=ctk.CTkFont(size=12),
            command=lambda: self._open_edit(None),
        ).pack(side="left")

        # ── Notification bar ─────────────────────────────────────────────────
        self._notif_bar = ctk.CTkFrame(self, fg_color="#0d2b1a", corner_radius=0, height=38)
        # NOT placed in grid yet (hidden by default)

        self._notif_lbl = ctk.CTkLabel(
            self._notif_bar,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=ACCENT_GREEN,
        )
        self._notif_lbl.pack(fill="x", padx=24, pady=9)

        # ── Content ───────────────────────────────────────────────────────────
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=2, column=0, sticky="nsew", padx=22, pady=18)
        content.rowconfigure(1, weight=1)
        content.columnconfigure(0, weight=1)

        # Search row
        search_row = ctk.CTkFrame(content, fg_color="transparent")
        search_row.grid(row=0, column=0, sticky="ew", pady=(0, 14))

        ctk.CTkLabel(search_row, text="Search:", font=ctk.CTkFont(size=13)).pack(
            side="left", padx=(0, 8)
        )
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refresh())
        ctk.CTkEntry(
            search_row,
            textvariable=self._search_var,
            placeholder_text="Filter shows…",
            width=240,
            height=34,
        ).pack(side="left")

        self._count_lbl = ctk.CTkLabel(
            search_row, text="", font=ctk.CTkFont(size=12), text_color="gray50"
        )
        self._count_lbl.pack(side="right")

        # Scrollable card grid
        self._scroll = ctk.CTkScrollableFrame(content, fg_color="transparent")
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.columnconfigure((0, 1, 2), weight=1)

    # ── Data refresh ─────────────────────────────────────────────────────────

    def _refresh(self):
        shows = database.get_all_shows()
        q = self._search_var.get().lower().strip() if hasattr(self, "_search_var") else ""
        if q:
            shows = [s for s in shows if q in s["name"].lower()]

        # Clear old cards
        for w in self._scroll.winfo_children():
            w.destroy()

        if not shows:
            msg = (
                "No shows match your search."
                if q
                else "No shows tracked yet.\nAdd one manually or play an episode in VLC!"
            )
            ctk.CTkLabel(
                self._scroll,
                text=msg,
                font=ctk.CTkFont(size=14),
                text_color="gray45",
                justify="center",
            ).grid(row=0, column=0, columnspan=3, pady=70)
            self._count_lbl.configure(text="")
            return

        for i, show in enumerate(shows):
            card = ShowCard(
                self._scroll,
                show,
                on_edit=self._open_edit,
                on_delete=self._delete_show,
            )
            card.grid(row=i // 3, column=i % 3, padx=8, pady=8, sticky="nsew")

        n = len(shows)
        self._count_lbl.configure(text=f"{n} show{'s' if n != 1 else ''}")

    # ── VLC callbacks (called from background thread → dispatch to main) ──────

    def _on_episode_detected(self, show: str, season: int, episode: int):
        updated = database.upsert_show(show, season, episode)
        if updated:
            self.after(
                0,
                lambda: self._show_notification(
                    f"▶  Now watching:  {show}  —  S{season:02d}E{episode:02d}"
                ),
            )
        self.after(0, self._refresh)

    def _on_connection_change(self, connected: bool):
        self.after(0, lambda: self._update_vlc_indicator(connected))

    def _update_vlc_indicator(self, connected: bool):
        if connected:
            self._dot.configure(text_color=ACCENT_GREEN)
            self._vlc_lbl.configure(text="VLC: Connected", text_color=ACCENT_GREEN)
        else:
            self._dot.configure(text_color="gray35")
            self._vlc_lbl.configure(text="VLC: Disconnected", text_color="gray45")

    # ── Notification bar ─────────────────────────────────────────────────────

    def _show_notification(self, msg: str):
        if self._notif_job:
            self.after_cancel(self._notif_job)

        self._notif_lbl.configure(text=msg)
        self._notif_bar.grid(row=1, column=0, sticky="ew")

        self._notif_job = self.after(5000, self._hide_notification)

    def _hide_notification(self):
        self._notif_bar.grid_remove()
        self._notif_job = None

    # ── Dialogs ───────────────────────────────────────────────────────────────

    def _open_settings(self):
        SettingsDialog(self, self._config, self._apply_settings)

    def _apply_settings(self, new_cfg: dict):
        self._config.update(new_cfg)
        self._save_config()
        self._monitor.update_config(new_cfg["host"], new_cfg["port"], new_cfg["password"])

    def _open_edit(self, show: Optional[dict]):
        EditShowDialog(self, show, self._save_show)

    def _save_show(self, name: str, season: int, episode: int, existing: Optional[dict]):
        if existing:
            database.update_show_manual(existing["id"], name, season, episode)
        else:
            database.upsert_show(name, season, episode)
        self._refresh()

    def _delete_show(self, show: dict):
        if messagebox.askyesno(
            "Remove Show",
            f"Remove \"{show['name']}\" from tracking?",
            parent=self,
        ):
            database.delete_show(show["id"])
            self._refresh()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_close(self):
        self._monitor.stop()
        self.destroy()
