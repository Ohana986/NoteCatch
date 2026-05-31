# /// script
# dependencies = []
# ///

"""audio-analyzer 共享工具模块。

提供各脚本通用的：
  - 输出子目录分类 (audio / midi / data / plots / sheets)
  - 步骤输出、子进程封装（含 TF/CUDA 噪音过滤）
  - 文件查找与路径解析
"""

import os
import sys
import subprocess

# ── 输出分类：类型 → 子目录名 ──
CAT_AUDIO = "audio"    # .wav
CAT_MIDI = "midi"      # .mid
CAT_DATA = "data"      # .csv
CAT_PLOTS = "plots"    # .png
CAT_SHEETS = "sheets"  # .musicxml

_CATEGORY_DIRS = {CAT_AUDIO, CAT_MIDI, CAT_DATA, CAT_PLOTS, CAT_SHEETS}

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


def get_project_root(file_path: str) -> str:
    """根据输入文件路径推导项目根目录。

    如果输入文件位于某个分类子目录（audio/midi/data/plots/sheets），
    返回上级目录；否则返回文件所在目录。
    """
    parent = os.path.dirname(os.path.abspath(file_path))
    if os.path.basename(parent) in _CATEGORY_DIRS:
        return os.path.dirname(parent)
    return parent


def get_output_path(root: str, filename: str, category: str) -> str:
    """在分类子目录下构造输出路径，自动创建子目录。

    参数:
        root:     项目根目录（来自 get_project_root）
        filename: 完整文件名（含扩展名）
        category: 分类名 (CAT_AUDIO / CAT_MIDI / CAT_DATA / CAT_PLOTS / CAT_SHEETS)
    """
    subdir = os.path.join(root, category)
    os.makedirs(subdir, exist_ok=True)
    return os.path.join(subdir, filename)


def resolve_paths(audio_path: str) -> dict:
    """根据音频文件路径，推导出所有产物路径（使用分类子目录）。

    返回包含以下键的 dict:
        root, basename, audio_dir, midi_dir, data_dir, plots_dir, sheets_dir,
        vocals, midi, play, mixed, seg_csv, pitch_csv, pitch_png, full_midi,
        seg_csv_flat (pitch_analyzer.py 全频段 segments)
    """
    audio_path = os.path.abspath(audio_path)
    root = get_project_root(audio_path)
    basename = os.path.splitext(os.path.basename(audio_path))[0]

    def _p(cat, fname):
        return get_output_path(root, fname, cat)

    return {
        "root": root,
        "basename": basename,
        "audio_dir": os.path.join(root, CAT_AUDIO),
        "midi_dir": os.path.join(root, CAT_MIDI),
        "data_dir": os.path.join(root, CAT_DATA),
        "plots_dir": os.path.join(root, CAT_PLOTS),
        "sheets_dir": os.path.join(root, CAT_SHEETS),
        # 人声/纯音/混合 → audio/
        "vocals": _p(CAT_AUDIO, f"{basename}_vocals.wav"),
        "play": _p(CAT_AUDIO, f"{basename}_vocals_play.wav"),
        "mixed": _p(CAT_AUDIO, f"{basename}_vocals_mixed.wav"),
        "original": _p(CAT_AUDIO, os.path.basename(audio_path)),
        # MIDI → midi/
        "midi": _p(CAT_MIDI, f"{basename}_vocals_basic_pitch.mid"),
        "full_midi": _p(CAT_MIDI, f"{basename}_basic_pitch.mid"),
        # CSV → data/
        "seg_csv": _p(CAT_DATA, f"{basename}_vocals_segments.csv"),
        "pitch_csv": _p(CAT_DATA, f"{basename}_vocals_pitch.csv"),
        "pitch_csv_flat": _p(CAT_DATA, f"{basename}_pitch.csv"),
        # PNG → plots/
        "pitch_png": _p(CAT_PLOTS, f"{basename}_vocals_pitch.png"),
        "pitch_png_flat": _p(CAT_PLOTS, f"{basename}_pitch.png"),
        # MusicXML → sheets/
        "sheet_xml": _p(CAT_SHEETS, f"{basename}.musicxml"),
    }


def find_wav(directory: str) -> str | None:
    """在目录的 audio/ 子目录（或目录本身）中找最新的原始录音。

    排除 _vocals / _play / _mixed 结尾的生成文件。
    """
    audio_dir = os.path.join(directory, CAT_AUDIO)
    search_dirs = []
    if os.path.isdir(audio_dir):
        search_dirs.append(audio_dir)
    search_dirs.append(directory)

    wavs = []
    for sd in search_dirs:
        if not os.path.isdir(sd):
            continue
        for f in os.listdir(sd):
            if not f.endswith(".wav"):
                continue
            if any(x in f for x in ("_vocals", "_play", "_mixed")):
                continue
            wavs.append(os.path.join(sd, f))

    if not wavs:
        return None
    wavs.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return wavs[0]