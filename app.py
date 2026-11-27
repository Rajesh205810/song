import html
import json
import os
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote
from urllib.request import Request, urlopen

import streamlit as st
import streamlit.components.v1 as components
import yt_dlp

BASE_DIR = Path(__file__).resolve().parent
FAVORITES_FILE = BASE_DIR / "favorites.json"
HISTORY_FILE = BASE_DIR / "history.json"
MAX_FAVORITES = 200
MAX_HISTORY_ITEMS = 24
SEARCH_LIMIT = 12
RECOMMENDATION_LIMIT = 30
PRELOAD_NEXT = 2  # how many upcoming songs the browser player keeps ready (for screen-lock playback)

_FALLBACK_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' width='600' height='600'>"
    "<rect width='100%' height='100%' fill='#121212'/>"
    "<text x='50%' y='50%' fill='#1DB954' font-family='Arial' font-size='34' "
    "text-anchor='middle'>No Cover Art</text></svg>"
)
FALLBACK_THUMBNAIL = "data:image/svg+xml;charset=utf-8," + quote(_FALLBACK_SVG)

st.set_page_config(
    page_title="Spotify Streamer",
    page_icon="🎧",
    layout="wide",
    initial_sidebar_state="collapsed",
)

SPOTIFY_CSS = """
<style>
    @keyframes popIn {
        0% { opacity: 0; transform: translateY(8px) scale(0.985); }
        100% { opacity: 1; transform: translateY(0) scale(1); }
    }

    html, body, [data-testid="stMain"], section.main { scroll-behavior: smooth; }

    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: #000000 !important;
        color: #ffffff !important;
    }
    section[data-testid="stSidebar"] {
        background-color: #090909 !important;
        border-right: 1px solid #262626 !important;
        transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1), width 0.28s cubic-bezier(0.22, 1, 0.36, 1) !important;
    }
    section[data-testid="stSidebar"] * { color: #ffffff !important; }
    .block-container {
        padding-top: 3.8rem !important;
        padding-bottom: 6rem !important;
        animation: popIn 0.26s ease-out;
    }
    .top-bar-spacer { height: 12px; }
    h1, h2, h3, h4, p, label, span, div, .stMarkdown { color: #ffffff !important; }
    [data-testid="stCaptionContainer"], .stCaption { color: #d4d4d8 !important; }

    /* smooth fade/slide for everything that appears on a page */
    [data-testid="stElementContainer"] { animation: popIn 0.28s ease-out both; }
    [data-testid="stImage"] { overflow: hidden; }
    [data-testid="stImage"] img {
        transition: transform 0.35s cubic-bezier(0.22, 1, 0.36, 1), filter 0.25s ease;
    }
    [data-testid="stImage"]:hover img { transform: scale(1.04); filter: brightness(1.08); }

    /* invisible helper iframes / hidden sync button must not take up space */
    [data-testid="stElementContainer"]:has(iframe[height="0"]) {
        position: absolute; width: 0; height: 0; overflow: hidden;
        opacity: 0; pointer-events: none; margin: 0;
    }
    .st-key-player_sync_btn { display: none !important; }

    [data-testid="stForm"] {
        background: #141417 !important;
        border: 1.5px solid #2e2e36 !important;
        border-radius: 999px !important;
        padding: 6px 12px !important;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.75), 0 0 0 1px rgba(29, 185, 84, 0.18) !important;
        transform: translateY(0px);
        transition: transform 0.2s cubic-bezier(0.22, 1, 0.36, 1), box-shadow 0.2s ease, border-color 0.2s ease !important;
    }
    [data-testid="stForm"]:hover, [data-testid="stForm"]:focus-within {
        transform: translateY(-3px) !important;
        border-color: #1db954 !important;
        box-shadow: 0 16px 32px rgba(0, 0, 0, 0.9), 0 0 18px rgba(29, 185, 84, 0.38) !important;
    }
    input[type="text"] {
        background-color: #1f1f24 !important;
        color: #ffffff !important;
        border: 1px solid #3f3f46 !important;
        border-radius: 999px !important;
        padding: 0.45rem 0.9rem !important;
    }
    input[type="text"]::placeholder { color: #a1a1aa !important; }

    .song-card {
        background-color: #111111;
        border: 1px solid #27272a;
        border-radius: 12px;
        padding: 12px;
        margin-bottom: 14px;
        animation: popIn 0.24s ease-out;
        transition: transform 0.2s ease, border-color 0.2s ease, background-color 0.2s ease;
    }
    .song-card:hover {
        transform: translateY(-2px);
        border-color: #1db954;
        background-color: #16161a;
    }
    .song-title {
        font-weight: 700;
        font-size: 0.96rem;
        color: #ffffff !important;
        margin-top: 8px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .song-artist {
        font-size: 0.84rem;
        color: #d4d4d8 !important;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        margin-bottom: 8px;
    }
    .now-playing-box {
        background-color: #111111;
        border: 1px solid #27272a;
        border-radius: 16px;
        padding: 22px;
        max-width: 580px;
        margin: 0 auto 24px auto;
        text-align: center;
        animation: popIn 0.32s ease-out;
    }
    div.stButton > button, div.stFormSubmitButton > button {
        background-color: #1db954 !important;
        color: #000000 !important;
        border: none !important;
        border-radius: 999px !important;
        font-weight: 700 !important;
        padding: 0.3rem 0.75rem !important;
        font-size: 0.84rem !important;
        min-height: 2.1rem !important;
        transition: transform 0.14s ease, background-color 0.14s ease !important;
    }
    div.stButton > button:hover, div.stFormSubmitButton > button:hover {
        background-color: #1ed760 !important;
        color: #000000 !important;
        transform: scale(1.02);
    }
    div.stButton > button:active, div.stFormSubmitButton > button:active { transform: scale(0.97) !important; }

    @media (prefers-reduced-motion: reduce) {
        * { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
    }
</style>
"""
st.markdown(SPOTIFY_CSS, unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# Persistence (local JSON + optional GitHub Gist). Favorites are never wiped:
#  - writes are atomic
#  - Gist is only written when it was reachable at load time (otherwise merged later)
# ----------------------------------------------------------------------------
def get_gist_config() -> tuple:
    try:
        token = st.secrets.get("GITHUB_TOKEN")
        gist_id = st.secrets.get("GIST_ID")
    except Exception:
        return None, None
    if token and gist_id:
        return str(token).strip(), str(gist_id).strip()
    return None, None


def _gist_headers(token: str, with_body: bool = False) -> Dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "SpotifyStreamerApp",
    }
    if with_body:
        headers["Content-Type"] = "application/json"
    return headers


def fetch_gist_files() -> Optional[Dict[str, Any]]:
    token, gist_id = get_gist_config()
    if not token or not gist_id:
        return None
    req = Request(f"https://api.github.com/gists/{gist_id}", headers=_gist_headers(token), method="GET")
    try:
        with urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        files = payload.get("files")
        return files if isinstance(files, dict) else None
    except Exception:
        return None


class GistWriter:
    """Background, latest-wins Gist writer so saving never blocks the UI."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: Dict[str, str] = {}
        self._running = False
        self.last_error: Optional[str] = None

    def submit(self, token: str, gist_id: str, filename: str, content: str) -> None:
        with self._lock:
            self._pending[filename] = content
            if self._running:
                return
            self._running = True
        threading.Thread(target=self._drain, args=(token, gist_id), daemon=True).start()

    def _drain(self, token: str, gist_id: str) -> None:
        while True:
            with self._lock:
                if not self._pending:
                    self._running = False
                    return
                name, content = self._pending.popitem()
            try:
                body = json.dumps({"files": {name: {"content": content}}}).encode("utf-8")
                req = Request(
                    f"https://api.github.com/gists/{gist_id}",
                    data=body,
                    headers=_gist_headers(token, with_body=True),
                    method="PATCH",
                )
                with urlopen(req, timeout=15) as resp:
                    resp.read()
            except Exception as exc:
                self.last_error = f"Could not sync {name} to Gist: {exc}"


@st.cache_resource
def get_gist_writer() -> GistWriter:
    return GistWriter()


def format_duration(seconds: Optional[float]) -> str:
    if not seconds or seconds <= 0:
        return "0:00"
    total = int(seconds)
    mins, secs = divmod(total, 60)
    hours, mins = divmod(mins, 60)
    if hours > 0:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def pick_thumbnail(entry: Dict[str, Any]) -> str:
    if entry.get("thumbnail"):
        return str(entry["thumbnail"])
    thumbs = entry.get("thumbnails")
    if isinstance(thumbs, list) and thumbs:
        for item in reversed(thumbs):
            if isinstance(item, dict) and item.get("url"):
                return str(item["url"])
    return FALLBACK_THUMBNAIL


def normalize_track(entry: Any, fallback_index: int = 0) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None
    video_id = entry.get("id") or entry.get("webpage_url_basename")
    url = entry.get("webpage_url") or entry.get("url")
    if not url and video_id:
        url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        duration = float(entry.get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    return {
        "id": str(video_id or url or f"track_{fallback_index}"),
        "title": str(entry.get("title") or entry.get("name") or "Untitled Track"),
        "artist": str(
            entry.get("artist") or entry.get("uploader") or entry.get("channel") or "Unknown Artist"
        ),
        "duration": duration,
        "thumbnail": pick_thumbnail(entry),
        "webpage_url": str(url or ""),
    }


def parse_track_list(raw_data: Any, max_items: Optional[int] = None) -> List[Dict[str, Any]]:
    if not isinstance(raw_data, list):
        return []
    normalized: List[Dict[str, Any]] = []
    seen_ids = set()
    for idx, item in enumerate(raw_data):
        clean = normalize_track(item, fallback_index=idx)
        if clean and clean["id"] not in seen_ids:
            seen_ids.add(clean["id"])
            normalized.append(clean)
            if max_items and len(normalized) >= max_items:
                break
    return normalized


def merge_unique(primary: List[Dict[str, Any]], secondary: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = {t.get("id") for t in primary}
    return primary + [t for t in secondary if t.get("id") not in seen]


def load_json_list(
    file_path: Path, gist_files: Optional[Dict[str, Any]], max_items: Optional[int] = None
) -> List[Dict[str, Any]]:
    # 1) Gist (cloud copy)
    if gist_files and file_path.name in gist_files:
        file_obj = gist_files[file_path.name]
        raw = file_obj.get("content") if isinstance(file_obj, dict) else None
        if isinstance(raw, str) and raw.strip():
            try:
                items = parse_track_list(json.loads(raw), max_items=max_items)
                if items:
                    return items
            except json.JSONDecodeError:
                pass
    # 2) Local file (also covers "Gist empty but local favorites exist")
    if file_path.exists():
        try:
            with file_path.open("r", encoding="utf-8") as f:
                return parse_track_list(json.load(f), max_items=max_items)
        except (json.JSONDecodeError, OSError):
            pass
    return []


def save_json_list(file_path: Path, items: List[Dict[str, Any]]) -> None:
    serialized = json.dumps(items, indent=2, ensure_ascii=False)
    try:  # atomic write: a crash can never leave a half-written (empty) file
        fd, tmp = tempfile.mkstemp(dir=BASE_DIR, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(serialized)
        os.replace(tmp, file_path)
    except OSError:
        pass
    token, gist_id = get_gist_config()
    if token and gist_id and st.session_state.get("gist_ready", True):
        get_gist_writer().submit(token, gist_id, file_path.name, serialized)


# ----------------------------------------------------------------------------
# yt-dlp helpers
# ----------------------------------------------------------------------------
def _yt_search(query: str, limit: int) -> List[Dict[str, Any]]:
    clean_query = query.strip()
    if not clean_query:
        return []
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{limit}:{clean_query}", download=False)
    entries = info.get("entries") if isinstance(info, dict) else []
    tracks: List[Dict[str, Any]] = []
    for idx, raw in enumerate(entries or []):
        track = normalize_track(raw, fallback_index=idx)
        if track and track.get("webpage_url"):
            tracks.append(track)
    return tracks[:limit]


@st.cache_data(ttl=900, show_spinner=False)
def search_tracks(query: str, limit: int = SEARCH_LIMIT) -> List[Dict[str, Any]]:
    return _yt_search(query, limit)


@st.cache_data(ttl=900, show_spinner=False)
def get_similar_tracks(
    track_id: str,
    title: str,
    artist: str,
    last_query: str = "",
    limit: int = RECOMMENDATION_LIMIT,
) -> List[Dict[str, Any]]:
    similar: List[Dict[str, Any]] = []
    seen_ids = {track_id} if track_id else set()

    if track_id and not track_id.startswith("http") and not track_id.startswith("track_"):
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "skip_download": True,
            "playlistend": limit + 10,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={track_id}&list=RD{track_id}", download=False
                )
            entries = info.get("entries") if isinstance(info, dict) else []
            for idx, raw in enumerate(entries or []):
                item = normalize_track(raw, fallback_index=idx)
                if item and item["id"] not in seen_ids and item.get("webpage_url"):
                    seen_ids.add(item["id"])
                    similar.append(item)
                    if len(similar) >= limit:
                        return similar
        except Exception:
            pass

    queries: List[str] = []
    if last_query.strip():
        queries.append(f"{last_query.strip()} songs")
    if artist and artist != "Unknown Artist":
        queries.append(f"{artist} top songs")
        queries.append(f"songs like {artist}")
    if title and title != "Untitled Track":
        queries.append(f"{title} similar songs")
        queries.append(f"{artist} {title} mix".strip())

    def safe_search(q: str) -> List[Dict[str, Any]]:
        try:
            return _yt_search(q, 14)
        except Exception:
            return []

    if queries:  # run the searches in parallel instead of one after another
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(safe_search, queries))
        for batch in results:
            for item in batch:
                if item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    similar.append(item)
                    if len(similar) >= limit:
                        return similar
    return similar[:limit]


@st.cache_data(ttl=1200, show_spinner=False)
def resolve_stream(webpage_url: str) -> Optional[Dict[str, Any]]:
    if not webpage_url:
        return None
    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(webpage_url, download=False)
    if not isinstance(info, dict):
        return None
    url = info.get("url")
    if not url:
        for fmt in reversed(info.get("formats") or []):
            if isinstance(fmt, dict) and fmt.get("url") and fmt.get("acodec") != "none":
                url = fmt["url"]
                break
    if not url:
        return None
    try:
        duration = float(info.get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    return {"url": str(url), "duration": duration}


# ----------------------------------------------------------------------------
# Session state
# ----------------------------------------------------------------------------
def init_state() -> None:
    ss = st.session_state
    if "sid" in ss:
        return
    ss.sid = uuid.uuid4().hex
    ss.page = "Home"
    ss.show_favorites = False
    ss.collapse_sidebar_once = False

    configured = bool(get_gist_config()[0])
    gist_files = fetch_gist_files() if configured else None
    ss.gist_ready = (gist_files is not None) or not configured
    ss.favorites = load_json_list(FAVORITES_FILE, gist_files, max_items=MAX_FAVORITES)
    ss.history = load_json_list(HISTORY_FILE, gist_files, max_items=MAX_HISTORY_ITEMS)

    ss.recommendations = []
    ss.search_results = []
    ss.last_query = ""
    ss.current_track = ss.history[0] if ss.history else None
    ss.is_playing = False
    ss.player_seq = 0
    ss.scroll_top = False
    ss.upcoming_cache = []


def ensure_storage_ready() -> None:
    """If the Gist was unreachable at start, retry and MERGE (never overwrite) when it is back."""
    ss = st.session_state
    if ss.gist_ready or not get_gist_config()[0]:
        return
    files = fetch_gist_files()
    if files is None:
        return
    ss.gist_ready = True
    ss.favorites = merge_unique(
        ss.favorites, load_json_list(FAVORITES_FILE, files, max_items=MAX_FAVORITES)
    )[:MAX_FAVORITES]
    ss.history = merge_unique(
        ss.history, load_json_list(HISTORY_FILE, files, max_items=MAX_HISTORY_ITEMS)
    )[:MAX_HISTORY_ITEMS]
    save_json_list(FAVORITES_FILE, ss.favorites)
    save_json_list(HISTORY_FILE, ss.history)


def toggle_favorite(track: Dict[str, Any]) -> None:
    safe = normalize_track(track)
    if not safe:
        return
    favs = st.session_state.favorites
    if any(item.get("id") == safe["id"] for item in favs):
        updated = [item for item in favs if item.get("id") != safe["id"]]
    else:
        updated = ([safe] + favs)[:MAX_FAVORITES]
    st.session_state.favorites = updated
    save_json_list(FAVORITES_FILE, updated)


def record_history(track: Dict[str, Any]) -> None:
    safe = normalize_track(track)
    if not safe:
        return
    history = st.session_state.history
    if history and history[0].get("id") == safe["id"]:
        return
    updated = ([safe] + [t for t in history if t.get("id") != safe["id"]])[:MAX_HISTORY_ITEMS]
    st.session_state.history = updated
    save_json_list(HISTORY_FILE, updated)


# ----------------------------------------------------------------------------
# Queue logic: after a song ends, play on through the FAVORITES list.
# ----------------------------------------------------------------------------
def ensure_recommendations(seed: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ss = st.session_state
    if not ss.recommendations and seed:
        with st.spinner("Loading similar song recommendations..."):
            ss.recommendations = get_similar_tracks(
                track_id=seed.get("id", ""),
                title=seed.get("title", ""),
                artist=seed.get("artist", ""),
                last_query=ss.last_query,
                limit=RECOMMENDATION_LIMIT,
            )
    return ss.recommendations


def next_track_for(current: Optional[Dict[str, Any]], delta: int) -> Optional[Dict[str, Any]]:
    ss = st.session_state
    cid = current.get("id") if current else None
    favs = ss.favorites
    ids = [t.get("id") for t in favs]
    if delta > 0:
        if favs:
            return favs[(ids.index(cid) + 1) % len(favs)] if cid in ids else favs[0]
        for t in ensure_recommendations(current):
            if t.get("id") != cid:
                return t
        return None
    if favs and cid in ids:
        return favs[(ids.index(cid) - 1) % len(favs)]
    for t in ss.history:
        if t.get("id") != cid:
            return t
    return favs[-1] if favs else None


def upcoming_tracks(current: Dict[str, Any], count: int) -> List[Dict[str, Any]]:
    ss = st.session_state
    if not ss.favorites:
        cid = current.get("id")
        return [t for t in ensure_recommendations(current) if t.get("id") != cid][:count]
    out: List[Dict[str, Any]] = []
    cursor: Optional[Dict[str, Any]] = current
    for _ in range(count):
        cursor = next_track_for(cursor, 1)
        if not cursor:
            break
        out.append(cursor)
    return out


def find_known_track(track_id: str) -> Optional[Dict[str, Any]]:
    ss = st.session_state
    for pool in (ss.favorites, ss.recommendations, ss.upcoming_cache, ss.history, ss.search_results):
        for item in pool:
            if item.get("id") == track_id:
                return item
    return None


def start_track(track: Dict[str, Any], autoplay: bool = True, navigate: bool = True) -> None:
    clean = normalize_track(track)
    if not clean:
        return
    ss = st.session_state
    ss.current_track = clean
    ss.is_playing = autoplay
    ss.recommendations = []  # loaded lazily AFTER playback starts
    ss.player_seq += 1
    if navigate:
        ss.show_favorites = False
        ss.page = "Song Page"
        ss.scroll_top = True
    record_history(clean)


def open_song_page(track: Dict[str, Any], autoplay: bool = True) -> None:
    start_track(track, autoplay=autoplay)
    st.rerun()


def step_track(delta: int, rerun: bool = True, navigate: bool = True) -> None:
    current = normalize_track(st.session_state.current_track)
    target = next_track_for(current, delta)
    if not target:
        return
    start_track(target, autoplay=True, navigate=navigate)
    if rerun:
        st.rerun()


def stop_playback() -> None:
    st.session_state.is_playing = False
    st.session_state.player_seq += 1
    st.rerun()


def apply_player_sync() -> None:
    """The browser player moved on by itself (song ended / screen locked); catch Python state up."""
    ss = st.session_state
    np_id = st.query_params.get("np")
    st.query_params.clear()
    if not np_id:
        return
    if np_id in ("__next__", "__prev__"):
        step_track(1 if np_id == "__next__" else -1, rerun=False, navigate=False)
        return
    track = find_known_track(np_id)
    if track:
        ss.current_track = track
        ss.is_playing = True
        ss.recommendations = []
        if ss.page == "Song Page":
            ss.scroll_top = True
        record_history(track)


# ----------------------------------------------------------------------------
# Browser-side player. The <audio> element lives in the PARENT page (outside
# Streamlit's re-render cycle), so playback survives reruns and screen lock, and
# the next song is swapped in directly (no tap needed). Track end is detected by
# the real duration, which fixes the "plays blank for minutes after the song" bug.
# ----------------------------------------------------------------------------
PLAYER_JS = r"""
<script>
(function () {
  var P = window.parent, D = P.document;
  var payload = __PAYLOAD__;

  function build() {
    var pl = { v: 3, track: null, upcoming: [], seq: -1, sid: null, advancing: false };
    var bar = D.createElement("div");
    bar.id = "sp-player-bar";
    bar.style.cssText = "position:fixed;left:50%;bottom:calc(14px + env(safe-area-inset-bottom));width:min(620px,94vw);" +
      "z-index:99999;background:#141417;border:1px solid #2e2e36;border-radius:999px;padding:6px 14px;" +
      "box-shadow:0 12px 32px rgba(0,0,0,.85),0 0 0 1px rgba(29,185,84,.22);transform:translate(-50%,170%);opacity:0;" +
      "transition:transform .45s cubic-bezier(.22,1,.36,1),opacity .3s ease;";
    var audio = D.createElement("audio");
    audio.controls = true;
    audio.preload = "auto";
    audio.setAttribute("playsinline", "");
    audio.style.cssText = "width:100%;height:38px;display:block;color-scheme:dark;";
    bar.appendChild(audio);
    D.body.appendChild(bar);

    function scrollTop() {
      var el = D.querySelector('[data-testid="stMain"]') || D.querySelector("section.main") ||
               D.querySelector('[data-testid="stAppViewContainer"]');
      if (el && el.scrollTo) el.scrollTo({ top: 0, behavior: "smooth" });
      P.scrollTo({ top: 0, behavior: "smooth" });
    }

    function clickSync(tries) {
      var btn = D.querySelector(".st-key-player_sync_btn button");
      if (!btn) {
        var all = D.querySelectorAll("button");
        for (var i = 0; i < all.length; i++) {
          if ((all[i].textContent || "").trim() === "player-sync") { btn = all[i]; break; }
        }
      }
      if (btn) { btn.click(); return; }
      if (tries < 10) setTimeout(function () { clickSync(tries + 1); }, 400);
    }

    function notify(id) {
      try {
        var u = new URL(P.location.href);
        u.searchParams.set("np", id);
        P.history.replaceState(null, "", u.toString());
      } catch (e) {}
      clickSync(0);
    }

    function setMedia(t) {
      try {
        if ("mediaSession" in P.navigator) {
          P.navigator.mediaSession.metadata = new P.MediaMetadata({
            title: t.title, artist: t.artist,
            artwork: [{ src: t.thumb, sizes: "512x512", type: "image/jpeg" }]
          });
        }
      } catch (e) {}
    }

    function load(t, play) {
      pl.track = t;
      pl.advancing = false;
      audio.src = t.url;
      if (play) {
        var p = audio.play();
        if (p && p.catch) p.catch(function () {});
      }
      setMedia(t);
      bar.style.transform = "translate(-50%,0)";
      bar.style.opacity = "1";
    }

    function advance() {
      if (pl.advancing) return;
      pl.advancing = true;
      var next = pl.upcoming.shift();
      if (next) {
        load(next, true);
        notify(next.id);
      } else {
        audio.pause();
        notify("__next__");
      }
    }

    audio.addEventListener("ended", advance);
    audio.addEventListener("timeupdate", function () {
      var t = pl.track;
      // stop at the REAL song length (some streams report a much longer, blank tail)
      if (t && !pl.advancing && t.duration > 5 && audio.currentTime >= t.duration - 0.4) advance();
    });

    try {
      var ms = P.navigator.mediaSession;
      if (ms) {
        ms.setActionHandler("nexttrack", advance);
        ms.setActionHandler("previoustrack", function () { notify("__prev__"); });
      }
    } catch (e) {}

    pl.sync = function (p) {
      if (pl.sid !== p.sid) { pl.sid = p.sid; pl.seq = -1; }
      if (Array.isArray(p.upcoming)) {
        var ups = p.upcoming.filter(function (x) { return x && x.url; });
        if (pl.track) {
          for (var i = 0; i < ups.length; i++) {
            if (ups[i].id === pl.track.id) { ups = ups.slice(i + 1); break; }
          }
        }
        pl.upcoming = ups;
      }
      if (p.seq > pl.seq) {
        pl.seq = p.seq;
        if (!p.playing) {
          audio.pause();
        } else if (p.current) {
          if (!pl.track || pl.track.id !== p.current.id || pl.advancing) {
            load(p.current, true);
          } else {
            var pr = audio.play();
            if (pr && pr.catch) pr.catch(function () {});
          }
        }
      }
      if (p.scroll) setTimeout(scrollTop, 80);
    };

    P.__spotifyPlayer = pl;
    return pl;
  }

  var pl = P.__spotifyPlayer;
  if (!pl || pl.v !== 3) pl = build();
  pl.sync(payload);
})();
</script>
"""


def emit_player_payload(payload: Dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    components.html(PLAYER_JS.replace("__PAYLOAD__", data), height=0)


def player_track(track: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    info = resolve_stream(track.get("webpage_url", ""))
    if not info:
        return None
    return {
        "id": track.get("id"),
        "title": track.get("title", ""),
        "artist": track.get("artist", ""),
        "thumb": track.get("thumbnail", FALLBACK_THUMBNAIL),
        "url": info["url"],
        "duration": info.get("duration") or track.get("duration") or 0,
    }


def render_player() -> None:
    ss = st.session_state
    scroll = bool(ss.pop("scroll_top", False))
    track = normalize_track(ss.current_track)
    base = {"sid": ss.sid, "seq": ss.player_seq, "playing": bool(ss.is_playing and track), "scroll": scroll}

    if not base["playing"]:
        emit_player_payload({**base, "current": None, "upcoming": None})
        return

    try:
        with st.spinner("Loading audio stream..."):
            current = player_track(track)
    except Exception as exc:
        st.error(f"Could not extract audio stream: {exc}")
        emit_player_payload({**base, "current": None, "upcoming": None})
        return
    if not current:
        st.warning("Direct audio stream unavailable for this track.")
        emit_player_payload({**base, "current": None, "upcoming": None})
        return

    # 1) start playing immediately
    emit_player_payload({**base, "current": current, "upcoming": None})

    # 2) then prepare the next songs (from favorites) for hands-free / screen-locked playback
    upcoming: List[Dict[str, Any]] = []
    queue = upcoming_tracks(track, PRELOAD_NEXT)
    ss.upcoming_cache = queue
    for item in queue:
        try:
            ready = player_track(item)
        except Exception:
            ready = None
        if ready:
            upcoming.append(ready)
    emit_player_payload({**base, "scroll": False, "current": current, "upcoming": upcoming})


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------
def trigger_sidebar_collapse_animation() -> None:
    st.session_state.collapse_sidebar_once = True


def render_sidebar_collapse_if_requested() -> None:
    if not st.session_state.get("collapse_sidebar_once"):
        return
    st.session_state.collapse_sidebar_once = False
    components.html(
        """
        <script>
        (function() {
            const parentDoc = window.parent.document;
            let attempts = 0;
            const interval = setInterval(() => {
                attempts += 1;
                const sidebar = parentDoc.querySelector('section[data-testid="stSidebar"]');
                const isExpanded = sidebar && sidebar.getAttribute('aria-expanded') === 'true';
                if (!sidebar || !isExpanded) { clearInterval(interval); return; }
                const closeBtn =
                    parentDoc.querySelector('[data-testid="stSidebarCollapseButton"] button') ||
                    parentDoc.querySelector('section[data-testid="stSidebar"] button[kind="header"]') ||
                    parentDoc.querySelector('button[aria-label="Close sidebar"]');
                if (closeBtn) { closeBtn.click(); clearInterval(interval); }
                if (attempts >= 12) clearInterval(interval);
            }, 60);
        })();
        </script>
        """,
        height=0,
    )


def render_track_grid(tracks: List[Dict[str, Any]], key_prefix: str) -> None:
    fav_ids = {item.get("id") for item in st.session_state.favorites}
    cols = st.columns(3)
    for idx, raw_track in enumerate(tracks):
        track = normalize_track(raw_track, fallback_index=idx)
        if not track:
            continue
        title = track["title"]
        artist = track["artist"]
        track_id = track["id"]
        with cols[idx % 3]:
            st.markdown('<div class="song-card">', unsafe_allow_html=True)
            st.image(track["thumbnail"], use_container_width=True)
            st.markdown(
                f'<div class="song-title" title="{html.escape(title)}">{html.escape(title)}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="song-artist" title="{html.escape(artist)}">'
                f"{html.escape(artist)} · {format_duration(track['duration'])}</div>",
                unsafe_allow_html=True,
            )
            c1, c2 = st.columns([2, 1])
            with c1:
                if st.button("Play", key=f"{key_prefix}_open_{idx}_{track_id}", use_container_width=True):
                    open_song_page(track)
            with c2:
                fav_label = "♥" if track_id in fav_ids else "♡"
                if st.button(fav_label, key=f"{key_prefix}_fav_{idx}_{track_id}", use_container_width=True):
                    toggle_favorite(track)
                    st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)


def run_search_from_top(query: str) -> None:
    clean_query = query.strip()
    if not clean_query:
        return
    st.session_state.last_query = clean_query
    st.session_state.show_favorites = False
    trigger_sidebar_collapse_animation()
    with st.spinner("Searching tracks..."):
        try:
            st.session_state.search_results = search_tracks(clean_query, limit=SEARCH_LIMIT)
        except Exception as exc:
            st.error(f"Search failed: {exc}")
            st.session_state.search_results = []
    st.session_state.page = "Search"
    st.rerun()


def render_top_bar() -> None:
    st.markdown('<div class="top-bar-spacer"></div>', unsafe_allow_html=True)
    col_search, col_fav_btn = st.columns([5.2, 1.3])
    with col_search:
        with st.form("top_home_search_form", clear_on_submit=False):
            c_in, c_go = st.columns([5, 1.3])
            with c_in:
                top_query = st.text_input(
                    "Search",
                    value=st.session_state.last_query,
                    placeholder="Search songs or artists...",
                    label_visibility="collapsed",
                )
            with c_go:
                go_clicked = st.form_submit_button("Search", use_container_width=True)
    with col_fav_btn:
        fav_btn_label = (
            "Hide Favourites"
            if st.session_state.show_favorites
            else f"♥ Favourites ({len(st.session_state.favorites)}/{MAX_FAVORITES})"
        )
        if st.button(fav_btn_label, key="top_favourites_bar_btn", use_container_width=True):
            st.session_state.show_favorites = not st.session_state.show_favorites
            trigger_sidebar_collapse_animation()
            st.rerun()

    if go_clicked and top_query.strip():
        run_search_from_top(top_query)


def render_favorites_drawer_section() -> None:
    if not st.session_state.show_favorites:
        return
    st.subheader(f"♥ Favourites ({len(st.session_state.favorites)} / {MAX_FAVORITES})")
    if not st.session_state.favorites:
        st.info("No favourite songs saved yet. Click ♡ on any song card to add one.")
    else:
        render_track_grid(st.session_state.favorites, key_prefix="fav_section")
    st.divider()


def render_recommendations_section(key_prefix: str) -> None:
    ss = st.session_state
    seed = normalize_track(ss.current_track) or (normalize_track(ss.history[0]) if ss.history else None)
    recs = ensure_recommendations(seed)
    if not recs:
        return
    st.subheader(f"Recommended Similar Songs ({len(recs)})")
    render_track_grid(recs, key_prefix=key_prefix)


def render_sidebar() -> None:
    with st.sidebar:
        st.title("🎧 Spotify Streamer")
        for label, key, page in (
            ("Home", "side_home_btn", "Home"),
            ("Search", "side_search_btn", "Search"),
            ("Now Playing", "side_player_btn", "Song Page"),
        ):
            if st.button(label, key=key, use_container_width=True):
                st.session_state.page = page
                st.session_state.show_favorites = False
                trigger_sidebar_collapse_animation()
                st.rerun()

        st.divider()
        fav_side_label = f"♥ Favourites ({len(st.session_state.favorites)}/{MAX_FAVORITES})"
        if st.button(fav_side_label, key="side_fav_toggle_btn", use_container_width=True):
            st.session_state.show_favorites = True
            trigger_sidebar_collapse_animation()
            st.rerun()

        current = normalize_track(st.session_state.current_track)
        if current:
            st.divider()
            st.caption("Now Selected")
            st.markdown(f"**{current['title']}**")
            st.caption(current["artist"])
        if not st.session_state.gist_ready:
            st.caption("☁ Cloud sync offline - favourites are safe locally and will merge when it reconnects.")


def render_home_page() -> None:
    render_top_bar()
    render_favorites_drawer_section()
    st.header("Home — Previously Played Songs")
    if not st.session_state.history:
        st.info("No previously played songs yet. Use the search bar above to find and play a song.")
        render_player()
        return
    render_track_grid(st.session_state.history, key_prefix="home_history")
    render_player()
    st.divider()
    render_recommendations_section(key_prefix="home_recs")


def render_search_page() -> None:
    render_top_bar()
    render_favorites_drawer_section()
    st.header("Search Results")
    if st.session_state.search_results:
        st.caption(f'Showing up to {SEARCH_LIMIT} results for "{st.session_state.last_query}"')
        render_track_grid(st.session_state.search_results, key_prefix="search_results")
    elif st.session_state.last_query:
        st.warning("No matching tracks found. Try another search term.")
    else:
        st.info("Type a song or artist in the search bar at the top and click Search.")
    render_player()


def render_song_page() -> None:
    render_top_bar()
    render_favorites_drawer_section()
    track = normalize_track(st.session_state.current_track)
    if not track:
        st.info("No track selected yet. Search for a song or pick one from Home.")
        render_player()
        return

    title = track["title"]
    track_id = track["id"]

    st.header("Now Playing")
    st.markdown('<div class="now-playing-box">', unsafe_allow_html=True)
    _, img_col, _ = st.columns([1, 2, 1])
    with img_col:
        st.image(track["thumbnail"], use_container_width=True)

    st.markdown(f"### {title}")
    st.markdown(
        f'<div class="song-artist">{html.escape(track["artist"])} · {format_duration(track["duration"])}</div>',
        unsafe_allow_html=True,
    )
    if not st.session_state.is_playing:
        st.caption("Stopped. Click **Play** below to stream audio.")

    c_prev, c_next, c_stop, c_fav = st.columns(4)
    with c_prev:
        if st.button("⏮ Prev", key="now_playing_prev_btn", use_container_width=True):
            step_track(-1)
    with c_next:
        if st.button("⏭ Next", key="now_playing_next_btn", use_container_width=True):
            step_track(1)
    with c_stop:
        if st.button("⏹ Stop", key="now_playing_stop_btn", use_container_width=True):
            stop_playback()
    with c_fav:
        is_fav = any(item.get("id") == track_id for item in st.session_state.favorites)
        if st.button("♥ Saved" if is_fav else "♡ Fav", key="now_playing_fav_btn", use_container_width=True):
            toggle_favorite(track)
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
    render_player()
    render_recommendations_section(key_prefix="song_recs")


def main() -> None:
    init_state()
    ensure_storage_ready()

    # hidden button the browser player "clicks" when it moves to the next song by itself
    if st.button("player-sync", key="player_sync_btn"):
        apply_player_sync()

    render_sidebar()
    render_sidebar_collapse_if_requested()

    writer = get_gist_writer()
    if writer.last_error:
        st.warning(writer.last_error)
        writer.last_error = None

    page = st.session_state.page
    if page == "Home":
        render_home_page()
    elif page == "Search":
        render_search_page()
    elif page == "Song Page":
        render_song_page()


if __name__ == "__main__":
    main()
