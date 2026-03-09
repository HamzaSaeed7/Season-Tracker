import re
import os
from typing import Optional, Tuple

# Ordered by reliability — most common patterns first
_PATTERNS = [
    # S01E01 / s01e01 / S01E001
    (r"[Ss](\d{1,2})[Ee](\d{1,3})", 1, 2),
    # 1x01 / 01x01
    (r"(\d{1,2})x(\d{2,3})", 1, 2),
    # Season 1 Episode 1
    (r"[Ss]eason\s*(\d{1,2})\s*[Ee]pisode\s*(\d{1,3})", 1, 2),
]

# Extensions we consider valid video files
_VIDEO_EXTS = {
    ".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv",
    ".m4v", ".ts", ".mpg", ".mpeg", ".webm", ".rmvb",
}


def parse_episode(filepath: str) -> Optional[Tuple[str, int, int]]:
    """
    Parse a file path and return (show_name, season, episode) or None.

    Works with filenames like:
      The.Rookie.S07E12.1080p.BluRay.mkv
      The Rookie - S07E12 - Episode Title.mkv
      the_rookie_7x12.mkv
      Breaking.Bad.Season.2.Episode.3.mkv
    """
    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()

    # Ignore non-video files
    if ext and ext not in _VIDEO_EXTS:
        return None

    name_no_ext = os.path.splitext(filename)[0]

    for pattern, season_group, ep_group in _PATTERNS:
        match = re.search(pattern, name_no_ext)
        if match:
            season = int(match.group(season_group))
            episode = int(match.group(ep_group))

            # Everything before the season marker is the show name
            pre = name_no_ext[: match.start()]
            show_name = _clean_show_name(pre)

            if show_name:
                return show_name, season, episode

    return None


def _clean_show_name(raw: str) -> str:
    """Normalise a raw filename fragment into a readable show name."""
    # Replace dots and underscores used as word separators with spaces
    name = re.sub(r"[._]", " ", raw)

    # Strip trailing separators: dash, space
    name = re.sub(r"[\s\-]+$", "", name)

    # Collapse multiple spaces
    name = re.sub(r"\s+", " ", name).strip()

    # Title-case each word
    name = name.title()

    return name
