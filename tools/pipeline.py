# /// script
# dependencies = []
# ///

"""完整音高分析管线：录音 → 人声提取 → 音高检测 → 纯音合成 → 混合播放。

流程:
  1. Demucs 提取人声          →  *_vocals.wav
  2. Basic Pitch 检测音高      →  *_vocals_segments.csv / *_vocals_basic_pitch.mid
  3. 合成纯音                  →  *_vocals_play.wav
  4. ffmpeg 混合原声+纯音      →  *_vocals_mixed.wav
  5. 播放混合音频

模式:
  --midi-only         只跑 1-2 步，输出 MIDI
  --analyze           额外运行 pYIN 逐帧分析，输出 CSV + 可视化 PNG

用法:
    python pipeline.py <音频文件>                             # 完整流程
    python pipeline.py <音频文件> --midi-only                  # 只到 MIDI
    python pipeline.py <音频文件> --midi-only --preset 75      # 预设参数
    python pipeline.py <音频文件> --analyze                    # 含 pYIN 分析
    python pipeline.py <音频文件> --onset 0.2 --no-play        # 自定义
    python pipeline.py                                         # 自动找最新录音

依赖:
    uv tool install --python 3.11 basic-pitch
    uv tool install demucs
"""

import sys
import os
from pathlib import Path
import subprocess

SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))
from common import step, run_cmd, find_wav, resolve_paths


def build_bp_args(vocals_path: str, *,
                  vocal: bool = False,
                  sensitive: bool = False,
                  onset: float | None = None,
                  frame: float | None = None,
                  min_note_len: float | None = None,
                  min_vel: int = 0,
                  save_midi: bool = True) -> list[str]:
    """构造 Basic Pitch 子进程命令行参数。"""
    cmd = [sys.executable, str(SCRIPT_DIR / "pitch_basic.py")]
    if save_midi:
        cmd.append("--save-midi")
    if vocal:
        cmd.append("--vocal")
    if sensitive:
        cmd.append("--sensitive")
    if onset is not None:
        cmd += ["--onset", str(onset)]
    if frame is not None:
        cmd += ["--frame", str(frame)]
    if min_note_len is not None:
        cmd += ["--min-note-length", str(min_note_len)]
    if min_vel > 0:
        cmd += ["--min-vel", str(min_vel)]
    cmd.append(vocals_path)
    return cmd


def apply_preset(preset: str, onset, frame, min_note_len, vocal):
    """应用预设参数。返回 (onset, frame, min_note_len, vocal)。"""
    if preset == "66":
        return None, None, None, False
    elif preset == "75":
        return 0.15, None, None, True
    else:
        print(f"未知预设: {preset}，可选 66, 75", file=sys.stderr)
        sys.exit(1)


def main():
    args = sys.argv[1:]
    if not args and sys.stdin.isatty():
        # 无参数但有 tty → 尝试自动找录音
        wav = find_wav(os.getcwd())
        if wav:
            print(f"自动选择: {os.path.basename(wav)}")
            args = [wav]
        else:
            print(__doc__)
            sys.exit(1)
    elif not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(1)

    # ── 参数解析 ──
    audio = None
    midi_only = False
    no_play = False
    analyze = False
    onset = None
    frame = None
    min_note_len = None
    min_vel = 0
    vocal = False
    sensitive = False

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--midi-only":
            midi_only = True; i += 1
        elif a == "--no-play":
            no_play = True; i += 1
        elif a == "--analyze":
            analyze = True; i += 1
        elif a == "--vocal":
            vocal = True; i += 1
        elif a == "--sensitive":
            sensitive = True; i += 1
        elif a == "--preset" and i + 1 < len(args):
            onset, frame, min_note_len, vocal = apply_preset(
                args[i + 1], onset, frame, min_note_len, vocal)
            i += 2
        elif a == "--onset" and i + 1 < len(args):
            onset = float(args[i + 1]); i += 2
        elif a == "--frame" and i + 1 < len(args):
            frame = float(args[i + 1]); i += 2
        elif a == "--min-note-length" and i + 1 < len(args):
            min_note_len = float(args[i + 1]); i += 2
        elif a == "--min-vel" and i + 1 < len(args):
            min_vel = int(float(args[i + 1])); i += 2
        elif a.startswith("--"):
            print(f"未知参数: {a}", file=sys.stderr)
            sys.exit(1)
        else:
            audio = a; i += 1

    if not audio:
        print("错误：缺少音频文件", file=sys.stderr)
        sys.exit(1)

    paths = resolve_paths(audio)
    out_dir = paths["out_dir"]
    vocals_path = paths["vocals"]
    midi_path = paths["midi"]
    play_path = paths["play"]
    mixed_path = paths["mixed"]

    # ── 参数摘要 ──
    params = []
    if onset is not None: params.append(f"onset={onset}")
    if frame is not None: params.append(f"frame={frame}")
    if min_note_len is not None: params.append(f"min_len={min_note_len}s")
    if min_vel > 0: params.append(f"min_vel={min_vel}")
    if vocal: params.append("vocal")
    if sensitive: params.append("sensitive")
    mode = "MIDI-only" if midi_only else "完整"
    print(f"\n输入: {audio}")
    print(f"模式: {mode}  |  参数: {' '.join(params) if params else '默认(66段)'}")

    # ── Step 1: Demucs 人声提取 ──
    step("1/4  Demucs 人声分离")
    if os.path.isfile(vocals_path):
        print(f"  已存在: {vocals_path}，跳过")
    else:
        run_cmd(
            [sys.executable, str(SCRIPT_DIR / "vocal_extract.py"), audio],
            desc="Demucs 人声提取", timeout=600)

    if not os.path.isfile(vocals_path):
        print(f"  错误：人声文件未生成 {vocals_path}", file=sys.stderr)
        sys.exit(1)

    # ── Step 2: Basic Pitch 音高检测 ──
    step("2/4  Basic Pitch 音高分析")
    bp_cmd = build_bp_args(
        vocals_path,
        vocal=vocal, sensitive=sensitive,
        onset=onset, frame=frame, min_note_len=min_note_len,
        min_vel=min_vel, save_midi=True)
    run_cmd(bp_cmd, desc="Basic Pitch 分析", timeout=600)

    # ── (可选) pYIN 分析 ──
    if analyze:
        step("(附加)  pYIN 逐帧音高分析")
        run_cmd(
            [sys.executable, str(SCRIPT_DIR / "pitch_analyzer.py"),
             "--vocal", vocals_path],
            desc="pYIN 分析", timeout=300)

    if midi_only:
        print(f"\n{'=' * 50}")
        print(f"  输出文件:")
        print(f"    人声:  {vocals_path}")
        print(f"    MIDI:  {midi_path}")
        print(f"{'=' * 50}")
        print(f"  MuseScore 打开: mscore \"{midi_path}\"")
        return

    # ── Step 3: 合成纯音 ──
    step("3/4  合成纯音")
    seg_csv = paths["seg_csv"]
    if not os.path.isfile(seg_csv):
        print(f"  错误：segments CSV 未生成 {seg_csv}", file=sys.stderr)
        sys.exit(1)
    run_cmd(
        [sys.executable, str(SCRIPT_DIR / "pitch_play.py"), seg_csv, "--no-play"],
        desc="纯音合成", timeout=120)

    # 确认 play 文件路径（pitch_play.py 会自动替换 _segments 为 _play）
    if not os.path.isfile(play_path):
        for f in os.listdir(out_dir):
            if f.endswith("_play.wav") and paths["basename"] in f:
                play_path = os.path.join(out_dir, f)
                break
        else:
            print(f"  错误：纯音文件未生成", file=sys.stderr)
            sys.exit(1)

    # ── Step 4: 混合并播放 ──
    step("4/4  混合原声+纯音")
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-i", vocals_path,
        "-i", play_path,
        "-filter_complex",
        "[0:a]volume=0.5[a];[1:a]volume=0.5[b];[a][b]amix=inputs=2:duration=first",
        "-ac", "1",
        mixed_path,
    ]
    run_cmd(ffmpeg_cmd, desc="ffmpeg 混合", timeout=60)
    size_kb = os.path.getsize(mixed_path) / 1024
    print(f"\n混合文件: {mixed_path} ({size_kb:.0f} KB)")

    if not no_play:
        print("\n正在播放混合音频...")
        subprocess.run(["paplay", mixed_path])

    print(f"\n{'=' * 50}")
    print(f"  ✅ 管线完成")
    print(f"    人声:  {vocals_path}")
    print(f"    MIDI:  {midi_path}")
    print(f"    纯音:  {play_path}")
    print(f"    混合:  {mixed_path}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()