# /// script
# dependencies = []
# ///

"""录音→人声提取→MIDI 转五线谱一站式工具。

流程:
  1. Demucs 提取人声  →  *_vocals.wav
  2. Basic Pitch 转 MIDI  →  *_vocals_basic_pitch.mid
  3. 输出文件列表

用法:
    uv run vocal2midi.py <音频文件>                          # 默认
    uv run vocal2midi.py <音频文件> --onset 0.25             # 调灵敏度
    uv run vocal2midi.py <音频文件> --frame 0.4              # 调帧阈值
    uv run vocal2midi.py <音频文件> --vocal                  # Basic Pitch 单声部模式
    uv run vocal2midi.py <音频文件> --sensitive              # 高灵敏度模式
    uv run vocal2midi.py <音频文件> --preset 66              # 预设: Basic Pitch 默认 (66段)
    uv run vocal2midi.py <音频文件> --preset 75              # 预设: 更敏感 (75段)

依赖:
    uv tool install demucs
    uv tool install --python 3.11 basic-pitch
"""

import sys
import os
import subprocess
import shutil


def step(msg):
    print(f"\n── {msg} ──")


def run_cmd(cmd, desc, timeout=600):
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        for line in result.stderr.split("\n"):
            if line.strip() and not any(k in line for k in
                ["WARNING", "Could not find", "Unable to register",
                 "CUDA", "TensorRT", "tensorflow", "external/"]):
                print(f"  {line}")
        print(f"  ✗ {desc} 失败", file=sys.stderr)
        sys.exit(1)
    for line in result.stdout.split("\n"):
        s = line.strip()
        if s and not any(k in s for k in
            ["WARNING", "external/", "tensorflow", "CUDA",
             "cuda", "Could not", "Unable to", "Skipping"]):
            print(f"  {s}")


def find_wav(directory):
    """找目录中最新的一条录音（排除 _vocals _play _mixed）。"""
    wavs = [f for f in os.listdir(directory) if f.endswith(".wav")
            and not any(x in f for x in ["_vocals", "_play", "_mixed"])]
    if not wavs:
        return None
    wavs.sort(key=lambda f: os.path.getmtime(os.path.join(directory, f)),
              reverse=True)
    return os.path.join(directory, wavs[0])


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(1)

    # 默认参数
    audio = None
    onset = None
    frame = None
    min_note_len = None
    vocal = False
    sensitive = False

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--onset" and i + 1 < len(args):
            onset = float(args[i + 1]); i += 2
        elif a == "--frame" and i + 1 < len(args):
            frame = float(args[i + 1]); i += 2
        elif a == "--min-note-length" and i + 1 < len(args):
            min_note_len = float(args[i + 1]); i += 2
        elif a == "--vocal":
            vocal = True; i += 1
        elif a == "--sensitive":
            sensitive = True; i += 1
        elif a == "--preset" and i + 1 < len(args):
            val = args[i + 1]; i += 2
            if val == "66":
                onset, frame, min_note_len = None, None, None
                vocal = False
            elif val == "75":
                onset, frame = 0.15, None
                vocal = True
            else:
                print(f"未知预设: {val}，可选 66, 75", file=sys.stderr)
                sys.exit(1)
        elif a.startswith("--"):
            print(f"未知参数: {a}", file=sys.stderr)
            sys.exit(1)
        else:
            audio = a; i += 1

    # 自动找录音
    if audio is None or audio == ".":
        audio = find_wav(os.getcwd())
        if not audio:
            print("错误：未找到录音文件", file=sys.stderr)
            sys.exit(1)
        print(f"自动选择: {os.path.basename(audio)}")

    audio_path = os.path.abspath(audio)
    if not os.path.isfile(audio_path):
        print(f"文件不存在: {audio_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = os.path.dirname(audio_path)
    base = os.path.splitext(os.path.basename(audio_path))[0]

    # --- 构造 Basic Pitch 参数描述 ---
    params_desc = []
    if onset is not None: params_desc.append(f"onset={onset}")
    if frame is not None: params_desc.append(f"frame={frame}")
    if min_note_len is not None: params_desc.append(f"min_len={min_note_len}")
    if vocal: params_desc.append("vocal")
    if sensitive: params_desc.append("sensitive")
    if not params_desc: params_desc.append("default(66段)")

    print(f"\n输入: {audio_path}")
    print(f"参数: {' '.join(params_desc)}")

    # --- Step 1: Demucs 人声提取 ---
    vocals_path = os.path.join(out_dir, f"{base}_vocals.wav")
    step("1/2  Demucs 人声分离")
    if os.path.isfile(vocals_path):
        print(f"  已存在，跳过: {vocals_path}")
    else:
        run_cmd(
            ["uv", "run", "vocal_extract.py", audio_path],
            "Demucs")

    if not os.path.isfile(vocals_path):
        print(f"  失败：{vocals_path} 未生成", file=sys.stderr)
        sys.exit(1)

    # --- Step 2: Basic Pitch 转 MIDI ---
    midi_path = os.path.join(out_dir, f"{base}_vocals_basic_pitch.mid")
    step("2/2  Basic Pitch → MIDI")
    bp_cmd = ["uv", "run", "pitch_basic.py", "--save-midi", vocals_path]
    if vocal: bp_cmd.insert(-1, "--vocal")
    if sensitive: bp_cmd.insert(-1, "--sensitive")
    if onset is not None: bp_cmd += ["--onset", str(onset)]
    if frame is not None: bp_cmd += ["--frame", str(frame)]
    if min_note_len is not None: bp_cmd += ["--min-note-length", str(min_note_len)]
    run_cmd(bp_cmd, "Basic Pitch")

    if not os.path.isfile(midi_path):
        print(f"  警告：{midi_path} 未生成", file=sys.stderr)

    # --- 输出 ---
    print(f"\n{'='*50}")
    print(f"  输出文件:")
    print(f"    原始录音:  {audio_path}")
    print(f"    人声文件:  {vocals_path}")
    print(f"    MIDI:      {midi_path}")
    print(f"{'='*50}")
    print(f"  在 MuseScore 中打开:")
    print(f"    mscore \"{midi_path}\"")


if __name__ == "__main__":
    main()