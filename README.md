# ✂️ TrimTool

A minimal batch video trimmer. Quickly remove intros, outros, or extract segments from multiple videos at once.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![FFmpeg](https://img.shields.io/badge/FFmpeg-Required-green)

## Features

- **Batch processing** — Trim multiple videos simultaneously
- **Three modes** — Skip Start, Skip End, or extract a Range
- **Two encoding options:**
  - **Fast mode** — Stream copy, instant but may cause playback glitches at cut points
  - **Re-encode** — Slower but guarantees clean playback, matches original quality
- **Real-time progress** — Per-video progress bar with percentage and encoding speed
- **Minimal dark UI** — Clean, distraction-free interface

## Requirements

- Python 3.10+
- FFmpeg (must be in PATH)

### Installing FFmpeg

**Windows:**
```
winget install FFmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Linux:**
```bash
sudo apt install ffmpeg
```

## Installation

```bash
cd trimtool
pip install -r requirements.txt
python trimtool.py
```

## Usage

1. Click **+ Add** or drag video files into the window
2. Select a **Mode**:
   - `Skip Start` — Remove first X seconds
   - `Skip End` — Remove last X seconds  
   - `Range` — Keep only from X to Y seconds
3. Enter the time in **seconds**
4. Choose **Encoding** mode
5. Click **Start**

### Encoding Modes

| Mode | Quality | Description |
|------|---------|-------------|
| **Instant** | May glitch | Stream copy — no re-encoding. Fastest but may glitch at cut. |
| **Fast** | Good | Ultrafast re-encoding. Clean output, quick processing. |
| **Slow** | Best | High-quality re-encoding. Best quality, takes longer. |

**Recommended:** Use **Fast** — it's quick and produces clean output.

**Why does Instant mode sometimes glitch?**

Instant mode copies video data directly without re-encoding. If the cut point doesn't land on a keyframe, the first few frames may be corrupted. Fast mode avoids this with quick re-encoding.

### Examples

| Task | Mode | Seconds |
|------|------|---------|
| Remove 10s intro | Skip Start | `10` |
| Remove 5s outro | Skip End | `5` |
| Keep only 0:30–1:00 | Range | `30` to `60` |

## Interface

```
○  video1.mp4                   45.2s
◐  video2.mp4                   encoding...
                                [████████░░] 78% · 1.2x
●  video3.mp4                   done
```

- `○` Pending (gray)
- `◐` Processing (yellow) — shows progress bar, %, and speed
- `●` Done (green) or Error (red)

## Troubleshooting

**FFmpeg not found**
```bash
ffmpeg -version  # Should show version info
```
If not, install FFmpeg and ensure it's in your system PATH.

**Video glitches at the start after trimming**

Switch from **Instant** to **Fast** mode. Fast re-encodes the video quickly to ensure clean output.

**Large output file size**

With **Slow** mode, TrimTool matches the original video's bitrate. If the original was high bitrate, the output will be too. This is expected behavior.

## License

MIT
