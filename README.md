# KeepTrack — VLC TV Show Tracker

Automatically tracks which episode you're watching in VLC and keeps your progress up to date.

## Setup

### 1. Install Python dependencies

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

### 3. Configure KeepTrack

Run the app:

```
python main.py
```

Click **⚙ Settings** and enter the password you set in step 6 (host and port can stay as `localhost` / `8080`).

## Usage

- **Auto-tracking**: Play any video file in VLC whose filename includes a season/episode pattern (e.g. `The.Rookie.S07E12.mkv`). KeepTrack detects it within a few seconds and updates your progress automatically.
- **Manual add**: Click **＋ Add Show** to add or start tracking a show by hand.
- **Edit**: Click **Edit** on any card to adjust the season/episode.
- **Remove**: Click **Remove** to stop tracking a show.

## Supported filename patterns

| Pattern | Example |
|---|---|
| `S01E01` | `The.Rookie.S07E12.1080p.mkv` |
| `1x01` | `breaking_bad_3x07.mp4` |
| `Season X Episode Y` | `Show Season 2 Episode 5.avi` |
