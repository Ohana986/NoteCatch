#!/usr/bin/env bash
# audio-analyzer 一键安装脚本
# 用法: bash setup.sh
set -eu

echo "========================================"
echo "  audio-analyzer 环境安装"
echo "========================================"

# ── 检查 Python ──
if ! command -v python3 &>/dev/null; then
    echo "❌ 未找到 python3，请先安装 Python 3.10+"
    exit 1
fi

PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✅ Python $PYVER"

# ── 系统依赖提示 ──
echo ""
echo "── 系统依赖（如未安装请手动执行）──"
echo "  Fedora:   sudo dnf install python3-gobject gtk4 libadwaita gstreamer1-plugins-good pulseaudio-utils ffmpeg"
echo "  Debian:   sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gstreamer1.0-plugins-good pulseaudio-utils ffmpeg"
echo ""

# ── 创建 venv ──
VENV_DIR="$(dirname "$0")/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "── 创建虚拟环境 ──"
    python3 -m venv "$VENV_DIR"
fi

# ── 安装 Python 依赖 ──
echo "── 安装 Python 依赖 ──"
"$VENV_DIR/bin/pip" install -r "$(dirname "$0")/requirements.txt"

# ── 安装 CLI 工具 ──
echo "── 安装 CLI 工具 ──"
if command -v pipx &>/dev/null; then
    pipx install demucs 2>/dev/null || echo "  demucs 已安装或跳过"
    pipx install basic-pitch 2>/dev/null || echo "  basic-pitch 已安装或跳过"
else
    echo "  ⚠ pipx 未安装，跳过 CLI 工具"
    echo "  安装 pipx: python3 -m pip install --user pipx && python3 -m pipx ensurepath"
    echo "  然后运行: pipx install demucs && pipx install basic-pitch"
fi

# ── 完成 ──
echo ""
echo "========================================"
echo "  安装完成！"
echo ""
echo "  使用方式："
echo "    source .venv/bin/activate"
echo "    cd tools"
echo "    python gui.py"
echo ""
echo "  或直接运行："
echo "    .venv/bin/python tools/gui.py"
echo "========================================"