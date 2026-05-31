# /// script
# dependencies = [
#   "numpy>=1.24",
#   "soundfile>=0.12",
# ]
# ///

"""根据音高分析结果合成音频并播放。

用法:
    uv run pitch_play.py <segments.csv>              # 读取音段CSV，合成WAV并播放
    uv run pitch_play.py <segments.csv> --no-play    # 只合成不播放
    uv run pitch_play.py <segments.csv> --tone sine  # 波形: sine | saw | square (默认 sine)
"""

import sys
import os
from pathlib import Path
import subprocess
import csv
import math

import numpy as np
import soundfile as sf

SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))
from common import get_project_root, get_output_path, CAT_AUDIO


def synthesize_segments(csv_path: str, tone: str = "sine",
                        sample_rate: int = 44100) -> str:
    """读取音段 CSV，合成为音频文件。返回输出路径。"""
    # 读取音段
    segments = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            segments.append({
                "start": float(row["start_s"]),
                "end": float(row["end_s"]),
                "pitch": float(row["pitch_mean"]),
            })

    if not segments:
        print("错误：没有音段数据", file=sys.stderr)
        sys.exit(1)

    total_duration = max(s["end"] for s in segments)
    total_samples = int(total_duration * sample_rate)

    # 选择波形函数
    if tone == "sine":
        wave_func = lambda t, f: np.sin(2 * np.pi * f * t)
    elif tone == "saw":
        wave_func = lambda t, f: 2 * (f * t - np.floor(f * t + 0.5))
    elif tone == "square":
        wave_func = lambda t, f: np.sign(np.sin(2 * np.pi * f * t))
    else:
        print(f"错误：未知波形 '{tone}'，可选 sine/saw/square", file=sys.stderr)
        sys.exit(1)

    # 添加淡入淡出包络（每段起止 5ms）
    fade_len = int(0.005 * sample_rate)

    print(f"合成: {len(segments)} 音段, {total_duration:.1f}s, 波形={tone}")
    audio = np.zeros(total_samples, dtype=np.float64)

    for i, seg in enumerate(segments):
        s = int(seg["start"] * sample_rate)
        e = int(seg["end"] * sample_rate)
        length = e - s
        if length < 2:
            continue

        t = np.arange(length) / sample_rate
        wave = wave_func(t, seg["pitch"])

        # 淡入淡出
        fade = np.ones(length)
        fade[:fade_len] = np.linspace(0, 1, min(fade_len, length))
        fade[-fade_len:] = np.linspace(1, 0, min(fade_len, length))
        wave *= fade

        # 归一化到 -0.5~0.5（留余量避免削波）
        peak = np.max(np.abs(wave))
        if peak > 0:
            wave *= 0.5 / peak

        audio[s:e] += wave

    # 整体归一化
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio /= peak

    # 保存
    # 从 CSV 文件名推导 play 文件名：替换 _segments 为 _play
    csv_basename = os.path.basename(csv_path)
    play_name = csv_basename.replace("_segments", "_play").replace(".csv", ".wav")
    root = get_project_root(csv_path)
    out_path = get_output_path(root, play_name, CAT_AUDIO)

    sf.write(out_path, audio, sample_rate, subtype="PCM_16")
    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"输出: {out_path} ({size_mb:.1f} MB)")

    return out_path


def play_audio(path: str):
    """用系统默认方式播放音频。"""
    print("正在播放...")
    try:
        subprocess.run(["paplay", path], check=True)
    except FileNotFoundError:
        try:
            subprocess.run(["ffplay", "-nodisp", "-autoexit", path],
                           capture_output=True, check=True)
        except FileNotFoundError:
            print(f"提示：未找到播放工具，文件在 {path}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--tone=")]
    tone_arg = next((a.split("=", 1)[1] for a in sys.argv[1:]
                     if a.startswith("--tone=")), "sine")
    no_play = "--no-play" in sys.argv

    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(1)

    csv_path = os.path.abspath(args[0])
    if not os.path.isfile(csv_path):
        print(f"错误：文件不存在 {csv_path}", file=sys.stderr)
        sys.exit(1)

    wav_path = synthesize_segments(csv_path, tone=tone_arg)

    if not no_play:
        play_audio(wav_path)


if __name__ == "__main__":
    main()