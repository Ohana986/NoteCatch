# /// script
# dependencies = []
# ///

"""audio-analyzer 共享工具模块。

输出按条目划分文件夹，每个录音的所有产物存放在同一目录下。

提供：
  - 步骤输出、子进程封装（含 TF/CUDA 噪音过滤）
  - 文件查找与路径解析
"""

import os
import sys
import subprocess

# ── 已知噪音关键词 (TensorFlow / CUDA / oneDNN 等) ──
_NOISE_KEYWORDS = [
    "WARNING", "external/", "tensorflow", "CUDA", "cuda",
    "Could not find", "Unable to register", "Skipping",
    "TensorRT", "oneDNN",
]


def is_noise(line: str) -> bool:
    """判断一行输出是否为已知噪音。"""
    return any(k in line for k in _NOISE_KEYWORDS)


def step(msg: str) -> None:
    """打印步骤标题。"""
    print(f"\n{'=' * 50}")
    print(f"  [{msg}]")
    print(f"{'=' * 50}")


def run_cmd(cmd: list[str], desc: str = "", timeout: int = 600):
    """执行子进程命令，自动过滤噪音输出。失败时打印过滤后的 stderr 并退出。"""
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        for line in result.stderr.split("\n"):
            if line.strip() and not is_noise(line):
                print(f"  {line}", file=sys.stderr)
        label = f" ({desc})" if desc else ""
        print(f"  ✗ 命令失败{label}", file=sys.stderr)
        sys.exit(1)
    for line in result.stdout.split("\n"):
        s = line.strip()
        if s and not is_noise(s):
            print(f"  {s}")
    return result


def find_wav(directory: str) -> str | None:
    """在目录的各个子文件夹中查找最新的原始录音。

    扫描 directory 下所有一级子目录，找不以 _vocals/_play/_mixed 结尾的 .wav 文件。
    """
    wavs = []
    for entry in os.listdir(directory):
        subdir = os.path.join(directory, entry)
        if not os.path.isdir(subdir):
            continue
        for f in os.listdir(subdir):
            if not f.endswith(".wav"):
                continue
            if any(x in f for x in ("_vocals", "_play", "_mixed")):
                continue
            wavs.append(os.path.join(subdir, f))
    if not wavs:
        return None
    wavs.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return wavs[0]


def resolve_paths(audio_path: str) -> dict:
    """根据音频文件路径，推导出所有产物路径（同目录下）。

    返回包含以下键的 dict:
        out_dir, basename, vocals, midi, play, mixed, seg_csv,
        pitch_csv, pitch_png, full_midi, pitch_csv_flat, pitch_png_flat, sheet_xml
    """
    audio_path = os.path.abspath(audio_path)
    out_dir = os.path.dirname(audio_path)
    basename = os.path.splitext(os.path.basename(audio_path))[0]

    return {
        "out_dir": out_dir,
        "basename": basename,
        "vocals": os.path.join(out_dir, f"{basename}_vocals.wav"),
        "midi": os.path.join(out_dir, f"{basename}_vocals_basic_pitch.mid"),
        "play": os.path.join(out_dir, f"{basename}_vocals_play.wav"),
        "mixed": os.path.join(out_dir, f"{basename}_vocals_mixed.wav"),
        "seg_csv": os.path.join(out_dir, f"{basename}_vocals_segments.csv"),
        "pitch_csv": os.path.join(out_dir, f"{basename}_vocals_pitch.csv"),
        "pitch_png": os.path.join(out_dir, f"{basename}_vocals_pitch.png"),
        "full_midi": os.path.join(out_dir, f"{basename}_basic_pitch.mid"),
        "pitch_csv_flat": os.path.join(out_dir, f"{basename}_pitch.csv"),
        "pitch_png_flat": os.path.join(out_dir, f"{basename}_pitch.png"),
        "sheet_xml": os.path.join(out_dir, f"{basename}.musicxml"),
    }