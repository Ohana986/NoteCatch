# 🎵 NoteCatch — 听见旋律，抓住音符

- 注意：得益于Demucs，人声的分离效果比较好，但是人声-midi的转化还很一般
- Note: Thanks to Demucs, the vocal separation works fairly well, but the conversion from vocals to MIDI is still mediocre at best.
- 目前的思路是尝试使用传统的频谱分析，类似cava，加上一些算法实现，但是可能要鸽一段时间
- My current plan is to try using traditional spectrum analysis, similar to what Cava does, combined with some custom algorithmic implementations. However, this might be put on hold for a while.

> 播放任意音频 → 自动分离人声 → 识别音高 → 输出 MIDI / 五线谱 / 纯音合成

**NoteCatch** 是一款桌面端音乐学习辅助工具。你在电脑上播放歌曲、教学录音或视唱素材，它就能实时捕获系统音频、分离人声、分析旋律走向，最终生成 MIDI 文件和五线谱——无需任何外部设备，一个 GNOME 窗口即可完成。

### 典型场景

- 🎤 **扒谱辅助** — 听到喜欢的旋律，录制下来直接出 MIDI，导入 MuseScore 查看五线谱
- 🎼 **视唱参考** — 老师弹一段，立刻看到音高曲线和标准乐谱
- 🎹 **练耳对比** — 自己哼唱一段，对比原曲音高差异
- 🎧 **浏览器音乐** — 播放任何网页/App 中的音频都能捕获分析

### 技术链路

```
系统音频录制 → Demucs 人声分离 → Basic Pitch / pYIN 音高分析
                                        ↓
                              MIDI / 五线谱 / 纯音合成回放
```

基于 [Demucs](https://github.com/facebookresearch/demucs)（Meta 人声分离）和 [Basic Pitch](https://github.com/spotify/basic-pitch)（Spotify 音高检测）两个成熟开源项目，通过 GTK4 + Adwaita 提供直观的 GNOME 桌面界面。

> ⚠️ **开发中**：音高→MIDI 的精度仍在优化，使用中可能遇到 bug，欢迎反馈。

## 环境准备（首次使用）

### 方式一：一键安装（推荐）

```bash
git clone https://github.com/Ohana986/audio-analyzer.git
cd audio-analyzer
bash setup.sh
```

`setup.sh` 会自动检测系统，列出四项操作：系统依赖 → Python 虚拟环境 → pip 依赖 → CLI 工具（demucs、basic-pitch）。确认后一键执行，无需手动操作。

如需卸载：`bash uninstall.sh`。

安装后使用：

```bash
source .venv/bin/activate
cd tools
python gui.py          # 启动 GUI
python pipeline.py ../recordings/录音.wav   # 命令行管线
```

### 方式二：使用 uv（可选）

```bash
git clone https://github.com/Ohana986/audio-analyzer.git
cd audio-analyzer

# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装 CLI 工具
uv tool install demucs
uv tool install --python 3.11 basic-pitch

# 使用（uv 自动处理 PEP 723 依赖）
cd tools
uv run gui.py
```

## 项目结构

```
audio-analyzer/
├── setup.sh                       # 一键安装
├── uninstall.sh                   # 一键卸载
├── tools/                         # 所有脚本
│   ├── record-system-audio.sh     # 系统音频录制（PipeWire/PulseAudio）
│   ├── vocal_extract.py           # Demucs 人声分离
│   ├── pitch_basic.py             # Basic Pitch 音高检测 → MIDI
│   ├── pitch_analyzer.py          # pYIN 逐帧音高分析 → CSV + PNG 可视化
│   ├── pitch_play.py              # 纯音合成与播放
│   ├── pipeline.py                # 统一管线入口
│   ├── midi_to_sheet.py           # MIDI → MusicXML 五线谱
│   ├── gui.py                     # GNOME GUI (GTK4 + Adwaita + GStreamer)
│   └── common.py                  # 共享工具模块
└── recordings/                    # 录音与产物输出
    ├── 系统录音_20260531_191222/   # 每条录音一个独立文件夹
    │   ├── 系统录音_20260531_191222.wav
    │   ├── 系统录音_20260531_191222_vocals.wav
    │   ├── 系统录音_20260531_191222_vocals_basic_pitch.mid
    │   └── ...
    └── 系统录音_20260531_190539/
        └── ...
```

## 快速开始

### 1. 录制系统音频

```bash
cd tools
./record-system-audio.sh          # 手动 Ctrl+C 停止
./record-system-audio.sh 30       # 录制 30 秒
```

文件保存至 `recordings/系统录音_YYYYMMDD_HHMMSS.wav`。

### 2. 完整管线

```bash
cd tools

# 完整流程: 人声分离 → 音高检测 → 纯音合成 → 混合播放
uv run pipeline.py ../recordings/录音.wav

# 只到 MIDI
uv run pipeline.py ../recordings/录音.wav --midi-only

# 预设参数 (66=默认, 75=更敏感)
uv run pipeline.py ../recordings/录音.wav --midi-only --preset 75

# 含 pYIN 逐帧分析（额外输出 CSV + 可视化 PNG）
uv run pipeline.py ../recordings/录音.wav --analyze

# 自动找最新录音
uv run pipeline.py
```

### 3. 单独使用各工具

```bash
# 仅人声分离
uv run vocal_extract.py 录音.wav

# 仅 Basic Pitch 音高检测
uv run pitch_basic.py --vocal --save-midi 人声.wav

# pYIN 逐帧分析 + 可视化
uv run pitch_analyzer.py --vocal 录音.wav

# 纯音合成
uv run pitch_play.py 音段.csv

# MIDI → 五线谱
uv run midi_to_sheet.py 文件.mid --png
```

### 4. GUI

```bash
cd tools && python3 gui.py
```

功能：录制 / 播放（含拖动进度+暂停） / 处理（Demucs → Basic Pitch → MIDI） / 文件管理（隐藏/删除）。

## 输出文件命名约定

输出按录音条目划分文件夹，每个录音的产物存放在以录音名命名的子目录中：

| 后缀 | 内容 | 生成工具 |
|------|------|----------|
| `.wav` (无后缀) | 原始录音 | `record-system-audio.sh` |
| `_vocals.wav` | 分离后的人声 | `vocal_extract.py` |
| `_vocals_play.wav` | 纯音合成 | `pitch_play.py` |
| `_vocals_mixed.wav` | 原声+纯音混合 | `pipeline.py` |
| `_vocals_basic_pitch.mid` | 人声 MIDI | `pitch_basic.py` |
| `_basic_pitch.mid` | 全频段 MIDI | `pitch_basic.py` |
| `_vocals_segments.csv` | 人声音段 (Basic Pitch) | `pitch_basic.py` |
| `_vocals_pitch.csv` | 人声逐帧音高 (pYIN) | `pitch_analyzer.py` |
| `_pitch.csv` | 全频段逐帧音高 (pYIN) | `pitch_analyzer.py` |
| `_segments.csv` | 全频段音段 (pYIN) | `pitch_analyzer.py` |
| `_vocals_pitch.png` | 人声音高可视化 | `pitch_analyzer.py` |
| `_pitch.png` | 全频段音高可视化 | `pitch_analyzer.py` |
| `.musicxml` | 五线谱 | `midi_to_sheet.py` |

## 管线架构

```
record-system-audio.sh ──→ 系统录音_xxx.wav
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
         gui.py            pipeline.py        独立 CLI 工具
    (GTK4 + GStreamer)   (统一管线入口)    vocal_extract.py
              │                  │           pitch_basic.py
              │    ┌─────────────┤           pitch_analyzer.py
              │    │             │           pitch_play.py
              ▼    ▼             ▼           midi_to_sheet.py
         vocal_extract.py   pitch_basic.py
              │                  │
              ▼                  ▼
         *_vocals.wav      *_segments.csv
              │            *_basic_pitch.mid
              ▼                  │
         pitch_basic.py          ▼
              │            pitch_play.py
              ▼                  │
         *_vocals_basic_pitch.mid ▼
                            *_vocals_play.wav
                                   │
                                   ▼
                            ffmpeg + paplay
                            *_vocals_mixed.wav
```
