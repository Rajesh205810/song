import json
import uuid
from pathlib import Path
from urllib.parse import quote
import streamlit as st
import yt_dlp

st.set_page_config(page_title="Spotify-Style Personal Streamer", layout="wide")

FAVORITES_FILE = Path(__file__).with_name("favorites.json")
HISTORY_FILE = Path(__file__).with_name("history.json")


def load_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_json_list(path: Path, items: list[dict]) -> None:
    path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "playlist" not in st.session_state:
    st.session_state.playlist = []
if "favorites" not in st.session_state:
    st.session_state.favorites = load_json_list(FAVORITES_FILE)
if "history" not in st.session_state:
    st.session_state.history = load_json_list(HISTORY_FILE)
if "current_idx" not in st.session_state:
    st.session_state.current_idx = 0
if "fav_cursor" not in st.session_state:
    st.session_state.fav_cursor = -1
if "seek_sec" not in st.session_state:
    st.session_state.seek_sec = 0
if "is_playing" not in st.session_state:
    st.session_state.is_playing = True
if "active_view" not in st.session_state:
    st.session_state.active_view = "home"

st.markdown(
    """
    <style>
        .stApp {
            background-color: #121212;
            color: #FFFFFF;
        }
        [data-testid="stHeader"] {
            background-color: #121212;
        }
        .spotify-banner {
            background: linear-gradient(180deg, #1db95438 0%, #181818 100%);
            border: 1px solid #282828;
            border-radius: 12px;
            padding: 16px 22px;
            margin-bottom: 16px;
        }
        .spotify-pill {
            display: inline-block;
            background-color: #1DB954;
            color: #000000;
            font-weight: 700;
            font-size: 11px;
            letter-spacing: 0.08em;
            padding: 3px 9px;
            border-radius: 999px;
            margin-bottom: 6px;
        }
        .center-timer {
            text-align: center;
            color: #B3B3B3;
            font-size: 1rem;
            font-weight: 600;
            margin: 8px 0 6px 0;
        }
        .center-title {
            text-align: center;
            margin: 6px 0 2px 0;
        }
        .center-artist {
            text-align: center;
            color: #B3B3B3;
            font-size: 0.9rem;
            margin-bottom: 10px;
        }
        .muted-text {
            color: #B3B3B3;
            font-size: 0.85rem;
        }
        div[data-testid="stButton"] > button,
        div[data-testid="stFormSubmitButton"] > button {
            background-color: #282828 !important;
            color: #FFFFFF !important;
            border: 1px solid #3E3E3E !important;
            border-radius: 999px !important;
            font-weight: 600 !important;
        }
        div[data-testid="stButton"] > button:hover,
        div[data-testid="stFormSubmitButton"] > button:hover {
            background-color: #333333 !important;
            color: #FFFFFF !important;
            border-color: #535353 !important;
        }
        div[data-testid="stButton"] > button:disabled,
        div[data-testid="stFormSubmitButton"] > button:disabled {
            background-color: #1C1C1C !important;
            color: #6A6A6A !important;
            border-color: #262626 !important;
        }
        div[data-testid="stButton"] > button[kind="primary"],
        div[data-testid="stFormSubmitButton"] > button[kind="primary"] {
            background-color: #1DB954 !important;
            color: #000000 !important;
            border: none !important;
        }
        div[data-testid="stButton"] > button[kind="primary"]:hover,
        div[data-testid="stFormSubmitButton"] > button[kind="primary"]:hover {
            background-color: #1ED760 !important;
            color: #000000 !important;
        }
        div[data-testid="stImage"] img {
            border-radius: 12px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


def format_duration(seconds: int | None) -> str:
    if not seconds or seconds < 0:
        return "0:00"
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    if hours > 0:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def record_history(track: dict) -> None:
    history = st.session_state.history
    history = [h for h in history if str(h.get("id")) != str(track.get("id"))]
    entry = {
        "id": str(track.get("id")),
        "uuid": str(track.get("uuid") or uuid.uuid4()),
        "title": track.get("title", "Unknown Title"),
        "uploader": track.get("uploader", "Unknown Artist"),
        "duration": track.get("duration", 0),
        "thumbnail": track.get("thumbnail"),
        "webpage_url": track.get("webpage_url", ""),
    }
    history.insert(0, entry)
    st.session_state.history = history[:40]
    save_json_list(HISTORY_FILE, st.session_state.history)


def is_favorite(track: dict) -> bool:
    return any(str(f.get("id")) == str(track.get("id")) for f in st.session_state.favorites)


def toggle_favorite(track: dict) -> None:
    favs = st.session_state.favorites
    match_idx = next((i for i, f in enumerate(favs) if str(f.get("id")) == str(track.get("id"))), None)
    if match_idx is not None:
        favs.pop(match_idx)
        st.toast(f"Removed from Favourites: {track['title']}")
    else:
        saved_entry = {
            "id": str(track.get("id")),
            "uuid": str(track.get("uuid") or uuid.uuid4()),
            "title": track.get("title", "Unknown Title"),
            "uploader": track.get("uploader", "Unknown Artist"),
            "duration": track.get("duration", 0),
            "thumbnail": track.get("thumbnail"),
            "webpage_url": track.get("webpage_url", ""),
        }
        favs.append(saved_entry)
        st.toast(f"Saved to Favourites: {track['title']}")
    save_json_list(FAVORITES_FILE, favs)


def clear_all_favorites() -> None:
    st.session_state.favorites = []
    st.session_state.fav_cursor = -1
    if FAVORITES_FILE.exists():
        FAVORITES_FILE.unlink()
    st.toast("Cleared all saved favourites.")


def clear_history() -> None:
    st.session_state.history = []
    if HISTORY_FILE.exists():
        HISTORY_FILE.unlink()
    st.toast("Cleared played history.")


@st.cache_data(ttl=3600, show_spinner="Searching YouTube...")
def search_tracks(query: str, limit: int = 12) -> list[dict]:
    target = query.strip()
    if not target:
        return []

    search_target = target if target.startswith(("http://", "https://")) else f"ytsearch{limit}:{target}"

    ydl_opts = {
        "format": "ba[ext=m4a]/ba/bestaudio",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }

    tracks: list[dict] = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(search_target, download=False)
        entries = info.get("entries") if isinstance(info, dict) and "entries" in info else [info]

        for entry in entries or []:
            if not entry or not entry.get("url"):
                continue
            vid = str(entry.get("id") or entry.get("url"))
            tracks.append(
                {
                    "id": vid,
                    "uuid": str(uuid.uuid4()),
                    "title": entry.get("title", "Unknown Title"),
                    "uploader": entry.get("uploader") or entry.get("channel") or "Unknown Artist",
                    "duration": entry.get("duration") or 0,
                    "url": entry.get("url"),
                    "thumbnail": entry.get("thumbnail"),
                    "webpage_url": entry.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}",
                }
            )
    return tracks


@st.cache_data(ttl=3600, show_spinner="Fetching stream...")
def fetch_by_id(song_id: str) -> dict | None:
    clean_id = str(song_id).strip()
    if not clean_id:
        return None
    target = clean_id if clean_id.startswith(("http://", "https://")) else f"https://www.youtube.com/watch?v={clean_id}"
    results = search_tracks(target, limit=1)
    return results[0] if results else None


def ensure_playable_url(track: dict) -> dict:
    if track.get("url"):
        return track
    fresh = fetch_by_id(str(track.get("id", "")))
    if fresh and fresh.get("url"):
        merged = dict(track)
        merged["url"] = fresh["url"]
        merged["duration"] = track.get("duration") or fresh.get("duration") or 0
        merged["thumbnail"] = track.get("thumbnail") or fresh.get("thumbnail")
        merged["webpage_url"] = track.get("webpage_url") or fresh.get("webpage_url")
        return merged
    return track


def add_to_playlist(track: dict) -> int:
    playlist = st.session_state.playlist
    match_idx = next((i for i, item in enumerate(playlist) if str(item["id"]) == str(track["id"])), None)
    if match_idx is not None:
        return match_idx
    item_copy = dict(track)
    if not item_copy.get("uuid"):
        item_copy["uuid"] = str(uuid.uuid4())
    playlist.append(item_copy)
    return len(playlist) - 1


def open_and_play_song(track: dict, start_sec: int = 0, add_hist: bool = True) -> None:
    idx = add_to_playlist(track)
    active_track = ensure_playable_url(st.session_state.playlist[idx])
    st.session_state.playlist[idx] = active_track
    st.session_state.current_idx = idx
    st.session_state.seek_sec = start_sec
    st.session_state.is_playing = True
    if add_hist:
        record_history(active_track)
    st.query_params["song"] = str(active_track["id"])
    st.query_params["title"] = quote(active_track["title"])


def play_previous_repeat(current_track: dict) -> None:
    hist = st.session_state.history
    prev_candidate = None
    for item in hist:
        if str(item.get("id")) != str(current_track.get("id")):
            prev_candidate = item
            break
    target_track = prev_candidate or current_track
    open_and_play_song(target_track, start_sec=0, add_hist=True)


def play_next_from_favorites(current_track: dict) -> None:
    favs = st.session_state.favorites
    if not favs:
        st.toast("No songs in Favourites yet.")
        return

    cur_id = str(current_track.get("id"))
    matched_idx = next((i for i, f in enumerate(favs) if str(f.get("id")) == cur_id), -1)
    if matched_idx >= 0:
        next_idx = (matched_idx + 1) % len(favs)
    else:
        next_idx = (st.session_state.fav_cursor + 1) % len(favs)

    st.session_state.fav_cursor = next_idx
    open_and_play_song(favs[next_idx], start_sec=0, add_hist=True)


def render_favourites_and_search_below() -> None:
    st.markdown("---")
    tab_favs, tab_search = st.tabs(["My Favourites", "Search Songs & Versions"])

    with tab_favs:
        f_top_l, f_top_r = st.columns([5, 1.5])
        with f_top_l:
            st.markdown(f"### Favourites ({len(st.session_state.favorites)})")
        with f_top_r:
            if st.session_state.favorites and st.button("Clean All", key="below_clean_favs", width="stretch"):
                clear_all_favorites()
                st.rerun()

        if st.session_state.favorites:
            for f_idx, f_track in enumerate(st.session_state.favorites):
                c1, c2, c3, c4 = st.columns([0.9, 3.6, 1.1, 0.9])
                with c1:
                    if f_track.get("thumbnail"):
                        st.image(f_track["thumbnail"], width="stretch")
                with c2:
                    st.markdown(f"**♥ {f_track['title']}**")
                    st.caption(f"{f_track.get('uploader', 'Unknown')} • {format_duration(f_track.get('duration'))}")
                with c3:
                    if st.button("Play", key=f"below_fav_play_{f_idx}", type="primary", width="stretch"):
                        st.session_state.fav_cursor = f_idx
                        open_and_play_song(f_track)
                        st.rerun()
                with c4:
                    if st.button("✕", key=f"below_fav_rm_{f_idx}", help="Remove favourite", width="stretch"):
                        toggle_favorite(f_track)
                        st.rerun()
                st.divider()
        else:
            st.info("No favourite songs saved yet. Click the favourite button under a song to keep it here.")

    with tab_search:
        with st.form("below_search_form", clear_on_submit=False):
            q_col, b_col = st.columns([4.2, 1.3])
            with q_col:
                q_val = st.text_input(
                    "Search songs, remixes, covers, live versions, or YouTube URL",
                    placeholder="Search a song or version...",
                    label_visibility="collapsed",
                )
            with b_col:
                go_search = st.form_submit_button("Search", type="primary", width="stretch")

        if go_search and q_val.strip():
            st.session_state.search_results = search_tracks(q_val.strip(), limit=12)

        results = st.session_state.search_results
        if results:
            st.markdown(f"**Search Results ({len(results)})**")
            for r_idx, r_item in enumerate(results):
                r1, r2, r3, r4 = st.columns([0.9, 3.4, 1.1, 1.1])
                with r1:
                    if r_item.get("thumbnail"):
                        st.image(r_item["thumbnail"], width="stretch")
                with r2:
                    st.markdown(f"**{r_idx + 1}. {r_item['title']}**")
                    st.caption(f"{r_item['uploader']} • {format_duration(r_item.get('duration'))}")
                with r3:
                    if st.button("Play", key=f"below_res_play_{r_idx}", type="primary", width="stretch"):
                        open_and_play_song(r_item)
                        st.rerun()
                with r4:
                    fav_state = is_favorite(r_item)
                    if st.button("♥ Fav" if fav_state else "♡ Fav", key=f"below_res_fav_{r_idx}", width="stretch"):
                        toggle_favorite(r_item)
                        st.rerun()
                st.divider()
        elif go_search:
            st.warning("No matching songs found.")


# --- TOP NAVIGATION BAR (HOME + SEARCH) ---
nav_home, nav_search, nav_spacer = st.columns([1.2, 1.2, 6.6])
with nav_home:
    if st.button(
        "Home",
        key="top_nav_home",
        type="primary" if st.session_state.active_view == "home" and not st.query_params.get("song") else "secondary",
        width="stretch",
    ):
        st.session_state.active_view = "home"
        st.query_params.clear()
        st.rerun()
with nav_search:
    if st.button(
        "Search",
        key="top_nav_search",
        type="primary" if st.session_state.active_view == "search" and not st.query_params.get("song") else "secondary",
        width="stretch",
    ):
        st.session_state.active_view = "search"
        st.query_params.clear()
        st.rerun()

selected_song_id = st.query_params.get("song", "")

# --- CENTERED SONG PLAYER VIEW ---
if selected_song_id:
    track = next((t for t in st.session_state.playlist if str(t["id"]) == str(selected_song_id)), None)
    if not track:
        track = next((t for t in st.session_state.search_results if str(t["id"]) == str(selected_song_id)), None)
    if not track:
        track = next((t for t in st.session_state.favorites if str(t["id"]) == str(selected_song_id)), None)
    if not track:
        track = next((t for t in st.session_state.history if str(t["id"]) == str(selected_song_id)), None)
    if not track:
        track = fetch_by_id(str(selected_song_id))

    if track:
        track = ensure_playable_url(track)
        idx = add_to_playlist(track)
        st.session_state.playlist[idx] = track
        st.session_state.current_idx = idx
        record_history(track)
        st.query_params["title"] = quote(track["title"])

        _, center_col, _ = st.columns([1, 2.2, 1])
        with center_col:
            st.markdown(f"<h2 class='center-title'>{track['title']}</h2>", unsafe_allow_html=True)
            st.markdown(f"<div class='center-artist'>{track['uploader']}</div>", unsafe_allow_html=True)

            if track.get("thumbnail"):
                st.image(track["thumbnail"], width="stretch")

            duration_sec = int(track.get("duration") or 0)
            current_pos = min(st.session_state.seek_sec, duration_sec) if duration_sec > 0 else 0

            st.markdown(
                f"<div class='center-timer'>{format_duration(current_pos)} / {format_duration(duration_sec)}</div>",
                unsafe_allow_html=True,
            )

            c_prev, c_pp, c_next = st.columns([1.2, 1.8, 1.2])
            with c_prev:
                if st.button("⏮ Back", key="mid_prev_btn", width="stretch"):
                    play_previous_repeat(track)
                    st.rerun()
            with c_pp:
                pp_label = "⏸ Pause" if st.session_state.is_playing else "▶ Play"
                if st.button(pp_label, key="mid_pp_btn", type="primary", width="stretch"):
                    st.session_state.is_playing = not st.session_state.is_playing
                    st.rerun()
            with c_next:
                if st.button("Next ⏭", key="mid_next_btn", width="stretch"):
                    play_next_from_favorites(track)
                    st.rerun()

            if duration_sec > 1:
                slide_pos = st.slider(
                    "Skip song position",
                    min_value=0,
                    max_value=duration_sec,
                    value=current_pos,
                    step=1,
                    label_visibility="collapsed",
                    key="song_skip_slider",
                )
                if slide_pos != st.session_state.seek_sec:
                    st.session_state.seek_sec = slide_pos
                    st.rerun()
            else:
                slide_pos = 0

            if track.get("url"):
                st.audio(track["url"], start_time=slide_pos, autoplay=st.session_state.is_playing)
            else:
                st.error("Could not load audio stream.")

            fav_active = is_favorite(track)
            fav_label = "♥ Favourited" if fav_active else "♡ Favourite"
            if st.button(fav_label, key="mid_fav_btn", type="primary" if fav_active else "secondary", width="stretch"):
                toggle_favorite(track)
                st.rerun()

        render_favourites_and_search_below()
    else:
        st.error("Could not load that song.")

# --- HOME VIEW: PREVIOUSLY PLAYED COVER PHOTOS ONLY + BELOW LISTS ---
elif st.session_state.active_view == "home":
    st.markdown(
        """
        <div class="spotify-banner">
            <span class="spotify-pill">HOME</span>
            <h1 style="margin: 4px 0 4px 0;">Recently Played</h1>
            <div class="muted-text">Click Play under any cover photo to start listening.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    h_left, h_right = st.columns([6, 1.5])
    with h_right:
        if st.session_state.history and st.button("Clear History", key="clear_hist_btn", width="stretch"):
            clear_history()
            st.rerun()

    history_items = st.session_state.history
    if history_items:
        cols_per_row = 4
        for row_start in range(0, len(history_items), cols_per_row):
            row_items = history_items[row_start : row_start + cols_per_row]
            grid_cols = st.columns(cols_per_row, gap="medium")
            for col_idx, item in enumerate(row_items):
                with grid_cols[col_idx]:
                    if item.get("thumbnail"):
                        st.image(item["thumbnail"], width="stretch")
                    if st.button("Play", key=f"hist_play_{row_start + col_idx}", type="primary", width="stretch"):
                        open_and_play_song(item)
                        st.rerun()
    else:
        st.info("No songs played yet. Use Search below or at the top to find a song.")

    render_favourites_and_search_below()

# --- SEARCH VIEW ---
else:
    st.markdown(
        """
        <div class="spotify-banner">
            <span class="spotify-pill">SEARCH</span>
            <h1 style="margin: 4px 0 4px 0;">Find Songs & Versions</h1>
            <div class="muted-text">Pick from 12 versions, save favourites, or jump to any track.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("spotify_search_form", clear_on_submit=False):
        q_input, q_btn = st.columns([4.5, 1.3])
        with q_input:
            query = st.text_input(
                "Search songs, remixes, live versions, covers, or YouTube URL",
                placeholder="Search a song or version...",
                label_visibility="collapsed",
            )
        with q_btn:
            submitted = st.form_submit_button("Search", type="primary", width="stretch")

    if submitted and query.strip():
        st.session_state.search_results = search_tracks(query.strip(), limit=12)

    results = st.session_state.search_results
    if results:
        st.markdown(f"**Top {len(results)} Results**")
        for idx, item in enumerate(results):
            c_img, c_meta, c_act1, c_act2 = st.columns([0.9, 3.5, 1.1, 1.1])
            with c_img:
                if item.get("thumbnail"):
                    st.image(item["thumbnail"], width="stretch")
            with c_meta:
                st.markdown(f"**{idx + 1}. {item['title']}**")
                st.caption(f"{item['uploader']} • {format_duration(item.get('duration'))}")
            with c_act1:
                if st.button("Play", key=f"sp_open_{idx}", type="primary", width="stretch"):
                    open_and_play_song(item)
                    st.rerun()
            with c_act2:
                fav_now = is_favorite(item)
                if st.button("♥ Fav" if fav_now else "♡ Fav", key=f"sp_fav_{idx}", width="stretch"):
                    toggle_favorite(item)
                    st.rerun()
            st.divider()
    elif submitted:
        st.warning("No matching songs found.")

    render_favourites_and_search_below()