# /// script
# dependencies = [
#   "librosa>=0.10.0",
#   "numpy>=1.24",
#   "matplotlib>=3.7",
#   "soundfile>=0.12",
# ]
# ///

"""音高分析工具：逐帧追踪音高，输出 CSV + 可视化图。

用法:
    python pitch_analyzer.py <音频文件>              # 全频段 (C2~C7)
    python pitch_analyzer.py --vocal <音频文件>      # 人声范围 (80~500 Hz)
    python pitch_analyzer.py --range 80 800 <文件>   # 自定义范围 (Hz)
    python pitch_analyzer.py --vocal --tol 0.5 <文件> # 调整音高合并精度(半音)

输出:
    *_pitch.csv       — 逐帧音高详情
    *_segments.csv    — 自适应合并后的音段（相似音高>1半音合并）
    *_pitch.png       — 可视化图
"""

import sys
import os
import warnings

import librosa
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import soundfile as sf

# 中文字体（直接指定路径，绕过 matplotlib 缓存）
_CJK_FONT_PATH = "/usr/share/fonts/google-noto-sans-cjk-fonts/NotoSansCJK-Regular.ttc"
from matplotlib.font_manager import FontProperties
_cjk_font = FontProperties(fname=_CJK_FONT_PATH)
plt.rcParams["axes.unicode_minus"] = False

warnings.filterwarnings("ignore", category=UserWarning, module="librosa")

# 音名表（C0=0）
_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def hz_to_note(freq: float) -> str:
    """将频率 (Hz) 转换为音名，如 440 -> 'A4', 0/NaN -> '-' """
    if not np.isfinite(freq) or freq <= 0:
        return "-"
    midi = 12 * np.log2(freq / 440.0) + 69
    midi_int = int(round(midi))
    octave = midi_int // 12 - 1
    name = _NOTE_NAMES[midi_int % 12]
    return f"{name}{octave}"


def merge_pitch_segments(times, f0, voiced_flag, sr,
                         semitone_tol: float = 1.0,
                         max_gap_s: float = 0.05):
    """将连续帧中音高相近的合并为音段。

    返回: list of dicts, 每个 dict:
        {start, end, duration, pitch_mean, pitch_min, pitch_max,
         pitch_std, note, n_frames}
    """
    voiced = voiced_flag.astype(bool)
    segments = []
    i = 0
    n = len(times)
    frame_interval = times[1] - times[0] if n > 1 else 0.01
    max_gap_frames = max(1, int(max_gap_s / frame_interval))

    while i < n:
        # 跳过无声段
        if not voiced[i]:
            i += 1
            continue

        # 开始一个新段
        seg_idx = []
        seg_pitches = []
        total_unvoiced = 0  # 段内连续无声帧计数

        j = i
        while j < n:
            if voiced[j]:
                pitch = f0[j]
                if seg_pitches:
                    # 计算距 segment 平均音高的偏差（半音）
                    mean_p = np.mean(seg_pitches)
                    dev_st = 12 * abs(np.log2(pitch / mean_p)) if pitch > 0 and mean_p > 0 else 99
                else:
                    dev_st = 0

                if dev_st <= semitone_tol or not seg_pitches:
                    seg_idx.append(j)
                    seg_pitches.append(pitch)
                    total_unvoiced = 0
                    j += 1
                else:
                    break
            else:
                total_unvoiced += 1
                if total_unvoiced > max_gap_frames:
                    break
                j += 1

        if len(seg_idx) >= 2:
            pitches = np.array(seg_pitches)
            seg_times = times[seg_idx]
            seg = {
                "start": seg_times[0],
                "end": seg_times[-1],
                "duration": seg_times[-1] - seg_times[0],
                "pitch_mean": np.mean(pitches),
                "pitch_min": np.min(pitches),
                "pitch_max": np.max(pitches),
                "pitch_std": np.std(pitches),
                "note": hz_to_note(np.mean(pitches)),
                "n_frames": len(seg_idx),
            }
            segments.append(seg)

        i = j

    return segments


def analyze_pitch(audio_path: str, output_dir: str = ".",
                  fmin: float = 65.4, fmax: float = 2093.0,
                  semitone_tol: float = 1.0):
    basename = os.path.splitext(os.path.basename(audio_path))[0]
    out_dir = os.path.dirname(audio_path)
    csv_path = os.path.join(out_dir, f"{basename}_pitch.csv")
    seg_path = os.path.join(out_dir, f"{basename}_segments.csv")
    png_path = os.path.join(out_dir, f"{basename}_pitch.png")

    print(f"加载: {audio_path}")
    y, sr = librosa.load(audio_path, sr=None, mono=True)
    duration = len(y) / sr
    range_desc = f"{hz_to_note(fmin)}~{hz_to_note(fmax)} ({fmin:.0f}~{fmax:.0f} Hz)"
    print(f"采样率: {sr} Hz, 时长: {duration:.2f} s, 分析范围: {range_desc}")

    # --- 音高追踪 (pYIN) ---
    print("正在分析音高 (pYIN)...")
    frame_length = max(2048, int(4 * sr / fmin))
    f0, voiced_flag, voiced_probs = librosa.pyin(
        y, fmin=fmin, fmax=fmax, sr=sr, frame_length=frame_length)
    times = librosa.times_like(f0, sr=sr)
    note_names = np.array([hz_to_note(f) for f in f0])

    # --- 保存逐帧 CSV ---
    header = "time_s,pitch_hz,note,voiced"
    with open(csv_path, "w", newline="") as f:
        f.write(header + "\n")
        for t, p, n_, v in zip(times, f0, note_names, voiced_flag):
            p_str = f"{p:.2f}" if np.isfinite(p) else ""
            f.write(f"{t:.4f},{p_str},{n_},{int(v)}\n")
    print(f"CSV: {csv_path}")

    # --- 自适应音段合并 ---
    segments = merge_pitch_segments(times, f0, voiced_flag, sr,
                                    semitone_tol=semitone_tol)
    with open(seg_path, "w", newline="") as f:
        f.write("start_s,end_s,duration_s,pitch_mean,pitch_min,pitch_max,note,n_frames\n")
        for seg in segments:
            f.write(f"{seg['start']:.4f},{seg['end']:.4f},{seg['duration']:.4f},"
                    f"{seg['pitch_mean']:.2f},{seg['pitch_min']:.2f},{seg['pitch_max']:.2f},"
                    f"{seg['note']},{seg['n_frames']}\n")
    print(f"音段: {seg_path}  ({len(segments)} 段)")

    # --- 统计信息 ---
    voiced_indices = voiced_flag.astype(bool)
    valid_pitches = f0[voiced_indices]
    if len(valid_pitches) > 0:
        low_note = hz_to_note(valid_pitches.min())
        high_note = hz_to_note(valid_pitches.max())
        mean_note = hz_to_note(valid_pitches.mean())
        print(f"  逐帧范围: {valid_pitches.min():.1f}~{valid_pitches.max():.1f} Hz ({low_note}~{high_note})")
        print(f"  逐帧平均: {valid_pitches.mean():.1f} Hz ({mean_note})")
        print(f"  有声占比: {len(valid_pitches) / len(f0) * 100:.1f}%")
        if segments:
            print(f"  音段: {len(segments)} 段:")
            for seg in segments:
                print(f"    {seg['start']:.2f}s~{seg['end']:.2f}s "
                      f"({seg['duration']:.2f}s)  {seg['note']}  "
                      f"{seg['pitch_mean']:.0f} Hz")
    else:
        print("  (未检测到明显音高，可能为噪声或静音)")

    # --- 可视化 ---
    print("生成可视化...")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 5), sharex=True,
                                    gridspec_kw={"height_ratios": [1, 1.2]})
    fig.suptitle(f"音高分析: {basename}", fontsize=13, fontproperties=_cjk_font)

    # 波形
    t_wave = np.linspace(0, duration, len(y))
    ax1.plot(t_wave, y, color="gray", linewidth=0.3)
    ax1.set_ylabel("振幅", fontproperties=_cjk_font)
    ax1.set_xlim(0, duration)

    # 音高轮廓（散点 + 音段色块）
    ax2.plot(times[voiced_indices], valid_pitches, "o", markersize=1.5,
             color="crimson", alpha=0.4, label="逐帧音高")
    # 叠加音段：水平线 + 浅色背景
    colors = plt.cm.Set1(np.linspace(0, 1, max(len(segments), 1)))
    for k, seg in enumerate(segments):
        color = colors[k % len(colors)]
        mid = seg["pitch_mean"]
        ax2.hlines(mid, seg["start"], seg["end"],
                    color=color, linewidth=4, alpha=0.7)
        ax2.fill_between([seg["start"], seg["end"]],
                          seg["pitch_min"], seg["pitch_max"],
                          color=color, alpha=0.12)
        # 标音名
        mid_time = (seg["start"] + seg["end"]) / 2
        ax2.text(mid_time, mid + 8, seg["note"],
                 fontsize=8, ha="center", va="bottom",
                 fontproperties=_cjk_font, color=color)

    ax2.set_ylabel("音高", fontproperties=_cjk_font)
    ax2.set_xlabel("时间 (s)", fontproperties=_cjk_font)
    ax2.legend(loc="upper right", markerscale=3, prop=_cjk_font)

    # y 轴范围：动态缩放
    if len(valid_pitches) > 0:
        p_min, p_max = valid_pitches.min(), valid_pitches.max()
        margin = max(10, (p_max - p_min) * 0.3)
        y_low = max(0, p_min - margin)
        y_high = p_max + margin
    else:
        y_low, y_high = 50, 500
    ax2.set_ylim(y_low, y_high)
    y_ticks = np.arange(np.floor(y_low / 10) * 10, y_high + 10, 10)
    ax2.set_yticks(y_ticks)
    ax2.set_yticklabels([f"{hz_to_note(t)} ({t:.0f})" for t in y_ticks],
                        fontsize=7)

    plt.tight_layout()
    fig.savefig(png_path, dpi=150)
    print(f"图片: {png_path}")
    plt.close(fig)


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(1)

    fmin, fmax = 65.4, 2093.0
    semitone_tol = 1.0  # 默认 1 半音

    # 解析 --tol
    tol_idx = next((i for i, a in enumerate(args) if a == "--tol"), None)
    if tol_idx is not None:
        try:
            semitone_tol = float(args[tol_idx + 1])
            # 移除 --tol 及其值
            args = args[:tol_idx] + args[tol_idx + 2:]
        except (IndexError, ValueError):
            print("错误：--tol 需要半音数值，如 --tol 0.5", file=sys.stderr)
            sys.exit(1)

    if args and args[0] == "--vocal":
        fmin, fmax = 80.0, 500.0
        args = args[1:]
    elif args and args[0] == "--range":
        try:
            fmin = float(args[1])
            fmax = float(args[2])
        except (IndexError, ValueError):
            print("错误：--range 需要两个数值参数（最低Hz 最高Hz）")
            sys.exit(1)
        args = args[3:]

    if not args:
        print("错误：缺少音频文件")
        print(__doc__)
        sys.exit(1)

    audio_path = os.path.abspath(args[0])
    if not os.path.isfile(audio_path):
        print(f"文件不存在: {audio_path}")
        sys.exit(1)

    analyze_pitch(audio_path, output_dir=os.path.dirname(audio_path),
                  fmin=fmin, fmax=fmax, semitone_tol=semitone_tol)


if __name__ == "__main__":
    main()