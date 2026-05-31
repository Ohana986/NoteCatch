# /// script
# dependencies = [
#   "music21>=8.0",
# ]
# ///

"""将 MIDI 文件转为五线谱 (MusicXML)。

用法:
    uv run midi_to_sheet.py <文件.mid>                    # 转 MusicXML
    uv run midi_to_sheet.py <文件.mid> --png              # 尝试渲染 PNG
    uv run midi_to_sheet.py <文件.mid> --key C            # 指定调号 (默认自动)
    uv run midi_to_sheet.py <文件.mid> --time 4/4         # 指定拍号
"""

import sys
import os

import music21


def midi_to_sheet(midi_path: str, key_sig=None, time_sig="4/4",
                  render_png=False):
    midi_path = os.path.abspath(midi_path)
    basename = os.path.splitext(os.path.basename(midi_path))[0]
    out_dir = os.path.dirname(midi_path)

    print(f"读取: {midi_path}")
    score = music21.converter.parse(midi_path)

    # 尝试检测调号
    if key_sig:
        k = music21.key.Key(key_sig)
        for ks in score.flatten().getElementsByClass(music21.key.KeySignature):
            ks.replace(k)
        score.insert(0, k)
        print(f"调号: {key_sig}")

    # 设置拍号（如果未自动识别）
    ts = music21.meter.TimeSignature(time_sig)
    for ts_el in score.flatten().getElementsByClass(music21.meter.TimeSignature):
        ts_el.replace(ts)
        break
    else:
        score.insert(0, ts)
    print(f"拍号: {time_sig}")

    # 转调为 C（方便读谱）
    # score = score.transpose("C")

    # 输出 MusicXML
    xml_path = os.path.join(out_dir, f"{basename}.musicxml")
    score.write("musicxml", fp=xml_path)
    size_kb = os.path.getsize(xml_path) / 1024
    print(f"MusicXML: {xml_path} ({size_kb:.0f} KB)")

    # 可选：渲染 PNG（需要 MuseScore 或 LilyPond）
    if render_png:
        png_path = os.path.join(out_dir, f"{basename}_sheet.png")
        try:
            score.write("lily.png", fp=png_path)
            print(f"PNG: {png_path}")
        except Exception as e:
            print(f"PNG 渲染失败（需要安装 LilyPond）：{e}")

    return xml_path


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(1)

    midi_path = None
    key_sig = None
    time_sig = "4/4"
    render_png = "--png" in args

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--key" and i + 1 < len(args):
            key_sig = args[i + 1]
            i += 2
        elif a == "--time" and i + 1 < len(args):
            time_sig = args[i + 1]
            i += 2
        elif a == "--png":
            i += 1
        elif a.startswith("--"):
            print(f"未知参数: {a}", file=sys.stderr)
            sys.exit(1)
        else:
            midi_path = a
            i += 1

    if not midi_path:
        print("错误：缺少 MIDI 文件", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(midi_path):
        print(f"文件不存在: {midi_path}", file=sys.stderr)
        sys.exit(1)

    midi_to_sheet(midi_path, key_sig=key_sig, time_sig=time_sig,
                  render_png=render_png)


if __name__ == "__main__":
    main()