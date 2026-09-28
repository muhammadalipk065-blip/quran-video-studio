"""Quran Recitation Video Studio — web UI for recitation_video.py.

Run locally:
    streamlit run app.py

Deploy free: push this folder to GitHub, then deploy at share.streamlit.io.
"""
import os
import tempfile
from types import SimpleNamespace

import requests
import streamlit as st

import recitation_video as rv

st.set_page_config(
    page_title="Quran Recitation Video Studio",
    page_icon="🕌",
    layout="centered",
)

BASE = os.path.dirname(os.path.abspath(__file__))
BG_DIR = os.path.join(BASE, "assets", "backgrounds")

BACKGROUNDS = {
    "✨ Default geometric": os.path.join(BG_DIR, "bg-geometric.jpg"),
    "🕌 Mosque at dusk": os.path.join(BG_DIR, "bg-mosque-dusk.jpg"),
    "🌟 Golden particles": os.path.join(BG_DIR, "bg-golden-particles.jpg"),
    "🎞️ Animated particles (video)": os.path.join(BG_DIR, "bg-loop-particles.mp4"),
    "⬛ Plain navy": "none",
    "📤 Upload my own…": "upload",
}


@st.cache_data(show_spinner=False)
def chapter_list():
    try:
        r = requests.get(
            "https://api.quran.com/api/v4/chapters?language=en", timeout=15)
        r.raise_for_status()
        return r.json()["chapters"]
    except Exception:
        return [{"id": i, "name_simple": f"Surah {i}",
                 "name_arabic": "", "verses_count": "?"} for i in range(1, 115)]


st.title("🕌 Quran Recitation Video Studio")
st.caption("Recitation-synced Arabic + translation videos — no terminal needed.")

chapters = chapter_list()
ch_opts = {c["id"]: f"{c['id']} · {c['name_simple']} "
                    f"({c['verses_count']} verses)" for c in chapters}

col1, col2 = st.columns(2)
with col1:
    surah = st.selectbox("Surah", options=list(ch_opts.keys()),
                         format_func=lambda i: ch_opts[i], index=111)
with col2:
    verses_raw = st.text_input("Verses (optional)",
                               placeholder="blank = whole surah, e.g. 1-3")

col3, col4 = st.columns(2)
with col3:
    reciter = st.selectbox("Reciter", options=sorted(rv.RECITERS.keys()),
                           format_func=lambda k: rv.RECITERS[k], index=0)
with col4:
    tr_ids = sorted(rv.TRANSLATIONS.keys())
    translation = st.selectbox(
        "Translation", options=tr_ids,
        format_func=lambda i: f"{rv.TRANSLATIONS[i]} (id {i})",
        index=tr_ids.index(20) if 20 in tr_ids else 0)

fmt = st.radio("Format", ["📱 Vertical 9:16 — YouTube Short",
                          "🖥️ Horizontal 16:9"], horizontal=True)
vertical = fmt.startswith("📱")

bg_choice = st.selectbox("Background", options=list(BACKGROUNDS.keys()))
uploaded = None
if BACKGROUNDS[bg_choice] == "upload":
    uploaded = st.file_uploader("Background image or video",
                                type=["jpg", "jpeg", "png", "mp4", "mov"])

channel = st.text_input("Channel name", value="Quran Explained Simply")

st.divider()

if st.button("🎬 Generate video", type="primary", use_container_width=True):
    # -- validate verses --
    verses = None
    if verses_raw.strip():
        try:
            verses = rv.parse_verses(verses_raw.strip())
        except ValueError:
            st.error("Verses should look like `2` or `1-3`.")
            st.stop()

    # -- resolve background --
    workdir = tempfile.mkdtemp(prefix="qrv_")
    if uploaded is not None:
        suffix = os.path.splitext(uploaded.name)[1].lower() or ".jpg"
        bg_path = os.path.join(workdir, f"custom-bg{suffix}")
        with open(bg_path, "wb") as f:
            f.write(uploaded.getbuffer())
    else:
        bg_path = BACKGROUNDS[bg_choice]

    tag = "short" if vertical else "full"
    out_path = os.path.join(workdir, f"surah-{surah:03d}-{tag}.mp4")

    args = SimpleNamespace(
        surah=surah, verses=verses, reciter=reciter,
        translation=int(translation), vertical=vertical,
        channel=channel, background=bg_path, out=out_path,
    )

    with st.spinner("Rendering your video — this usually takes a few "
                    "minutes. ☕"):
        try:
            rv.build(args)
        except SystemExit as e:
            st.error(f"Couldn't build that video: {e}")
            st.stop()
        except Exception as e:  # noqa: BLE001
            st.error(f"Something went wrong: {e}")
            st.stop()

    st.success("Done! Preview below, or download the MP4.")
    st.video(out_path)
    with open(out_path, "rb") as f:
        st.download_button("⬇️ Download MP4", data=f,
                           file_name=os.path.basename(out_path),
                           mime="video/mp4",
                           use_container_width=True)

st.divider()
st.caption("Audio: EveryAyah recitations · Text: Quran.com API · "
           "Check translation/recitation licensing before monetizing.")

with st.expander("🔧 Diagnostics (typography check)"):
    import sys as _sys
    from importlib import metadata as _md
    _diag = {
        "python": _sys.version.split()[0],
        "HAS_HB": bool(getattr(rv, "HAS_HB", False)),
        "uharfbuzz": _md.version("uharfbuzz") if _md else "?",
        "freetype-py": _md.version("freetype-py") if _md else "?",
        "pillow": _md.version("pillow") if _md else "?",
    }
    _fp = getattr(rv, "FONT_AR_HB", "")
    _diag["font_path"] = _fp
    _diag["font_exists"] = os.path.exists(_fp)
    _diag["font_bytes"] = os.path.getsize(_fp) if os.path.exists(_fp) else 0
    _sample = rv.with_verse_ornament("قُلْ هُوَ اللَّهُ أَحَدٌ", 1)
    _diag["ornamented_tail_repr"] = ascii(_sample[-8:])
    st.json(_diag)
    if _diag["HAS_HB"]:
        try:
            _img = rv.hb_render_line(_sample, 90, (255, 255, 255))
            st.image(_img, caption="Direct HarfBuzz render of ornamented verse")
        except Exception as _e:  # noqa: BLE001
            st.error(f"hb_render_line failed: {_e}")
        # Exact video-path input: real API uthmani text, wrapped, size 100.
        try:
            _v = rv.api_get("/quran/verses/uthmani",
                            {"chapter_number": 112})["verses"][0]["text_uthmani"]
            _api_sample = rv.with_verse_ornament(_v, 1)
            _diag2 = {
                "api_tail_repr": ascii(_api_sample[-10:]),
                "api_len": len(_api_sample),
            }
            _wlines = rv.wrap_arabic_hb(_api_sample, 100, 940)
            _diag2["wrapped"] = [ascii(_l) for _l in _wlines]
            st.json(_diag2)
            _img2 = rv.hb_render_line(_wlines[0], 100, (255, 255, 255))
            st.image(_img2, caption="Video-path render: API text, wrapped, size 100")
        except Exception as _e2:  # noqa: BLE001
            st.error(f"API-path diagnostics failed: {_e2}")
    else:
        st.warning("HarfBuzz renderer inactive — fallback path in use.")
