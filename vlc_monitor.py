import threading
import time
from urllib.parse import unquote
from typing import Optional, Callable

import requests

from episode_parser import parse_episode, parse_movie


class VLCMonitor:
    """
    Polls the VLC HTTP interface every few seconds.

    Callbacks (set before calling start()):
      on_episode_detected(show: str, season: int, episode: int)
      on_movie_detected(title: str, position_seconds: int)
      on_connection_change(connected: bool)

    Movie position is also updated periodically (~every 30 s) while playing.

    VLC HTTP interface setup:
      VLC → Tools → Preferences → Show All →
      Interface → Main interfaces → ☑ Web
      Interface → Main interfaces → Lua → Lua HTTP → set a Password
      Restart VLC
    """

    POLL_INTERVAL   = 3   # seconds between polls
    MOVIE_UPDATE_N  = 10  # update movie position every N polls (≈ 30 s)

    def __init__(self, host: str = "localhost", port: int = 8080, password: str = ""):
        self.host     = host
        self.port     = port
        self.password = password

        self.on_episode_detected: Optional[Callable[[str, int, int], None]] = None
        self.on_movie_detected:   Optional[Callable[[str, int], None]]       = None
        self.on_connection_change: Optional[Callable[[bool], None]]          = None

        self._running       = False
        self._thread: Optional[threading.Thread] = None
        self._connected     = False
        self._last_filepath: Optional[str] = None
        self._current_movie: Optional[str] = None
        self._movie_ticks   = 0

    # ── Public ────────────────────────────────────────────────────────────────

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread  = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def update_config(self, host: str, port: int, password: str):
        self.host     = host
        self.port     = port
        self.password = password
        self._last_filepath  = None
        self._current_movie  = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── Internal ──────────────────────────────────────────────────────────────

    @property
    def _base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def _fetch_status(self) -> Optional[dict]:
        try:
            r = requests.get(
                f"{self._base_url}/requests/status.json",
                auth=("", self.password),
                timeout=2,
            )
            return r.json() if r.status_code == 200 else None
        except Exception:
            return None

    def _extract_filepath(self, status: dict) -> Optional[str]:
        try:
            meta = status["information"]["category"]["meta"]
            uri: str = meta.get("uri", "")
            if uri.startswith("file://"):
                path = unquote(uri)
                path = path[8:] if path.startswith("file:///") else path[7:]
                return path
            return meta.get("filename") or None
        except (KeyError, TypeError):
            return None

    def _poll_loop(self):
        while self._running:
            status    = self._fetch_status()
            connected = status is not None

            if connected != self._connected:
                self._connected = connected
                if self.on_connection_change:
                    self.on_connection_change(connected)

            if status and status.get("state") == "playing":
                filepath = self._extract_filepath(status)

                if filepath and filepath != self._last_filepath:
                    # ── New file started ──────────────────────────────────
                    self._last_filepath = filepath
                    self._movie_ticks   = 0

                    result = parse_episode(filepath)
                    if result:
                        self._current_movie = None
                        show, season, episode = result
                        if self.on_episode_detected:
                            self.on_episode_detected(show, season, episode)
                    else:
                        movie_title = parse_movie(filepath)
                        if movie_title:
                            self._current_movie = movie_title
                            position = int(status.get("time", 0))
                            if self.on_movie_detected:
                                self.on_movie_detected(movie_title, position)
                        else:
                            self._current_movie = None

                elif self._current_movie:
                    # ── Periodic movie position save ──────────────────────
                    self._movie_ticks += 1
                    if self._movie_ticks >= self.MOVIE_UPDATE_N:
                        self._movie_ticks = 0
                        position = int(status.get("time", 0))
                        if self.on_movie_detected:
                            self.on_movie_detected(self._current_movie, position)

            time.sleep(self.POLL_INTERVAL)
