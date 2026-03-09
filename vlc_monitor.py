import threading
import time
from urllib.parse import unquote
from typing import Optional, Callable, Tuple

import requests

from episode_parser import parse_episode


class VLCMonitor:
    """
    Polls the VLC HTTP interface every few seconds.

    Callbacks (set before calling start()):
      on_episode_detected(show: str, season: int, episode: int)
      on_connection_change(connected: bool)

    VLC HTTP interface must be enabled:
      VLC > Tools > Preferences > Show All >
      Interface > Main interfaces > check "Web"
      Interface > Main interfaces > Lua > Lua HTTP > set a password
      Restart VLC
    """

    POLL_INTERVAL = 3  # seconds

    def __init__(self, host: str = "localhost", port: int = 8080, password: str = ""):
        self.host = host
        self.port = port
        self.password = password

        self.on_episode_detected: Optional[Callable[[str, int, int], None]] = None
        self.on_connection_change: Optional[Callable[[bool], None]] = None

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._connected = False
        self._last_filepath: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def update_config(self, host: str, port: int, password: str):
        self.host = host
        self.port = port
        self.password = password
        self._last_filepath = None  # force re-detection after config change

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @property
    def _base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def _fetch_status(self) -> Optional[dict]:
        try:
            resp = requests.get(
                f"{self._base_url}/requests/status.json",
                auth=("", self.password),
                timeout=2,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    def _extract_filepath(self, status: dict) -> Optional[str]:
        """Pull the currently-playing file path from a VLC status dict."""
        try:
            meta = status["information"]["category"]["meta"]

            # Prefer the full URI so we have the complete path
            uri: str = meta.get("uri", "")
            if uri.startswith("file://"):
                path = unquote(uri)
                # Strip file:/// (Windows) or file:// (Unix)
                if path.startswith("file:///"):
                    path = path[8:]  # -> C:/path/file.mkv
                elif path.startswith("file://"):
                    path = path[7:]
                return path

            # Fallback: just the filename
            filename = meta.get("filename", "")
            return filename or None
        except (KeyError, TypeError):
            return None

    def _poll_loop(self):
        while self._running:
            status = self._fetch_status()
            connected = status is not None

            # Fire connection-change callback
            if connected != self._connected:
                self._connected = connected
                if self.on_connection_change:
                    self.on_connection_change(connected)

            if status and status.get("state") == "playing":
                filepath = self._extract_filepath(status)
                if filepath and filepath != self._last_filepath:
                    self._last_filepath = filepath
                    result = parse_episode(filepath)
                    if result and self.on_episode_detected:
                        show, season, episode = result
                        self.on_episode_detected(show, season, episode)

            time.sleep(self.POLL_INTERVAL)
