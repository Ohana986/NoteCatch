# /// script
# dependencies = []
# ///

"""人声提取工具：使用 Demucs (Hybrid Transformer) 分离人声轨道。

用法:
    uv run vocal_extract.py <音频文件>                       # 提取人声，保存为 <原名>_vocals.wav
    uv run vocal_extract.py <音频文件> --out 输出路径.wav    # 指定输出路径
    uv run vocal_extract.py <音频文件> --mp3                  # 输出 MP3 格式

依赖: 需要全局安装 demucs (uv tool install demucs)
"""

import sys
import os
import subprocess
import shutil
import tempfile


def extract_vocals(audio_path: str, out_path: str = None, out_format: str = "wav"):
    """使用 demucs 提取人声轨道。"""
    audio_path = os.path.abspath(audio_path)
    if not os.path.isfile(audio_path):
        print(f"错误：文件不存在 {audio_path}", file=sys.stderr)
        sys.exit(1)

    basename = os.path.splitext(os.path.basename(audio_path))[0]
    out_dir = os.path.dirname(audio_path)

    if out_path is None:
        out_path = os.path.join(out_dir, f"{basename}_vocals.{out_format}")

    print(f"输入: {audio_path}")
    print(f"模型: htdemucs (Hybrid Transformer Demucs)")
    print("正在分离人声...")

    # 使用临时目录作为 demucs 的输出，避免污染当前目录
    with tempfile.TemporaryDirectory(prefix="vocal_extract_") as tmpdir:
        cmd = [
            "demucs",
            "--two-stems", "vocals",   # 只分离 vocals + 其他（比全分离快）
            "-o", tmpdir,              # 输出到临时目录
            audio_path,
        ]
        if out_format == "mp3":
            cmd.append("--mp3")

        print(f"运行: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"Demucs 分离失败：{result.stderr}", file=sys.stderr)
            sys.exit(1)

        # demucs 输出路径: <tmpdir>/htdemucs/<basename>/vocals.wav
        model = "htdemucs"
        src_vocals = os.path.join(tmpdir, model, basename, f"vocals.{out_format}")
        if not os.path.isfile(src_vocals):
            print(f"错误：未找到分离后的人声文件 {src_vocals}", file=sys.stderr)
            print(f"demucs 输出：\n{result.stdout}\n{result.stderr}")
            sys.exit(1)

        shutil.copy2(src_vocals, out_path)

    # 获取文件大小
    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"人声已保存: {out_path} ({size_mb:.1f} MB)")
    return out_path


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(1)

    out_format = "wav"
    out_path = None
    positional = []

    for a in args:
        if a == "--mp3":
            out_format = "mp3"
        elif a.startswith("--out="):
            out_path = a[6:]
        elif a == "--out" and len(positional) == 1:
            # 处理 --out <path> 将在下面通过索引处理
            pass
        else:
            positional.append(a)

    if not positional:
        print("错误：缺少音频文件", file=sys.stderr)
        print(__doc__)
        sys.exit(1)

    audio_path = positional[0]

    # 检查 --out <path> 格式
    if "--out" in args:
        idx = args.index("--out")
        if idx + 1 < len(args):
            out_path = args[idx + 1]

    extract_vocals(audio_path, out_path, out_format)


if __name__ == "__main__":
    main()