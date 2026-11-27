import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
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
FALLBACK_THUMBNAIL = "https://via.placeholder.com/600x600/121212/1DB954?text=No+Cover+Art"

st.set_page_config(
    page_title="Spotify Streamer",
    page_icon="🎧",
    layout="wide",
    initial_sidebar_state="collapsed",
)

SPOTIFY_CSS = """
<style>
    @keyframes popIn {
        0% {
            opacity: 0;
            transform: translateY(8px) scale(0.985);
        }
        100% {
            opacity: 1;
            transform: translateY(0) scale(1);
        }
    }

    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: #000000 !important;
        color: #ffffff !important;
    }
    section[data-testid="stSidebar"] {
        background-color: #090909 !important;
        border-right: 1px solid #262626 !important;
        transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1), width 0.28s cubic-bezier(0.22, 1, 0.36, 1) !important;
    }
    section[data-testid="stSidebar"] * {
        color: #ffffff !important;
    }
    .block-container {
        padding-top: 3.8rem !important;
        padding-bottom: 3rem !important;
        animation: popIn 0.26s ease-out;
    }
    .top-bar-spacer {
        height: 12px;
    }
    h1, h2, h3, h4, p, label, span, div, .stMarkdown {
        color: #ffffff !important;
    }
    [data-testid="stCaptionContainer"], .stCaption {
        color: #d4d4d8 !important;
    }

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
    input[type="text"]::placeholder {
        color: #a1a1aa !important;
    }

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
        animation: popIn 0.28s ease-out;
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
</style>
"""
st.markdown(SPOTIFY_CSS, unsafe_allow_html=True)


def get_gist_config() -> tuple[Optional[str], Optional[str]]:
    token = st.secrets.get("GITHUB_TOKEN") if "GITHUB_TOKEN" in st.secrets else None
    gist_id = st.secrets.get("GIST_ID") if "GIST_ID" in st.secrets else None
    if token and gist_id:
        return str(token).strip(), str(gist_id).strip()
    return None, None


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


def fetch_gist_files() -> Optional[Dict[str, Any]]:
    token, gist_id = get_gist_config()
    if not token or not gist_id:
        return None
    url = f"https://api.github.com/gists/{gist_id}"
    req = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "SpotifyStreamerApp",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        files = payload.get("files")
        return files if isinstance(files, dict) else None
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def patch_gist_file(filename: str, content_str: str) -> bool:
    token, gist_id = get_gist_config()
    if not token or not gist_id:
        return False
    url = f"https://api.github.com/gists/{gist_id}"
    body = json.dumps({"files": {filename: {"content": content_str}}}).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "SpotifyStreamerApp",
        },
        method="PATCH",
    )
    try:
        with urlopen(req, timeout=12) as resp:
            return 200 <= resp.status < 300
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        st.warning(f"Could not sync {filename} to Gist: {exc}")
        return False


def load_json_list(file_path: Path, max_items: Optional[int] = None) -> List[Dict[str, Any]]:
    token, gist_id = get_gist_config()
    if token and gist_id:
        files = fetch_gist_files()
        if files and file_path.name in files:
            file_obj = files[file_path.name]
            raw_content = file_obj.get("content") if isinstance(file_obj, dict) else None
            if isinstance(raw_content, str) and raw_content.strip():
                try:
                    parsed = json.loads(raw_content)
                    return parse_track_list(parsed, max_items=max_items)
                except json.JSONDecodeError:
                    pass

    if not file_path.exists():
        return []
    try:
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return parse_track_list(data, max_items=max_items)
    except (json.JSONDecodeError, OSError):
        return []


def save_json_list(file_path: Path, items: List[Dict[str, Any]]) -> None:
    serialized = json.dumps(items, indent=2, ensure_ascii=False)
    try:
        with file_path.open("w", encoding="utf-8") as f:
            f.write(serialized)
    except OSError:
        pass

    token, gist_id = get_gist_config()
    if token and gist_id:
        patch_gist_file(file_path.name, serialized)


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
                if (!sidebar || !isExpanded) {
                    clearInterval(interval);
                    return;
                }
                const closeBtn =
                    parentDoc.querySelector('[data-testid="stSidebarCollapseButton"] button') ||
                    parentDoc.querySelector('section[data-testid="stSidebar"] button[kind="header"]') ||
                    parentDoc.querySelector('button[aria-label="Close sidebar"]');
                if (closeBtn) {
                    closeBtn.click();
                    clearInterval(interval);
                }
                if (attempts >= 12) {
                    clearInterval(interval);
                }
            }, 60);
        })();
        </script>
        """,
        height=0,
    )


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

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "playlistend": limit + 10,
    }

    if track_id and not track_id.startswith("http") and not track_id.startswith("track_"):
        mix_url = f"https://www.youtube.com/watch?v={track_id}&list=RD{track_id}"
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(mix_url, download=False)
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

    for q in queries:
        if len(similar) >= limit:
            break
        for item in search_tracks(q, limit=14):
            if item["id"] not in seen_ids and item.get("webpage_url"):
                seen_ids.add(item["id"])
                similar.append(item)
                if len(similar) >= limit:
                    break

    return similar[:limit]


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
    if "show_favorites" not in st.session_state:
        st.session_state.show_favorites = False
    if "collapse_sidebar_once" not in st.session_state:
        st.session_state.collapse_sidebar_once = False
    if "favorites" not in st.session_state:
        st.session_state.favorites = load_json_list(FAVORITES_FILE, max_items=MAX_FAVORITES)
    if "history" not in st.session_state:
        st.session_state.history = load_json_list(HISTORY_FILE, max_items=MAX_HISTORY_ITEMS)
    if "recommendations" not in st.session_state:
        st.session_state.recommendations = []
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
        updated = [
            item for item in st.session_state.favorites if item.get("id") != track_id
        ][:MAX_FAVORITES]
    else:
        remaining = [
            item for item in st.session_state.favorites if item.get("id") != track_id
        ]
        updated = ([safe_track] + remaining)[:MAX_FAVORITES]
    st.session_state.favorites = updated
    save_json_list(FAVORITES_FILE, updated)


def record_history(track: Dict[str, Any]) -> None:
    safe_track = normalize_track(track)
    if not safe_track:
        return
    track_id = safe_track["id"]
    filtered = [item for item in st.session_state.history if item.get("id") != track_id]
    updated = ([safe_track] + filtered)[:MAX_HISTORY_ITEMS]
    st.session_state.history = updated
    save_json_list(HISTORY_FILE, updated)


def build_queue(track: Dict[str, Any], source_pool: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    pools = []
    if source_pool:
        pools.append(source_pool)
    pools.extend([
        st.session_state.recommendations,
        st.session_state.search_results,
        st.session_state.history,
        st.session_state.favorites,
    ])
    for pool in pools:
        for item in pool:
            clean = normalize_track(item)
            if clean and all(existing.get("id") != clean["id"] for existing in candidates):
                candidates.append(clean)
    clean_current = normalize_track(track)
    if clean_current and all(existing.get("id") != clean_current["id"] for existing in candidates):
        candidates.insert(0, clean_current)
    return candidates


def open_song_page(
    track: Dict[str, Any],
    autoplay: bool = True,
    source_pool: Optional[List[Dict[str, Any]]] = None,
) -> None:
    clean = normalize_track(track)
    if not clean:
        return
    st.session_state.current_track = clean
    st.session_state.is_playing = autoplay
    st.session_state.show_favorites = False
    st.session_state.page = "Song Page"
    record_history(clean)
    st.session_state.recommendations = get_similar_tracks(
        track_id=clean.get("id", ""),
        title=clean.get("title", ""),
        artist=clean.get("artist", ""),
        last_query=st.session_state.last_query,
        limit=RECOMMENDATION_LIMIT,
    )
    st.session_state.queue = build_queue(clean, source_pool=source_pool)
    st.rerun()


def stop_playback() -> None:
    st.session_state.is_playing = False
    st.rerun()


def step_track(delta: int, autoplay: bool = True) -> None:
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
    open_song_page(queue[next_idx], autoplay=autoplay)


def handle_query_auto_next() -> None:
    if st.query_params.get("auto_next") == "1":
        st.query_params.clear()
        step_track(1, autoplay=True)


def render_auto_advance_listener(
    is_playing: bool,
    title: str = "",
    artist: str = "",
    thumbnail: str = "",
) -> None:
    if not is_playing:
        return
    safe_title = json.dumps(title)
    safe_artist = json.dumps(artist)
    safe_thumb = json.dumps(thumbnail)
    components.html(
        f"""
        <script>
        (function() {{
            const parentDoc = window.parent.document;
            const parentWin = window.parent;
            let triggered = false;

            function advanceNow() {{
                if (triggered) return;
                triggered = true;
                const nextBtn = Array.from(parentDoc.querySelectorAll('button')).find(
                    (btn) => btn.innerText && btn.innerText.includes('Next')
                );
                if (nextBtn) {{
                    nextBtn.click();
                }} else {{
                    const url = new URL(parentWin.location.href);
                    url.searchParams.set('auto_next', '1');
                    parentWin.location.href = url.toString();
                }}
            }}

            try {{
                if ('mediaSession' in navigator) {{
                    navigator.mediaSession.metadata = new MediaMetadata({{
                        title: {safe_title},
                        artist: {safe_artist},
                        artwork: [{{ src: {safe_thumb}, sizes: '512x512', type: 'image/jpeg' }}]
                    }});
                    navigator.mediaSession.setActionHandler('nexttrack', () => {{
                        advanceNow();
                    }});
                }}
            }} catch (e) {{}}

            function bindAudioElements() {{
                const audios = parentDoc.querySelectorAll('audio');
                for (const audio of audios) {{
                    if (!audio.dataset.bgAutoNextBound) {{
                        audio.dataset.bgAutoNextBound = '1';
                        audio.addEventListener('ended', advanceNow);
                        audio.addEventListener('timeupdate', () => {{
                            if (
                                !triggered &&
                                audio.duration &&
                                isFinite(audio.duration) &&
                                audio.duration > 5 &&
                                (audio.duration - audio.currentTime) <= 0.45
                            ) {{
                                advanceNow();
                            }}
                        }});
                    }}
                }}
            }}

            parentDoc.addEventListener('visibilitychange', () => {{
                if (!triggered) {{
                    bindAudioElements();
                    const audios = parentDoc.querySelectorAll('audio');
                    for (const audio of audios) {{
                        if (audio.ended) {{
                            advanceNow();
                            break;
                        }}
                    }}
                }}
            }});

            bindAudioElements();
            const timer = setInterval(bindAudioElements, 400);
            setTimeout(() => clearInterval(timer), 7200000);
        }})();
        </script>
        """,
        height=0,
    )


def render_track_grid(
    tracks: List[Dict[str, Any]],
    key_prefix: str,
    autoplay_on_open: bool = True,
) -> None:
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
                if st.button("Play", key=f"{key_prefix}_open_{idx}_{track_id}", use_container_width=True):
                    open_song_page(track, autoplay=autoplay_on_open, source_pool=tracks)
            with c2:
                fav_label = "♥" if is_favorite(track_id) else "♡"
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
        render_track_grid(
            st.session_state.favorites,
            key_prefix="fav_section",
            autoplay_on_open=True,
        )
    st.divider()


def render_recommendations_section(key_prefix: str) -> None:
    current = normalize_track(st.session_state.current_track)
    history_seed = normalize_track(st.session_state.history[0]) if st.session_state.history else None
    seed = current or history_seed

    recs = st.session_state.recommendations
    if not recs and seed:
        with st.spinner("Loading similar song recommendations..."):
            recs = get_similar_tracks(
                track_id=seed.get("id", ""),
                title=seed.get("title", ""),
                artist=seed.get("artist", ""),
                last_query=st.session_state.last_query,
                limit=RECOMMENDATION_LIMIT,
            )
        st.session_state.recommendations = recs

    if not recs:
        return

    st.subheader(f"Recommended Similar Songs ({len(recs)})")
    render_track_grid(recs, key_prefix=key_prefix, autoplay_on_open=True)


def render_sidebar() -> None:
    with st.sidebar:
        st.title("🎧 Spotify Streamer")
        if st.button("Home", key="side_home_btn", use_container_width=True):
            st.session_state.page = "Home"
            st.session_state.show_favorites = False
            trigger_sidebar_collapse_animation()
            st.rerun()
        if st.button("Search", key="side_search_btn", use_container_width=True):
            st.session_state.page = "Search"
            st.session_state.show_favorites = False
            trigger_sidebar_collapse_animation()
            st.rerun()
        if st.button("Now Playing", key="side_player_btn", use_container_width=True):
            st.session_state.page = "Song Page"
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
            st.markdown(f"**{current.get('title', 'Untitled Track')}**")
            st.caption(current.get("artist", "Unknown Artist"))


def render_home_page() -> None:
    render_top_bar()
    render_favorites_drawer_section()
    st.header("Home — Previously Played Songs")
    if not st.session_state.history:
        st.info("No previously played songs yet. Use the search bar above to find and play a song.")
        return
    render_track_grid(st.session_state.history, key_prefix="home_history", autoplay_on_open=True)
    st.divider()
    render_recommendations_section(key_prefix="home_recs")


def render_search_page() -> None:
    render_top_bar()
    render_favorites_drawer_section()
    st.header("Search Results")
    if st.session_state.search_results:
        st.caption(f'Showing up to {SEARCH_LIMIT} results for "{st.session_state.last_query}"')
        render_track_grid(st.session_state.search_results, key_prefix="search_results", autoplay_on_open=True)
    elif st.session_state.last_query:
        st.warning("No matching tracks found. Try another search term.")
    else:
        st.info("Type a song or artist in the search bar at the top and click Search.")


def render_song_page() -> None:
    render_top_bar()
    render_favorites_drawer_section()
    track = normalize_track(st.session_state.current_track)
    if not track:
        st.info("No track selected yet. Search for a song or pick one from Home.")
        return

    title = track.get("title", "Untitled Track")
    artist = track.get("artist", "Unknown Artist")
    track_id = track.get("id", "current")
    thumbnail = track.get("thumbnail", FALLBACK_THUMBNAIL)
    webpage_url = track.get("webpage_url", "")
    duration_str = format_duration(track.get("duration"))

    st.header("Now Playing")
    st.markdown('<div class="now-playing-box">', unsafe_allow_html=True)
    _, img_col, _ = st.columns([1, 2, 1])
    with img_col:
        st.image(thumbnail, use_container_width=True)

    st.markdown(f"### {title}")
    st.markdown(f'<div class="song-artist">{artist} · {duration_str}</div>', unsafe_allow_html=True)

    if st.session_state.is_playing:
        with st.spinner("Loading audio stream..."):
            try:
                stream_url = resolve_stream_url(webpage_url)
            except Exception as exc:
                stream_url = None
                st.error(f"Could not extract audio stream: {exc}")

        if stream_url:
            st.audio(stream_url, format="audio/mp4", autoplay=True)
            render_auto_advance_listener(
                is_playing=True,
                title=title,
                artist=artist,
                thumbnail=thumbnail,
            )
        else:
            st.warning("Direct audio stream unavailable for this track.")
    else:
        st.caption("Stopped. Click **Play** below to stream audio.")

    c_prev, c_next, c_stop, c_fav = st.columns(4)
    with c_prev:
        if st.button("⏮ Prev", key="now_playing_prev_btn", use_container_width=True):
            step_track(-1, autoplay=True)
    with c_next:
        if st.button("⏭ Next", key="now_playing_next_btn", use_container_width=True):
            step_track(1, autoplay=True)
    with c_stop:
        if st.button("⏹ Stop", key="now_playing_stop_btn", use_container_width=True):
            stop_playback()
    with c_fav:
        fav_text = "♥ Saved" if is_favorite(track_id) else "♡ Fav"
        if st.button(fav_text, key="now_playing_fav_btn", use_container_width=True):
            toggle_favorite(track)
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
    render_recommendations_section(key_prefix="song_recs")


def main() -> None:
    init_state()
    handle_query_auto_next()
    render_sidebar()
    render_sidebar_collapse_if_requested()

    if st.session_state.page == "Home":
        render_home_page()
    elif st.session_state.page == "Search":
        render_search_page()
    elif st.session_state.page == "Song Page":
        render_song_page()


if __name__ == "__main__":
    main()
