"""
clipper_gui_modern.py — Desktop GUI (CustomTkinter) for YT Short Clipper.
Imports core logic from clipper_core.py.
"""
import os, sys, subprocess, threading, time, json, re
from pathlib import Path

from clipper_core import (
    BASE_DIR, TEMP_DIR, OUTPUT_DIR, CONFIG_FILE,
    TEMPLATES, RENDER_PRESETS, DEFAULT_CONFIG, GEMINI_PROMPT, UA,
    load_config, save_config, check_dependencies, list_available_fonts,
    get_safe_id, save_queue_state, load_queue_state, clear_queue_state,
    safe_generate_content, download_youtube, process_single_video,
    voicebox_generate, draw_pro_text, draw_karaoke_line, draw_end_card,
    apply_vignette, apply_cinematic_grade, render_grid_layout,
    compute_speech_segments, is_in_speech_segment, detect_emphasis_words,
    detect_whisper_device, apply_sharpen, get_audio_duration,
    time_str_to_seconds, run_cmd, ensure_bgm, fetch_pexels_broll,
    extract_keywords_from_transcript, KalmanFilter, SpeakerTracker, FaceState,
    QUEUE_STATE_FILE, VOICEBOX_API, IS_COLAB,
    get_ffmpeg_path, get_ytdlp_path, get_detector_path, setup_directories,
)

import customtkinter as ctk
from tkinter import messagebox, Menu, filedialog, TclError
import cv2
import numpy as np
from PIL import Image as PILImage, ImageDraw, ImageFont


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, config, on_save):
        super().__init__(parent); self.title("Settings"); self.geometry("620x950"); self.config = config; self.on_save = on_save
        self.configure(fg_color="#1e1e2e")
        self.grid_columnconfigure(1, weight=1); r = 0
        ctk.CTkLabel(self, text="AI Provider:", font=("Arial", 14, "bold"), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w")
        self.p_var = ctk.StringVar(value=config.get("ai_provider", "Gemini (Native)")); self.p_cb = ctk.CTkComboBox(self, values=["Gemini (Native)", "OpenRouter (DeepSeek/GPT/etc)", "Groq"], variable=self.p_var, command=self.toggle_ai, width=300, corner_radius=8); self.p_cb.grid(row=r, column=1, padx=20, pady=10, sticky="ew"); r += 1
        self.g_f = ctk.CTkFrame(self, fg_color="transparent"); self.g_f.grid(row=r, column=0, columnspan=2, sticky="ew", padx=20, pady=5); self.g_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.g_f, text="Gemini API Key:", text_color="#aaa").grid(row=0, column=0, padx=10, pady=5, sticky="w"); self.gk_var = ctk.StringVar(value=config.get("gemini_api_key", "")); ctk.CTkEntry(self.g_f, textvariable=self.gk_var, width=300, show="*", corner_radius=8).grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(self.g_f, text="Gemini Model:", text_color="#aaa").grid(row=1, column=0, padx=10, pady=5, sticky="w"); self.gm_var = ctk.StringVar(value=config.get("gemini_model", "gemini-2.0-flash")); ctk.CTkComboBox(self.g_f, values=["gemini-2.0-flash", "gemini-1.5-flash"], variable=self.gm_var, width=300, corner_radius=8).grid(row=1, column=1, padx=10, pady=5, sticky="ew")
        self.o_f = ctk.CTkFrame(self, fg_color="transparent"); self.o_f.grid(row=r, column=0, columnspan=2, sticky="ew", padx=20, pady=5); self.o_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.o_f, text="OpenRouter Key:", text_color="#aaa").grid(row=0, column=0, padx=10, pady=5, sticky="w"); self.ok_var = ctk.StringVar(value=config.get("openrouter_api_key", "")); ctk.CTkEntry(self.o_f, textvariable=self.ok_var, width=300, show="*", corner_radius=8).grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(self.o_f, text="Model ID:", text_color="#aaa").grid(row=1, column=0, padx=10, pady=5, sticky="w"); self.om_var = ctk.StringVar(value=config.get("openrouter_model", "nvidia/nemotron-3-super-120b-a12b:free")); ctk.CTkEntry(self.o_f, textvariable=self.om_var, width=300, corner_radius=8).grid(row=1, column=1, padx=10, pady=5, sticky="ew")
        self.gr_f = ctk.CTkFrame(self, fg_color="transparent"); self.gr_f.grid(row=r, column=0, columnspan=2, sticky="ew", padx=20, pady=5); self.gr_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.gr_f, text="Groq API Key:", text_color="#aaa").grid(row=0, column=0, padx=10, pady=5, sticky="w"); self.grk_var = ctk.StringVar(value=config.get("groq_api_key", "")); ctk.CTkEntry(self.gr_f, textvariable=self.grk_var, width=300, show="*", corner_radius=8).grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(self.gr_f, text="Model ID:", text_color="#aaa").grid(row=1, column=0, padx=10, pady=5, sticky="w"); self.grm_var = ctk.StringVar(value=config.get("groq_model", "llama-3.3-70b-versatile")); ctk.CTkEntry(self.gr_f, textvariable=self.grm_var, width=300, corner_radius=8).grid(row=1, column=1, padx=10, pady=5, sticky="ew"); r += 1
        ctk.CTkLabel(self, text="Whisper Provider:", font=("Arial", 13, "bold"), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w")
        self.wp_var = ctk.StringVar(value=config.get("whisper_provider", "Local (faster-whisper)"))
        ctk.CTkComboBox(self, values=["OpenRouter", "Local (faster-whisper)"], variable=self.wp_var, width=300, corner_radius=8).grid(row=r, column=1, padx=20, pady=10, sticky="ew"); r += 1
        ctk.CTkLabel(self, text="Whisper Model (API):", font=("Arial", 13), text_color="#aaa").grid(row=r, column=0, padx=20, pady=5, sticky="w")
        self.wm_var = ctk.StringVar(value=config.get("whisper_model", "openai/whisper-1"))
        ctk.CTkEntry(self, textvariable=self.wm_var, width=300, corner_radius=8).grid(row=r, column=1, padx=20, pady=5, sticky="ew"); r += 1
        ctk.CTkLabel(self, text="Cookies:", font=("Arial", 13), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w"); self.c_var = ctk.StringVar(value=config.get("cookies_path", "")); f_c = ctk.CTkFrame(self, fg_color="transparent"); f_c.grid(row=r, column=1, padx=20, pady=10, sticky="ew"); f_c.grid_columnconfigure(0, weight=1); ctk.CTkEntry(f_c, textvariable=self.c_var, corner_radius=8).grid(row=0, column=0, padx=(0,5), sticky="ew"); ctk.CTkButton(f_c, text="📁", width=50, command=self.browse_cookies, fg_color="#3a3d4e", corner_radius=8).grid(row=0, column=1); r += 1
        ctk.CTkLabel(self, text="Watermark:", font=("Arial", 13), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w"); self.w_var = ctk.StringVar(value=config.get("watermark", "")); ctk.CTkEntry(self, textvariable=self.w_var, width=300, corner_radius=8).grid(row=r, column=1, padx=20, pady=10, sticky="ew"); r += 1
        ctk.CTkLabel(self, text="Pexels API Key:", font=("Arial", 13), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w"); self.pk_var = ctk.StringVar(value=config.get("pexels_api_key", "")); ctk.CTkEntry(self, textvariable=self.pk_var, width=300, corner_radius=8, show="*").grid(row=r, column=1, padx=20, pady=10, sticky="ew"); r += 1
        ctk.CTkLabel(self, text="BGM Volume:", font=("Arial", 13), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w"); self.bv_var = ctk.DoubleVar(value=config.get("bgm_volume", 0.15)); ctk.CTkSlider(self, from_=0, to=1, variable=self.bv_var, width=300).grid(row=r, column=1, padx=20, pady=10, sticky="ew"); r += 1
        ctk.CTkLabel(self, text="Logo:", font=("Arial", 13), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w"); self.l_var = ctk.StringVar(value=config.get("logo_path", "")); f_l = ctk.CTkFrame(self, fg_color="transparent"); f_l.grid(row=r, column=1, padx=20, pady=10, sticky="ew"); f_l.grid_columnconfigure(0, weight=1); ctk.CTkEntry(f_l, textvariable=self.l_var, corner_radius=8).grid(row=0, column=0, padx=(0,5), sticky="ew"); ctk.CTkButton(f_l, text="🖼️", width=50, command=self.browse_logo, fg_color="#3a3d4e", corner_radius=8).grid(row=0, column=1); r += 1
        ctk.CTkLabel(self, text="Font:", font=("Arial", 13), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w");         self.f_opts = list_available_fonts(); self.f_var = ctk.StringVar(value=config.get("subtitle_font", "KOMIKAX_.ttf")); ctk.CTkComboBox(self, values=self.f_opts, variable=self.f_var, width=300, corner_radius=8).grid(row=r, column=1, padx=20, pady=10, sticky="ew"); r += 1
        ctk.CTkLabel(self, text="Render Quality:", font=("Arial", 14, "bold"), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w")
        self.rq_var = ctk.StringVar(value=config.get("render_quality", "normal"))
        ctk.CTkComboBox(self, values=["draft", "normal", "high"], variable=self.rq_var, width=300, corner_radius=8).grid(row=r, column=1, padx=20, pady=10, sticky="ew"); r += 1
        ctk.CTkLabel(self, text="Template:", font=("Arial", 14, "bold"), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w")
        self.tpl_var = ctk.StringVar(value=config.get("template", "cinematic"))
        ctk.CTkComboBox(self, values=list(TEMPLATES.keys()), variable=self.tpl_var, width=300, corner_radius=8).grid(row=r, column=1, padx=20, pady=10, sticky="ew"); r += 1
        ctk.CTkLabel(self, text="Export Resolusi:", font=("Arial", 13), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w")
        self.er_var = ctk.StringVar(value=config.get("export_resolution", "1080x1920"))
        ctk.CTkComboBox(self, values=["1080x1920", "720x1280"], variable=self.er_var, width=300, corner_radius=8).grid(row=r, column=1, padx=20, pady=10, sticky="ew"); r += 1
        ctk.CTkLabel(self, text="Silence Threshold (detik):", font=("Arial", 13), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w")
        self.st_var = ctk.DoubleVar(value=config.get("silence_threshold", 0.6))
        ctk.CTkSlider(self, from_=0.0, to=1.5, variable=self.st_var, width=200).grid(row=r, column=1, padx=20, pady=10, sticky="w")
        ctk.CTkLabel(self, textvariable=self.st_var, text_color="#aaa", width=40).grid(row=r, column=1, padx=(220,0), pady=10, sticky="w"); r += 1
        self.ec_var = ctk.BooleanVar(value=config.get("end_card", True))
        ctk.CTkCheckBox(self, text="End Card (CTA di akhir video)", variable=self.ec_var, fg_color="#4b6e9c").grid(row=r, column=0, columnspan=2, padx=20, pady=5, sticky="w"); r += 1
        ctk.CTkLabel(self, text="End Card Text:", font=("Arial", 13), text_color="#ddd").grid(row=r, column=0, padx=20, pady=5, sticky="w")
        self.ec_text_var = ctk.StringVar(value=config.get("end_card_text", "Follow for more!"))
        ctk.CTkEntry(self, textvariable=self.ec_text_var, width=300, corner_radius=8).grid(row=r, column=1, padx=20, pady=5, sticky="ew"); r += 1

        ctk.CTkButton(self, text="👁️ Preview Subtitle Style", command=self.preview_subtitle, fg_color="#4b6e9c", hover_color="#3a5a7a", corner_radius=8).grid(row=r, column=0, columnspan=2, padx=20, pady=10); r += 1

        b_f = ctk.CTkFrame(self, fg_color="transparent"); b_f.grid(row=r, column=0, columnspan=2, pady=30); ctk.CTkButton(b_f, text="💾 Save", command=self.save, fg_color="#2e8b57", hover_color="#236b43", corner_radius=8, width=100).pack(side="left", padx=20); ctk.CTkButton(b_f, text="Cancel", fg_color="#555", hover_color="#444", corner_radius=8, width=100, command=self.destroy).pack(side="left", padx=20); self.toggle_ai(self.p_var.get())
    def toggle_ai(self, c):
        self.g_f.grid_remove(); self.o_f.grid_remove(); self.gr_f.grid_remove()
        if c == "Gemini (Native)": self.g_f.grid()
        elif c == "Groq": self.gr_f.grid()
        else: self.o_f.grid()
    def browse_logo(self):
        p = filedialog.askopenfilename(filetypes=[("Image", "*.png *.jpg *.jpeg"), ("PNG", "*.png"), ("JPEG", "*.jpg *.jpeg")])
        if p: self.l_var.set(p)
    def browse_cookies(self):
        p = filedialog.askopenfilename(filetypes=[("TXT", "*.txt")])
        if p: self.c_var.set(p)
    def preview_subtitle(self):
        try:
            font_name = self.f_var.get()
            font_path = str(BASE_DIR / "fonts" / font_name)
            if not os.path.exists(font_path):
                font_path = "C:/Windows/Fonts/impact.ttf"
            tpl_name = self.tpl_var.get()
            tpl = TEMPLATES.get(tpl_name, TEMPLATES["cinematic"])
            preview = PILImage.new('RGB', (400, 700), (30, 30, 50))
            draw = ImageDraw.Draw(preview)
            font = ImageFont.truetype(font_path, 40)
            font_small = ImageFont.truetype(font_path, 28)
            sample = "CONTOH SUBTITLE KARAOKE"
            words = sample.split()
            cx = 200
            y_pos = 500
            for w in words:
                is_a = w == "KARAOKE"
                c = tpl.get("active_color", (255, 230, 0)) if is_a else tpl.get("inactive_color", (255, 255, 255))
                f = font if is_a else font_small
                bbox = draw.textbbox((0, 0), w, font=f)
                ww = bbox[2] - bbox[0]
                draw.text((cx - ww//2 + 2, y_pos + 2), w, font=f, fill=(0, 0, 0))
                draw.text((cx - ww//2, y_pos), w, font=f, fill=c)
                cx += ww + 15
            draw.text((10, 10), f"Template: {tpl_name}", font=font_small, fill=(150, 150, 150))
            draw.text((10, 50), f"Font: {font_name}", font=font_small, fill=(150, 150, 150))
            draw.text((10, 90), f"Aktif: {tpl.get('active_color')}", font=font_small, fill=tpl.get("active_color", (255,255,255)))
            draw.text((10, 130), f"Non-aktif: {tpl.get('inactive_color')}", font=font_small, fill=tpl.get("inactive_color", (200,200,200)))
            preview.show()
        except Exception as e:
            messagebox.showerror("Preview Error", str(e))
    def save(self):
        nc = {"ai_provider": self.p_var.get(), "gemini_api_key": self.gk_var.get().strip(), "gemini_model": self.gm_var.get(), "openrouter_api_key": self.ok_var.get().strip(), "openrouter_model": self.om_var.get().strip(), "groq_api_key": self.grk_var.get().strip(), "groq_model": self.grm_var.get().strip(), "pexels_api_key": self.pk_var.get().strip(), "cookies_path": self.c_var.get().strip(), "watermark": self.w_var.get().strip(), "subtitle_font": self.f_var.get(), "logo_path": self.l_var.get().strip(), "bgm_volume": self.bv_var.get(), "render_quality": self.rq_var.get(), "template": self.tpl_var.get(), "export_resolution": self.er_var.get(), "end_card": self.ec_var.get(), "end_card_text": self.ec_text_var.get().strip(), "whisper_provider": self.wp_var.get(), "whisper_model": self.wm_var.get().strip(), "silence_threshold": self.st_var.get()}
        self.on_save(nc); self.destroy()

class VideoItem(ctk.CTkFrame):
    def __init__(self, master, index, remove_cb, log_func, config, get_link):
        super().__init__(master, fg_color="#2a2d3e", corner_radius=12, border_width=1, border_color="#3a3d4e")
        self.index, self.remove_cb, self.log_func, self.config, self.get_link = index, remove_cb, log_func, config, get_link; self.is_json = False; self.sel_var = ctk.BooleanVar(value=True); ctk.CTkCheckBox(self, text="", variable=self.sel_var, width=20, fg_color="#4b6e9c", hover_color="#3a5a7a").grid(row=0, column=0, rowspan=2, padx=15, pady=10)
        self.l_f = ctk.CTkFrame(self, fg_color="transparent", width=70); self.l_f.grid(row=0, column=1, rowspan=2, padx=10, pady=10, sticky="nsew"); self.idx_lbl = ctk.CTkLabel(self.l_f, text=f"#{index+1}", font=("Arial", 18, "bold"), text_color="#4b6e9c"); self.idx_lbl.pack(); self.st_lbl = ctk.CTkLabel(self.l_f, text="Ready", font=("Arial", 11), text_color="#aaa"); self.st_lbl.pack()
        self.top = ctk.CTkFrame(self, fg_color="transparent"); self.top.grid(row=0, column=2, sticky="ew", padx=10, pady=(10,0)); self.m_sw = ctk.CTkSegmentedButton(self.top, values=["Manual", "JSON"], command=self.toggle_mode); self.m_sw.set("Manual"); self.m_sw.pack(side="left")
        self.cont = ctk.CTkFrame(self, fg_color="transparent"); self.cont.grid(row=1, column=2, sticky="ew", padx=10, pady=(0,10)); self.man_f = ctk.CTkFrame(self.cont, fg_color="transparent"); self.man_f.pack(fill="x"); r1 = ctk.CTkFrame(self.man_f, fg_color="transparent"); r1.pack(fill="x", pady=2)
        ctk.CTkLabel(r1, text="Mulai:", text_color="#aaa").pack(side="left", padx=3); self.s_var = ctk.StringVar(value="00:00:00"); ctk.CTkEntry(r1, textvariable=self.s_var, width=70, corner_radius=6).pack(side="left", padx=3)
        ctk.CTkLabel(r1, text="Selesai:", text_color="#aaa").pack(side="left", padx=3); self.e_var = ctk.StringVar(value="00:00:10"); ctk.CTkEntry(r1, textvariable=self.e_var, width=70, corner_radius=6).pack(side="left", padx=3)
        self.l_var = ctk.StringVar(value="id"); ctk.CTkEntry(r1, textvariable=self.l_var, width=45, corner_radius=6).pack(side="left", padx=3)
        self.mo_var = ctk.StringVar(value="small"); ctk.CTkComboBox(r1, values=["tiny", "base", "small", "medium", "large-v3"], variable=self.mo_var, width=90, corner_radius=6).pack(side="left", padx=3)
        ctk.CTkLabel(r1, text="Z:", text_color="#aaa").pack(side="left", padx=2); self.z_var = ctk.StringVar(value="1.0"); ctk.CTkEntry(r1, textvariable=self.z_var, width=40, corner_radius=6).pack(side="left", padx=2)
        ctk.CTkLabel(r1, text="Y:", text_color="#aaa").pack(side="left", padx=2); self.y_var = ctk.StringVar(value="0.35"); ctk.CTkEntry(r1, textvariable=self.y_var, width=40, corner_radius=6).pack(side="left", padx=2)
        self.sp_var = ctk.BooleanVar(value=False); ctk.CTkCheckBox(r1, text="Split", variable=self.sp_var, width=60, fg_color="#4b6e9c").pack(side="left", padx=5)
        r2 = ctk.CTkFrame(self.man_f, fg_color="transparent"); r2.pack(fill="x", pady=(5,0))
        ctk.CTkLabel(r2, text="Judul:", text_color="#aaa").pack(side="left", padx=3)
        self.t_var = ctk.StringVar(); ctk.CTkEntry(r2, textvariable=self.t_var, width=160, corner_radius=6).pack(side="left", padx=5)
        ctk.CTkLabel(r2, text="Opini:", text_color="#aaa").pack(side="left", padx=3)
        self.thumb_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(r2, text="IMG", variable=self.thumb_var, width=50, fg_color="#4b6e9c").pack(side="left", padx=3)
        self.op_var = ctk.StringVar(value="Masukkan teks judul opini"); ctk.CTkEntry(r2, textvariable=self.op_var, width=250, corner_radius=6).pack(side="left", padx=5)
        self.gem_b = ctk.CTkButton(r2, text="✨ Analisis", width=90, command=self.analyze_with_ai, fg_color="#4b6e9c", hover_color="#3a5a7a", corner_radius=8); self.gem_b.pack(side="left", padx=10)
        r3 = ctk.CTkFrame(self.man_f, fg_color="transparent")
        r3.pack(fill="x", pady=(2,0))
        self.br_var = ctk.BooleanVar(value=False)
        self.br_cb = ctk.CTkCheckBox(r3, text="🎨 B-Roll Pexels (otomatis)", variable=self.br_var, fg_color="#4b6e9c")
        self.br_cb.pack(side="left", padx=5)
        
        pk = self.config.get("pexels_api_key")
        if not pk:
            self.br_cb.configure(state="disabled")
            self.br_var.set(False)

        ctk.CTkLabel(r3, text="Voice Hook MP3:", text_color="#aaa").pack(side="left", padx=(15,3))
        self.vh_var = ctk.StringVar(value="Pilih file MP3 hook..."); ctk.CTkEntry(r3, textvariable=self.vh_var, width=300, corner_radius=6).pack(side="left", padx=5)
        ctk.CTkButton(r3, text="📂", width=40, command=self.browse_voice_hook, fg_color="#3a3d4e", corner_radius=6).pack(side="left", padx=2)
        ctk.CTkLabel(r3, text="Hook Durasi:", text_color="#aaa").pack(side="left", padx=(10,3))
        self.hook_dur_var = ctk.DoubleVar(value=1.5)
        ctk.CTkSlider(r3, from_=0.5, to=5.0, variable=self.hook_dur_var, width=100).pack(side="left", padx=3)
        ctk.CTkLabel(r3, textvariable=self.hook_dur_var, text_color="#aaa", width=35).pack(side="left", padx=2)
        self.js_f = ctk.CTkFrame(self.cont, fg_color="transparent"); self.js_t = ctk.CTkTextbox(self.js_f, width=500, height=80, corner_radius=8, fg_color="#1e1e2e", text_color="#ccc"); self.js_t.pack(side="left", padx=10)
        ctk.CTkButton(self, text="✕", width=35, fg_color="#c44", hover_color="#a33", corner_radius=8, command=lambda: remove_cb(self)).grid(row=0, column=3, padx=15, pady=10, rowspan=2); self.update_ai_button(); self.toggle_mode("Manual")
    def toggle_mode(self, m):
        if m == "Manual": self.js_f.pack_forget(); self.man_f.pack(fill="x"); self.is_json = False
        else: self.man_f.pack_forget(); self.js_f.pack(fill="x"); self.is_json = True
    def set_status(self, s, c=None): self.st_lbl.configure(text=s, text_color=c if c else "#aaa")
    def set_active(self, a=True): self.configure(border_color="#4b6e9c" if a else "#3a3d4e", border_width=2 if a else 1)
    def update_ai_button(self):
        p = self.config.get("ai_provider")
        if p == "Gemini (Native)": k = self.config.get("gemini_api_key")
        elif p == "Groq": k = self.config.get("groq_api_key")
        else: k = self.config.get("openrouter_api_key")
        self.gem_b.configure(state="normal" if k else "disabled")
    def get_data(self):
        lk = self.get_link()
        try:
            z = float(self.z_var.get() or 1.0)
            y = float(self.y_var.get() or 0.35)
        except (ValueError, TypeError) as e:
            z, y = 1.0, 0.35
            import logging
            logging.getLogger("clipper").debug("Zoom/Y-offset parse fallback: %s", e)
        hook_dur = self.hook_dur_var.get()
        
        if not self.is_json: return [{ "link": lk, "start": self.s_var.get(), "end": self.e_var.get(), "title": self.t_var.get(), "lang": self.l_var.get() or "id", "model": self.mo_var.get(), "selected": self.sel_var.get(), "split": self.sp_var.get(), "thumb": self.thumb_var.get(), "mood": getattr(self, "_mood", "santai"), "zoom": z, "y_offset": y, "voice_hook": self.vh_var.get().strip(), "judul_opini": self.op_var.get().strip(), "use_broll": self.br_var.get(), "hook_dur": hook_dur, "_thumb_time": getattr(self, "_thumb_time", None), "_ai_desc": getattr(self, "_ai_desc", ""), "_hook_text": getattr(self, "_hook_text", "") }]
        try:
            segs = json.loads(self.js_t.get("1.0", "end").strip())
            if isinstance(segs, dict): segs = [segs]
            for s in segs: 
                s.update({"link": lk, "selected": self.sel_var.get()})
                if "split_screen" in s:
                    s["split"] = s.pop("split_screen")
                s.setdefault("split", self.sp_var.get()); s.setdefault("mood", "santai"); s.setdefault("model", self.mo_var.get()); s.setdefault("lang", self.l_var.get() or "id")
                s.setdefault("zoom", z); s.setdefault("y_offset", y)
                s.setdefault("voice_hook", self.vh_var.get().strip()); s.setdefault("judul_opini", self.op_var.get().strip())
                s.setdefault("use_broll", self.br_var.get())
            return segs
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            import logging
            logging.getLogger("clipper").warning("JSON segment parse failed: %s", e)
            return []
    def browse_voice_hook(self):
        p = filedialog.askopenfilename(filetypes=[("MP3", "*.mp3")])
        if p: self.vh_var.set(p)
    def analyze_with_ai(self):
        lk = self.get_link()
        if not lk: return
        self.log_func("[#] Analisis segmen...")
        try:
            rt = safe_generate_content(self.config, f"{GEMINI_PROMPT}\nLink: {lk}", self.log_func)
            jm = re.search(r'(\[.*\]|\{.*\})', rt, re.DOTALL)
            if jm:
                raw_json = re.sub(r'[\x00-\x1f]', '', jm.group(1))
                d = json.loads(raw_json)
            else:
                d = []
            if isinstance(d, dict): d = [d]
            if d:
                if len(d) > 1: self.m_sw.set("JSON"); self.toggle_mode("JSON"); self.js_t.delete("1.0", "end"); self.js_t.insert("1.0", json.dumps(d, indent=2))
                else:
                    s = d[0]
                    self.s_var.set(s.get("start","00:00:00")); self.e_var.set(s.get("end","00:00:10"))
                    self.t_var.set(s.get("title","")); self._mood = s.get("mood","santai"); self._ai_desc = s.get("description","")
                    self._hook_text = s.get("hook","")
                    self.op_var.set(s.get("judul_opini",""))
                    if s.get("split_screen", False):
                        self.sp_var.set(True)
                    if not s.get("thumb", True):
                        self.thumb_var.set(False)
                    vhs = s.get("voice_hook_script","")
                    if vhs:
                        hook_path = TEMP_DIR / f"voicehook_{int(time.time())}.mp3"
                        self.log_func(f"\n🎤=== VOICE HOOK SCRIPT ===\n{vhs}\n==========================")
                        if voicebox_generate(vhs, hook_path, self.log_func):
                            self.vh_var.set(str(hook_path))
                            self.log_func(f"[✅] Voice hook generated -> {hook_path.name}")
                        else:
                            self.log_func("🎤 Rekam manual dan upload MP3-nya!\n")
        except Exception as e: messagebox.showerror("Error", str(e))

class App(ctk.CTk):
    def __init__(self):
        super().__init__(); self.title("YT Short Clipper v3.0"); self.geometry("1100x850"); 
        ctk.set_appearance_mode("dark"); ctk.set_default_color_theme("blue")
        de = check_dependencies(); self.dependency_failed = len(de) > 0
        self.config = load_config(); self.v_items = []; self.proc = False; self.proc_lock = threading.Lock()
        self.grid_columnconfigure(0, weight=1); [self.grid_rowconfigure(i, weight=0) for i in range(6)]; self.grid_rowconfigure(6, weight=1)
        m = ctk.CTkFrame(self, height=40, fg_color="#1e1e2e", corner_radius=0); m.grid(row=0, column=0, sticky="ew"); m.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(m, text="⚙️ Settings", command=self.open_settings, fg_color="transparent", hover_color="#3a3d4e").pack(side="left", padx=10, pady=5)
        ctk.CTkButton(m, text="ℹ️ About", command=lambda: messagebox.showinfo("About", "YT Short Clipper v3.0\nAI-powered video segment clipper.\n\nFeatures: Templates, Auto-split, Queue Persist, Subtitle Animation, End Cards"), fg_color="transparent", hover_color="#3a3d4e").pack(side="right", padx=10, pady=5)
        ctk.CTkLabel(self, text="YT Shorts Clipper Pro", font=("Arial", 26, "bold"), text_color="#fff").grid(row=1, column=0, pady=15)
        f_l = ctk.CTkFrame(self, fg_color="#2a2d3e", corner_radius=10); f_l.grid(row=2, column=0, padx=30, pady=5, sticky="ew"); f_l.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(f_l, text="🎬 Link YouTube:", font=("Arial", 14, "bold"), text_color="#ddd").pack(side="left", padx=(15,10), pady=10)
        self.l_var = ctk.StringVar(); ctk.CTkEntry(f_l, textvariable=self.l_var, width=500, corner_radius=8).pack(side="left", padx=10, fill="x", expand=True, pady=10)
        ctk.CTkButton(f_l, text="🔍 Ambil & Analisis", command=self.start_analysis, fg_color="#4b6e9c", hover_color="#3a5a7a", corner_radius=8).pack(side="left", padx=(10,15), pady=10)
        self.scr = ctk.CTkScrollableFrame(self, width=1050, height=350, fg_color="#13141c", corner_radius=12); self.scr.grid(row=3, column=0, padx=30, pady=10, sticky="nsew"); self.scr.grid_columnconfigure(0, weight=1)
        f_b = ctk.CTkFrame(self, fg_color="transparent"); f_b.grid(row=4, column=0, pady=15)
        ctk.CTkButton(f_b, text="➕ Tambah Segmen Manual", command=self.add_video_item, width=180, fg_color="#3a3d4e", hover_color="#2a2d3e", corner_radius=8).pack(side="left", padx=10)
        self.p_btn = ctk.CTkButton(f_b, text="▶ PROSES TERPILIH", fg_color="#2e8b57", hover_color="#236b43", width=200, command=self.start_processing, corner_radius=8).pack(side="left", padx=30)
        self.p_bar = ctk.CTkProgressBar(self, width=1050, corner_radius=5, fg_color="#2a2d3e", progress_color="#4b6e9c"); self.p_bar.grid(row=5, column=0, pady=5, padx=30); self.p_bar.set(0)
        self.log_t = ctk.CTkTextbox(self, width=1050, height=180, fg_color="#13141c", text_color="#ddd", corner_radius=12, border_width=1, border_color="#3a3d4e"); self.log_t.grid(row=6, column=0, padx=30, pady=(5,20), sticky="nsew")
        sys.stdout = self
        self._stdout_lock = threading.Lock()
        saved = load_queue_state()
        if saved and saved.get("segments"):
            self.log("[📂] Queue sebelumnya ditemukan, memulihkan...")
            for s in saved["segments"]:
                self.add_video_item()
                it = self.v_items[-1]
                it.s_var.set(s.get("start", "00:00:00"))
                it.e_var.set(s.get("end", "00:00:10"))
                it.t_var.set(s.get("title", ""))
                it.l_var.set(s.get("lang", "id"))
                it.mo_var.set(s.get("model", "small"))
                it.op_var.set(s.get("judul_opini", ""))
                if s.get("split"): it.sp_var.set(True)
                if s.get("voice_hook"): it.vh_var.set(s["voice_hook"])
                if s.get("link"): self.l_var.set(s["link"])
            self.log(f"[📂] {len(saved['segments'])} segmen dipulihkan.")
        else:
            self.add_video_item()
    def write(self, m):
        with self._stdout_lock:
            try:
                self.log_t.configure(state="normal")
                self.log_t.insert("end", m)
                self.log_t.see("end")
                self.log_t.configure(state="disabled")
            except Exception:
                pass
    def flush(self): pass
    def open_settings(self): SettingsDialog(self, self.config, self.on_settings_save).grab_set()
    def on_settings_save(self, nc): self.config = nc; save_config(nc); [setattr(it, 'config', nc) for it in self.v_items]; [it.update_ai_button() for it in self.v_items]
    def add_video_item(self): i = len(self.v_items); it = VideoItem(self.scr, i, self.remove_video_item, self.log, self.config, lambda: self.l_var.get()); it.grid(row=i, column=0, pady=8, padx=15, sticky="ew"); self.v_items.append(it)
    def remove_video_item(self, item):
        if len(self.v_items) > 1:
            item.destroy()
            self.v_items.remove(item)
            for i, v in enumerate(self.v_items):
                v.idx_lbl.configure(text=f"#{i+1}")
    def log(self, m): self.write(m + "\n")
    def start_analysis(self):
        lk = self.l_var.get().strip()
        if lk: threading.Thread(target=self.run_analysis, args=(lk,), daemon=True).start()
    def run_analysis(self, link):
        try:
            self.log("[#] Fetching metadata...")
            vid_id = get_safe_id(link)
            sid = vid_id
            y_p = get_ytdlp_path()
            cp = self.config.get("cookies_path", "")
            c_o = f'--cookies "{cp}"' if cp and os.path.exists(cp) else ""
            cmd_info = f'{y_p} {c_o} --user-agent "{UA}" --extractor-args "youtube:player_client=android" --skip-download --write-info-json -o "{TEMP_DIR}/{sid}_full" "{link}"'
            subprocess.run(cmd_info, shell=True, capture_output=True, timeout=30)
            info_f = TEMP_DIR / f"{sid}_full.info.json"
            title, desc = sid, ""
            if info_f.exists():
                with open(info_f, "r", encoding="utf-8") as f:
                    m = json.load(f)
                    title = m.get("title", sid)
                    desc = m.get("description","")[:500]
            self.log(f"[#] Video: {title}")
            cmd_subs = f'{y_p} {c_o} --user-agent "{UA}" --extractor-args "youtube:player_client=android" --skip-download --write-auto-subs --sub-langs "id,en" --convert-subs srt -o "{TEMP_DIR}/{sid}_full" "{link}"'
            try:
                subprocess.run(cmd_subs, shell=True, capture_output=True, timeout=60)
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError) as e:
                self.log("[!] Subtitle tidak tersedia, lanjut tanpa transkrip.")
                import logging
                logging.getLogger("clipper").debug("Subtitle download failed: %s", e)
            orig = TEMP_DIR / f"{sid}_full.mp4"
            if not orig.exists():
                self.log("[#] Downloading...")
                try:
                    download_youtube(link, orig, self.config.get("cookies_path"), self.log)
                except Exception as e:
                    import logging
                    logging.getLogger("clipper").error("YouTube download failed: %s", e)
                    self.log(f"❌ {str(e)}")
                    return
            srt = list(TEMP_DIR.glob(f"{sid}_full.*.srt"))
            txt = ""
            if srt:
                self.log("[#] Parsing subtitle...")
                with open(srt[0], "r", encoding="utf-8", errors="replace") as f:
                    for l in f:
                        if "-->" not in l and l.strip() and not l.strip().isdigit():
                            txt += l.strip() + " "
            ctx = f"TITLE: {title}\nDESC: {desc}\nTRANSCRIPT: {txt[:20000]}"
            self.log("[#] Menganalisis dengan AI...")
            rt = safe_generate_content(self.config, f"{GEMINI_PROMPT.format(transcript=ctx)}\nLink: {link}", self.log)
            jm = re.search(r'(\[.*\]|\{.*\})', rt, re.DOTALL)
            if jm:
                raw_json = re.sub(r'[\x00-\x1f]', '', jm.group(1))
                d = json.loads(raw_json)
            else:
                d = []
            self.after(0, lambda: self.populate_segments(d))
        except Exception as e:
            import logging
            logging.getLogger("clipper").error("Analysis failed: %s", e)
            self.log(f"❌ Error: {str(e)}")
    def populate_segments(self, d):
        [i.destroy() for i in self.v_items]; self.v_items.clear()
        if isinstance(d, dict): d = [d]
        for s in d:
            self.add_video_item(); it = self.v_items[-1]
            it.s_var.set(s.get("start","00:00:00")); it.e_var.set(s.get("end","00:00:10"))
            it.t_var.set(s.get("title","")); it._mood = s.get("mood","santai"); it._ai_desc = s.get("description","")
            it.op_var.set(s.get("judul_opini",""))
            if s.get("split_screen", False):
                it.sp_var.set(True)
            if not s.get("thumb", True):
                it.thumb_var.set(False)
            vhs = s.get("voice_hook_script","")
            if vhs:
                hook_path = TEMP_DIR / f"voicehook_{int(time.time())}.mp3"
                self.log(f"\n🎤=== VOICE HOOK SCRIPT ===\n{vhs}\n==========================")
                if voicebox_generate(vhs, hook_path, self.log):
                    it.vh_var.set(str(hook_path))
                    self.log(f"[✅] Voice hook generated -> {hook_path.name}")
                else:
                    self.log("🎤 Rekam manual dan upload MP3-nya!\n")
    def start_processing(self):
        al = []
        for it in self.v_items:
            for d in it.get_data():
                if d.get("selected"): d["_item"] = it; al.append(d)
        if not al:
            self.log("[!] Tidak ada segmen dipilih.")
            return
        save_queue_state(al, self.config)
        with self.proc_lock:
            if self.proc:
                return
            self.proc = True
        self.p_bar.set(0)
        threading.Thread(target=self.run_batch, args=(al,), daemon=True).start()
    def run_batch(self, segs):
        total = len(segs)
        for i, v in enumerate(segs):
            it = v["_item"]; it.set_active(True); it.set_status("Processing..."); ss = time_str_to_seconds(v["start"]); es = time_str_to_seconds(v["end"])
            o = { 
                "cookies_path": self.config.get("cookies_path"), 
                "watermark": self.config.get("watermark"), 
                "status_func": it.set_status, 
                "selected_font": self.config.get("subtitle_font"), 
                "logo_path": self.config.get("logo_path"), 
                "ai_desc": v.get("_ai_desc"), 
                "split_screen": v.get("split"), 
                "mood": v.get("mood"), 
                "bgm_volume": self.config.get("bgm_volume", 0.15),
                "zoom": v.get("zoom", 1.0),
                "y_offset": v.get("y_offset", 0.35),
                "voice_hook": v.get("voice_hook", ""),
                "judul_opini": v.get("judul_opini", ""),
                "use_broll": v.get("use_broll", False),
                "hook_dur": v.get("hook_dur", 1.5),
                "hook_text": v.get("_hook_text", ""),
                "gen_thumb": v.get("thumb", True),
                "root": self,
                "config": self.config,
                "render_quality": self.config.get("render_quality", "normal"),
                "template": self.config.get("template", "cinematic"),
                "export_resolution": self.config.get("export_resolution", "1080x1920"),
                "end_card": self.config.get("end_card", True),
                "end_card_text": self.config.get("end_card_text", "Follow for more!"),
                "silence_threshold": self.config.get("silence_threshold", 0.6),
            }
            success, msg = process_single_video(v["link"], ss, es, v["title"], v["lang"], v["model"], self.log, lambda p, idx=i: self.p_bar.set((idx*100+p)/(total*100)), opts=o)
            it.set_status("Done" if success else "Error"); it.set_active(False)
        clear_queue_state()
        self.log("✅ Finished."); self.p_bar.set(1)
        with self.proc_lock:
            self.proc = False

if __name__ == "__main__": app = App(); app.mainloop()
