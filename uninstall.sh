#!/usr/bin/env bash
# audio-analyzer 卸载脚本
# 用法: bash uninstall.sh
set -eu

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(dirname "$(realpath "$0")")"

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  audio-analyzer 卸载${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# ── 检测系统 ──
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS="$ID"
else
    OS="unknown"
fi

# ════════════════════════════════════════════
# 收集将要移除的内容
# ════════════════════════════════════════════

ITEMS=()

# 1) 虚拟环境
VENV_DIR="$SCRIPT_DIR/.venv"
if [ -d "$VENV_DIR" ]; then
    ITEMS+=("Python 虚拟环境: $VENV_DIR")
else
    echo -e "  ${YELLOW}⏭ 未找到虚拟环境，跳过${NC}"
fi

# 2) pipx CLI 工具
PIPX_TOOLS=("demucs" "basic-pitch")
INSTALLED_PIPX=()
for tool in "${PIPX_TOOLS[@]}"; do
    if pipx list 2>/dev/null | grep -q "package $tool "; then
        INSTALLED_PIPX+=("$tool")
    fi
done
if [ ${#INSTALLED_PIPX[@]} -gt 0 ]; then
    ITEMS+=("pipx CLI 工具: ${INSTALLED_PIPX[*]}")
else
    echo -e "  ${YELLOW}⏭ 未找到 pipx 工具，跳过${NC}"
fi

# 3) 系统依赖（仅列出，不自动卸载）
case "$OS" in
    fedora|rhel|centos)
        SYS_PKGS="python3-gobject gtk4 libadwaita gstreamer1-plugins-good gstreamer1-plugins-base pulseaudio-utils ffmpeg pipx"
        SYS_PKG_MGR="dnf"
        ;;
    debian|ubuntu)
        SYS_PKGS="python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gstreamer1.0-plugins-good gstreamer1.0-plugins-base pulseaudio-utils ffmpeg pipx"
        SYS_PKG_MGR="apt"
        ;;
    *)
        SYS_PKGS=""
        SYS_PKG_MGR=""
        ;;
esac

if [ ${#ITEMS[@]} -eq 0 ]; then
    echo -e "  ${GREEN}没有需要卸载的内容。${NC}"
    exit 0
fi

# ════════════════════════════════════════════
# 展示
# ════════════════════════════════════════════

echo -e "${YELLOW}── 将要移除的内容 ──${NC}"
echo ""
for i in "${!ITEMS[@]}"; do
    num=$((i + 1))
    echo -e "  ${RED}$num.${NC} ${ITEMS[$i]}"
done
echo ""

# ── 确认 ──
read -r -p "$(echo -e "${RED}确认卸载？${NC} [y/N] ")" CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "已取消。"
    exit 0
fi

echo ""

# ════════════════════════════════════════════
# 执行
# ════════════════════════════════════════════

# ── 1) 虚拟环境 ──
if [ -d "$VENV_DIR" ]; then
    echo -e "${CYAN}── 移除虚拟环境 ──${NC}"
    rm -rf "$VENV_DIR"
    echo -e "  ${GREEN}✅ 已移除${NC}"
    echo ""
fi

# ── 2) pipx 工具 ──
if [ ${#INSTALLED_PIPX[@]} -gt 0 ]; then
    echo -e "${CYAN}── 卸载 pipx 工具 ──${NC}"
    for tool in "${INSTALLED_PIPX[@]}"; do
        pipx uninstall "$tool"
        echo -e "  ${GREEN}✅ $tool 已卸载${NC}"
    done
    echo ""
fi

# ── 完成 ──
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  卸载完成${NC}"

# 3) 提示系统依赖
if [ -n "$SYS_PKGS" ]; then
    echo ""
    echo -e "  ${YELLOW}⚠ 系统包未自动移除（可能被其他程序使用）：${NC}"
    echo "      $SYS_PKGS"
    echo ""
    echo -e "  如需移除，请手动执行："
    case "$SYS_PKG_MGR" in
        dnf)
            echo -e "      ${YELLOW}sudo dnf remove $SYS_PKGS${NC}"
            ;;
        apt)
            echo -e "      ${YELLOW}sudo apt remove $SYS_PKGS${NC}"
            ;;
    esac
fi

echo ""
echo -e "  ${YELLOW}💡 recordings/ 目录（录音数据）未被删除，如需清理请手动操作。${NC}"
echo -e "${CYAN}========================================${NC}"
