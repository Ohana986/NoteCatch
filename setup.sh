#!/usr/bin/env bash
# audio-analyzer 一键安装脚本
# 用法: bash setup.sh
set -eu

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  audio-analyzer 环境安装${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# ── 检测系统 ──
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS="$ID"
else
    OS="unknown"
fi

# ── 列出将要执行的操作 ──
echo -e "${YELLOW}── 将要执行的操作 ──${NC}"
echo ""
echo -e "  ${GREEN}1.${NC} 创建 Python 虚拟环境：  $(pwd)/.venv"
echo -e "  ${GREEN}2.${NC} 安装 Python 依赖："
while IFS= read -r line; do
    [ -n "$line" ] && echo "      • $line"
done < "$(dirname "$0")/requirements.txt"
echo ""

case "$OS" in
    fedora|rhel|centos)
        echo -e "  ${GREEN}3.${NC} 系统依赖（需手动执行）："
        echo "      sudo dnf install python3-gobject gtk4 libadwaita \\"
        echo "          gstreamer1-plugins-good gstreamer1-plugins-base \\"
        echo "          pulseaudio-utils ffmpeg pipx"
        ;;
    debian|ubuntu)
        echo -e "  ${GREEN}3.${NC} 系统依赖（需手动执行）："
        echo "      sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 \\"
        echo "          gstreamer1.0-plugins-good gstreamer1.0-plugins-base \\"
        echo "          pulseaudio-utils ffmpeg pipx"
        ;;
    *)
        echo -e "  ${GREEN}3.${NC} 系统依赖（请手动安装）："
        echo "      python3-gobject, gtk4, libadwaita, gstreamer1-plugins-good,"
        echo "      pulseaudio-utils, ffmpeg, pipx"
        ;;
esac
echo ""

echo -e "  ${GREEN}4.${NC} CLI 工具（需手动执行）："
echo "      pipx install demucs"
echo "      pipx install basic-pitch"
echo ""

echo -e "${YELLOW}────────────────────────────────────────${NC}"
echo -e "  脚本将自动执行 ${GREEN}步骤 1-2${NC}（创建 venv + pip 安装）。"
echo -e "  ${GREEN}步骤 3-4${NC} 需要 sudo/pipx，请手动执行。"
echo ""

# ── 确认 ──
read -r -p "$(echo -e "${YELLOW}是否继续？${NC} [y/N] ")" CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "已取消。"
    exit 0
fi

echo ""

# ── 检查 Python ──
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}❌ 未找到 python3，请先安装 Python 3.10+${NC}"
    exit 1
fi
PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "${GREEN}✅ Python $PYVER${NC}"

# ── 创建 venv ──
VENV_DIR="$(dirname "$0")/.venv"
if [ -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}⚠ 虚拟环境已存在，跳过创建${NC}"
else
    echo "── 创建虚拟环境 ──"
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}✅ 虚拟环境已创建${NC}"
fi

# ── 安装 Python 依赖 ──
echo "── 安装 Python 依赖 ──"
"$VENV_DIR/bin/pip" install -r "$(dirname "$0")/requirements.txt"
echo -e "${GREEN}✅ Python 依赖安装完成${NC}"

# ── 完成 ──
echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  安装完成！${NC}"
echo ""
echo -e "  使用方式："
echo -e "    ${GREEN}source .venv/bin/activate${NC}"
echo -e "    cd tools"
echo -e "    python gui.py"
echo ""
echo -e "  或直接运行："
echo -e "    ${GREEN}.venv/bin/python tools/gui.py${NC}"
echo ""
echo -e "  ${YELLOW}⚠ 请确保已安装系统依赖和 CLI 工具（步骤 3-4）${NC}"
echo -e "${CYAN}========================================${NC}"