import re
import os
from typing import Optional, Tuple

# Ordered by reliability
_PATTERNS = [
    (r"[Ss](\d{1,2})[Ee](\d{1,3})", 1, 2),           # S01E01
    (r"(\d{1,2})x(\d{2,3})", 1, 2),                    # 1x01
    (r"[Ss]eason\s*(\d{1,2})\s*[Ee]pisode\s*(\d{1,3})", 1, 2),  # Season 1 Episode 1
]

_VIDEO_EXTS = {
    ".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv",
    ".m4v", ".ts", ".mpg", ".mpeg", ".webm", ".rmvb",
}

# First quality/codec keyword signals the end of the actual title
_QUALITY_RE = re.compile(
    r"\b(1080[pi]|720[pi]|480[pi]|4[Kk]|2160[pi]|UHD|BluRay|Blu-Ray|"
    r"BDRip|DVDRip|WEBRip|WEB-DL|HDTV|x264|x265|HEVC|AVC|XviD|DivX|"
    r"HDR|SDR|REMUX|REPACK|PROPER|EXTENDED|UNRATED)\b"
)


def _strip_tags(s: str) -> str:
    """Remove anything inside square brackets: [720p], [judas], [group], etc."""
    return re.sub(r"\[.*?\]", "", s)


def _clean_name(raw: str) -> str:
    """Turn a raw filename fragment into a readable title."""
    name = re.sub(r"[._]", " ", raw)       # dots / underscores → spaces
    name = re.sub(r"[\s\-]+$", "", name)   # strip trailing separators
    name = re.sub(r"\s+", " ", name).strip()
    return name.title()


def parse_episode(filepath: str) -> Optional[Tuple[str, int, int]]:
    """
    Parse a filepath and return (show_name, season, episode) or None.

    Examples that work:
      The.Rookie.S07E12.1080p.mkv          → ("The Rookie", 7, 12)
      [judas] Attack on Titan S04E01.mkv   → ("Attack On Titan", 4, 1)
      breaking_bad_3x07.mp4                → ("Breaking Bad", 3, 7)
    """
    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()
    if ext and ext not in _VIDEO_EXTS:
        return None

    name_no_ext = os.path.splitext(filename)[0]
    name_no_ext = _strip_tags(name_no_ext)  # remove [tag] groups first

    for pattern, sg, eg in _PATTERNS:
        m = re.search(pattern, name_no_ext)
        if m:
            season  = int(m.group(sg))
            episode = int(m.group(eg))
            pre     = name_no_ext[: m.start()]
            show    = _clean_name(pre)
            if show:
                return show, season, episode

    return None


def parse_movie(filepath: str) -> Optional[str]:
    """
    Try to parse a filepath as a movie title.
    Returns a cleaned title string, or None if it looks like a TV episode
    or the title cannot be determined.

    Examples:
      Inception.2010.1080p.BluRay.mkv      → "Inception 2010"
      The.Dark.Knight.[2008].[1080p].mkv   → "The Dark Knight"
      some_show.S01E01.mkv                 → None  (episode, not movie)
    """
    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()
    if ext and ext not in _VIDEO_EXTS:
        return None

    name_no_ext = os.path.splitext(filename)[0]
    name_no_ext = _strip_tags(name_no_ext)

    # If it matches any episode pattern, it's a TV episode — skip
    for pattern, _, _ in _PATTERNS:
        if re.search(pattern, name_no_ext):
            return None

    # Truncate at the first quality/codec keyword so we keep only the title
    m = _QUALITY_RE.search(name_no_ext)
    cleaned = name_no_ext[: m.start()] if m else name_no_ext

    title = _clean_name(cleaned)
    return title if len(title) >= 2 else None
