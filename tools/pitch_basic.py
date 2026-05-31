# /// script
# dependencies = []
# ///

"""使用 Spotify Basic Pitch 进行音高分析。

Basic Pitch 原生 CSV 格式:
    start_time_s,end_time_s,pitch_midi,velocity,pitch_bend...
    pitch_midi: MIDI 音符号 (0-127), velocity: 音量 (0-127)

用法:
    uv run pitch_basic.py <音频文件>                    # 默认
    uv run pitch_basic.py --vocal <音频文件>            # 人声模式（限频+弱音敏感）
    uv run pitch_basic.py --vocal --sensitive <文件>    # 更敏感（检测弱音）
    uv run pitch_basic.py --vocal --min-vel 30 <文件>   # 过滤低音量杂音
    uv run pitch_basic.py --save-midi <文件>            # 同时输出 MIDI

参数:
    --onset <f>         起音阈值，默认 0.5，越低越敏感
    --frame <f>         帧阈值，默认 0.5，越低越敏感
    --min-note-length <s>  最短音符，默认 0.058
    --min-vel <n>       最低音量过滤 (0-127)，默认 0
    --sensitive         快捷：--onset 0.3 --frame 0.3 --min-note-length 0.03

依赖: uv tool install --python 3.11 basic-pitch
"""

import sys
import os
import subprocess
import tempfile
import csv
import shutil

_VOCAL_MIN = 80.0
_VOCAL_MAX = 800.0

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _midi_to_note(midi: int) -> str:
    octave = midi // 12 - 1
    return f"{_NOTE_NAMES[midi % 12]}{octave}"


def _midi_to_hz(midi: float) -> float:
    return 440.0 * (2.0 ** ((midi - 69.0) / 12.0))


def pick_loudest_per_frame(segments, min_freq=0, max_freq=99999):
    """同时间有多个音时，只保留音量最大的那个（假设单声部）。"""
    # 按时间排序
    segs = sorted(segments, key=lambda s: s["start"])
    filtered = []
    i = 0
    while i < len(segs):
        best = segs[i]
        j = i + 1
        # 找重叠的音，取音量最大的
        while j < len(segs) and segs[j]["start"] < best["end"]:
            if (min_freq <= segs[j]["pitch_mean"] <= max_freq
                    and segs[j]["velocity"] > best["velocity"]):
                best = segs[j]
            j += 1
        filtered.append(best)
        i = j
    return filtered


def parse_bp_csv(csv_path: str, min_velocity: int = 0,
                 min_freq: float = 0, max_freq: float = 99999,
                 monophonic: bool = True) -> list[dict]:
    segments = []
    with open(csv_path, newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # 跳过表头
        for row in reader:
            if len(row) < 4:
                continue
            try:
                start = float(row[0])
                end = float(row[1])
                midi = float(row[2])
                velocity = float(row[3])
            except (ValueError, IndexError):
                continue
            if velocity < min_velocity:
                continue
            if end - start < 0.01:
                continue
            hz = _midi_to_hz(midi)
            if hz < min_freq or hz > max_freq:
                continue
            segments.append({
                "start": start,
                "end": end,
                "duration": end - start,
                "pitch_mean": hz,
                "note": _midi_to_note(round(midi)),
                "velocity": int(velocity),
            })

    if monophonic:
        segments = pick_loudest_per_frame(segments, min_freq, max_freq)

    return segments


def analyze_basic_pitch(audio_path, output_dir=".",
                        save_midi=False, vocal=False,
                        onset=None, frame=None, min_note_len=None,
                        min_vel=0, sensitive=False):
    audio_path = os.path.abspath(audio_path)
    basename = os.path.splitext(os.path.basename(audio_path))[0]
    seg_path = os.path.join(output_dir, f"{basename}_segments.csv")

    print(f"加载: {audio_path}")
    print("模型: Basic Pitch (Spotify)")

    with tempfile.TemporaryDirectory(prefix="bp_") as tmpdir:
        cmd = ["basic-pitch", tmpdir, "--save-note-events"]

        if sensitive:
            onset = onset if onset is not None else 0.3
            frame = frame if frame is not None else 0.3
            min_note_len = min_note_len if min_note_len is not None else 0.03

        if onset is not None:
            cmd += ["--onset-threshold", str(onset)]
        if frame is not None:
            cmd += ["--frame-threshold", str(frame)]
        if min_note_len is not None:
            cmd += ["--minimum-note-length", str(min_note_len)]
        if save_midi:
            cmd += ["--save-midi"]
        cmd.append(audio_path)

        params_desc = []
        if onset is not None:
            params_desc.append(f"onset={onset}")
        if frame is not None:
            params_desc.append(f"frame={frame}")
        if min_note_len is not None:
            params_desc.append(f"min_len={min_note_len}s")
        if min_vel > 0:
            params_desc.append(f"min_vel={min_vel}")
        if vocal:
            params_desc.append(f"vocal({_VOCAL_MIN:.0f}~{_VOCAL_MAX:.0f}Hz)")
        print(f"参数: {' '.join(params_desc) if params_desc else '默认'}")

        print("分析中...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            print(f"失败：{result.stderr}", file=sys.stderr)
            sys.exit(1)

        # 找 CSV
        bp_csv = None
        for f in os.listdir(tmpdir):
            if f.endswith("_basic_pitch.csv"):
                bp_csv = os.path.join(tmpdir, f)
                break
        if not bp_csv:
            # 回退找任何 csv
            for f in os.listdir(tmpdir):
                if f.endswith(".csv"):
                    bp_csv = os.path.join(tmpdir, f)
                    break
        if not bp_csv:
            print("错误：未找到 Basic Pitch 输出", file=sys.stderr)
            print(result.stdout, result.stderr)
            sys.exit(1)

        # 解析
        min_freq = _VOCAL_MIN if vocal else 0
        max_freq = _VOCAL_MAX if vocal else 99999
        segments = parse_bp_csv(bp_csv, min_velocity=min_vel,
                                min_freq=min_freq, max_freq=max_freq,
                                monophonic=vocal)

        # 保存 segments CSV（带 velocity 列供参考）
        with open(seg_path, "w", newline="") as f:
            f.write("start_s,end_s,duration_s,pitch_mean,pitch_min,pitch_max,note,n_frames\n")
            for seg in segments:
                f.write(f"{seg['start']:.4f},{seg['end']:.4f},{seg['duration']:.4f},"
                        f"{seg['pitch_mean']:.2f},{seg['pitch_mean']:.2f},{seg['pitch_mean']:.2f},"
                        f"{seg['note']},1\n")

        if save_midi:
            for f in os.listdir(tmpdir):
                if f.endswith(".mid"):
                    shutil.copy2(os.path.join(tmpdir, f),
                                 os.path.join(output_dir, f))
                    print(f"MIDI: {f}")

    print(f"音段: {seg_path}  ({len(segments)} 段)")
    if segments:
        pitches = [s["pitch_mean"] for s in segments]
        notes = [s["note"] for s in segments]
        print(f"  范围: {min(pitches):.0f}~{max(pitches):.0f} Hz "
              f"({notes[pitches.index(min(pitches))]}~{notes[pitches.index(max(pitches))]})")
        sorted_segs = sorted(segments, key=lambda s: s["start"])
        for seg in sorted_segs[:12]:
            bar = "█" * max(1, seg["velocity"] // 10)
            print(f"    {seg['start']:.2f}s~{seg['end']:.2f}s "
                  f"({seg['duration']:.2f}s)  {seg['note']:>4s}  "
                  f"{seg['pitch_mean']:.0f}Hz  vel={seg['velocity']:>3d} {bar}")
        if len(sorted_segs) > 12:
            print(f"    ... 还有 {len(sorted_segs) - 12} 段")
    else:
        print("  (未检测到音符)")

    return seg_path


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(1)

    audio = None
    save_midi = False
    vocal = False
    sensitive = False
    onset = frame = min_note_len = None
    min_vel = 0

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--save-midi":
            save_midi = True
            i += 1
        elif a == "--vocal":
            vocal = True
            i += 1
        elif a == "--sensitive":
            sensitive = True
            i += 1
        elif a == "--min-vel" and i + 1 < len(args):
            min_vel = int(float(args[i + 1]))
            i += 2
        elif a == "--onset" and i + 1 < len(args):
            onset = float(args[i + 1])
            i += 2
        elif a == "--frame" and i + 1 < len(args):
            frame = float(args[i + 1])
            i += 2
        elif a == "--min-note-length" and i + 1 < len(args):
            min_note_len = float(args[i + 1])
            i += 2
        elif a.startswith("--"):
            print(f"错误：未知参数 {a}", file=sys.stderr)
            sys.exit(1)
        else:
            audio = a
            i += 1

    if not audio:
        print("错误：缺少音频文件", file=sys.stderr)
        print(__doc__)
        sys.exit(1)

    audio_path = os.path.abspath(audio)
    if not os.path.isfile(audio_path):
        print(f"文件不存在: {audio_path}", file=sys.stderr)
        sys.exit(1)

    analyze_basic_pitch(audio_path, output_dir=os.path.dirname(audio_path),
                        save_midi=save_midi, vocal=vocal,
                        onset=onset, frame=frame, min_note_len=min_note_len,
                        min_vel=min_vel, sensitive=sensitive)


if __name__ == "__main__":
    main()