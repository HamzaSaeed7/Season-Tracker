import colorsys
import hashlib
import json
import os
from datetime import datetime
from tkinter import messagebox
from typing import Optional

import customtkinter as ctk

import database
from vlc_monitor import VLCMonitor

# ── Theme ─────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ACCENT      = "#4da6ff"
GREEN       = "#4dff88"
CARD_BG     = "#1a1b2e"
HEADER_BG   = "#0f0f1a"
DANGER      = "#c0392b"
DANGER_HVR  = "#a93226"

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _poster_color(name: str) -> str:
    """Generate a stable, pleasant colour from a show/movie name."""
    digest = hashlib.md5(name.lower().encode()).hexdigest()
    hue = int(digest[:8], 16) / 0xFFFFFFFF
    r, g, b = colorsys.hsv_to_rgb(hue, 0.55, 0.68)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def _fmt_time(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


# ── Sub-widgets ───────────────────────────────────────────────────────────────

class _Poster(ctk.CTkFrame):
    """Coloured placeholder poster showing the entry's initials."""

    def __init__(self, parent, name: str, width: int = 80, height: int = 112, **kw):
        super().__init__(parent, width=width, height=height,
                         fg_color=_poster_color(name), corner_radius=10, **kw)
        self.pack_propagate(False)
        self.grid_propagate(False)
        initials = "".join(w[0].upper() for w in name.split() if w)[:2]
        ctk.CTkLabel(self, text=initials,
                     font=ctk.CTkFont(size=26, weight="bold"),
                     text_color="white").pack(expand=True)


class _Counter(ctk.CTkFrame):
    """Inline  [−]  value  [+]  control with a label."""

    def __init__(self, parent, label: str, value: int, on_change, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        ctk.CTkLabel(self, text=label, width=60, anchor="w",
                     font=ctk.CTkFont(size=11),
                     text_color="gray55").pack(side="left")
        ctk.CTkButton(self, text="−", width=28, height=26,
                      fg_color="gray20", hover_color="gray30",
                      font=ctk.CTkFont(size=15, weight="bold"),
                      command=lambda: on_change(-1)).pack(side="left", padx=(0, 2))
        self._lbl = ctk.CTkLabel(self, text=str(value), width=36,
                                  font=ctk.CTkFont(size=13, weight="bold"),
                                  anchor="center")
        self._lbl.pack(side="left", padx=2)
        ctk.CTkButton(self, text="+", width=28, height=26,
                      fg_color="gray20", hover_color="gray30",
                      font=ctk.CTkFont(size=15, weight="bold"),
                      command=lambda: on_change(+1)).pack(side="left", padx=(2, 0))
        self._val = value

    def set_value(self, v: int):
        self._val = v
        self._lbl.configure(text=str(v))

    @property
    def value(self) -> int:
        return self._val


# ── Show / Movie Card ─────────────────────────────────────────────────────────

class ShowCard(ctk.CTkFrame):
    def __init__(self, parent, show: dict, on_edit, on_delete, **kw):
        super().__init__(parent, corner_radius=14, fg_color=CARD_BG, **kw)
        self._show = show.copy()
        self._on_edit = on_edit
        self._on_delete = on_delete
        self._build()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        show = self._show
        is_tv = show.get("type", "show") == "show"

        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=14, pady=14)

        # Left: coloured poster
        _Poster(outer, show["name"]).pack(side="left", anchor="n", padx=(0, 14))

        # Right: content
        right = ctk.CTkFrame(outer, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)

        # Name + type badge
        header_row = ctk.CTkFrame(right, fg_color="transparent")
        header_row.pack(fill="x")
        ctk.CTkLabel(header_row, text=show["name"],
                     font=ctk.CTkFont(size=14, weight="bold"),
                     anchor="w").pack(side="left")
        badge = "📺 TV Show" if is_tv else "🎬 Movie"
        ctk.CTkLabel(header_row, text=badge,
                     font=ctk.CTkFont(size=10),
                     text_color="gray50").pack(side="right")

        # Big progress display
        if is_tv:
            prog_text = f"S{show['current_season']:02d}  E{show['current_episode']:02d}"
        else:
            prog_text = _fmt_time(show.get("watch_time_seconds", 0))

        self._prog_lbl = ctk.CTkLabel(right, text=prog_text,
                                       font=ctk.CTkFont(size=26, weight="bold"),
                                       text_color=ACCENT, anchor="w")
        self._prog_lbl.pack(fill="x", pady=(4, 6))

        # +/− counters
        if is_tv:
            self._season_ctr = _Counter(right, "Season",
                                         show["current_season"],
                                         lambda d: self._adjust("season", d))
            self._season_ctr.pack(anchor="w", pady=2)
            self._episode_ctr = _Counter(right, "Episode",
                                          show["current_episode"],
                                          lambda d: self._adjust("episode", d))
            self._episode_ctr.pack(anchor="w", pady=2)
        else:
            t = show.get("watch_time_seconds", 0)
            h, m, s = t // 3600, (t % 3600) // 60, t % 60
            self._hours_ctr = _Counter(right, "Hours", h,
                                        lambda d: self._adjust("hours", d))
            self._hours_ctr.pack(anchor="w", pady=2)
            self._mins_ctr = _Counter(right, "Minutes", m,
                                       lambda d: self._adjust("minutes", d))
            self._mins_ctr.pack(anchor="w", pady=2)
            self._secs_ctr = _Counter(right, "Seconds", s,
                                       lambda d: self._adjust("seconds", d))
            self._secs_ctr.pack(anchor="w", pady=2)

        # Last watched
        lw = show.get("last_watched") or ""
        if lw:
            try:
                lw = datetime.strptime(lw, "%Y-%m-%d %H:%M:%S").strftime("%b %d, %Y")
            except ValueError:
                pass
        ctk.CTkLabel(right,
                     text=f"Last watched  {lw}" if lw else "Not watched yet",
                     font=ctk.CTkFont(size=10), text_color="gray50",
                     anchor="w").pack(fill="x", pady=(6, 6))

        # Action buttons
        btn_row = ctk.CTkFrame(right, fg_color="transparent")
        btn_row.pack(anchor="w")
        ctk.CTkButton(btn_row, text="Edit", width=60, height=28,
                      font=ctk.CTkFont(size=12),
                      command=lambda: self._on_edit(self._show)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Remove", width=76, height=28,
                      font=ctk.CTkFont(size=12),
                      fg_color=DANGER, hover_color=DANGER_HVR,
                      command=lambda: self._on_delete(self._show)).pack(side="left")

    # ── Adjust logic ──────────────────────────────────────────────────────────

    def _adjust(self, field: str, delta: int):
        show = self._show
        if show.get("type", "show") == "show":
            if field == "season":
                new = max(1, show["current_season"] + delta)
                show["current_season"] = new
                self._season_ctr.set_value(new)
            elif field == "episode":
                new = max(1, show["current_episode"] + delta)
                show["current_episode"] = new
                self._episode_ctr.set_value(new)
            self._prog_lbl.configure(
                text=f"S{show['current_season']:02d}  E{show['current_episode']:02d}"
            )
            database.update_show_progress(show["id"],
                                           show["current_season"],
                                           show["current_episode"])
        else:
            t = show.get("watch_time_seconds", 0)
            h, m, s = t // 3600, (t % 3600) // 60, t % 60
            if field == "hours":
                h = max(0, h + delta)
            elif field == "minutes":
                m = max(0, min(59, m + delta))
            elif field == "seconds":
                s = max(0, min(59, s + delta))
            new_t = h * 3600 + m * 60 + s
            show["watch_time_seconds"] = new_t
            self._hours_ctr.set_value(h)
            self._mins_ctr.set_value(m)
            self._secs_ctr.set_value(s)
            self._prog_lbl.configure(text=_fmt_time(new_t))
            database.update_movie_progress(show["id"], new_t)

    def refresh(self, show: dict):
        self._show = show.copy()
        for w in self.winfo_children():
            w.destroy()
        self._build()


# ── Settings Dialog ───────────────────────────────────────────────────────────

class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, config: dict, on_save):
        super().__init__(parent)
        self.title("VLC Settings")
        self.geometry("400x330")
        self.resizable(False, False)
        self.grab_set()
        self.lift()
        self._on_save = on_save

        ctk.CTkLabel(self, text="VLC HTTP Interface",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(22, 4))
        ctk.CTkLabel(self,
                     text="Enable in VLC → Tools → Preferences → Show All\n"
                          "→ Interface → Main interfaces → ☑ Web\n"
                          "→ Lua HTTP → set a Password → restart VLC",
                     font=ctk.CTkFont(size=11), text_color="gray50",
                     justify="center").pack(pady=(0, 16))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(padx=40, fill="x")
        form.columnconfigure(1, weight=1)

        self._host = ctk.StringVar(value=config.get("host", "localhost"))
        self._port = ctk.StringVar(value=str(config.get("port", 8080)))
        self._pwd  = ctk.StringVar(value=config.get("password", ""))

        for r, (lbl, var, show) in enumerate([
            ("Host:",     self._host, ""),
            ("Port:",     self._port, ""),
            ("Password:", self._pwd,  "•"),
        ]):
            ctk.CTkLabel(form, text=lbl, anchor="w").grid(
                row=r, column=0, sticky="w", pady=7)
            ctk.CTkEntry(form, textvariable=var, show=show).grid(
                row=r, column=1, sticky="ew", padx=(12, 0), pady=7)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=18)
        ctk.CTkButton(btns, text="Save", width=110,
                      command=self._save).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Cancel", width=110,
                      fg_color="gray25", hover_color="gray35",
                      command=lambda: self.after(10, self.destroy)).pack(side="left", padx=6)

    def _save(self):
        try:
            port = int(self._port.get())
        except ValueError:
            messagebox.showerror("Error", "Port must be a number.", parent=self)
            return
        self._on_save({"host": self._host.get(),
                       "port": port,
                       "password": self._pwd.get()})
        self.after(10, self.destroy)


# ── Add / Edit Dialog ─────────────────────────────────────────────────────────

class EditDialog(ctk.CTkToplevel):
    def __init__(self, parent, entry: Optional[dict], on_save):
        super().__init__(parent)
        is_new = entry is None
        self.title("Add Entry" if is_new else f"Edit  —  {entry['name']}")
        self.geometry("390x420")
        self.resizable(False, False)
        self.grab_set()
        self.lift()

        self._entry = entry
        self._on_save = on_save

        initial_type = "show" if entry is None else entry.get("type", "show")
        t = 0 if entry is None else entry.get("watch_time_seconds", 0)

        # Title
        title_text = "Add New Entry" if is_new else f"Edit  ·  {entry['name']}"
        ctk.CTkLabel(self, text=title_text,
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(20, 10))

        # Type selector
        self._type_seg = ctk.CTkSegmentedButton(
            self, values=["TV Show", "Movie"],
            command=self._on_type_change)
        self._type_seg.set("TV Show" if initial_type == "show" else "Movie")
        self._type_seg.pack(pady=(0, 14))

        # Form grid
        self._form = ctk.CTkFrame(self, fg_color="transparent")
        self._form.pack(padx=40, fill="x")
        self._form.columnconfigure(1, weight=1)

        # Row 0: Name (always visible)
        ctk.CTkLabel(self._form, text="Name:", anchor="w").grid(
            row=0, column=0, sticky="w", pady=8)
        self._name_var = ctk.StringVar(value="" if is_new else entry["name"])
        ctk.CTkEntry(self._form, textvariable=self._name_var).grid(
            row=0, column=1, sticky="ew", padx=(12, 0), pady=8)

        # Rows 1-2: TV Show fields
        self._season_lbl = ctk.CTkLabel(self._form, text="Season:", anchor="w")
        self._season_var = ctk.StringVar(
            value=str(1 if is_new else entry.get("current_season", 1)))
        self._season_ent = ctk.CTkEntry(self._form, textvariable=self._season_var, width=110)

        self._ep_lbl = ctk.CTkLabel(self._form, text="Episode:", anchor="w")
        self._ep_var = ctk.StringVar(
            value=str(1 if is_new else entry.get("current_episode", 1)))
        self._ep_ent = ctk.CTkEntry(self._form, textvariable=self._ep_var, width=110)

        # Rows 1-3: Movie fields
        self._hours_lbl = ctk.CTkLabel(self._form, text="Hours:", anchor="w")
        self._hours_var = ctk.StringVar(value=str(t // 3600))
        self._hours_ent = ctk.CTkEntry(self._form, textvariable=self._hours_var, width=110)

        self._mins_lbl = ctk.CTkLabel(self._form, text="Minutes:", anchor="w")
        self._mins_var = ctk.StringVar(value=str((t % 3600) // 60))
        self._mins_ent = ctk.CTkEntry(self._form, textvariable=self._mins_var, width=110)

        self._secs_lbl = ctk.CTkLabel(self._form, text="Seconds:", anchor="w")
        self._secs_var = ctk.StringVar(value=str(t % 60))
        self._secs_ent = ctk.CTkEntry(self._form, textvariable=self._secs_var, width=110)

        # Grid all dynamic widgets once so grid_remove() works later
        for (lbl, ent), row in zip(
            [(self._season_lbl, self._season_ent),
             (self._ep_lbl,     self._ep_ent),
             (self._hours_lbl,  self._hours_ent),
             (self._mins_lbl,   self._mins_ent),
             (self._secs_lbl,   self._secs_ent)],
            [1, 2, 1, 2, 3],
        ):
            lbl.grid(row=row, column=0, sticky="w", pady=8)
            ent.grid(row=row, column=1, sticky="w", padx=(12, 0), pady=8)

        # Apply initial visibility
        self._on_type_change()

        # Buttons
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=20)
        ctk.CTkButton(btns, text="Save", width=110,
                      command=self._save).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Cancel", width=110,
                      fg_color="gray25", hover_color="gray35",
                      command=lambda: self.after(10, self.destroy)).pack(side="left", padx=6)

    def _on_type_change(self, _=None):
        is_tv = self._type_seg.get() == "TV Show"
        tv_widgets     = [self._season_lbl, self._season_ent, self._ep_lbl, self._ep_ent]
        movie_widgets  = [self._hours_lbl, self._hours_ent,
                          self._mins_lbl, self._mins_ent,
                          self._secs_lbl, self._secs_ent]
        for w in (tv_widgets if is_tv else movie_widgets):
            w.grid()
        for w in (movie_widgets if is_tv else tv_widgets):
            w.grid_remove()

    def _save(self):
        name = self._name_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Name cannot be empty.", parent=self)
            return

        is_tv = self._type_seg.get() == "TV Show"
        if is_tv:
            try:
                season  = int(self._season_var.get())
                episode = int(self._ep_var.get())
            except ValueError:
                messagebox.showerror("Error", "Season and episode must be numbers.", parent=self)
                return
            self._on_save(name, "show", season, episode, 0, self._entry)
        else:
            try:
                h = int(self._hours_var.get())
                m = int(self._mins_var.get())
                s = int(self._secs_var.get())
            except ValueError:
                messagebox.showerror("Error",
                                     "Hours, minutes, and seconds must be numbers.", parent=self)
                return
            self._on_save(name, "movie", 1, 1, h * 3600 + m * 60 + s, self._entry)

        self.after(10, self.destroy)


# ── Main App ──────────────────────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("KeepTrack")
        self.geometry("980x680")
        self.minsize(680, 440)

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

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=0)   # header
        self.grid_rowconfigure(1, weight=0)   # notification (hidden initially)
        self.grid_rowconfigure(2, weight=1)   # content
        self.grid_columnconfigure(0, weight=1)

        # Header
        header = ctk.CTkFrame(self, fg_color=HEADER_BG, corner_radius=0, height=64)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.columnconfigure(1, weight=1)

        logo_f = ctk.CTkFrame(header, fg_color="transparent")
        logo_f.grid(row=0, column=0, padx=22, pady=14, sticky="w")
        ctk.CTkLabel(logo_f, text="KeepTrack",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=ACCENT).pack(side="left")
        ctk.CTkLabel(logo_f, text="  ·  TV & Movie Tracker",
                     font=ctk.CTkFont(size=12),
                     text_color="gray45").pack(side="left")

        right_f = ctk.CTkFrame(header, fg_color="transparent")
        right_f.grid(row=0, column=2, padx=22, pady=14, sticky="e")

        self._dot = ctk.CTkLabel(right_f, text="●",
                                  font=ctk.CTkFont(size=14), text_color="gray35")
        self._dot.pack(side="left", padx=(0, 4))
        self._vlc_lbl = ctk.CTkLabel(right_f, text="VLC: Disconnected",
                                      font=ctk.CTkFont(size=12), text_color="gray45")
        self._vlc_lbl.pack(side="left", padx=(0, 20))

        ctk.CTkButton(right_f, text="⚙  Settings", width=98, height=32,
                      font=ctk.CTkFont(size=12),
                      fg_color="gray22", hover_color="gray32",
                      command=self._open_settings).pack(side="left", padx=(0, 8))
        ctk.CTkButton(right_f, text="＋  Add", width=84, height=32,
                      font=ctk.CTkFont(size=12),
                      command=lambda: self._open_edit(None)).pack(side="left")

        # Notification bar (hidden until needed)
        self._notif_bar = ctk.CTkFrame(self, fg_color="#0c2b18", corner_radius=0, height=38)
        self._notif_lbl = ctk.CTkLabel(self._notif_bar, text="",
                                        font=ctk.CTkFont(size=12), text_color=GREEN)
        self._notif_lbl.pack(fill="x", padx=24, pady=9)

        # Content area
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=2, column=0, sticky="nsew", padx=22, pady=18)
        content.rowconfigure(1, weight=1)
        content.columnconfigure(0, weight=1)

        # Search row
        search_row = ctk.CTkFrame(content, fg_color="transparent")
        search_row.grid(row=0, column=0, sticky="ew", pady=(0, 14))

        ctk.CTkLabel(search_row, text="Search:",
                     font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 8))
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refresh())
        ctk.CTkEntry(search_row, textvariable=self._search_var,
                     placeholder_text="Filter…", width=240, height=34).pack(side="left")

        self._count_lbl = ctk.CTkLabel(search_row, text="",
                                        font=ctk.CTkFont(size=12), text_color="gray50")
        self._count_lbl.pack(side="right")

        # Scrollable card grid (2 columns)
        self._scroll = ctk.CTkScrollableFrame(content, fg_color="transparent")
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.columnconfigure((0, 1), weight=1)

    # ── Data ──────────────────────────────────────────────────────────────────

    def _refresh(self):
        entries = database.get_all_shows()
        q = self._search_var.get().lower().strip() if hasattr(self, "_search_var") else ""
        if q:
            entries = [e for e in entries if q in e["name"].lower()]

        for w in self._scroll.winfo_children():
            w.destroy()

        if not entries:
            msg = ("No results match your search."
                   if q else
                   "Nothing tracked yet.\nAdd an entry manually or play an episode in VLC!")
            ctk.CTkLabel(self._scroll, text=msg,
                         font=ctk.CTkFont(size=14), text_color="gray45",
                         justify="center").grid(row=0, column=0, columnspan=2, pady=80)
            self._count_lbl.configure(text="")
            return

        for i, entry in enumerate(entries):
            card = ShowCard(self._scroll, entry,
                            on_edit=self._open_edit,
                            on_delete=self._delete_entry)
            card.grid(row=i // 2, column=i % 2, padx=9, pady=9, sticky="nsew")

        n = len(entries)
        self._count_lbl.configure(text=f"{n} entr{'ies' if n != 1 else 'y'}")

    # ── VLC callbacks ─────────────────────────────────────────────────────────

    def _on_episode_detected(self, show: str, season: int, episode: int):
        updated = database.upsert_show(show, season, episode)
        if updated:
            self.after(0, lambda: self._notify(
                f"▶  Now watching:  {show}  —  S{season:02d}E{episode:02d}"))
        self.after(0, self._refresh)

    def _on_connection_change(self, connected: bool):
        self.after(0, lambda: self._set_vlc_status(connected))

    def _set_vlc_status(self, connected: bool):
        if connected:
            self._dot.configure(text_color=GREEN)
            self._vlc_lbl.configure(text="VLC: Connected", text_color=GREEN)
        else:
            self._dot.configure(text_color="gray35")
            self._vlc_lbl.configure(text="VLC: Disconnected", text_color="gray45")

    # ── Notification ──────────────────────────────────────────────────────────

    def _notify(self, msg: str):
        if self._notif_job:
            self.after_cancel(self._notif_job)
        self._notif_lbl.configure(text=msg)
        self._notif_bar.grid(row=1, column=0, sticky="ew")
        self._notif_job = self.after(5000, self._hide_notif)

    def _hide_notif(self):
        self._notif_bar.grid_remove()
        self._notif_job = None

    # ── Dialogs ───────────────────────────────────────────────────────────────

    def _open_settings(self):
        SettingsDialog(self, self._config, self._apply_settings)

    def _apply_settings(self, cfg: dict):
        self._config.update(cfg)
        self._save_config()
        self._monitor.update_config(cfg["host"], cfg["port"], cfg["password"])

    def _open_edit(self, entry: Optional[dict]):
        EditDialog(self, entry, self._save_entry)

    def _save_entry(self, name: str, entry_type: str, season: int,
                    episode: int, watch_time: int, existing: Optional[dict]):
        if existing:
            database.update_entry(existing["id"], name, entry_type,
                                   season, episode, watch_time)
        else:
            database.add_entry(name, entry_type, season, episode, watch_time)
        self._refresh()

    def _delete_entry(self, entry: dict):
        if messagebox.askyesno("Remove",
                                f"Remove \"{entry['name']}\" from tracking?",
                                parent=self):
            database.delete_show(entry["id"])
            self._refresh()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_close(self):
        self._monitor.stop()
        self.destroy()
