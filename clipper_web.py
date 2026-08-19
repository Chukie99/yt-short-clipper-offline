"""
clipper_web.py — Gradio Web UI for YT Short Clipper.
Designed for Google Colab. Voice Hook disabled (desktop-only feature).
"""
import os, sys, json, time, re, threading, queue as qmod
from pathlib import Path

# --- Setup paths for Colab ---
if "google.colab" in sys.modules:
    _drive_output = Path("/content/drive/MyDrive/YTShortClipper/output")
    _drive_config = Path("/content/drive/MyDrive/YTShortClipper/config.json")
    _temp_dir = Path("/content/temp")
    _drive_output.mkdir(parents=True, exist_ok=True)
    _temp_dir.mkdir(parents=True, exist_ok=True)
    from clipper_core import setup_directories
    setup_directories(
        temp_dir=str(_temp_dir),
        output_dir=str(_drive_output),
        config_file=str(_drive_config),
    )

from clipper_core import (
    BASE_DIR, TEMP_DIR, OUTPUT_DIR, CONFIG_FILE,
    TEMPLATES, RENDER_PRESETS, DEFAULT_CONFIG, GEMINI_PROMPT, UA,
    load_config, save_config, check_dependencies, list_available_fonts,
    get_safe_id, safe_generate_content, process_single_video,
    time_str_to_seconds, IS_COLAB,
)

import gradio as gr

# ---------- Globals ----------
config = load_config()
analysis_results = {}  # {link: [segments]}
processing_active = False

# ---------- Log & Progress Queue Pattern ----------
class OutputCollector:
    """Thread-safe log collector for Gradio streaming."""
    def __init__(self):
        self.q = qmod.Queue()
    def log(self, msg):
        self.q.put(msg)
    def get_logs(self):
        lines = []
        while not self.q.empty():
            try:
                lines.append(self.q.get_nowait())
            except qmod.Empty:
                break
        return "\n".join(lines)

# ---------- AI Analysis ----------
def run_analysis(link, ai_provider, gemini_key, groq_key, openrouter_key,
                 gemini_model, groq_model, openrouter_model, cookies_file):
    """Analyze a YouTube link and return segments."""
    if not link or not link.strip():
        return None, "❌ Link YouTube tidak boleh kosong.", ""

    link = link.strip()
    collector = OutputCollector()

    # Update config with provided keys
    cfg = config.copy()
    cfg["ai_provider"] = ai_provider
    if gemini_key:
        cfg["gemini_api_key"] = gemini_key
    if groq_key:
        cfg["groq_api_key"] = groq_key
    if openrouter_key:
        cfg["openrouter_api_key"] = openrouter_key
    cfg["gemini_model"] = gemini_model
    cfg["groq_model"] = groq_model
    cfg["openrouter_model"] = openrouter_model

    # Check API key
    if ai_provider == "Gemini (Native)" and not cfg.get("gemini_api_key"):
        return None, "❌ Gemini API Key belum diisi.", ""
    elif ai_provider == "Groq" and not cfg.get("groq_api_key"):
        return None, "❌ Groq API Key belum diisi.", ""
    elif ai_provider == "OpenRouter" and not cfg.get("openrouter_api_key"):
        return None, "❌ OpenRouter API Key belum diisi.", ""

    try:
        collector.log("[#] Fetching metadata...")
        vid_id = get_safe_id(link)
        sid = vid_id

        # Get yt-dlp path
        from clipper_core import get_ytdlp_path
        y_p = get_ytdlp_path()

        cookies_opts = ""
        if cookies_file:
            cookies_opts = f'--cookies "{cookies_file}"'

        cmd_info = f'{y_p} {cookies_opts} --user-agent "{UA}" --extractor-args "youtube:player_client=tv,mweb" --skip-download --write-info-json -o "{TEMP_DIR}/{sid}_full" "{link}"'
        import subprocess
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
        cmd_subs = f'{y_p} {cookies_opts} --user-agent "{UA}" --extractor-args "youtube:player_client=tv,mweb" --skip-download --write-auto-subs --sub-langs "id,en" --convert-subs srt -o "{TEMP_DIR}/{sid}_full" "{link}"'
        try:
            subprocess.run(cmd_subs, shell=True, capture_output=True, timeout=60)
        except Exception:
            collector.log("[!] Subtitle tidak tersedia, lanjut tanpa transkrip.")

        # Check if full video exists, download if not
        orig = TEMP_DIR / f"{sid}_full.mp4"
        if not orig.exists():
            collector.log("[#] Downloading video untuk transkrip...")
            from clipper_core import download_youtube
            try:
                download_youtube(link, orig, cfg.get("cookies_path"), collector.log)
            except Exception as e:
                collector.log(f"⚠️ Download gagal: {str(e)[:200]}")
                collector.log("[#] Mencoba analisis tanpa transkrip lengkap...")

        # Parse subtitle
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
            analysis_results[link] = d
            # Build table data
            table_data = []
            for i, seg in enumerate(d):
                table_data.append([
                    i + 1,
                    seg.get("start", "?"),
                    seg.get("end", "?"),
                    seg.get("title", "Untitled"),
                    seg.get("mood", "santai"),
                    "Yes" if seg.get("split_screen") else "No",
                ])
            logs = collector.get_logs()
            return table_data, f"✅ Ditemukan {len(d)} segmen viral!", logs
        else:
            return None, "⚠️ Tidak ada segmen viral ditemukan.", collector.get_logs()

    except Exception as e:
        return None, f"❌ Error: {str(e)}", collector.get_logs()


def process_segments(selected_indices, link,
                     template, render_quality, export_resolution,
                     watermark, bgm_volume, pexels_key,
                     end_card, end_card_text, silence_threshold,
                     logo_file, font_name,
                     progress=gr.Progress()):
    """Process selected segments."""
    global processing_active
    if processing_active:
        yield "⚠️ Sedang memproses, tunggu selesai.", ""
        return

    if not link or link not in analysis_results:
        yield "❌ Belum ada hasil analisis. Klik 'Analisis' dulu.", ""
        return

    if not selected_indices:
        yield "❌ Pilih segmen yang mau diproses.", ""
        return

    processing_active = True
    collector = OutputCollector()

    cfg = config.copy()
    cfg["template"] = template
    cfg["render_quality"] = render_quality
    cfg["export_resolution"] = export_resolution
    cfg["watermark"] = watermark
    cfg["bgm_volume"] = bgm_volume
    cfg["pexels_api_key"] = pexels_key
    cfg["end_card"] = end_card
    cfg["end_card_text"] = end_card_text
    cfg["silence_threshold"] = silence_threshold
    cfg["subtitle_font"] = font_name
    if logo_file:
        cfg["logo_path"] = logo_file

    segments = analysis_results[link]
    total = len(selected_indices)
    results = []

    try:
        for idx_i, idx in enumerate(selected_indices):
            seg_idx = idx - 1  # 1-indexed to 0-indexed
            if seg_idx < 0 or seg_idx >= len(segments):
                continue
            seg = segments[seg_idx]
            ss = time_str_to_seconds(seg.get("start", "00:00:00"))
            es = time_str_to_seconds(seg.get("end", "00:00:10"))

            collector.log(f"\n{'='*50}")
            collector.log(f"[{idx_i+1}/{total}] Memproses: {seg.get('title', 'Untitled')}")
            collector.log(f"{'='*50}")

            opts = {
                "cookies_path": cfg.get("cookies_path"),
                "watermark": cfg.get("watermark"),
                "status_func": lambda t: collector.log(f"[status] {t}"),
                "selected_font": cfg.get("subtitle_font", "KOMIKAX_.ttf"),
                "logo_path": cfg.get("logo_path", ""),
                "ai_desc": seg.get("description", ""),
                "split_screen": seg.get("split_screen", False),
                "mood": seg.get("mood", "santai"),
                "bgm_volume": cfg.get("bgm_volume", 0.15),
                "zoom": 1.0,
                "y_offset": 0.35,
                "voice_hook": "",  # DISABLED in web mode
                "judul_opini": seg.get("judul_opini", ""),
                "use_broll": bool(pexels_key),
                "hook_dur": 1.5,
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

            def progress_callback(p):
                overall = ((idx_i * 100) + p) / (total * 100)
                progress(overall, desc=f"Segment {idx_i+1}/{total}")

            success, msg = process_single_video(
                link, ss, es, seg.get("title", "Untitled"),
                seg.get("lang", "id"), seg.get("model", "small"),
                collector.log, progress_callback, opts=opts
            )

            if success:
                results.append(msg)
                collector.log(f"✅ Selesai: {seg.get('title', 'Untitled')}")
            else:
                collector.log(f"❌ Gagal: {msg}")

        # Find output files
        today_folder = time.strftime("%d-%m-%Y")
        today_dir = OUTPUT_DIR / today_folder
        output_files = []
        if today_dir.exists():
            for f in sorted(today_dir.glob("*.mp4"), key=lambda x: x.stat().st_mtime, reverse=True):
                if any(r and f.name in r for r in results):
                    output_files.append(str(f))

        progress(1.0, desc="Selesai!")
        log_text = collector.get_logs()
        status = f"✅ {len(results)}/{total} segmen berhasil diproses!"

        if output_files:
            yield status, log_text, gr.update(value=output_files, visible=True)
        else:
            yield status, log_text, gr.update(value=[], visible=True)

    except Exception as e:
        collector.log(f"❌ Error: {str(e)}")
        yield f"❌ Error: {str(e)}", collector.get_logs(), gr.update(value=[], visible=True)
    finally:
        processing_active = False


# ---------- Build Gradio UI ----------
def build_ui():
    with gr.Blocks(
        title="YT Short Clipper Pro — Web",
        theme=gr.themes.Soft(),
        css="""
        .gradio-container { max-width: 1200px !important; }
        .status-box { padding: 10px; border-radius: 8px; }
        """
    ) as demo:
        gr.Markdown("""
        # 🎬 YT Short Clipper Pro — Web Edition
        **AI-Powered YouTube Shorts Generator** — Jalankan dari Google Colab atau browser mana saja.

        > ⚠️ **Voice Hook** tidak tersedia di versi web (butuh Voicebox running di komputer lokal).
        """)

        with gr.Tabs():
            # ===== TAB 1: Input & Analysis =====
            with gr.Tab("🔍 Input & Analisis"):
                with gr.Row():
                    with gr.Column(scale=3):
                        link_input = gr.Textbox(
                            label="Link YouTube",
                            placeholder="https://www.youtube.com/watch?v=...",
                            lines=1
                        )
                    with gr.Column(scale=1):
                        analyze_btn = gr.Button("✨ Analisis", variant="primary", size="lg")

                with gr.Accordion("⚙️ API Keys & Provider", open=False):
                    with gr.Row():
                        ai_provider = gr.Radio(
                            ["Gemini (Native)", "Groq", "OpenRouter"],
                            value="Gemini (Native)",
                            label="AI Provider"
                        )
                    with gr.Row():
                        gemini_key = gr.Textbox(label="Gemini API Key", type="password", value=config.get("gemini_api_key", ""))
                        gemini_model = gr.Dropdown(["gemini-2.0-flash", "gemini-1.5-flash"], value=config.get("gemini_model", "gemini-2.0-flash"), label="Gemini Model")
                    with gr.Row():
                        groq_key = gr.Textbox(label="Groq API Key", type="password", value=config.get("groq_api_key", ""))
                        groq_model = gr.Dropdown(["llama-3.3-70b-versatile"], value=config.get("groq_model", "llama-3.3-70b-versatile"), label="Groq Model")
                    with gr.Row():
                        openrouter_key = gr.Textbox(label="OpenRouter API Key", type="password", value=config.get("openrouter_api_key", ""))
                        openrouter_model = gr.Textbox(label="OpenRouter Model", value=config.get("openrouter_model", "nvidia/nemotron-3-super-120b-a12b:free"))

                with gr.Accordion("🍪 YouTube Cookies (optional)", open=False):
                    cookies_file = gr.File(label="Upload cookies.txt", file_types=[".txt"])

                analysis_status = gr.Textbox(label="Status", interactive=False, lines=1)
                analysis_log = gr.Textbox(label="Log", interactive=False, lines=8)

                analysis_table = gr.Dataframe(
                    headers=["#", "Start", "End", "Title", "Mood", "Split"],
                    label="Hasil Analisis — Pilih segmen yang mau diproses",
                    interactive=False,
                    wrap=True,
                )

                selected_indices = gr.CheckboxGroup(
                    choices=[],
                    label="Pilih Segmen (centang nomor yang mau diproses)"
                )

                # Store link for processing
                _stored_link = gr.State(value="")

                def on_analyze(link, provider, gk, rk, ok, gm, rm, om, cookies):
                    table_data, status, logs = run_analysis(
                        link, provider, gk, rk, ok, gm, rm, om,
                        str(cookies) if cookies else None
                    )
                    if table_data:
                        choices = [str(row[0]) for row in table_data]
                        return (
                            table_data, status, logs,
                            gr.update(choices=choices, value=[]),
                            link
                        )
                    return None, status, logs, gr.update(choices=[], value=[]), link

                analyze_btn.click(
                    fn=on_analyze,
                    inputs=[link_input, ai_provider, gemini_key, groq_key, openrouter_key,
                            gemini_model, groq_model, openrouter_model, cookies_file],
                    outputs=[analysis_table, analysis_status, analysis_log,
                             selected_indices, _stored_link]
                )

            # ===== TAB 2: Settings =====
            with gr.Tab("⚙️ Settings"):
                with gr.Row():
                    with gr.Column():
                        template = gr.Dropdown(
                            list(TEMPLATES.keys()),
                            value=config.get("template", "cinematic"),
                            label="Template"
                        )
                        render_quality = gr.Dropdown(
                            list(RENDER_PRESETS.keys()),
                            value=config.get("render_quality", "normal"),
                            label="Render Quality"
                        )
                        export_resolution = gr.Dropdown(
                            ["1080x1920", "720x1280"],
                            value=config.get("export_resolution", "1080x1920"),
                            label="Export Resolution"
                        )
                        font_name = gr.Dropdown(
                            list_available_fonts(),
                            value=config.get("subtitle_font", "KOMIKAX_.ttf"),
                            label="Font"
                        )
                    with gr.Column():
                        watermark = gr.Textbox(
                            label="Watermark",
                            value=config.get("watermark", ""),
                            placeholder="@username"
                        )
                        logo_file = gr.File(label="Logo (PNG/JPG)", file_types=[".png", ".jpg", ".jpeg"])
                        bgm_volume = gr.Slider(0, 1, value=config.get("bgm_volume", 0.15), label="BGM Volume")
                        pexels_key = gr.Textbox(
                            label="Pexels API Key (untuk B-Roll)",
                            value=config.get("pexels_api_key", ""),
                            type="password"
                        )
                with gr.Row():
                    end_card = gr.Checkbox(label="End Card (CTA)", value=config.get("end_card", True))
                    end_card_text = gr.Textbox(label="End Card Text", value=config.get("end_card_text", "Follow for more!"))
                    silence_threshold = gr.Slider(0, 1.5, value=config.get("silence_threshold", 0.6), label="Silence Threshold (detik)")

                gr.Markdown("""
                > 💡 **Tips:** Pexels API key gratis di [pexels.com/api](https://www.pexels.com/api/). Diperlukan untuk B-Roll overlay otomatis.
                """)

            # ===== TAB 3: Process & Output =====
            with gr.Tab("🎬 Proses & Output"):
                process_btn = gr.Button("▶ PROSES TERPILIH", variant="primary", size="lg")
                process_status = gr.Textbox(label="Status", interactive=False, lines=1)
                process_log = gr.Textbox(label="Log", interactive=False, lines=15)

                gr.Markdown("### 📥 Hasil Output")
                output_gallery = gr.File(label="Video Output", visible=True, interactive=False)

                gr.Markdown("""
                > 📁 Video tersimpan otomatis di folder `output/` di Google Drive (jika Colab) atau folder project.
                """)

                def on_process(selected, link, tpl, rq, er, wm, bv, pk, ec, ect, st, logo, font):
                    # Convert logo path
                    logo_path = None
                    if logo:
                        logo_path = logo if isinstance(logo, str) else logo.name
                    status, logs, files = process_segments(
                        selected, link, tpl, rq, er, wm, bv, pk, ec, ect, st,
                        logo_path, font
                    )
                    return status, logs, files

                process_btn.click(
                    fn=on_process,
                    inputs=[selected_indices, _stored_link, template, render_quality,
                            export_resolution, watermark, bgm_volume, pexels_key,
                            end_card, end_card_text, silence_threshold,
                            logo_file, font_name],
                    outputs=[process_status, process_log, output_gallery]
                )

        gr.Markdown("""
        ---
        **YT Short Clipper Pro v3.0** — [GitHub](https://github.com/Chukie99/yt-short-clipper-offline) | Made with ❤️
        """)

    return demo


# ---------- Entry Point ----------
if __name__ == "__main__":
    demo = build_ui()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
    )
