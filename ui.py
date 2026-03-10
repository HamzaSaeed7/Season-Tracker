import colorsys
import hashlib
import json
import os
import shutil
import sys
import threading
import xml.etree.ElementTree as ET
from tkinter import messagebox, filedialog
from typing import Optional

import pystray


def _resource_dir() -> str:
    """Bundled read-only assets (icons). Uses _MEIPASS when frozen by PyInstaller."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def _data_dir() -> str:
    """User-writable data (posters, config). Always next to the exe / script."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

import aggdraw
from PIL import Image, ImageDraw, ImageOps
from svg.path import parse_path, Move, Line, CubicBezier, QuadraticBezier, Arc, Close
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
GOLD        = "#FFD700"
GOLD_DIM    = "#444433"

POSTER_DIR  = os.path.join(_data_dir(), "posters")
CONFIG_PATH = os.path.join(_data_dir(), "config.json")

os.makedirs(POSTER_DIR, exist_ok=True)

POSTER_W, POSTER_H = 100, 145  # display size on card


# ── Helpers ───────────────────────────────────────────────────────────────────

def _poster_color(name: str) -> str:
    digest = hashlib.md5(name.lower().encode()).hexdigest()
    hue    = int(digest[:8], 16) / 0xFFFFFFFF
    r, g, b = colorsys.hsv_to_rgb(hue, 0.55, 0.68)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"


def _fmt_time(seconds: int) -> str:
    h, rem = divmod(max(0, seconds), 3600)
    m, s   = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _load_poster_image(poster_path: str) -> Optional[ctk.CTkImage]:
    """Load a poster, fit it, and apply rounded corners matching the card radius."""
    if not poster_path or not os.path.isfile(poster_path):
        return None
    try:
        img = Image.open(poster_path).convert("RGBA")
        img = ImageOps.fit(img, (POSTER_W, POSTER_H), Image.LANCZOS)

        # Rounded-corner mask (radius must match _Poster corner_radius)
        mask = Image.new("L", (POSTER_W, POSTER_H), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, POSTER_W - 1, POSTER_H - 1], radius=14, fill=255
        )
        img.putalpha(mask)

        return ctk.CTkImage(light_image=img, dark_image=img, size=(POSTER_W, POSTER_H))
    except Exception:
        return None


# ── Icon helpers ──────────────────────────────────────────────────────────────

ICONS_DIR   = os.path.join(_resource_dir(), "icons")
_SVG_FILES  = {"edit": "edit-2.svg", "delete": "trash.svg"}
_ICON_CACHE: dict = {}


def _get_icon(kind: str, size: int = 22) -> ctk.CTkImage:
    key = (kind, size)
    if key not in _ICON_CACHE:
        _ICON_CACHE[key] = _render_svg_icon(kind, size)
    return _ICON_CACHE[key]


def _svg_path_to_polylines(d: str, scale: float):
    """Parse an SVG path string and return a list of [(x,y)…] polylines."""
    subpaths, current = [], []
    for seg in parse_path(d):
        if isinstance(seg, Move):
            if current:
                subpaths.append(current)
            p = seg.start
            current = [(p.real * scale, p.imag * scale)]
        elif isinstance(seg, (Line, Close)):
            p = seg.end
            current.append((p.real * scale, p.imag * scale))
        else:  # Arc, CubicBezier, QuadraticBezier — sample as polyline
            steps = max(12, int(abs(seg.end - seg.start) * scale * 3))
            for i in range(1, steps + 1):
                p = seg.point(i / steps)
                current.append((p.real * scale, p.imag * scale))
    if current:
        subpaths.append(current)
    return subpaths


def _render_svg_icon(kind: str, display_size: int = 22) -> ctk.CTkImage:
    """Render an SVG icon from the icons/ folder at 2× then LANCZOS-downsample."""
    S     = display_size * 2
    scale = S / 24.0
    path  = os.path.join(ICONS_DIR, _SVG_FILES[kind])

    root  = ET.parse(path).getroot()
    # Inherit stroke colour from the root <svg> element
    default_stroke = root.get("stroke", "#ffffff")
    sw = float(root.get("stroke-width", "2")) * scale

    img  = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = aggdraw.Draw(img)

    def _hex_to_rgb(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    def _draw_elem(elem):
        stroke = elem.get("stroke", default_stroke)
        if stroke == "none":
            return
        pen = aggdraw.Pen(_hex_to_rgb(stroke), sw)
        tag = elem.tag.split("}")[-1]

        if tag == "path":
            for pts in _svg_path_to_polylines(elem.get("d", ""), scale):
                if len(pts) >= 2:
                    draw.line([c for pt in pts for c in pt], pen)

        elif tag == "polyline":
            raw = list(map(float, elem.get("points", "").split()))
            pts = [(raw[i] * scale, raw[i+1] * scale) for i in range(0, len(raw)-1, 2)]
            if len(pts) >= 2:
                draw.line([c for pt in pts for c in pt], pen)

        elif tag == "line":
            x1 = float(elem.get("x1", 0)) * scale
            y1 = float(elem.get("y1", 0)) * scale
            x2 = float(elem.get("x2", 0)) * scale
            y2 = float(elem.get("y2", 0)) * scale
            draw.line([x1, y1, x2, y2], pen)

        for child in elem:
            _draw_elem(child)

    for child in root:
        _draw_elem(child)

    draw.flush()
    img = img.resize((display_size, display_size), Image.LANCZOS)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(display_size, display_size))


def _copy_poster(src_path: str, show_id: int) -> str:
    """Copy the chosen image into the posters folder and return the new path."""
    ext  = os.path.splitext(src_path)[1].lower()
    dest = os.path.join(POSTER_DIR, f"{show_id}{ext}")
    shutil.copy2(src_path, dest)
    return dest


# ── Sub-widgets ───────────────────────────────────────────────────────────────

class _Poster(ctk.CTkFrame):
    """Poster area: shows a user image if available, else a coloured initial tile."""

    def __init__(self, parent, name: str, poster_path: str = "", **kw):
        super().__init__(parent, width=POSTER_W, height=POSTER_H,
                         corner_radius=14, **kw)
        self.pack_propagate(False)
        self.grid_propagate(False)

        img = _load_poster_image(poster_path)
        if img:
            self.configure(fg_color=CARD_BG)
            ctk.CTkLabel(self, text="", image=img, fg_color=CARD_BG).pack(expand=True)
        else:
            self.configure(fg_color=_poster_color(name))
            initials = "".join(w[0].upper() for w in name.split() if w)[:2]
            ctk.CTkLabel(self, text=initials,
                         font=ctk.CTkFont(size=26, weight="bold"),
                         text_color="white").pack(expand=True)


class _Counter(ctk.CTkFrame):
    """Inline  [−]  value  [+]  row with a label."""

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


class _RatingSlider(ctk.CTkFrame):
    """Slider for a 0.0 – 5.0 rating in 0.1 steps.  0.0 means 'not rated'."""

    def __init__(self, parent, initial: float = 0.0, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self._var = ctk.DoubleVar(value=float(initial))

        ctk.CTkLabel(self, text="0", font=ctk.CTkFont(size=11),
                     text_color="gray50").pack(side="left", padx=(0, 4))

        self._slider = ctk.CTkSlider(
            self, from_=0, to=5,
            number_of_steps=50,          # 0.1 per step
            variable=self._var,
            width=180,
            command=self._on_change,
        )
        self._slider.pack(side="left")

        ctk.CTkLabel(self, text="5", font=ctk.CTkFont(size=11),
                     text_color="gray50").pack(side="left", padx=(4, 10))

        self._lbl = ctk.CTkLabel(self, text=self._fmt(initial),
                                  font=ctk.CTkFont(size=14, weight="bold"),
                                  text_color=GOLD, width=42, anchor="w")
        self._lbl.pack(side="left")

    def _on_change(self, v):
        self._lbl.configure(text=self._fmt(round(v, 1)))

    @staticmethod
    def _fmt(v: float) -> str:
        return "—" if v == 0 else f"{v:.1f} ★"

    @property
    def rating(self) -> float:
        return round(self._var.get(), 1)


# ── Show / Movie Card ─────────────────────────────────────────────────────────

_CARD_H = POSTER_H + 28  # poster + top/bottom padding


class ShowCard(ctk.CTkFrame):
    def __init__(self, parent, show: dict, on_edit, on_delete, on_copy=None, **kw):
        super().__init__(parent, corner_radius=14, fg_color=CARD_BG,
                         height=_CARD_H, **kw)
        self.pack_propagate(False)
        self.grid_propagate(False)
        self._show      = show.copy()
        self._on_edit   = on_edit
        self._on_delete = on_delete
        self._on_copy   = on_copy
        self._build()

    def _build(self):
        show   = self._show
        is_tv  = show.get("type", "show") == "show"

        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=14, pady=14)

        # Left: poster
        _Poster(outer, show["name"],
                poster_path=show.get("poster_path", "") or "").pack(
            side="left", anchor="n", padx=(0, 14))

        # Right: content
        right = ctk.CTkFrame(outer, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)

        # ── Pack btn_row at bottom FIRST so it always anchors there ──────────
        btn_row = ctk.CTkFrame(right, fg_color="transparent")
        btn_row.pack(side="bottom", fill="x")
        ctk.CTkButton(btn_row, text="", image=_get_icon("delete", 20),
                      width=30, height=30, corner_radius=6,
                      fg_color="gray20", hover_color="gray30",
                      command=lambda: self._on_delete(self._show)).pack(side="right", padx=(4, 0))
        ctk.CTkButton(btn_row, text="", image=_get_icon("edit", 20),
                      width=30, height=30, corner_radius=6,
                      fg_color="gray20", hover_color="gray30",
                      command=lambda: self._on_edit(self._show)).pack(side="right")

        # ── Rest of content fills from top ───────────────────────────────────

        # Name + type badge
        hdr = ctk.CTkFrame(right, fg_color="transparent")
        hdr.pack(fill="x")
        name_lbl = ctk.CTkLabel(hdr, text=show["name"],
                                font=ctk.CTkFont(size=16, weight="bold"),
                                anchor="w")
        name_lbl.pack(side="left")
        name_lbl.bind("<Double-Button-1>",
                      lambda e, n=show["name"]: self._copy_name(n))
        ctk.CTkLabel(hdr, text="📺 TV Show" if is_tv else "🎬 Movie",
                     font=ctk.CTkFont(size=10),
                     text_color="gray50").pack(side="right")

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
            self._hours_ctr = _Counter(right, "Hours",   h,
                                        lambda d: self._adjust("hours",   d))
            self._hours_ctr.pack(anchor="w", pady=2)
            self._mins_ctr  = _Counter(right, "Minutes", m,
                                        lambda d: self._adjust("minutes", d))
            self._mins_ctr.pack(anchor="w", pady=2)
            self._secs_ctr  = _Counter(right, "Seconds", s,
                                        lambda d: self._adjust("seconds", d))
            self._secs_ctr.pack(anchor="w", pady=2)

        # Rating (only if set)
        rating = show.get("rating", 0) or 0
        if rating:
            ctk.CTkLabel(right,
                         text=f"★  {float(rating):.1f} / 5.0",
                         font=ctk.CTkFont(size=12),
                         text_color=GOLD,
                         anchor="w").pack(fill="x", pady=(4, 0))

        # Description (only if set, single line)
        desc = (show.get("description") or "").strip()
        if desc:
            preview = desc if len(desc) <= 55 else desc[:52] + "…"
            ctk.CTkLabel(right, text=preview,
                         font=ctk.CTkFont(size=10),
                         text_color="gray50",
                         anchor="w").pack(fill="x")

    # ── Copy name ─────────────────────────────────────────────────────────────

    def _copy_name(self, name: str):
        self.clipboard_clear()
        self.clipboard_append(name)
        if self._on_copy:
            self._on_copy(name)

    # ── Adjust ────────────────────────────────────────────────────────────────

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
        self.after(150, lambda: (self.lift(), self.focus_force(), self.grab_set()))
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
        self.geometry("420x560")
        self.resizable(False, False)
        # Defer grab_set/lift — calling grab_set before the window is drawn
        # causes CTkToplevel to swallow all events and become unresponsive.
        self.after(150, lambda: (self.lift(), self.focus_force(), self.grab_set()))

        self._entry   = entry
        self._on_save = on_save
        # pending poster path chosen this session (not yet saved to DB)
        self._pending_poster: str = entry.get("poster_path", "") or "" if entry else ""

        initial_type = "show" if entry is None else entry.get("type", "show")
        t = 0 if entry is None else (entry.get("watch_time_seconds") or 0)
        existing_rating = 0 if entry is None else (entry.get("rating") or 0)
        existing_desc   = "" if entry is None else (entry.get("description") or "")

        # ── Title ─────────────────────────────────────────────────────────────
        ctk.CTkLabel(self,
                     text="Add New Entry" if is_new else f"Edit  ·  {entry['name']}",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(18, 8))

        # ── Type selector ──────────────────────────────────────────────────────
        self._type_seg = ctk.CTkSegmentedButton(
            self, values=["TV Show", "Movie"],
            command=self._on_type_change)
        self._type_seg.set("TV Show" if initial_type == "show" else "Movie")
        self._type_seg.pack(pady=(0, 10))

        # ── Form (grid) ────────────────────────────────────────────────────────
        self._form = ctk.CTkFrame(self, fg_color="transparent")
        self._form.pack(padx=36, fill="x")
        self._form.columnconfigure(1, weight=1)

        # Row 0: Name
        ctk.CTkLabel(self._form, text="Name:", anchor="w").grid(
            row=0, column=0, sticky="w", pady=7)
        self._name_var = ctk.StringVar(value="" if is_new else entry["name"])
        ctk.CTkEntry(self._form, textvariable=self._name_var).grid(
            row=0, column=1, sticky="ew", padx=(12, 0), pady=7)

        # TV Show rows
        self._season_lbl = ctk.CTkLabel(self._form, text="Season:", anchor="w")
        self._season_var = ctk.StringVar(
            value=str(1 if is_new else (entry.get("current_season") or 1)))
        self._season_ent = ctk.CTkEntry(self._form, textvariable=self._season_var, width=110)

        self._ep_lbl = ctk.CTkLabel(self._form, text="Episode:", anchor="w")
        self._ep_var = ctk.StringVar(
            value=str(1 if is_new else (entry.get("current_episode") or 1)))
        self._ep_ent = ctk.CTkEntry(self._form, textvariable=self._ep_var, width=110)

        # Movie rows
        self._hours_lbl = ctk.CTkLabel(self._form, text="Hours:", anchor="w")
        self._hours_var = ctk.StringVar(value=str(t // 3600))
        self._hours_ent = ctk.CTkEntry(self._form, textvariable=self._hours_var, width=110)

        self._mins_lbl = ctk.CTkLabel(self._form, text="Minutes:", anchor="w")
        self._mins_var = ctk.StringVar(value=str((t % 3600) // 60))
        self._mins_ent = ctk.CTkEntry(self._form, textvariable=self._mins_var, width=110)

        self._secs_lbl = ctk.CTkLabel(self._form, text="Seconds:", anchor="w")
        self._secs_var = ctk.StringVar(value=str(t % 60))
        self._secs_ent = ctk.CTkEntry(self._form, textvariable=self._secs_var, width=110)

        # Grid all dynamic rows once so grid_remove() works later
        for (lbl, ent), row in zip(
            [(self._season_lbl, self._season_ent),
             (self._ep_lbl,     self._ep_ent),
             (self._hours_lbl,  self._hours_ent),
             (self._mins_lbl,   self._mins_ent),
             (self._secs_lbl,   self._secs_ent)],
            [1, 2, 1, 2, 3],
        ):
            lbl.grid(row=row, column=0, sticky="w", pady=7)
            ent.grid(row=row, column=1, sticky="w", padx=(12, 0), pady=7)

        self._on_type_change()  # apply initial visibility

        # ── Poster ────────────────────────────────────────────────────────────
        poster_row = ctk.CTkFrame(self, fg_color="transparent")
        poster_row.pack(padx=36, fill="x", pady=(6, 0))

        ctk.CTkLabel(poster_row, text="Poster:", anchor="w",
                     width=60).pack(side="left")

        self._poster_lbl = ctk.CTkLabel(
            poster_row,
            text=self._short_poster_name(self._pending_poster),
            font=ctk.CTkFont(size=11), text_color="gray50",
            anchor="w")
        self._poster_lbl.pack(side="left", padx=(10, 0), expand=True, fill="x")

        ctk.CTkButton(poster_row, text="Browse…", width=80, height=28,
                      font=ctk.CTkFont(size=12),
                      fg_color="gray22", hover_color="gray32",
                      command=self._browse_poster).pack(side="right")

        # ── Rating ────────────────────────────────────────────────────────────
        rating_row = ctk.CTkFrame(self, fg_color="transparent")
        rating_row.pack(padx=36, fill="x", pady=(10, 0))
        ctk.CTkLabel(rating_row, text="Rating:", anchor="w",
                     width=60).pack(side="left")
        self._rating_slider = _RatingSlider(rating_row, initial=existing_rating)
        self._rating_slider.pack(side="left", padx=(10, 0))

        # ── Notes ─────────────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="Notes  (optional):", anchor="w",
                     font=ctk.CTkFont(size=12)).pack(padx=36, fill="x", pady=(10, 2))
        self._desc_box = ctk.CTkTextbox(self, height=64,
                                         font=ctk.CTkFont(size=12),
                                         corner_radius=8)
        self._desc_box.pack(padx=36, fill="x")
        if existing_desc:
            self._desc_box.insert("1.0", existing_desc)

        # ── Buttons ───────────────────────────────────────────────────────────
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=16)
        ctk.CTkButton(btns, text="Save", width=110,
                      command=self._save).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Cancel", width=110,
                      fg_color="gray25", hover_color="gray35",
                      command=lambda: self.after(10, self.destroy)).pack(side="left", padx=6)

    # ── Poster helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _short_poster_name(path: str) -> str:
        if not path:
            return "None"
        return os.path.basename(path)

    def _browse_poster(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Choose Poster Image",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.webp *.bmp"), ("All files", "*.*")],
        )
        if path:
            self._pending_poster = path
            self._poster_lbl.configure(text=self._short_poster_name(path))

    # ── Type toggle ───────────────────────────────────────────────────────────

    def _on_type_change(self, _=None):
        is_tv = self._type_seg.get() == "TV Show"
        tv_w  = [self._season_lbl, self._season_ent, self._ep_lbl,  self._ep_ent]
        mv_w  = [self._hours_lbl,  self._hours_ent,  self._mins_lbl, self._mins_ent,
                 self._secs_lbl,   self._secs_ent]
        for w in (tv_w if is_tv else mv_w):
            w.grid()
        for w in (mv_w if is_tv else tv_w):
            w.grid_remove()

    # ── Save ─────────────────────────────────────────────────────────────────

    def _save(self):
        name = self._name_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Name cannot be empty.", parent=self)
            return

        is_tv = self._type_seg.get() == "TV Show"
        rating  = self._rating_slider.rating
        desc    = self._desc_box.get("1.0", "end-1c").strip()

        if is_tv:
            try:
                season  = int(self._season_var.get())
                episode = int(self._ep_var.get())
            except ValueError:
                messagebox.showerror("Error",
                                     "Season and episode must be numbers.", parent=self)
                return
            self._on_save(name, "show", season, episode, 0,
                          rating, desc, self._pending_poster, self._entry)
        else:
            try:
                h = int(self._hours_var.get())
                m = int(self._mins_var.get())
                s = int(self._secs_var.get())
            except ValueError:
                messagebox.showerror("Error",
                                     "Hours, minutes, and seconds must be numbers.", parent=self)
                return
            self._on_save(name, "movie", 1, 1, h * 3600 + m * 60 + s,
                          rating, desc, self._pending_poster, self._entry)

        self.after(10, self.destroy)


# ── Main App ──────────────────────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("KeepTrack")
        self.geometry("980x680")
        self.minsize(680, 440)

        database.init_db()
        self._config   = self._load_config()
        self._notif_job: Optional[str] = None

        self._monitor = VLCMonitor(
            self._config["host"], self._config["port"], self._config["password"]
        )
        self._monitor.on_episode_detected  = self._on_episode_detected
        self._monitor.on_movie_detected    = self._on_movie_detected
        self._monitor.on_connection_change = self._on_connection_change

        self._build_ui()
        self._refresh()
        self._monitor.start()
        self._tray = self._create_tray()
        threading.Thread(target=self._tray.run, daemon=True).start()
        self.bind("<Unmap>", self._on_minimize)

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
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)
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
                     font=ctk.CTkFont(size=12), text_color="gray45").pack(side="left")

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

        # Notification bar
        self._notif_bar = ctk.CTkFrame(self, fg_color="#0c2b18", corner_radius=0, height=38)
        self._notif_lbl = ctk.CTkLabel(self._notif_bar, text="",
                                        font=ctk.CTkFont(size=12), text_color=GREEN)
        self._notif_lbl.pack(fill="x", padx=24, pady=9)

        # Content
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=2, column=0, sticky="nsew", padx=22, pady=18)
        content.rowconfigure(1, weight=1)
        content.columnconfigure(0, weight=1)

        search_row = ctk.CTkFrame(content, fg_color="transparent")
        search_row.grid(row=0, column=0, sticky="ew", pady=(0, 14))

        ctk.CTkLabel(search_row, text="Search:",
                     font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 8))
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refresh())
        ctk.CTkEntry(search_row, textvariable=self._search_var,
                     placeholder_text="Filter…", width=220, height=34).pack(side="left")

        # Rating filter
        ctk.CTkLabel(search_row, text="Rating:",
                     font=ctk.CTkFont(size=13)).pack(side="left", padx=(18, 8))
        self._rating_filter_var = ctk.StringVar(value="All")
        self._rating_filter_var.trace_add("write", lambda *_: self._refresh())
        ctk.CTkOptionMenu(
            search_row,
            variable=self._rating_filter_var,
            values=["All", "★ ≥ 1.0", "★ ≥ 2.0", "★ ≥ 3.0", "★ ≥ 4.0", "★ ≥ 4.5"],
            width=110, height=34,
            fg_color="gray22", button_color="gray30", button_hover_color="gray40",
        ).pack(side="left")

        self._count_lbl = ctk.CTkLabel(search_row, text="",
                                        font=ctk.CTkFont(size=12), text_color="gray50")
        self._count_lbl.pack(side="right")

        self._scroll = ctk.CTkScrollableFrame(content, fg_color="transparent")
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.columnconfigure((0, 1), weight=1)

    # ── Data ──────────────────────────────────────────────────────────────────

    def _refresh(self):
        entries = database.get_all_shows()
        q = self._search_var.get().lower().strip() if hasattr(self, "_search_var") else ""
        if q:
            entries = [e for e in entries if q in e["name"].lower()]

        # Rating filter
        rf = self._rating_filter_var.get() if hasattr(self, "_rating_filter_var") else "All"
        if rf != "All":
            threshold = float(rf.split("≥")[-1].strip())
            entries = [e for e in entries if (e.get("rating") or 0) >= threshold]

        for w in self._scroll.winfo_children():
            w.destroy()

        if not entries:
            msg = ("No results match your search."
                   if q else
                   "Nothing tracked yet.\nAdd an entry or play something in VLC!")
            ctk.CTkLabel(self._scroll, text=msg,
                         font=ctk.CTkFont(size=14), text_color="gray45",
                         justify="center").grid(row=0, column=0, columnspan=2, pady=80)
            self._count_lbl.configure(text="")
            return

        for i, entry in enumerate(entries):
            card = ShowCard(self._scroll, entry,
                            on_edit=self._open_edit,
                            on_delete=self._delete_entry,
                            on_copy=lambda n: self._notify(f"Copied:  {n}"))
            card.grid(row=i // 2, column=i % 2, padx=9, pady=9, sticky="ew")

        n = len(entries)
        self._count_lbl.configure(text=f"{n} entr{'ies' if n != 1 else 'y'}")

    # ── VLC callbacks ─────────────────────────────────────────────────────────

    def _on_episode_detected(self, show: str, season: int, episode: int):
        updated = database.upsert_show(show, season, episode)
        if updated:
            self.after(0, lambda: self._notify(
                f"▶  Now watching:  {show}  —  S{season:02d}E{episode:02d}"))
        self.after(0, self._refresh)

    def _on_movie_detected(self, title: str, position: int):
        is_new = database.upsert_movie(title, position)
        if is_new:
            self.after(0, lambda: self._notify(f"🎬  Detected movie:  {title}"))
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
                    episode: int, watch_time: int,
                    rating: float, description: str,
                    pending_poster: str, existing: Optional[dict]):
        """
        Persist the entry.  If a new poster image was chosen, copy it into
        the posters/ folder so it survives the original file moving/deleting.
        """
        # Determine final poster path
        poster_path = existing.get("poster_path", "") or "" if existing else ""

        if pending_poster and os.path.isfile(pending_poster):
            if existing:
                # Copy now (we have the DB id already)
                poster_path = _copy_poster(pending_poster, existing["id"])
            else:
                # For new entries we'll copy after insertion using a temp id
                poster_path = pending_poster  # will be fixed up below

        if existing:
            database.update_entry(existing["id"], name, entry_type,
                                   season, episode, watch_time,
                                   rating, description, poster_path)
        else:
            database.add_entry(name, entry_type, season, episode, watch_time,
                               rating, description, poster_path="")
            # Get the newly created row to copy the poster with the real id
            row = database.get_show_by_name(name)
            if row and pending_poster and os.path.isfile(pending_poster):
                real_poster = _copy_poster(pending_poster, row["id"])
                database.update_entry(row["id"], name, entry_type,
                                       season, episode, watch_time,
                                       rating, description, real_poster)

        self._refresh()

    def _delete_entry(self, entry: dict):
        if messagebox.askyesno("Remove",
                                f"Remove \"{entry['name']}\" from tracking?",
                                parent=self):
            database.delete_show(entry["id"])
            # Also delete poster file if stored in our folder
            pp = entry.get("poster_path", "") or ""
            if pp and pp.startswith(POSTER_DIR) and os.path.isfile(pp):
                try:
                    os.remove(pp)
                except OSError:
                    pass
            self._refresh()

    # ── System tray ───────────────────────────────────────────────────────────

    def _create_tray(self) -> pystray.Icon:
        # Draw a simple tray icon — blue rounded square with "KT"
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=14,
                               fill=(77, 166, 255, 255))
        draw.text((size // 2 - 10, size // 2 - 10), "KT", fill="white")

        menu = pystray.Menu(
            pystray.MenuItem("Show KeepTrack", self._tray_show, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._tray_quit),
        )
        return pystray.Icon("KeepTrack", img, "KeepTrack", menu)

    def _on_minimize(self, event):
        if event.widget is self:
            self.withdraw()          # hide from taskbar

    def _tray_show(self, icon=None, item=None):
        self.after(0, self._show_window)

    def _show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _tray_quit(self, icon=None, item=None):
        self._tray.stop()
        self.after(0, self.on_close)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_close(self):
        self._monitor.stop()
        try:
            self._tray.stop()
        except Exception:
            pass
        self.destroy()
