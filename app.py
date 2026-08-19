"""
app.py — Streamlit WebUI for YT Short Clipper.
Jalankan dari Google Colab dengan Ngrok tunneling, atau lokal.
Mirip arsitektur MoneyPrinterTurbo.
"""
import os, sys, json, time, re, subprocess, threading, queue as qmod, signal
from pathlib import Path

# --- Colab / Drive setup ---
IS_COLAB = "google.colab" in sys.modules

# Auto-mount Google Drive if running in Colab
if IS_COLAB:
    try:
        from google.colab import drive
        drive.mount('/content/drive')
        print("✅ Google Drive mounted!")
    except Exception as e:
        print(f"⚠️ Drive mount failed: {e} — using local output only")

# --- Tambahkan path repo agar clipper_core bisa di-import ---
REPO_DIR = Path(__file__).parent.absolute()
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

from clipper_core import (
    BASE_DIR, TEMP_DIR, OUTPUT_DIR, CONFIG_FILE,
    TEMPLATES, RENDER_PRESETS, DEFAULT_CONFIG, GEMINI_PROMPT, UA,
    load_config, save_config, check_dependencies, list_available_fonts,
    get_safe_id, safe_generate_content, process_single_video,
    download_youtube, time_str_to_seconds, setup_directories,
    IS_COLAB as _CORE_IS_COLAB, get_ffmpeg_path, get_ytdlp_path,
)

import streamlit as st

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="YT Short Clipper Pro",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# CUSTOM CSS
# ============================================================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    .block-container { max-width: 1200px; }
    div[data-testid="stSidebar"] { background-color: #161b22; }
    .log-box {
        background-color: #0d1117; color: #c9d1d9;
        font-family: 'Courier New', monospace; font-size: 12px;
        padding: 12px; border-radius: 6px; border: 1px solid #30363d;
        height: 400px; overflow-y: auto; white-space: pre-wrap;
    }
    .status-running { color: #f0883e; font-weight: bold; }
    .status-done { color: #3fb950; font-weight: bold; }
    .status-error { color: #f85149; font-weight: bold; }
    div[data-testid="stMetric"] { background-color: #161b22; padding: 10px; border-radius: 8px; border: 1px solid #30363d; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# SESSION STATE INIT
# ============================================================
if "log_buffer" not in st.session_state:
    st.session_state.log_buffer = []
if "processing" not in st.session_state:
    st.session_state.processing = False
if "results" not in st.session_state:
    st.session_state.results = []
if "analysis_data" not in st.session_state:
    st.session_state.analysis_data = None
if "ngrok_url" not in st.session_state:
    st.session_state.ngrok_url = None


# ============================================================
# LOG COLLECTOR
# ============================================================
class StreamlitLogCollector:
    """Thread-safe log collector that writes to session_state."""
    def __init__(self):
        self.q = qmod.Queue()

    def log(self, msg):
        self.q.put(msg)

    def flush_to_session(self):
        lines = []
        while not self.q.empty():
            try:
                lines.append(self.q.get_nowait())
            except qmod.Empty:
                break
        if lines:
            st.session_state.log_buffer.extend(lines)
        return lines


# ============================================================
# NGROK TUNNEL
# ============================================================
def setup_ngrok(authtoken, port=8501):
    """Setup Ngrok tunnel and return public URL."""
    if not authtoken:
        return None
    try:
        from pyngrok import ngrok, conf
        conf.get_default().auth_token = authtoken
        # Kill existing tunnels
        ngrok.kill()
        tunnel = ngrok.connect(port, "http")
        url = tunnel.public_url
        st.session_state.ngrok_url = url
        return url
    except Exception as e:
        st.error(f"❌ Ngrok error: {e}")
        return None


# ============================================================
# SIDEBAR: SETTINGS
# ============================================================
def render_sidebar():
    with st.sidebar:
        st.image("https://img.shields.io/badge/YT_Short_Clipper-v3.0-blue?style=for-the-badge", use_container_width=True)
        st.markdown("---")

        # --- Ngrok ---
        st.markdown("### 🔗 Ngrok Tunnel")
        ngrok_token = st.text_input(
            "Ngrok Authtoken",
            value=os.environ.get("NGROK_AUTH_TOKEN", ""),
            type="password",
            help="Dapatkan gratis di https://dashboard.ngrok.com/get-started/your-authtoken"
        )

        st.markdown("---")

        # --- AI Provider ---
        st.markdown("### 🤖 AI Provider")
        ai_provider = st.selectbox(
            "Provider",
            ["Gemini (Native)", "Groq", "OpenRouter"],
            index=0,
        )

        gemini_key = ""
        gemini_model = "gemini-2.0-flash"
        groq_key = ""
        groq_model = "llama-3.3-70b-versatile"
        openrouter_key = ""
        openrouter_model = "nvidia/nemotron-3-super-120b-a12b:free"

        if ai_provider == "Gemini (Native)":
            gemini_key = st.text_input("Gemini API Key", type="password", value=os.environ.get("GEMINI_API_KEY", ""))
            gemini_model = st.selectbox("Gemini Model", ["gemini-2.0-flash", "gemini-1.5-flash"], index=0)
        elif ai_provider == "Groq":
            groq_key = st.text_input("Groq API Key", type="password", value=os.environ.get("GROQ_API_KEY", ""))
            groq_model = st.selectbox("Groq Model", ["llama-3.3-70b-versatile"], index=0)
        else:
            openrouter_key = st.text_input("OpenRouter API Key", type="password", value=os.environ.get("OPENROUTER_API_KEY", ""))
            openrouter_model = st.text_input("OpenRouter Model", value="nvidia/nemotron-3-super-120b-a12b:free")

        st.markdown("---")

        # --- Video Settings ---
        st.markdown("### 🎬 Video Settings")
        template = st.selectbox("Template", list(TEMPLATES.keys()), index=0)
        render_quality = st.selectbox("Render Quality", list(RENDER_PRESETS.keys()), index=1)
        export_resolution = st.selectbox("Resolution", ["1080x1920", "720x1280"], index=0)
        font_name = st.selectbox("Font", list_available_fonts(), index=0)

        st.markdown("---")

        # --- Extras ---
        st.markdown("### ✨ Extras")
        watermark = st.text_input("Watermark", placeholder="@username")
        bgm_volume = st.slider("BGM Volume", 0.0, 1.0, 0.15, 0.05)
        pexels_key = st.text_input("Pexels API Key (B-Roll)", type="password", value="")
        end_card = st.checkbox("End Card (CTA)", value=True)
        end_card_text = st.text_input("End Card Text", value="Follow for more!")
        silence_threshold = st.slider("Silence Threshold", 0.0, 1.5, 0.6, 0.1)

        st.markdown("---")
        st.caption("⚠️ Voice Hook tidak tersedia di mode web (butuh Voicebox lokal)")

        return {
            "ngrok_token": ngrok_token,
            "ai_provider": ai_provider,
            "gemini_key": gemini_key,
            "gemini_model": gemini_model,
            "groq_key": groq_key,
            "groq_model": groq_model,
            "openrouter_key": openrouter_key,
            "openrouter_model": openrouter_model,
            "template": template,
            "render_quality": render_quality,
            "export_resolution": export_resolution,
            "font_name": font_name,
            "watermark": watermark,
            "bgm_volume": bgm_volume,
            "pexels_key": pexels_key,
            "end_card": end_card,
            "end_card_text": end_card_text,
            "silence_threshold": silence_threshold,
        }


# ============================================================
# CORE: ANALYSIS
# ============================================================
def run_analysis(link, settings, collector):
    """Analyze a YouTube link and return segments."""
    cfg = {
        "ai_provider": settings["ai_provider"],
        "gemini_api_key": settings["gemini_key"],
        "gemini_model": settings["gemini_model"],
        "groq_api_key": settings["groq_key"],
        "groq_model": settings["groq_model"],
        "openrouter_api_key": settings["openrouter_key"],
        "openrouter_model": settings["openrouter_model"],
    }

    # Check API key
    if settings["ai_provider"] == "Gemini (Native)" and not cfg["gemini_api_key"]:
        return None, "❌ Gemini API Key belum diisi."
    elif settings["ai_provider"] == "Groq" and not cfg["groq_api_key"]:
        return None, "❌ Groq API Key belum diisi."
    elif settings["ai_provider"] == "OpenRouter" and not cfg["openrouter_api_key"]:
        return None, "❌ OpenRouter API Key belum diisi."

    try:
        collector.log("[#] Fetching metadata...")
        vid_id = get_safe_id(link)
        sid = vid_id
        y_p = get_ytdlp_path()

        cmd_info = f'{y_p} --user-agent "{UA}" --extractor-args "youtube:player_client=tv,web_creator,mediaconnect" --skip-download --write-info-json -o "{TEMP_DIR}/{sid}_full" "{link}"'
        subprocess.run(cmd_info, shell=True, capture_output=True, timeout=30)

        info_f = TEMP_DIR / f"{sid}_full.info.json"
        title, desc = sid, ""
        if info_f.exists():
            with open(info_f, "r", encoding="utf-8") as f:
                m = json.load(f)
                title = m.get("title", sid)
                desc = m.get("description", "")[:500]
        collector.log(f"[#] Video: {title}")

        # Try subtitles
        cmd_subs = f'{y_p} --user-agent "{UA}" --extractor-args "youtube:player_client=tv,web_creator,mediaconnect" --skip-download --write-auto-subs --sub-langs "id,en" --convert-subs srt -o "{TEMP_DIR}/{sid}_full" "{link}"'
        try:
            subprocess.run(cmd_subs, shell=True, capture_output=True, timeout=60)
        except Exception:
            collector.log("[!] Subtitle tidak tersedia.")

        # Download video if needed
        orig = TEMP_DIR / f"{sid}_full.mp4"
        if not orig.exists():
            collector.log("[#] Downloading video...")
            try:
                download_youtube(link, orig, "", collector.log)
            except Exception as e:
                collector.log(f"⚠️ Download error: {str(e)[:200]}")

        # Parse subtitles
        srt = list(TEMP_DIR.glob(f"{sid}_full.*.srt"))
        txt = ""
        if srt:
            collector.log("[#] Parsing subtitle...")
            with open(srt[0], "r", encoding="utf-8", errors="replace") as f:
                for l in f:
                    if "-->" not in l and l.strip() and not l.strip().isdigit():
                        txt += l.strip() + " "

        ctx = f"TITLE: {title}\nDESC: {desc}\nTRANSCRIPT: {txt[:20000]}"
        collector.log("[#] Menganalisis dengan AI...")
        rt = safe_generate_content(cfg, f"{GEMINI_PROMPT.format(transcript=ctx)}\nLink: {link}", collector.log)

        jm = re.search(r'(\[.*\]|\{.*\})', rt, re.DOTALL)
        if jm:
            raw_json = re.sub(r'[\x00-\x1f]', '', jm.group(1))
            d = json.loads(raw_json)
        else:
            d = []
        if isinstance(d, dict):
            d = [d]

        if d:
            return d, f"✅ Ditemukan {len(d)} segmen viral!"
        else:
            return None, "⚠️ Tidak ada segmen viral ditemukan."

    except Exception as e:
        return None, f"❌ Error: {str(e)}"


# ============================================================
# CORE: PROCESSING
# ============================================================
def run_processing(link, segments, selected_indices, settings, collector):
    """Process selected segments in background thread."""
    cfg = {
        "ai_provider": settings["ai_provider"],
        "gemini_api_key": settings["gemini_key"],
        "gemini_model": settings["gemini_model"],
        "groq_api_key": settings["groq_key"],
        "groq_model": settings["groq_model"],
        "openrouter_api_key": settings["openrouter_key"],
        "openrouter_model": settings["openrouter_model"],
        "pexels_api_key": settings["pexels_key"],
        "template": settings["template"],
        "render_quality": settings["render_quality"],
        "export_resolution": settings["export_resolution"],
        "watermark": settings["watermark"],
        "bgm_volume": settings["bgm_volume"],
        "end_card": settings["end_card"],
        "end_card_text": settings["end_card_text"],
        "silence_threshold": settings["silence_threshold"],
        "subtitle_font": settings["font_name"],
    }

    total = len(selected_indices)
    results = []

    for idx_i, seg_idx in enumerate(selected_indices):
        if seg_idx < 0 or seg_idx >= len(segments):
            continue
        seg = segments[seg_idx]
        ss = time_str_to_seconds(seg.get("start", "00:00:00"))
        es = time_str_to_seconds(seg.get("end", "00:00:10"))

        collector.log(f"\n{'='*50}")
        collector.log(f"[{idx_i+1}/{total}] {seg.get('title', 'Untitled')}")
        collector.log(f"{'='*50}")

        opts = {
            "watermark": cfg.get("watermark", ""),
            "status_func": lambda t: collector.log(f"[status] {t}"),
            "selected_font": cfg.get("subtitle_font", "KOMIKAX_.ttf"),
            "ai_desc": seg.get("description", ""),
            "split_screen": seg.get("split_screen", False),
            "mood": seg.get("mood", "santai"),
            "bgm_volume": cfg.get("bgm_volume", 0.15),
            "zoom": 1.0,
            "y_offset": 0.35,
            "voice_hook": "",
            "judul_opini": seg.get("judul_opini", ""),
            "use_broll": bool(settings.get("pexels_key")),
            "hook_text": seg.get("hook", ""),
            "gen_thumb": True,
            "config": cfg,
            "render_quality": cfg.get("render_quality", "normal"),
            "template": cfg.get("template", "cinematic"),
            "export_resolution": cfg.get("export_resolution", "1080x1920"),
            "end_card": cfg.get("end_card", True),
            "end_card_text": cfg.get("end_card_text", "Follow for more!"),
            "silence_threshold": cfg.get("silence_threshold", 0.6),
        }

        def progress_cb(p):
            collector.log(f"[progress] {p}%")

        success, msg = process_single_video(
            link, ss, es, seg.get("title", "Untitled"),
            seg.get("lang", "id"), seg.get("model", "small"),
            collector.log, progress_cb, opts=opts
        )

        if success:
            results.append({"title": seg.get("title", "Untitled"), "path": msg})
            collector.log(f"✅ Selesai: {seg.get('title', 'Untitled')}")
        else:
            collector.log(f"❌ Gagal: {msg}")

    return results


# ============================================================
# MAIN APP
# ============================================================
def main():
    st.markdown("# 🎬 YT Short Clipper Pro")
    st.markdown("**AI-Powered YouTube Shorts Generator** — WebUI + Ngrok Tunneling")
    st.markdown("---")

    # ---- SIDEBAR ----
    settings = render_sidebar()

    # ---- DEPENDENCY CHECK ----
    with st.expander("🔧 System Status", expanded=False):
        deps = check_dependencies()
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("FFmpeg", "✅" if not any("ffmpeg" in e.lower() for e in deps) else "❌")
        with col2:
            st.metric("yt-dlp", "✅" if not any("yt-dlp" in e.lower() for e in deps) else "❌")
        with col3:
            st.metric("faster-whisper", "✅" if not any("faster-whisper" in e.lower() for e in deps) else "❌")

        # GPU info
        try:
            import torch
            if torch.cuda.is_available():
                st.success(f"🖥️ GPU: {torch.cuda.get_device_name(0)}")
            else:
                st.warning("🖥️ GPU: CPU only (GPU tidak tersedia)")
        except ImportError:
            st.info("🖥️ GPU check: torch tidak terinstall")

    # ---- NGROK SETUP ----
    if settings["ngrok_token"]:
        if st.session_state.ngrok_url is None:
            with st.spinner("Setting up Ngrok tunnel..."):
                url = setup_ngrok(settings["ngrok_token"], port=8501)
                if url:
                    st.success(f"🔗 **Public URL:** {url}")
        else:
            st.success(f"🔗 **Public URL:** {st.session_state.ngrok_url}")

    # ---- MAIN FORM ----
    st.markdown("### 📝 Input")

    with st.form("main_form"):
        col1, col2 = st.columns([3, 1])
        with col1:
            youtube_url = st.text_input(
                "🎬 YouTube URL",
                placeholder="https://www.youtube.com/watch?v=...",
            )
        with col2:
            st.markdown("<br>", unsafe_allow_html=True)
            analyze_btn = st.form_submit_button("🔍 Analisis", use_container_width=True, type="primary")

    # ---- ANALYSIS ----
    if analyze_btn and youtube_url:
        st.session_state.log_buffer = []
        collector = StreamlitLogCollector()

        with st.spinner("Analisis berlangsung..."):
            segments, status = run_analysis(youtube_url, settings, collector)
            collector.flush_to_session()

        if segments:
            st.session_state.analysis_data = {"link": youtube_url, "segments": segments}
            st.success(status)

            # Show segments table
            st.markdown("### 📊 Hasil Analisis")
            for i, seg in enumerate(segments):
                with st.expander(f"**#{i+1}** — {seg.get('title', 'Untitled')} | {seg.get('start', '?')} → {seg.get('end', '?')} | Mood: {seg.get('mood', '?')}", expanded=True):
                    st.markdown(f"**Hook:** {seg.get('hook', '-')}")
                    st.markdown(f"**Judul Opini:** {seg.get('judul_opini', '-')}")
                    st.markdown(f"**Split Screen:** {'✅' if seg.get('split_screen') else '❌'}")
                    if seg.get("description"):
                        st.markdown(f"**Deskripsi:** {seg['description'][:300]}...")
        else:
            st.warning(status)

    # ---- PROCESSING ----
    if st.session_state.analysis_data:
        data = st.session_state.analysis_data
        segments = data["segments"]
        link = data["link"]

        st.markdown("---")
        st.markdown("### 🎬 Pilih & Proses Segmen")

        # Checkbox for each segment
        selected = []
        for i, seg in enumerate(segments):
            col1, col2 = st.columns([0.1, 0.9])
            with col1:
                if st.checkbox(f"#{i+1}", key=f"sel_{i}", value=True):
                    selected.append(i)
            with col2:
                st.markdown(f"**{seg.get('title', 'Untitled')}** | `{seg.get('start', '?')} → {seg.get('end', '?')}` | {seg.get('mood', '?')}")

        # Process button
        if selected:
            if st.button("▶ PROSES TERPILIH", type="primary", use_container_width=True):
                st.session_state.processing = True
                st.session_state.log_buffer = []
                collector = StreamlitLogCollector()

                progress_bar = st.progress(0)
                log_placeholder = st.empty()

                def run_in_thread():
                    results = run_processing(link, segments, selected, settings, collector)
                    st.session_state.results = results
                    st.session_state.processing = False

                thread = threading.Thread(target=run_in_thread, daemon=True)
                thread.start()

                # Poll for updates
                while st.session_state.processing or not collector.q.empty():
                    new_lines = collector.flush_to_session()
                    if new_lines:
                        log_text = "\n".join(st.session_state.log_buffer[-100:])
                        log_placeholder.code(log_text, language=None)
                    time.sleep(0.5)

                # Final update
                collector.flush_to_session()
                log_text = "\n".join(st.session_state.log_buffer)
                log_placeholder.code(log_text, language=None)
                progress_bar.progress(1.0)

                if st.session_state.results:
                    st.success(f"✅ {len(st.session_state.results)} video berhasil diproses!")
        else:
            st.info("Centang segmen yang mau diproses.")

    # ---- RESULTS ----
    if st.session_state.results:
        st.markdown("---")
        st.markdown("### 📥 Hasil Output")

        today_folder = time.strftime("%d-%m-%Y")
        today_dir = OUTPUT_DIR / today_folder

        for result in st.session_state.results:
            path = Path(result["path"])
            if path.exists():
                st.markdown(f"**{result['title']}**")
                st.video(str(path))
                with open(path, "rb") as f:
                    st.download_button(
                        label=f"⬇️ Download {path.name}",
                        data=f.read(),
                        file_name=path.name,
                        mime="video/mp4",
                        key=f"dl_{path.name}",
                    )
            else:
                st.warning(f"File tidak ditemukan: {path}")

    # ---- LOG DISPLAY ----
    if st.session_state.log_buffer:
        with st.expander("📋 Full Log", expanded=False):
            st.code("\n".join(st.session_state.log_buffer), language=None)


# ============================================================
# ENTRY POINT
# ============================================================
if __name__ == "__main__":
    main()
