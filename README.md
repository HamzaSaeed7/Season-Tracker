# KeepTrack — TV Show & Movie Tracker

Automatically tracks what you're watching in VLC and keeps your progress up to date. Works for both TV shows and movies.

---

## Running from source

### 1. Install dependencies

```
pip install -r requirements.txt
```

### 2. Enable VLC's HTTP interface

1. Open VLC → **Tools → Preferences**
2. Bottom-left: click **Show All**
3. Navigate to **Interface → Main interfaces**
4. Tick **☑ Web**
5. Navigate to **Interface → Main interfaces → Lua**
6. Under **Lua HTTP**, set a **Password** (e.g. `vlc`)
7. Click **Save** and **restart VLC**

### 3. Run

```
python main.py
```

Click **⚙ Settings** and enter the VLC password (host and port default to `localhost` / `8080`).

---

## Running as an exe (Windows)

Just double-click `KeepTrack.exe` — no Python needed. Your data (`shows.db`, `config.json`, `posters/`) is stored next to the exe.

### Build it yourself

```
pyinstaller --noconfirm --onefile --windowed --name KeepTrack ^
  --add-data "icons;icons" ^
  --collect-all customtkinter ^
  --collect-all pystray ^
  main.py
```

Output: `dist/KeepTrack.exe`

---

## Features

- **Auto-detects VLC** — polls VLC every 3 seconds; updates progress as soon as a new episode or movie is detected
- **TV Shows** — tracks season & episode; +/− buttons for manual adjustment
- **Movies** — tracks watch position in HH:MM:SS
- **Poster images** — upload a custom poster per entry; shown with rounded corners
- **Ratings** — 0.1 – 5.0 star rating via slider
- **Notes** — optional description per entry
- **Search & filter** — filter by name or minimum rating (≥ 1.0 … ≥ 4.5)
- **Copy title** — double-click a card's title to copy it to clipboard
- **System tray** — minimizing hides the app to the tray; click the tray icon to restore
- **Add to startup** — press `Win + R`, type `shell:startup`, paste a shortcut to the exe

---

## Supported filename patterns

| Pattern | Example |
|---|---|
| `S01E01` | `The.Rookie.S07E12.1080p.mkv` |
| `1x01` | `breaking_bad_3x07.mp4` |
| `Season X Episode Y` | `Show Season 2 Episode 5.avi` |

Tags in square brackets are automatically stripped (e.g. `[judas]`, `[720p]`).

---

## File structure

```
KeepTrack.exe   ← single executable
shows.db        ← your watch history (auto-created)
config.json     ← VLC connection settings (auto-created)
posters/        ← uploaded poster images (auto-created)
```
