import tkinter as tk
from tkinter import ttk, messagebox
import time
import sys
import os
import json
import datetime as dt
import webbrowser
from PIL import Image, ImageTk  # Pillow for image handling

# Matplotlib for heatmap embed
import matplotlib
matplotlib.use("Agg")  # draw offscreen; we'll embed via FigureCanvasTkAgg
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import numpy as np
import threading
import random
try:
    import pygame
except Exception:
    pygame = None
# --- Resource path helper ---
def resource_path(rel_path: str) -> str:
    # Giúp lấy đúng đường dẫn asset khi chạy .py hoặc .exe (PyInstaller)
    try:
        base_path = sys._MEIPASS  # thuộc tính PyInstaller
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, rel_path)

# --- Optional desktop notification (non-blocking) ---
try:
    from plyer import notification as _plyer_notify
except Exception:
    _plyer_notify = None

APP_NAME = "Pomodoro Timer"
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")

# --- Sound helpers (Windows-first) ---
def play_beep(root: tk.Tk):
    """Beep at phase change. Uses winsound on Windows; safe fallbacks elsewhere."""
    try:
        if sys.platform.startswith("win"):
            import winsound
            winsound.Beep(880, 180)
            winsound.Beep(660, 180)
        else:
            root.bell()
    except Exception:
        pass


def notify(title: str, message: str):
    """Fire a desktop notification if possible; otherwise no-op."""
    try:
        if _plyer_notify:
            _plyer_notify.notify(title=title, message=message, app_name=APP_NAME, timeout=5)
    except Exception:
        pass

class MusicPlayer:
    def __init__(self, folder: str, shuffle: bool = True, volume: float = 0.6):
        self.folder = folder
        self.shuffle = shuffle
        self.volume = max(0.0, min(1.0, float(volume)))
        self._stop = threading.Event()
        self._thread = None
        self._playlist = []
        self._i = 0
        try:
            if pygame is None:
                raise RuntimeError("pygame not available")
            pygame.mixer.init()
            pygame.mixer.music.set_volume(self.volume)
            self.available = True
        except Exception as e:
            print("[Music] Disabled:", e)
            self.available = False

    def _load_playlist(self):
        if not os.path.isdir(self.folder):
            self._playlist = []
            return
        files = [os.path.join(self.folder, f) for f in os.listdir(self.folder) if f.lower().endswith(".mp3")]
        files.sort()
        if self.shuffle:
            random.shuffle(files)
        self._playlist = files

    def _loop(self):
        import time
        self._load_playlist()
        if not self._playlist:
            print(f"[Music] No .mp3 found in '{self.folder}'.")
            return
        self._i = 0
        while not self._stop.is_set():
            track = self._playlist[self._i]
            try:
                pygame.mixer.music.load(track)
                pygame.mixer.music.play()
                print("[Music] Playing:", os.path.basename(track))
            except Exception as e:
                print("[Music] Play error:", e)
            while not self._stop.is_set() and pygame.mixer.music.get_busy():
                time.sleep(0.2)
            self._i += 1
            if self._i >= len(self._playlist):
                if self.shuffle:
                    random.shuffle(self._playlist)
                self._i = 0

    def start(self):
        if not getattr(self, "available", False):
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        if not getattr(self, "available", False):
            return
        self._stop.set()
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass

class PomodoroApp:
    def _toggle_music(self):
        try:
            if self.music_enabled.get():
                self.music.start()
            else:
                self.music.stop()
        except Exception as e:
            print("[Music] toggle error:", e)

    def __init__(self, root: tk.Tk):
        self.root = root
        # Set app icon for window & taskbar
        try:
            self.root.iconbitmap(resource_path("assets/app.ico"))  # ưu tiên .ico trên Windows
        except Exception:
            # fallback cho nền tảng khác hoặc khi .ico không chạy được
            self._app_icon = tk.PhotoImage(file=resource_path("assets/app.png"))
            self.root.iconphoto(False, self._app_icon)

        self.root.title(APP_NAME)
        self.root.geometry("680x460")
        self.root.minsize(600, 420)

        # --- State ---
        self.modes = {
            "50 / 10": (50, 10),
            "25 / 5": (25, 5),
        }
        self.mode_var = tk.StringVar(value="25 / 5")
        self.phase = "focus"  # or "break"
        self.running = False
        self.start_ts = None          # monotonic seconds when (re)started
        self.remaining_secs = self._phase_duration_secs()
        self.completed_focus_sessions = 0  # in this runtime
        self.sound_enabled = tk.BooleanVar(value=True)

        # Data & settings
        self.data = self._load_data()
        self.playlist_var = tk.StringVar(value=self.data.get("settings", {}).get("playlist_url", ""))
        # --- Music (optional) ---
        self.music_enabled = tk.BooleanVar(value=True)
        try:
            # Nếu đã có class MusicPlayer (bước 2), đoạn dưới sẽ chạy
            music_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "music")
            self.music = MusicPlayer(folder=music_folder, shuffle=True, volume=0.6)
            if self.music_enabled.get():
                self.music.start()
        except NameError:
            # Chưa thêm class MusicPlayer thì vẫn tạo biến để UI không lỗi
            self.music = None

        # UI
        self._build_ui()
        self._update_labels()
        self._update_clock()

    # ----------------- Persistence -----------------
    def _load_data(self):
        if not os.path.exists(DATA_FILE):
            return {"days": {}, "settings": {}}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("bad data.json structure")
            data.setdefault("days", {})
            data.setdefault("settings", {})
            return data
        except Exception:
            return {"days": {}, "settings": {}}

    def _save_data(self):
        try:
            os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _log_focus_session(self, minutes: int):
        today = dt.date.today().isoformat()  # YYYY-MM-DD
        dayrec = self.data.setdefault("days", {}).setdefault(today, {"focus_sessions": 0, "minutes": 0})
        dayrec["focus_sessions"] += 1
        dayrec["minutes"] += int(minutes)
        self._save_data()
        # Refresh stats tab counter immediately
        self._render_heatmap(auto_size=False)

    # ----------------- UI -----------------
    def _build_ui(self):
        # Notebook with two tabs: Timer / Stats
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True)

        self.timer_tab = ttk.Frame(self.nb)
        self.stats_tab = ttk.Frame(self.nb)
        self.nb.add(self.timer_tab, text="Timer")
        self.nb.add(self.stats_tab, text="Stats")
                # ==== ẢNH NỀN CHO TAB STATS ====
        bg_file_stats = resource_path("assets/bg.jpg")  # có thể đổi ảnh khác cho Stats nếu muốn
        try:
            self._bg_stats_src = Image.open(bg_file_stats)
        except Exception as e:
            self._bg_stats_src = None
            print("Không load được ảnh nền Stats:", e)

        self._bg_stats_label = tk.Label(self.stats_tab, bd=0, highlightthickness=0)
        self._bg_stats_label.place(relx=0, rely=0, relwidth=1, relheight=1)

        def _img_cover_stats(img, target_size):
            tw, th = target_size
            iw, ih = img.size
            scale = max(tw / iw, th / ih)
            nw, nh = int(iw * scale), int(ih * scale)
            resized = img.resize((nw, nh), Image.LANCZOS)
            left = max((nw - tw) // 2, 0)
            top = max((nh - th) // 2, 0)
            return resized.crop((left, top, left + tw, top + th))

        def _redraw_bg_stats(event=None):
            if not self._bg_stats_src:
                return
            w, h = self.stats_tab.winfo_width(), self.stats_tab.winfo_height()
            if w < 2 or h < 2:
                return
            img = _img_cover_stats(self._bg_stats_src, (w, h))
            self._bg_stats_photo = ImageTk.PhotoImage(img)
            self._bg_stats_label.config(image=self._bg_stats_photo)

        self.stats_tab.bind("<Configure>", _redraw_bg_stats)

        # ==== ẢNH NỀN CHO TAB TIMER ====
        bg_file = resource_path("assets/bg.jpg")  # đổi theo tên ảnh của cậu
        try:
            self._bg_src = Image.open(bg_file)
        except Exception as e:
            self._bg_src = None
            print("Không load được ảnh nền:", e)

        self._bg_label = tk.Label(self.timer_tab, bd=0, highlightthickness=0)
        self._bg_label.place(relx=0, rely=0, relwidth=1, relheight=1)

        def _img_cover(img, target_size):
            tw, th = target_size
            iw, ih = img.size
            scale = max(tw / iw, th / ih)
            nw, nh = int(iw * scale), int(ih * scale)
            resized = img.resize((nw, nh), Image.LANCZOS)
            left = max((nw - tw) // 2, 0)
            top = max((nh - th) // 2, 0)
            return resized.crop((left, top, left + tw, top + th))

        def _redraw_bg(event=None):
            if not self._bg_src:
                return
            w, h = self.timer_tab.winfo_width(), self.timer_tab.winfo_height()
            if w < 2 or h < 2:
                return
            img = _img_cover(self._bg_src, (w, h))
            self._bg_photo = ImageTk.PhotoImage(img)
            self._bg_label.config(image=self._bg_photo)

        self.timer_tab.bind("<Configure>", _redraw_bg)

        # Khung nội dung đè lên nền
        self.timer_content = ttk.Frame(self.timer_tab, padding=12)
        self.timer_content.place(relx=0.5, rely=0.5, anchor="center")
        self.timer_content.tkraise()

        # --- Timer tab layout ---
        outer = ttk.Frame(self.timer_content, padding=12)
        outer.pack(fill="both", expand=True)

        # Mode selector
        mode_frame = ttk.LabelFrame(outer, text="Mode")
        mode_frame.pack(fill="x")
        for i, label in enumerate(self.modes.keys()):
            ttk.Radiobutton(
                mode_frame,
                text=label,
                value=label,
                variable=self.mode_var,
                command=self._on_change_mode,
            ).grid(row=0, column=i, padx=6, pady=6, sticky="w")

        # Phase label
        self.phase_label = ttk.Label(outer, text="Focus", font=("Segoe UI", 12, "bold"))
        self.phase_label.pack(pady=(10, 2))

        # Big timer
        self.time_label = ttk.Label(outer, text="25:00", font=("Segoe UI", 46, "bold"))
        self.time_label.pack(pady=(0, 8))

        # Next up label
        self.next_label = ttk.Label(outer, text="Next: Break 5 min", font=("Segoe UI", 10))
        self.next_label.pack(pady=(0, 10))

        # Controls
        controls = ttk.Frame(outer)
        controls.pack(pady=6)
        self.start_btn = ttk.Button(controls, text="Start", command=self.start)
        self.pause_btn = ttk.Button(controls, text="Pause", command=self.pause, state="disabled")
        self.reset_btn = ttk.Button(controls, text="Reset", command=self.reset)
        self.start_btn.grid(row=0, column=0, padx=6)
        self.pause_btn.grid(row=0, column=1, padx=6)
        self.reset_btn.grid(row=0, column=2, padx=6)

        # Footer row: sound + sessions + YouTube playlist opener
        footer = ttk.Frame(outer)
        footer.pack(fill="x", side="bottom", pady=(10, 0))

        ttk.Checkbutton(footer, text="Sound", variable=self.sound_enabled).pack(side="left")
        ttk.Checkbutton(footer, text="Music", variable=self.music_enabled, command=self._toggle_music).pack(side="left", padx=(8,0))

        self.counter_label = ttk.Label(footer, text="Focus sessions (runtime): 0")
        self.counter_label.pack(side="right")

        # Playlist controls
        pl_frame = ttk.LabelFrame(outer, text="YouTube Playlist (Optional)")
        pl_frame.pack(fill="x", pady=(12, 0))
        ttk.Label(pl_frame, text="URL:").grid(row=0, column=0, padx=6, pady=6, sticky="w")
        self.playlist_entry = ttk.Entry(pl_frame, textvariable=self.playlist_var)
        self.playlist_entry.grid(row=0, column=1, padx=6, pady=6, sticky="we")
        pl_frame.columnconfigure(1, weight=1)
        ttk.Button(pl_frame, text="Open in Browser", command=self._open_playlist).grid(row=0, column=2, padx=6, pady=6)
        ttk.Button(pl_frame, text="Save", command=self._save_playlist_setting).grid(row=0, column=3, padx=6, pady=6)

        # --- Stats tab layout ---
        self.stats_content = ttk.Frame(self.stats_tab, padding=8)
        self.stats_content.place(relx=0.5, rely=0.5, anchor="center")
        self.stats_content.tkraise()

        stats_outer = ttk.Frame(self.stats_content, padding=8)

        stats_outer.pack(fill="both", expand=True)

        top_row = ttk.Frame(stats_outer)
        top_row.pack(fill="x")
        ttk.Label(top_row, text="Study Heatmap (last 90 days)", font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(top_row, text="Refresh", command=self._render_heatmap).pack(side="right")

        self.heatmap_area = ttk.Frame(stats_outer)
        self.heatmap_area.pack(fill="both", expand=True, pady=(6, 0))
        self._render_heatmap()

        # Style
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

    # ----------------- Playlist helpers -----------------
    def _save_playlist_setting(self):
        url = self.playlist_var.get().strip()
        self.data.setdefault("settings", {})["playlist_url"] = url
        self._save_data()
        messagebox.showinfo(APP_NAME, "Saved playlist URL.")

    def _open_playlist(self):
        url = self.playlist_var.get().strip()
        if not url:
            messagebox.showwarning(APP_NAME, "Please paste a YouTube playlist or video URL first.")
            return
        try:
            webbrowser.open(url)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Failed to open URL: {e}")

    # ----------------- Timer logic -----------------
    def _phase_duration_secs(self):
        focus_m, break_m = self.modes[self.mode_var.get()]
        return (focus_m * 60) if self.phase == "focus" else (break_m * 60)

    def _on_change_mode(self):
        if not self.running:
            self.remaining_secs = self._phase_duration_secs()
            self._update_labels()

    def start(self):
        if self.running:
            return
        self.running = True
        self.start_ts = time.monotonic()
        self.start_btn.config(state="disabled")
        self.pause_btn.config(state="normal")
        self._tick()

    def pause(self):
        if not self.running:
            return
        self.running = False
        now = time.monotonic()
        dt_elapsed = now - (self.start_ts or now)
        self.remaining_secs = max(0, int(round(self.remaining_secs - dt_elapsed)))
        self.start_btn.config(state="normal")
        self.pause_btn.config(state="disabled")

    def reset(self):
        self.running = False
        self.phase = "focus"
        self.remaining_secs = self._phase_duration_secs()
        self.start_btn.config(state="normal")
        self.pause_btn.config(state="disabled")
        self._update_labels()

    def _tick(self):
        if not self.running:
            return
        now = time.monotonic()
        dt_elapsed = now - (self.start_ts or now)
        secs_left = int(round(self.remaining_secs - dt_elapsed))
        if secs_left <= 0:
            # Phase finished
            self.running = False
            self.start_btn.config(state="normal")
            self.pause_btn.config(state="disabled")

            if self.sound_enabled.get():
                play_beep(self.root)

            if self.phase == "focus":
                self.completed_focus_sessions += 1
                focus_m, _ = self.modes[self.mode_var.get()]
                self._log_focus_session(minutes=focus_m)
                self.phase = "break"
                notify("Focus done!", f"Great job. Time for a {self.modes[self.mode_var.get()][1]}-min break.")
            else:
                self.phase = "focus"
                notify("Break over", f"Back to focus: {self.modes[self.mode_var.get()][0]} minutes.")

            self.remaining_secs = self._phase_duration_secs()
            self._update_labels()
            self.root.after(500, self.start)  # auto-start next phase after short gap
            return
        else:
            # Keep ticking
            self.time_label.config(text=self._format_secs(secs_left))
            self.root.after(200, self._tick)

    def _update_labels(self):
        self.phase_label.config(text="Focus" if self.phase == "focus" else "Break")
        self.time_label.config(text=self._format_secs(self.remaining_secs))
        focus_m, break_m = self.modes[self.mode_var.get()]
        if self.phase == "focus":
            self.next_label.config(text=f"Next: Break {break_m} min")
        else:
            self.next_label.config(text=f"Next: Focus {focus_m} min")
        self.counter_label.config(text=f"Focus sessions (runtime): {self.completed_focus_sessions}")

    def _update_clock(self):
        if not self.running:
            self.time_label.config(text=self._format_secs(self.remaining_secs))
        self.root.after(500, self._update_clock)

    # ----------------- Heatmap -----------------
    def _render_heatmap(self, auto_size=True):
        # Clear previous canvas
        for w in self.heatmap_area.winfo_children():
            w.destroy()

        # Build 7 x weeks matrix for last 90 days
        days_map = self.data.get("days", {})
        today = dt.date.today()
        start_date = today - dt.timedelta(days=89)  # 90-day window
        # Align columns to Monday-start week
        first_monday = start_date - dt.timedelta(days=start_date.weekday())
        weeks = ((today - first_monday).days // 7) + 1
        heat = np.zeros((7, weeks), dtype=int)

        # Fill
        d = start_date
        while d <= today:
            key = d.isoformat()
            val = days_map.get(key, {}).get("focus_sessions", 0)
            row = d.weekday()  # 0=Mon..6=Sun
            col = (d - first_monday).days // 7
            heat[row, col] = val
            d += dt.timedelta(days=1)

        # Plot
        fig_w = max(6, weeks * 0.35)  # scale width by weeks
        fig_h = 2.8
        fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=100)
        im = ax.imshow(heat, aspect="auto", interpolation="none", cmap="Greens", origin="upper")
        ax.set_yticks(range(7))
        ax.set_yticklabels(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], fontsize=8)
        ax.set_xticks([])
        ax.set_title("Focus sessions / day (last 90 days)", fontsize=10)
        ax.grid(False)
        for spine in ax.spines.values():
            spine.set_visible(False)
        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.ax.set_ylabel("sessions", rotation=270, labelpad=10)

        canvas = FigureCanvasTkAgg(fig, master=self.heatmap_area)
        canvas.draw()
        widget = canvas.get_tk_widget()
        widget.pack(fill="both", expand=True)

        if auto_size:
            self.root.update_idletasks()

    # ----------------- Utils -----------------
    @staticmethod
    def _format_secs(secs: int) -> str:
        secs = int(max(0, secs))
        m, s = divmod(secs, 60)
        return f"{m:02d}:{s:02d}"


if __name__ == "__main__":
    root = tk.Tk()
    app = PomodoroApp(root)
    root.mainloop()
