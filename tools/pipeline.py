# /// script
# dependencies = []
# ///

"""完整音高分析管线: 人声提取 → 音高检测 → 纯音合成 → 混合播放。

流程:
  1. Demucs 提取人声
  2. Basic Pitch 检测音高 (默认参数，66段模式)
  3. 合成纯音
  4. 混合原声+纯音并播放

用法:
    uv run pipeline.py <音频文件>                          # 完整流程
    uv run pipeline.py <音频文件> --no-play                # 不播放
    uv run pipeline.py <音频文件> --onset 0.2              # 调整灵敏度
    uv run pipeline.py <音频文件> --midi-only              # 只跑前两步，生成 MIDI

依赖: uv tool install --python 3.11 basic-pitch (已安装)
      uv tool install demucs (已安装)
"""

import sys
import os
import subprocess
import tempfile
import shutil


def step(msg):
    print(f"\n{'='*50}")
    print(f"  [{msg}]")
    print(f"{'='*50}")


def run(cmd, desc, timeout=600):
    print(f"  运行: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        print(f"  {desc} 失败：{result.stderr[:500]}", file=sys.stderr)
        sys.exit(1)
    # 过滤 TensorFlow 警告，只显示有效输出
    for line in result.stdout.split("\n"):
        if line.strip() and not line.startswith("WARNING") and not line.startswith("20"):
            print(f"  {line}")
    return result


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(1)

    # 参数
    no_play = "--no-play" in args
    midi_only = "--midi-only" in args
    onset = None
    frame = None
    audio = None

    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--no-play", "--midi-only"):
            i += 1
        elif a == "--onset" and i + 1 < len(args):
            onset = float(args[i + 1])
            i += 2
        elif a == "--frame" and i + 1 < len(args):
            frame = float(args[i + 1])
            i += 2
        elif a.startswith("--"):
            print(f"未知参数: {a}", file=sys.stderr)
            sys.exit(1)
        else:
            audio = a
            i += 1

    if not audio:
        print("错误：缺少音频文件", file=sys.stderr)
        sys.exit(1)

    audio_path = os.path.abspath(audio)
    if not os.path.isfile(audio_path):
        print(f"文件不存在: {audio_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = os.path.dirname(audio_path)
    basename = os.path.splitext(os.path.basename(audio_path))[0]
    vocals_path = os.path.join(out_dir, f"{basename}_vocals.wav")
    midi_path = os.path.join(out_dir, f"{basename}_vocals_basic_pitch.mid")
    play_path = os.path.join(out_dir, f"{basename}_vocals_play.wav")
    mixed_path = os.path.join(out_dir, f"{basename}_vocals_mixed.wav")

    # --- Step 1: Demucs 人声提取 ---
    step("1/4  Demucs 人声分离")
    if os.path.isfile(vocals_path):
        print(f"  已存在: {vocals_path}，跳过")
    else:
        run(["uv", "run", "vocal_extract.py", audio_path],
            "Demucs 人声提取", timeout=600)

    if not os.path.isfile(vocals_path):
        print(f"  错误：人声文件未生成 {vocals_path}", file=sys.stderr)
        sys.exit(1)

    # --- Step 2: Basic Pitch 音高检测 ---
    step("2/4  Basic Pitch 音高分析")
    bp_cmd = ["uv", "run", "pitch_basic.py", "--save-midi", vocals_path]
    if onset is not None:
        bp_cmd.insert(4, "--onset")
        bp_cmd.insert(5, str(onset))
    if frame is not None:
        bp_cmd.insert(4, "--frame")
        bp_cmd.insert(5, str(frame))
    run(bp_cmd, "Basic Pitch 分析", timeout=600)

    if midi_only:
        print(f"\nMIDI: {midi_path}")
        print("管线完成（--midi-only）")
        return

    # --- Step 3: 合成纯音 ---
    step("3/4  合成纯音")
    seg_csv = os.path.join(out_dir, f"{basename}_vocals_segments.csv")
    if not os.path.isfile(seg_csv):
        print(f"  错误：segments CSV 未生成 {seg_csv}", file=sys.stderr)
        sys.exit(1)
    run(["uv", "run", "pitch_play.py", seg_csv, "--no-play"],
        "纯音合成", timeout=120)

    if not os.path.isfile(play_path):
        # 检查是否文件名后缀不一样
        for f in os.listdir(out_dir):
            if f.endswith("_play.wav") and basename in f:
                play_path = os.path.join(out_dir, f)
                break
        else:
            print(f"  错误：纯音文件未生成", file=sys.stderr)
            sys.exit(1)

    # --- Step 4: 混合并播放 ---
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
    run(ffmpeg_cmd, "混合", timeout=60)
    size_kb = os.path.getsize(mixed_path) / 1024
    print(f"\n混合文件: {mixed_path} ({size_kb:.0f} KB)")

    if not no_play:
        print("\n正在播放混合音频...")
        subprocess.run(["paplay", mixed_path])

    print("\n✅ 管线完成")
    print(f"   人声:    {vocals_path}")
    print(f"   MIDI:    {midi_path}")
    print(f"   纯音:    {play_path}")
    print(f"   混合:    {mixed_path}")


if __name__ == "__main__":
    main()