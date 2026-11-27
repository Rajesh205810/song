import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
import yt_dlp

BASE_DIR = Path(__file__).resolve().parent
FAVORITES_FILE = BASE_DIR / "favorites.json"
HISTORY_FILE = BASE_DIR / "history.json"
MAX_HISTORY_ITEMS = 24
SEARCH_LIMIT = 12
FALLBACK_THUMBNAIL = "https://via.placeholder.com/600x600/181818/1DB954?text=No+Cover+Art"

st.set_page_config(
    page_title="Spotify Streamer",
    page_icon="🎧",
    layout="wide",
    initial_sidebar_state="expanded",
)

SPOTIFY_CSS = """
<style>
    .stApp {
        background: linear-gradient(180deg, #191414 0%, #121212 38%, #0b0b0b 100%);
        color: #ffffff;
    }
    section[data-testid="stSidebar"] {
        background-color: #000000;
        border-right: 1px solid #242424;
    }
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
    }
    .song-card {
        background-color: #181818;
        border: 1px solid #282828;
        border-radius: 12px;
        padding: 12px;
        margin-bottom: 14px;
        transition: background-color 0.2s ease;
    }
    .song-card:hover {
        background-color: #242424;
    }
    .song-title {
        font-weight: 700;
        font-size: 0.98rem;
        color: #ffffff;
        margin-top: 8px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .song-artist {
        font-size: 0.84rem;
        color: #b3b3b3;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        margin-bottom: 8px;
    }
    .now-playing-box {
        background: rgba(24, 24, 24, 0.92);
        border: 1px solid #282828;
        border-radius: 16px;
        padding: 24px;
        max-width: 560px;
        margin: 0 auto 20px auto;
        text-align: center;
    }
    .muted-caption {
        color: #b3b3b3;
        font-size: 0.88rem;
    }
    div.stButton > button {
        border-radius: 999px;
        font-weight: 600;
    }
</style>
"""
st.markdown(SPOTIFY_CSS, unsafe_allow_html=True)


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
    track_id = str(video_id or url or f"track_{fallback_index}")
    title = str(entry.get("title") or entry.get("name") or "Untitled Track")
    artist = str(
        entry.get("artist")
        or entry.get("uploader")
        or entry.get("channel")
        or "Unknown Artist"
    )
    raw_duration = entry.get("duration")
    try:
        duration = float(raw_duration) if raw_duration else 0.0
    except (TypeError, ValueError):
        duration = 0.0
    thumbnail = str(entry.get("thumbnail") or pick_thumbnail(entry))
    return {
        "id": track_id,
        "title": title,
        "artist": artist,
        "duration": duration,
        "thumbnail": thumbnail,
        "webpage_url": str(url or ""),
    }


def load_json_list(file_path: Path) -> List[Dict[str, Any]]:
    if not file_path.exists():
        return []
    try:
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        normalized: List[Dict[str, Any]] = []
        for idx, item in enumerate(data):
            clean = normalize_track(item, fallback_index=idx)
            if clean:
                normalized.append(clean)
        return normalized
    except (json.JSONDecodeError, OSError):
        return []


def save_json_list(file_path: Path, items: List[Dict[str, Any]]) -> None:
    try:
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        st.warning(f"Could not save {file_path.name}: {exc}")


@st.cache_data(ttl=900, show_spinner=False)
def search_tracks(query: str, limit: int = SEARCH_LIMIT) -> List[Dict[str, Any]]:
    clean_query = query.strip()
    if not clean_query:
        return []
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
    }
    search_target = f"ytsearch{limit}:{clean_query}"
    tracks: List[Dict[str, Any]] = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(search_target, download=False)
    entries = info.get("entries") if isinstance(info, dict) else []
    for idx, raw in enumerate(entries or []):
        track = normalize_track(raw, fallback_index=idx)
        if track and track.get("webpage_url"):
            tracks.append(track)
    return tracks[:limit]


@st.cache_data(ttl=600, show_spinner=False)
def resolve_stream_url(webpage_url: str) -> Optional[str]:
    if not webpage_url:
        return None
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(webpage_url, download=False)
    if not isinstance(info, dict):
        return None
    if info.get("url"):
        return str(info["url"])
    formats = info.get("formats") or []
    for fmt in reversed(formats):
        if isinstance(fmt, dict) and fmt.get("url") and fmt.get("acodec") != "none":
            return str(fmt["url"])
    return None


def init_state() -> None:
    if "page" not in st.session_state:
        st.session_state.page = "Home"
    if "favorites" not in st.session_state:
        st.session_state.favorites = load_json_list(FAVORITES_FILE)
    if "history" not in st.session_state:
        st.session_state.history = load_json_list(HISTORY_FILE)
    if "search_results" not in st.session_state:
        st.session_state.search_results = []
    if "last_query" not in st.session_state:
        st.session_state.last_query = ""
    if "current_track" not in st.session_state:
        st.session_state.current_track = (
            st.session_state.history[0] if st.session_state.history else None
        )
    if "is_playing" not in st.session_state:
        st.session_state.is_playing = False
    if "seek_position" not in st.session_state:
        st.session_state.seek_position = 0
    if "queue" not in st.session_state:
        st.session_state.queue = []


def is_favorite(track_id: str) -> bool:
    return any(item.get("id") == track_id for item in st.session_state.favorites)


def toggle_favorite(track: Dict[str, Any]) -> None:
    safe_track = normalize_track(track)
    if not safe_track:
        return
    track_id = safe_track["id"]
    if is_favorite(track_id):
        st.session_state.favorites = [
            item for item in st.session_state.favorites if item.get("id") != track_id
        ]
    else:
        st.session_state.favorites = [safe_track] + [
            item for item in st.session_state.favorites if item.get("id") != track_id
        ]
    save_json_list(FAVORITES_FILE, st.session_state.favorites)


def record_history(track: Dict[str, Any]) -> None:
    safe_track = normalize_track(track)
    if not safe_track:
        return
    track_id = safe_track["id"]
    filtered = [item for item in st.session_state.history if item.get("id") != track_id]
    updated = [safe_track] + filtered
    st.session_state.history = updated[:MAX_HISTORY_ITEMS]
    save_json_list(HISTORY_FILE, st.session_state.history)


def build_queue(track: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for pool in (
        st.session_state.search_results,
        st.session_state.history,
        st.session_state.favorites,
    ):
        for item in pool:
            clean = normalize_track(item)
            if clean and all(existing.get("id") != clean["id"] for existing in candidates):
                candidates.append(clean)
    clean_current = normalize_track(track)
    if clean_current and all(existing.get("id") != clean_current["id"] for existing in candidates):
        candidates.insert(0, clean_current)
    return candidates


def open_song_page(track: Dict[str, Any], autoplay: bool = True) -> None:
    clean = normalize_track(track)
    if not clean:
        return
    st.session_state.current_track = clean
    st.session_state.queue = build_queue(clean)
    st.session_state.seek_position = 0
    st.session_state.is_playing = autoplay
    st.session_state.page = "Song Page"
    record_history(clean)
    st.rerun()


def step_track(delta: int) -> None:
    current = normalize_track(st.session_state.current_track)
    queue = st.session_state.queue or (build_queue(current) if current else [])
    if not queue or not current:
        return
    ids = [item.get("id") for item in queue]
    try:
        idx = ids.index(current.get("id"))
    except ValueError:
        idx = 0
    next_idx = (idx + delta) % len(queue)
    open_song_page(queue[next_idx], autoplay=True)


def render_track_grid(tracks: List[Dict[str, Any]], key_prefix: str) -> None:
    cols = st.columns(3)
    for idx, raw_track in enumerate(tracks):
        track = normalize_track(raw_track, fallback_index=idx)
        if not track:
            continue
        col = cols[idx % 3]
        with col:
            st.markdown('<div class="song-card">', unsafe_allow_html=True)
            st.image(track.get("thumbnail", FALLBACK_THUMBNAIL), use_container_width=True)
            title = track.get("title", "Untitled Track")
            artist = track.get("artist", "Unknown Artist")
            duration_str = format_duration(track.get("duration"))
            track_id = track.get("id", str(idx))
            st.markdown(
                f'<div class="song-title" title="{title}">{title}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="song-artist" title="{artist}">{artist} · {duration_str}</div>',
                unsafe_allow_html=True,
            )
            c1, c2 = st.columns([2, 1])
            with c1:
                if st.button("Play", key=f"{key_prefix}_play_{idx}_{track_id}", use_container_width=True):
                    open_song_page(track, autoplay=True)
            with c2:
                fav_label = "♥" if is_favorite(track_id) else "♡"
                if st.button(fav_label, key=f"{key_prefix}_fav_{idx}_{track_id}", use_container_width=True):
                    toggle_favorite(track)
                    st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)


def render_sidebar() -> None:
    with st.sidebar:
        st.title("🎧 Spotify Streamer")
        nav_options = ["Home", "Search", "Song Page"]
        current_index = nav_options.index(st.session_state.page)
        selected = st.radio("Navigation", nav_options, index=current_index)
        if selected != st.session_state.page:
            st.session_state.page = selected
            st.rerun()

        st.divider()
        st.subheader("♥ Favourites")
        if not st.session_state.favorites:
            st.caption("No saved favorites yet.")
        else:
            for idx, raw_fav in enumerate(st.session_state.favorites[:12]):
                fav = normalize_track(raw_fav, fallback_index=idx)
                if not fav:
                    continue
                fav_title = fav.get("title", "Untitled Track")
                fav_artist = fav.get("artist", "Unknown Artist")
                fav_id = fav.get("id", str(idx))
                col_title, col_play = st.columns([4, 1])
                with col_title:
                    st.caption(f"**{fav_title}**\n{fav_artist}")
                with col_play:
                    if st.button("▶", key=f"side_fav_{idx}_{fav_id}"):
                        open_song_page(fav, autoplay=True)

        current = normalize_track(st.session_state.current_track)
        if current:
            st.divider()
            st.caption("Now Selected")
            st.markdown(f"**{current.get('title', 'Untitled Track')}**")
            st.caption(current.get("artist", "Unknown Artist"))


def render_home_page() -> None:
    st.header("Home — Recent History")
    if not st.session_state.history:
        st.info("Your listening history is empty. Go to **Search** to find and play a song.")
        if st.button("Go to Search"):
            st.session_state.page = "Search"
            st.rerun()
        return
    render_track_grid(st.session_state.history, key_prefix="home")


def render_search_page() -> None:
    st.header("Search")
    with st.form("search_form", clear_on_submit=False):
        col_input, col_btn = st.columns([5, 1])
        with col_input:
            query = st.text_input(
                "Search songs or artists",
                value=st.session_state.last_query,
                placeholder="Search for a song, artist, or album...",
                label_visibility="collapsed",
            )
        with col_btn:
            submitted = st.form_submit_button("Search", use_container_width=True)

    if submitted and query.strip():
        st.session_state.last_query = query.strip()
        with st.spinner("Searching tracks..."):
            try:
                st.session_state.search_results = search_tracks(query.strip(), limit=SEARCH_LIMIT)
            except Exception as exc:
                st.error(f"Search failed: {exc}")
                st.session_state.search_results = []

    if st.session_state.search_results:
        st.caption(f'Showing up to {SEARCH_LIMIT} results for "{st.session_state.last_query}"')
        render_track_grid(st.session_state.search_results, key_prefix="search")
    elif st.session_state.last_query:
        st.warning("No matching tracks found. Try another search term.")


def render_song_page() -> None:
    track = normalize_track(st.session_state.current_track)
    if not track:
        st.info("No track selected yet. Search for a song or pick one from History.")
        return

    title = track.get("title", "Untitled Track")
    artist = track.get("artist", "Unknown Artist")
    track_id = track.get("id", "current")
    thumbnail = track.get("thumbnail", FALLBACK_THUMBNAIL)
    webpage_url = track.get("webpage_url", "")

    st.header("Now Playing")
    st.markdown('<div class="now-playing-box">', unsafe_allow_html=True)
    _, img_col, _ = st.columns([1, 2, 1])
    with img_col:
        st.image(thumbnail, use_container_width=True)

    st.markdown(f"### {title}")
    st.markdown(f'<div class="muted-caption">{artist}</div>', unsafe_allow_html=True)

    total_seconds = int(track.get("duration") or 0)
    max_seek = max(total_seconds, 1)
    current_seek = min(int(st.session_state.seek_position), max_seek)

    seek_val = st.slider(
        "Seek position",
        min_value=0,
        max_value=max_seek,
        value=current_seek,
        label_visibility="collapsed",
        key=f"seek_slider_{track_id}",
    )
    st.session_state.seek_position = seek_val

    t_left, t_right = st.columns(2)
    with t_left:
        st.caption(format_duration(seek_val))
    with t_right:
        st.caption(format_duration(total_seconds))

    c_prev, c_play, c_next, c_fav = st.columns(4)
    with c_prev:
        if st.button("⏮ Prev", use_container_width=True):
            step_track(-1)
    with c_play:
        play_label = "⏸ Pause" if st.session_state.is_playing else "▶ Play"
        if st.button(play_label, use_container_width=True):
            st.session_state.is_playing = not st.session_state.is_playing
            st.rerun()
    with c_next:
        if st.button("⏭ Next", use_container_width=True):
            step_track(1)
    with c_fav:
        fav_text = "♥ Saved" if is_favorite(track_id) else "♡ Favorite"
        if st.button(fav_text, use_container_width=True):
            toggle_favorite(track)
            st.rerun()

    if st.session_state.is_playing:
        with st.spinner("Loading audio stream..."):
            try:
                stream_url = resolve_stream_url(webpage_url)
            except Exception as exc:
                stream_url = None
                st.error(f"Could not extract audio stream: {exc}")

        if stream_url:
            st.audio(stream_url, format="audio/mp4", start_time=int(seek_val))
        else:
            st.warning("Direct audio stream unavailable for this track.")
    else:
        st.caption("Playback paused. Click **▶ Play** to stream audio.")

    st.markdown("</div>", unsafe_allow_html=True)


def main() -> None:
    init_state()
    render_sidebar()

    if st.session_state.page == "Home":
        render_home_page()
    elif st.session_state.page == "Search":
        render_search_page()
    elif st.session_state.page == "Song Page":
        render_song_page()


if __name__ == "__main__":
    main()
