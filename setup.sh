#!/usr/bin/env bash
# audio-analyzer 一键安装脚本
# 用法: bash setup.sh
set -eu

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(dirname "$(realpath "$0")")"

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

# ── 检查 Python ──
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}❌ 未找到 python3，请先安装 Python 3.10+${NC}"
    exit 1
fi
PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "${GREEN}✅ Python $PYVER${NC}"
echo ""

# ════════════════════════════════════════════
# 收集所有操作
# ════════════════════════════════════════════

# ── 1) 系统依赖 ──
case "$OS" in
    fedora|rhel|centos)
        SYS_PKGS=("python3-gobject" "gtk4" "libadwaita" "gstreamer1-plugins-good" "gstreamer1-plugins-base" "pulseaudio-utils" "ffmpeg" "pipx")
        SYS_CMD="sudo dnf install -y ${SYS_PKGS[*]}"
        SYS_LABEL="系统依赖 (dnf)"
        ;;
    debian|ubuntu)
        SYS_PKGS=("python3-gi" "gir1.2-gtk-4.0" "gir1.2-adw-1" "gstreamer1.0-plugins-good" "gstreamer1.0-plugins-base" "pulseaudio-utils" "ffmpeg" "pipx")
        SYS_CMD="sudo apt update && sudo apt install -y ${SYS_PKGS[*]}"
        SYS_LABEL="系统依赖 (apt)"
        ;;
    *)
        SYS_PKGS=()
        SYS_CMD=""
        SYS_LABEL="系统依赖（未知系统，请手动安装以下包）"
        SYS_MANUAL="python3-gobject, gtk4, libadwaita, gstreamer1-plugins-good, pulseaudio-utils, ffmpeg, pipx"
        ;;
esac

# ── 2) Python 虚拟环境 ──
VENV_DIR="$SCRIPT_DIR/.venv"
VENV_EXISTS=false
[ -d "$VENV_DIR" ] && VENV_EXISTS=true

# ── 3) pip 依赖 ──
PIP_PKGS=()
while IFS= read -r line; do
    line="${line%%#*}"        # 去掉行内注释
    line="$(echo "$line" | xargs)"  # trim
    [ -n "$line" ] && PIP_PKGS+=("$line")
done < "$SCRIPT_DIR/requirements.txt"

# ── 4) pipx CLI 工具 ──
PIPX_TOOLS=("demucs" "basic-pitch")

# ════════════════════════════════════════════
# 展示所有操作
# ════════════════════════════════════════════

echo -e "${YELLOW}── 将要执行的操作 ──${NC}"
echo ""

# 1
echo -e "  ${GREEN}1.${NC} $SYS_LABEL"
if [ ${#SYS_PKGS[@]} -gt 0 ]; then
    for pkg in "${SYS_PKGS[@]}"; do
        echo "      • $pkg"
    done
else
    echo "      $SYS_MANUAL"
fi
echo ""

# 2
echo -n "  ${GREEN}2.${NC} Python 虚拟环境: "
if $VENV_EXISTS; then
    echo -e "$VENV_DIR ${YELLOW}(已存在，将跳过创建)${NC}"
else
    echo "创建 $VENV_DIR"
fi
echo ""

# 3
echo -e "  ${GREEN}3.${NC} pip 依赖:"
for pkg in "${PIP_PKGS[@]}"; do
    echo "      • $pkg"
done
echo ""

# 4
echo -e "  ${GREEN}4.${NC} pipx CLI 工具:"
for tool in "${PIPX_TOOLS[@]}"; do
    echo "      • $tool"
done
echo ""

# ── 确认 ──
read -r -p "$(echo -e "${YELLOW}是否继续？${NC} [y/N] ")" CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "已取消。"
    exit 0
fi

echo ""

# ════════════════════════════════════════════
# 执行
# ════════════════════════════════════════════

TOTAL=4

# ── 1) 系统依赖 ──
echo -e "${CYAN}── [1/$TOTAL] $SYS_LABEL ──${NC}"
if [ -n "$SYS_CMD" ]; then
    eval "$SYS_CMD"
    echo -e "  ${GREEN}✅ 完成${NC}"
else
    echo -e "  ${YELLOW}⚠ 请手动安装：$SYS_MANUAL${NC}"
fi
echo ""

# ── 2) 虚拟环境 ──
echo -e "${CYAN}── [2/$TOTAL] Python 虚拟环境 ──${NC}"
if $VENV_EXISTS; then
    echo "  ⏭ 已存在，跳过创建"
else
    python3 -m venv "$VENV_DIR"
    echo -e "  ${GREEN}✅ 已创建${NC}"
fi
echo ""

# ── 3) pip 依赖 ──
echo -e "${CYAN}── [3/$TOTAL] pip 依赖 ──${NC}"
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
echo -e "  ${GREEN}✅ 完成${NC}"
echo ""

# ── 4) pipx CLI 工具 ──
echo -e "${CYAN}── [4/$TOTAL] pipx CLI 工具 ──${NC}"
for tool in "${PIPX_TOOLS[@]}"; do
    if pipx list 2>/dev/null | grep -q "package $tool "; then
        echo "  ⏭ $tool 已安装，跳过"
    else
        pipx install "$tool"
        echo -e "  ${GREEN}✅ $tool 安装完成${NC}"
    fi
done
echo ""

# ── 完成 ──
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
echo -e "${CYAN}========================================${NC}"
