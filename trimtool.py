"""
TrimTool - Batch Video Trimmer
A minimal tool for trimming multiple videos simultaneously.
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox
import subprocess
import threading
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional, Callable
import re


# ============================================================================
# CONFIGURATION & STYLING
# ============================================================================

# Minimal monochrome palette with cyan accent
COLORS = {
    "bg": "#0a0a0a",
    "surface": "#141414",
    "surface_hover": "#1a1a1a",
    "border": "#252525",
    "text": "#ffffff",
    "text_dim": "#666666",
    "accent": "#00d4aa",
    "accent_dim": "#00a88a",
    "danger": "#ff4444",
    "warning": "#ffaa00",
}

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class VideoFile:
    """Represents a video file to be processed."""
    path: str
    filename: str
    duration: Optional[float] = None
    status: str = "pending"
    progress: float = 0.0
    error_message: str = ""
    output_path: str = ""


# ============================================================================
# FFMPEG UTILITIES
# ============================================================================

def find_ffmpeg() -> Optional[str]:
    """Find FFmpeg executable."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        if result.returncode == 0:
            return "ffmpeg"
    except FileNotFoundError:
        pass
    
    if os.name == 'nt':
        common_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
            os.path.expanduser(r"~\ffmpeg\bin\ffmpeg.exe"),
        ]
        for path in common_paths:
            if os.path.exists(path):
                return path
    
    return None


def get_video_duration(filepath: str, ffmpeg_path: str = "ffmpeg") -> Optional[float]:
    """Get the duration of a video file in seconds."""
    ffprobe = ffmpeg_path.replace("ffmpeg", "ffprobe")
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", filepath],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except (ValueError, FileNotFoundError):
        pass
    return None


def get_video_bitrates(filepath: str, ffmpeg_path: str = "ffmpeg") -> tuple[Optional[int], Optional[int]]:
    """Get the video and audio bitrates of a file in bits/second."""
    ffprobe = ffmpeg_path.replace("ffmpeg", "ffprobe")
    video_bitrate = None
    audio_bitrate = None
    
    try:
        # Get video bitrate
        result = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=bit_rate",
             "-of", "default=noprint_wrappers=1:nokey=1", filepath],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        if result.returncode == 0 and result.stdout.strip().isdigit():
            video_bitrate = int(result.stdout.strip())
        
        # If stream bitrate not available, try format bitrate
        if not video_bitrate:
            result = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=bit_rate",
                 "-of", "default=noprint_wrappers=1:nokey=1", filepath],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if result.returncode == 0 and result.stdout.strip().isdigit():
                video_bitrate = int(result.stdout.strip())
        
        # Get audio bitrate
        result = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=bit_rate",
             "-of", "default=noprint_wrappers=1:nokey=1", filepath],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        if result.returncode == 0 and result.stdout.strip().isdigit():
            audio_bitrate = int(result.stdout.strip())
            
    except (ValueError, FileNotFoundError):
        pass
    
    return video_bitrate, audio_bitrate


@dataclass
class ProgressInfo:
    """Progress information from FFmpeg."""
    percent: float = 0.0
    speed: str = ""
    fps: str = ""
    time_str: str = ""


def trim_video_smart(
    input_path: str,
    output_path: str,
    start_time: float,
    end_time: Optional[float],
    ffmpeg_path: str = "ffmpeg",
    progress_callback: Optional[Callable[[ProgressInfo], None]] = None
) -> tuple[bool, str]:
    """
    Smart trim: Uses ultrafast encoding for speed with accurate cuts.
    Much faster than 'full' but guarantees clean output.
    """
    
    # Get original bitrates to match quality
    video_br, audio_br = get_video_bitrates(input_path, ffmpeg_path)
    
    # Build command: input seeking + ultrafast encode
    # -ss before -i = fast seek to nearest keyframe
    # ultrafast preset = very fast encoding, ~5-10x faster than 'medium'
    cmd = [ffmpeg_path, "-y", "-ss", str(start_time), "-i", input_path]
    
    if end_time is not None:
        cmd.extend(["-t", str(end_time - start_time)])
    
    # Use ultrafast preset for speed, copy audio for extra speed
    cmd.extend(["-c:v", "libx264", "-preset", "ultrafast"])
    
    if video_br:
        # Use slightly higher bitrate to compensate for ultrafast's lower efficiency
        cmd.extend(["-b:v", str(int(video_br * 1.2))])
    else:
        cmd.extend(["-crf", "20"])  # Slightly higher quality for ultrafast
    
    # Copy audio instead of re-encoding (much faster)
    cmd.extend(["-c:a", "copy"])
    
    cmd.extend(["-movflags", "+faststart", output_path])
    
    try:
        total_duration = get_video_duration(input_path, ffmpeg_path)
        if end_time and total_duration:
            total_duration = min(end_time - start_time, total_duration - start_time)
        elif total_duration:
            total_duration = total_duration - start_time
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        stderr_data = []
        progress_info = ProgressInfo()
        last_percent = [0.0]
        
        def read_stderr():
            while True:
                chunk = process.stderr.read(256)
                if not chunk:
                    break
                stderr_data.append(chunk.decode('utf-8', errors='ignore'))
        
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stderr_thread.start()
        
        import time
        while process.poll() is None:
            time.sleep(0.15)
            
            if stderr_data and total_duration and progress_callback:
                all_output = "".join(stderr_data[-50:])
                
                time_matches = re.findall(r'time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})', all_output)
                if time_matches:
                    h, m, s, cs = map(int, time_matches[-1])
                    current_time = h * 3600 + m * 60 + s + cs / 100
                    progress_info.percent = min(current_time / total_duration * 100, 99.9)
                
                speed_matches = re.findall(r'speed=\s*([\d.]+)x', all_output)
                if speed_matches:
                    progress_info.speed = f"{speed_matches[-1]}x"
                
                if progress_info.percent > last_percent[0] + 0.3:
                    last_percent[0] = progress_info.percent
                    progress_callback(progress_info)
        
        stderr_thread.join(timeout=2.0)
        
        if process.returncode == 0:
            if progress_callback:
                progress_info.percent = 100
                progress_callback(progress_info)
            return True, ""
        else:
            return False, "".join(stderr_data[-20:])
            
    except Exception as e:
        return False, str(e)


def trim_video(
    input_path: str,
    output_path: str,
    start_time: float,
    end_time: Optional[float],
    ffmpeg_path: str = "ffmpeg",
    re_encode: str = "fast",  # "fast", "smart", or "full"
    progress_callback: Optional[Callable[[ProgressInfo], None]] = None
) -> tuple[bool, str]:
    """Trim a video file."""
    
    # Fast mode: ultrafast encoding (quick + reliable)
    if re_encode == "fast":
        return trim_video_smart(input_path, output_path, start_time, end_time,
                                ffmpeg_path, progress_callback)
    
    if re_encode == "slow":
        # Get original bitrates to match quality
        video_br, audio_br = get_video_bitrates(input_path, ffmpeg_path)
        
        cmd = [ffmpeg_path, "-y", "-ss", str(start_time), "-i", input_path]
        if end_time is not None:
            cmd.extend(["-t", str(end_time - start_time)])
        
        # Video encoding - match original bitrate
        cmd.extend(["-c:v", "libx264", "-preset", "medium"])
        if video_br:
            cmd.extend(["-b:v", str(video_br)])
        else:
            # Fallback to CRF if bitrate unknown
            cmd.extend(["-crf", "23"])
        
        # Audio encoding - match original bitrate
        cmd.extend(["-c:a", "aac"])
        if audio_br:
            cmd.extend(["-b:a", str(audio_br)])
        else:
            cmd.extend(["-b:a", "128k"])
        
        cmd.extend(["-movflags", "+faststart", output_path])
    else:
        # Fast stream copy
        cmd = [ffmpeg_path, "-y", "-ss", str(start_time), "-i", input_path]
        if end_time is not None:
            cmd.extend(["-t", str(end_time - start_time)])
        cmd.extend(["-c", "copy", "-avoid_negative_ts", "make_zero", output_path])
    
    try:
        total_duration = get_video_duration(input_path, ffmpeg_path)
        if end_time and total_duration:
            total_duration = min(end_time - start_time, total_duration - start_time)
        elif total_duration:
            total_duration = total_duration - start_time
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        stderr_data = []
        progress_info = ProgressInfo()
        last_percent = [0.0]
        
        # Read stderr byte by byte to catch \r-delimited progress updates
        def read_stderr():
            buffer = ""
            while True:
                chunk = process.stderr.read(256)
                if not chunk:
                    break
                text = chunk.decode('utf-8', errors='ignore')
                buffer += text
                stderr_data.append(text)
                
                # Keep buffer manageable
                if len(buffer) > 2000:
                    buffer = buffer[-1000:]
        
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stderr_thread.start()
        
        # Parse progress from accumulated stderr
        import time
        while process.poll() is None:
            time.sleep(0.15)
            
            if stderr_data and total_duration and progress_callback:
                # Join all stderr data and look for progress
                all_output = "".join(stderr_data[-50:])
                
                # Parse time (look for last occurrence)
                time_matches = re.findall(r'time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})', all_output)
                if time_matches:
                    h, m, s, cs = map(int, time_matches[-1])
                    current_time = h * 3600 + m * 60 + s + cs / 100
                    progress_info.percent = min(current_time / total_duration * 100, 99.9)
                    progress_info.time_str = f"{int(current_time//60)}:{int(current_time%60):02d}"
                
                # Parse speed (last occurrence)
                speed_matches = re.findall(r'speed=\s*([\d.]+)x', all_output)
                if speed_matches:
                    progress_info.speed = f"{speed_matches[-1]}x"
                
                # Parse fps (last occurrence)
                fps_matches = re.findall(r'fps=\s*([\d.]+)', all_output)
                if fps_matches:
                    progress_info.fps = f"{fps_matches[-1]} fps"
                
                # Callback on meaningful progress change
                if progress_info.percent > last_percent[0] + 0.3:
                    last_percent[0] = progress_info.percent
                    progress_callback(progress_info)
        
        stderr_thread.join(timeout=2.0)
        
        if process.returncode == 0:
            if progress_callback:
                progress_info.percent = 100
                progress_callback(progress_info)
            return True, ""
        else:
            return False, "".join(stderr_data[-20:])
            
    except Exception as e:
        return False, str(e)


# ============================================================================
# UI COMPONENTS
# ============================================================================

class VideoRow(ctk.CTkFrame):
    """Minimal video row with progress tracking."""
    
    def __init__(self, parent, video: VideoFile, on_remove: Callable):
        super().__init__(parent, fg_color="transparent", height=48)
        
        self.video = video
        self.grid_columnconfigure(1, weight=1)
        
        # Status dot
        self.dot = ctk.CTkLabel(
            self, text="○", width=20,
            font=("Arial", 14),
            text_color=COLORS["text_dim"]
        )
        self.dot.grid(row=0, column=0, padx=(0, 12))
        
        # Filename
        self.name = ctk.CTkLabel(
            self,
            text=video.filename,
            font=("SF Mono", 13) if os.name == 'darwin' else ("Consolas", 12),
            text_color=COLORS["text"],
            anchor="w"
        )
        self.name.grid(row=0, column=1, sticky="w")
        
        # Duration / Status info
        self.duration_label = ctk.CTkLabel(
            self,
            text="—",
            font=("SF Mono", 11) if os.name == 'darwin' else ("Consolas", 10),
            text_color=COLORS["text_dim"],
            width=70
        )
        self.duration_label.grid(row=0, column=2, padx=(16, 8))
        
        # Progress container (bar + percentage + speed)
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.grid(row=0, column=3, padx=(8, 16))
        self.progress_frame.grid_remove()
        
        # Progress bar
        self.progress = ctk.CTkProgressBar(
            self.progress_frame, width=100, height=4,
            fg_color=COLORS["border"],
            progress_color=COLORS["accent"]
        )
        self.progress.set(0)
        self.progress.grid(row=0, column=0, pady=(0, 2))
        
        # Progress info (percentage + speed)
        self.progress_label = ctk.CTkLabel(
            self.progress_frame,
            text="0%",
            font=("SF Mono", 10) if os.name == 'darwin' else ("Consolas", 9),
            text_color=COLORS["text_dim"],
            anchor="w"
        )
        self.progress_label.grid(row=1, column=0, sticky="w")
        
        # Remove button
        self.remove_btn = ctk.CTkButton(
            self, text="×", width=28, height=28,
            font=("Arial", 16),
            fg_color="transparent",
            hover_color=COLORS["surface_hover"],
            text_color=COLORS["text_dim"],
            command=lambda: on_remove(video)
        )
        self.remove_btn.grid(row=0, column=4)
        
        self._original_duration = None
    
    def set_duration(self, duration: float):
        self._original_duration = duration
        self.duration_label.configure(text=f"{duration:.1f}s")
    
    def set_status(self, status: str):
        if status == "processing":
            self.dot.configure(text="◐", text_color=COLORS["warning"])
            self.duration_label.configure(text="encoding...")
            self.progress_frame.grid()
            self.progress.set(0)
            self.progress_label.configure(text="0%")
        elif status == "completed":
            self.dot.configure(text="●", text_color=COLORS["accent"])
            self.duration_label.configure(text="done")
            self.progress_frame.grid_remove()
        elif status == "error":
            self.dot.configure(text="●", text_color=COLORS["danger"])
            self.duration_label.configure(text="failed")
            self.progress_frame.grid_remove()
        else:
            self.dot.configure(text="○", text_color=COLORS["text_dim"])
            if self._original_duration:
                self.duration_label.configure(text=f"{self._original_duration:.1f}s")
            self.progress_frame.grid_remove()
    
    def set_progress(self, info: 'ProgressInfo'):
        self.progress.set(info.percent / 100)
        
        # Build progress text
        parts = [f"{info.percent:.0f}%"]
        if info.speed and info.speed != "N/A":
            parts.append(info.speed)
        elif info.fps:
            parts.append(info.fps)
        
        self.progress_label.configure(text=" · ".join(parts))


class TrimToolApp(ctk.CTk):
    """Main application."""
    
    def __init__(self):
        super().__init__()
        
        self.title("TrimTool")
        self.geometry("720x600")
        self.minsize(600, 400)
        self.configure(fg_color=COLORS["bg"])
        
        self.videos: list[VideoFile] = []
        self.video_rows: dict[str, VideoRow] = {}
        self.ffmpeg_path = find_ffmpeg()
        self.is_processing = False
        
        self._build_ui()
        self._check_ffmpeg()
    
    def _check_ffmpeg(self):
        if not self.ffmpeg_path:
            self.status.configure(text="FFmpeg not found", text_color=COLORS["danger"])
            self.start_btn.configure(state="disabled")
    
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=32, pady=(32, 24))
        header.grid_columnconfigure(1, weight=1)
        
        title = ctk.CTkLabel(
            header, text="TrimTool",
            font=("Helvetica Neue", 24, "bold") if os.name == 'darwin' else ("Segoe UI", 22, "bold"),
            text_color=COLORS["text"]
        )
        title.grid(row=0, column=0, sticky="w")
        
        # Header buttons
        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.grid(row=0, column=2)
        
        self.clear_btn = ctk.CTkButton(
            btn_frame, text="Clear",
            font=("Helvetica Neue", 13) if os.name == 'darwin' else ("Segoe UI", 12),
            fg_color="transparent",
            hover_color=COLORS["surface_hover"],
            text_color=COLORS["text_dim"],
            width=60, height=32,
            command=self._clear_all
        )
        self.clear_btn.grid(row=0, column=0, padx=(0, 8))
        
        self.add_btn = ctk.CTkButton(
            btn_frame, text="+ Add",
            font=("Helvetica Neue", 13, "bold") if os.name == 'darwin' else ("Segoe UI", 12, "bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["bg"],
            width=80, height=32,
            corner_radius=6,
            command=self._add_videos
        )
        self.add_btn.grid(row=0, column=1)
        
        # Settings bar
        settings = ctk.CTkFrame(self, fg_color=COLORS["surface"], corner_radius=8)
        settings.grid(row=1, column=0, sticky="ew", padx=32, pady=(0, 16))
        
        # Mode selector
        mode_frame = ctk.CTkFrame(settings, fg_color="transparent")
        mode_frame.pack(side="left", padx=16, pady=12)
        
        mode_label = ctk.CTkLabel(
            mode_frame, text="Mode",
            font=("Helvetica Neue", 11) if os.name == 'darwin' else ("Segoe UI", 10),
            text_color=COLORS["text_dim"]
        )
        mode_label.pack(anchor="w")
        
        self.mode = ctk.CTkSegmentedButton(
            mode_frame,
            values=["Skip Start", "Skip End", "Range"],
            font=("Helvetica Neue", 12) if os.name == 'darwin' else ("Segoe UI", 11),
            fg_color=COLORS["bg"],
            selected_color=COLORS["border"],
            selected_hover_color=COLORS["surface_hover"],
            unselected_color=COLORS["bg"],
            unselected_hover_color=COLORS["surface_hover"],
            text_color=COLORS["text"],
            corner_radius=4,
            command=self._on_mode_change
        )
        self.mode.set("Skip Start")
        self.mode.pack(pady=(4, 0))
        
        # Time input
        time_frame = ctk.CTkFrame(settings, fg_color="transparent")
        time_frame.pack(side="left", padx=16, pady=12)
        
        self.time_label = ctk.CTkLabel(
            time_frame, text="Seconds",
            font=("Helvetica Neue", 11) if os.name == 'darwin' else ("Segoe UI", 10),
            text_color=COLORS["text_dim"]
        )
        self.time_label.pack(anchor="w")
        
        time_input_frame = ctk.CTkFrame(time_frame, fg_color="transparent")
        time_input_frame.pack(pady=(4, 0))
        
        self.time_entry = ctk.CTkEntry(
            time_input_frame, width=60, height=28,
            font=("SF Mono", 12) if os.name == 'darwin' else ("Consolas", 11),
            fg_color=COLORS["bg"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=4
        )
        self.time_entry.insert(0, "10")
        self.time_entry.pack(side="left")
        
        self.end_label = ctk.CTkLabel(
            time_input_frame, text="to",
            font=("Helvetica Neue", 12) if os.name == 'darwin' else ("Segoe UI", 11),
            text_color=COLORS["text_dim"]
        )
        self.end_entry = ctk.CTkEntry(
            time_input_frame, width=60, height=28,
            font=("SF Mono", 12) if os.name == 'darwin' else ("Consolas", 11),
            fg_color=COLORS["bg"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=4
        )
        self.end_entry.insert(0, "30")
        # Hidden by default
        self.end_label.pack(side="left", padx=8)
        self.end_entry.pack(side="left")
        self.end_label.pack_forget()
        self.end_entry.pack_forget()
        
        # Encoding mode selector
        encode_frame = ctk.CTkFrame(settings, fg_color="transparent")
        encode_frame.pack(side="right", padx=16, pady=12)
        
        encode_label = ctk.CTkLabel(
            encode_frame, text="Encoding",
            font=("Helvetica Neue", 11) if os.name == 'darwin' else ("Segoe UI", 10),
            text_color=COLORS["text_dim"]
        )
        encode_label.pack(anchor="e")
        
        self.encode_mode = ctk.CTkSegmentedButton(
            encode_frame,
            values=["Instant", "Fast", "Slow"],
            font=("Helvetica Neue", 11) if os.name == 'darwin' else ("Segoe UI", 10),
            fg_color=COLORS["bg"],
            selected_color=COLORS["border"],
            selected_hover_color=COLORS["surface_hover"],
            unselected_color=COLORS["bg"],
            unselected_hover_color=COLORS["surface_hover"],
            text_color=COLORS["text"],
            corner_radius=4,
            command=self._on_encode_mode_change
        )
        self.encode_mode.set("Instant")
        self.encode_mode.pack(pady=(4, 0))
        
        # Quality description
        self.encode_desc = ctk.CTkLabel(
            encode_frame,
            text="May glitch at cut",
            font=("Helvetica Neue", 9) if os.name == 'darwin' else ("Segoe UI", 8),
            text_color=COLORS["text_dim"]
        )
        self.encode_desc.pack(anchor="e", pady=(2, 0))
        
        # Video list
        list_frame = ctk.CTkFrame(self, fg_color="transparent")
        list_frame.grid(row=2, column=0, sticky="nsew", padx=32)
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)
        
        self.video_list = ctk.CTkScrollableFrame(
            list_frame,
            fg_color="transparent",
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["text_dim"]
        )
        self.video_list.grid(row=0, column=0, sticky="nsew")
        self.video_list.grid_columnconfigure(0, weight=1)
        
        # Empty state
        self.empty = ctk.CTkLabel(
            self.video_list,
            text="Drop videos here or click + Add",
            font=("Helvetica Neue", 14) if os.name == 'darwin' else ("Segoe UI", 13),
            text_color=COLORS["text_dim"]
        )
        self.empty.grid(row=0, column=0, pady=80)
        
        # Footer
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=32, pady=24)
        footer.grid_columnconfigure(1, weight=1)
        
        # Output folder
        out_frame = ctk.CTkFrame(footer, fg_color="transparent")
        out_frame.grid(row=0, column=0, sticky="w")
        
        out_label = ctk.CTkLabel(
            out_frame, text="Output",
            font=("Helvetica Neue", 11) if os.name == 'darwin' else ("Segoe UI", 10),
            text_color=COLORS["text_dim"]
        )
        out_label.pack(anchor="w")
        
        out_input = ctk.CTkFrame(out_frame, fg_color="transparent")
        out_input.pack(pady=(4, 0))
        
        self.output_entry = ctk.CTkEntry(
            out_input, width=200, height=28,
            font=("Helvetica Neue", 12) if os.name == 'darwin' else ("Segoe UI", 11),
            fg_color=COLORS["surface"],
            border_width=0,
            corner_radius=4,
            placeholder_text="Same folder (_trimmed)"
        )
        self.output_entry.pack(side="left")
        
        browse_btn = ctk.CTkButton(
            out_input, text="…", width=28, height=28,
            font=("Arial", 14),
            fg_color=COLORS["surface"],
            hover_color=COLORS["surface_hover"],
            text_color=COLORS["text_dim"],
            corner_radius=4,
            command=self._browse_output
        )
        browse_btn.pack(side="left", padx=(4, 0))
        
        # Status
        self.status = ctk.CTkLabel(
            footer, text="Ready",
            font=("Helvetica Neue", 12) if os.name == 'darwin' else ("Segoe UI", 11),
            text_color=COLORS["text_dim"]
        )
        self.status.grid(row=0, column=1)
        
        # Start button
        self.start_btn = ctk.CTkButton(
            footer, text="Start",
            font=("Helvetica Neue", 14, "bold") if os.name == 'darwin' else ("Segoe UI", 13, "bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["bg"],
            width=100, height=36,
            corner_radius=6,
            command=self._start
        )
        self.start_btn.grid(row=0, column=2)
        
        # Setup DnD
        self._setup_dnd()
    
    def _setup_dnd(self):
        try:
            self.drop_target_register("DND_Files")
            self.dnd_bind("<<Drop>>", self._on_drop)
        except:
            pass
    
    def _on_mode_change(self, mode: str):
        if mode == "Range":
            self.time_label.configure(text="From")
            self.end_label.pack(side="left", padx=8)
            self.end_entry.pack(side="left")
        else:
            self.time_label.configure(text="Seconds")
            self.end_label.pack_forget()
            self.end_entry.pack_forget()
    
    def _on_encode_mode_change(self, mode: str):
        descriptions = {
            "Instant": "May glitch at cut",
            "Fast": "Good quality",
            "Slow": "Best quality"
        }
        self.encode_desc.configure(text=descriptions.get(mode, ""))
    
    def _browse_output(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_entry.delete(0, "end")
            self.output_entry.insert(0, folder)
    
    def _add_videos(self):
        files = filedialog.askopenfilenames(
            filetypes=[("Video files", "*.mp4 *.mkv *.avi *.mov *.webm *.m4v *.wmv *.flv")]
        )
        for f in files:
            self._add_file(f)
    
    def _on_drop(self, event):
        files = self.tk.splitlist(event.data)
        for f in files:
            if f.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v', '.wmv', '.flv')):
                self._add_file(f)
    
    def _add_file(self, path: str):
        if any(v.path == path for v in self.videos):
            return
        
        self.empty.grid_remove()
        
        video = VideoFile(path=path, filename=os.path.basename(path))
        self.videos.append(video)
        
        row = VideoRow(self.video_list, video, self._remove_video)
        row.grid(row=len(self.videos) - 1, column=0, sticky="ew", pady=4)
        self.video_rows[path] = row
        
        if self.ffmpeg_path:
            threading.Thread(target=self._load_duration, args=(video,), daemon=True).start()
        
        self._update_status()
    
    def _load_duration(self, video: VideoFile):
        duration = get_video_duration(video.path, self.ffmpeg_path)
        if duration:
            video.duration = duration
            self.after(0, lambda: self.video_rows[video.path].set_duration(duration))
    
    def _remove_video(self, video: VideoFile):
        if video.status == "processing":
            return
        
        self.videos.remove(video)
        self.video_rows.pop(video.path).destroy()
        
        for i, v in enumerate(self.videos):
            self.video_rows[v.path].grid(row=i, column=0, sticky="ew", pady=4)
        
        if not self.videos:
            self.empty.grid()
        
        self._update_status()
    
    def _clear_all(self):
        if self.is_processing:
            return
        
        for row in self.video_rows.values():
            row.destroy()
        
        self.videos.clear()
        self.video_rows.clear()
        self.empty.grid()
        self._update_status()
    
    def _update_status(self):
        if not self.is_processing:
            n = len(self.videos)
            done = sum(1 for v in self.videos if v.status == "completed")
            self.status.configure(
                text=f"{n} video{'s' if n != 1 else ''}" + (f" · {done} done" if done else ""),
                text_color=COLORS["text_dim"]
            )
    
    def _get_times(self) -> tuple[float, Optional[float]]:
        mode = self.mode.get()
        val = float(self.time_entry.get() or 0)
        
        if mode == "Skip Start":
            return val, None
        elif mode == "Skip End":
            return 0, -val
        else:
            return val, float(self.end_entry.get() or 0)
    
    def _start(self):
        if not self.videos or self.is_processing:
            return
        
        if not self.ffmpeg_path:
            messagebox.showerror("Error", "FFmpeg not found")
            return
        
        try:
            start, end = self._get_times()
        except ValueError:
            messagebox.showerror("Error", "Invalid time values")
            return
        
        output = self.output_entry.get().strip() or None
        encode_mode = self.encode_mode.get().lower()  # "fast", "smart", or "full"
        
        self.is_processing = True
        self.start_btn.configure(state="disabled", text="...")
        self.add_btn.configure(state="disabled")
        self.clear_btn.configure(state="disabled")
        
        threading.Thread(
            target=self._process,
            args=(start, end, output, encode_mode),
            daemon=True
        ).start()
    
    def _process(self, start: float, end: Optional[float], output: Optional[str], encode_mode: str):
        for video in self.videos:
            if video.status in ("pending", "error"):
                video.status = "pending"
                video.progress = 0
        
        # Track overall progress
        to_process = [v for v in self.videos if v.status != "completed"]
        total_count = len(to_process)
        completed_count = [0]  # Use list to allow modification in nested function
        
        def get_overall_progress():
            """Calculate overall progress: completed videos + average of in-progress videos."""
            done = completed_count[0]
            processing_videos = [v for v in to_process if v.status == "processing"]
            
            if not processing_videos:
                return done / total_count * 100 if total_count > 0 else 0
            
            # Average progress of processing videos
            avg_progress = sum(v.progress for v in processing_videos) / len(processing_videos)
            
            # Overall = (completed + fraction of in-progress) / total
            overall = (done + len(processing_videos) * avg_progress / 100) / total_count * 100
            return overall
        
        def update_overall_status():
            done = completed_count[0]
            processing_count = sum(1 for v in to_process if v.status == "processing")
            
            if processing_count > 0:
                overall = get_overall_progress()
                self.after(0, lambda: self.status.configure(
                    text=f"Processing {done + processing_count}/{total_count} · {overall:.0f}%",
                    text_color=COLORS["text"]
                ))
        
        def do_one(video: VideoFile):
            if video.status == "completed":
                return
            
            video.status = "processing"
            self.after(0, lambda: self.video_rows[video.path].set_status("processing"))
            update_overall_status()
            
            actual_end = end
            if end is not None and end < 0 and video.duration:
                actual_end = video.duration + end
            
            if output:
                base = os.path.splitext(video.filename)[0]
                ext = os.path.splitext(video.filename)[1]
                video.output_path = os.path.join(output, f"{base}_trimmed{ext}")
            else:
                base, ext = os.path.splitext(video.path)
                video.output_path = f"{base}_trimmed{ext}"
            
            def on_progress(info: ProgressInfo):
                video.progress = info.percent
                self.after(0, lambda: self.video_rows[video.path].set_progress(info))
                # Update overall status with averaged progress
                update_overall_status()
            
            ok, err = trim_video(
                video.path, video.output_path,
                start, actual_end,
                self.ffmpeg_path, encode_mode, on_progress
            )
            
            video.status = "completed" if ok else "error"
            video.error_message = err
            completed_count[0] += 1
            self.after(0, lambda: self.video_rows[video.path].set_status(video.status))
            update_overall_status()
        
        # Process sequentially for better progress tracking (or parallel with max_workers=2)
        max_workers = 4 if encode_mode == "instant" else 2
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(do_one, v) for v in to_process]
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception as e:
                    print(e)
        
        self.after(0, self._done)
    
    def _done(self):
        self.is_processing = False
        self.start_btn.configure(state="normal", text="Start")
        self.add_btn.configure(state="normal")
        self.clear_btn.configure(state="normal")
        
        done = sum(1 for v in self.videos if v.status == "completed")
        errs = sum(1 for v in self.videos if v.status == "error")
        
        if errs:
            self.status.configure(text=f"Done · {errs} failed", text_color=COLORS["warning"])
        else:
            self.status.configure(text=f"✓ {done} trimmed", text_color=COLORS["accent"])


if __name__ == "__main__":
    app = TrimToolApp()
    app.mainloop()
